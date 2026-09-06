from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest
import uuid

from cope.lineage_benchmark.client import OpenAICompatibleClient, OracleModelClient
from cope.lineage_benchmark.models import ModelPacket, ScenarioSpec, canonical_json
from cope.lineage_benchmark.operations import EVENT_TO_OPERATION, OPERATIONS, validate_operation
from cope.lineage_benchmark.prompts import development_examples, system_prompt
from cope.lineage_benchmark.reference import reference_transition
from cope.lineage_benchmark.schemas import output_schema, validate_output_document
from cope.lineage_benchmark.task import build_scenario


def packet(timeout=1.0):
    scenario = build_scenario(ScenarioSpec(901, "development", 6, 2, 4096, timeout))
    return ModelPacket(
        task_contract=scenario.task_contract, current_state=scenario.initial_state,
        event=scenario.events[0], event_history=(), completed_actions=(),
        world_state={}, compute_budget={"max_output_tokens": 4096, "timeout_s": timeout},
    )


def frame(content="", *, tokens=None, finish=None, choices=True):
    result = {
        "id": "chatcmpl-server-test",
        "choices": ([{"index": 0, "delta": {"content": content}, "finish_reason": finish}]
                    if choices else []),
    }
    if tokens is not None:
        result["usage"] = {"prompt_tokens": 99, "completion_tokens": tokens}
    return "data: " + json.dumps(result) + "\n\n"


@contextmanager
def fake_server(frames=(), status=200, http_body=b"bad request"):
    observed = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            observed.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(status)
            self.send_header("Content-Type", "text/event-stream" if status == 200 else "text/plain")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                if status != 200:
                    self.wfile.write(http_body)
                else:
                    for delay, data in frames:
                        if delay:
                            time.sleep(delay)
                        self.wfile.write(data.encode("utf-8"))
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", observed
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def call(base_url, timeout=1.0):
    return OpenAICompatibleClient(base_url=base_url, model="fixed-model").generate(
        method="CoPE", packet=packet(timeout), max_output_tokens=4096, timeout_s=timeout,
    )


class InterfaceSchemaTests(unittest.TestCase):
    def test_four_operation_examples_use_shared_canonical_names(self):
        seen = set()
        for example in development_examples():
            output = example["output"]
            event = example["input_excerpt"]["event"]
            validate_output_document("CoPE", output)
            validate_operation(output["ops"][0])
            self.assertEqual(output["ops"][0]["op"], EVENT_TO_OPERATION[event["kind"]])
            seen.add(output["ops"][0]["op"])
            self.assertIn(canonical_json(example), system_prompt("CoPE"))
        self.assertEqual(seen, set(OPERATIONS))

    def test_override_current_is_not_silently_aliased(self):
        output = deepcopy(development_examples()[2]["output"])
        output["ops"][0]["op"] = "override_current"
        with self.assertRaises(ValueError):
            validate_output_document("CoPE", output)
        with self.assertRaises(ValueError):
            validate_operation(output["ops"][0])

    def test_every_operation_branch_requires_its_arguments(self):
        for definition in OPERATIONS.values():
            with self.assertRaises(ValueError):
                validate_operation({"op": definition.name})
        with self.assertRaises(ValueError):
            validate_operation({"op": "restore", "slot_id": True})

    def test_schema_is_static_and_does_not_select_answer(self):
        schema = output_schema("CoPE")
        branches = schema["properties"]["ops"]["items"]["anyOf"]
        self.assertEqual({b["properties"]["op"]["enum"][0] for b in branches}, set(OPERATIONS))
        self.assertNotIn("seed-", canonical_json(schema))
        self.assertNotIn("order-critical", canonical_json(schema))
        output_schema("CoPE")["properties"].clear()
        self.assertTrue(output_schema("CoPE")["properties"])

    def test_both_schemas_accept_seven_complete_reference_steps(self):
        scenario = build_scenario(ScenarioSpec(901, "development", 6, 2, 4096, 1.0))
        state = scenario.initial_state
        for event in scenario.events:
            current = ModelPacket(scenario.task_contract, state, event, (), (), {},
                                  {"max_output_tokens": 4096, "timeout_s": 1.0})
            for method in ("CoPE", "FSR-PC"):
                result = OracleModelClient().generate(
                    method=method, packet=current, max_output_tokens=4096, timeout_s=1.0,
                )
                validate_output_document(method, result.parsed)
            state = reference_transition(state, event, scenario.critical_logical_id)
        self.assertEqual(state.revision, 7)

    def test_fsr_schema_checks_required_nested_structure(self):
        state = packet().current_state.to_dict()
        validate_output_document("FSR-PC", state)
        state["slots"][0]["lineage"].pop("parent_id")
        with self.assertRaises(ValueError):
            validate_output_document("FSR-PC", state)

    def test_vllm_projection_retains_local_cardinality_check(self):
        schema = canonical_json(output_schema("CoPE"))
        for keyword in ("minLength", "maxLength", "minItems", "maxItems"):
            self.assertNotIn(keyword, schema)
        invalid = deepcopy(development_examples()[0]["output"])
        invalid["ops"] = []
        with self.assertRaises(ValueError):
            validate_output_document("CoPE", invalid)


class StreamingClientTests(unittest.TestCase):
    def test_success_records_actual_stream_usage_and_one_request(self):
        text = canonical_json(development_examples()[0]["output"])
        frames = [(0, frame(text[:20], tokens=7)),
                  (0, frame(text[20:], tokens=20, finish="stop")),
                  (0, frame(tokens=21, choices=False)), (0, "data: [DONE]\n\n")]
        with fake_server(frames) as (url, observed):
            result = call(url)
        self.assertTrue(result.ok, result.to_dict())
        self.assertTrue(result.request_completed)
        self.assertEqual(result.text, text)
        self.assertEqual(result.completion_tokens, 21)
        self.assertEqual(result.observed_completion_tokens, 21)
        self.assertEqual(result.observed_token_count_kind, "server_usage_cumulative")
        self.assertEqual(result.streamed_chunks, 3)
        self.assertIsNotNone(result.ttft_s)
        self.assertEqual(str(uuid.UUID(result.request_id)), result.request_id)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["request_id"], result.request_id)
        self.assertEqual(observed[0]["guided_json"], output_schema("CoPE"))
        self.assertEqual(observed[0]["guided_decoding_backend"],
                         "xgrammar")
        self.assertTrue(observed[0]["stream_options"]["continuous_usage_stats"])
        self.assertEqual(observed[0]["max_tokens"], 4096)

    def test_deadline_keeps_partial_text_and_tokens_without_claiming_cancellation(self):
        frames = [(0, frame('{"schema_', tokens=3)), (0.3, frame("late", tokens=4))]
        with fake_server(frames) as (url, observed):
            result = call(url, timeout=0.08)
        self.assertEqual(result.status, "client_timeout")
        self.assertEqual(result.text, '{"schema_')
        self.assertEqual(result.observed_completion_tokens, 3)
        self.assertEqual(result.cancellation_status, "connection_closed_server_status_unknown")
        self.assertIsNone(result.telemetry["server_cancellation_confirmed"])
        self.assertFalse(result.request_completed)
        self.assertLess(result.latency_s, 0.25)
        self.assertEqual(len(observed), 1)

    def test_deadline_is_total_not_reset_by_each_stream_chunk(self):
        frames = [(0.03, frame("x", tokens=index)) for index in range(10)]
        with fake_server(frames) as (url, observed):
            result = call(url, timeout=0.09)
        self.assertEqual(result.status, "client_timeout")
        self.assertGreater(len(result.text), 0)
        self.assertLess(result.latency_s, 0.25)
        self.assertEqual(len(observed), 1)

    def test_missing_usage_does_not_estimate_tokens_from_chunks(self):
        text = canonical_json(development_examples()[0]["output"])
        with fake_server([(0, frame(text, finish="stop")), (0, "data: [DONE]\n\n")]) as (url, _):
            result = call(url)
        self.assertTrue(result.ok)
        self.assertIsNone(result.observed_completion_tokens)
        self.assertEqual(result.observed_token_count_kind, "unavailable")

    def test_explicit_guidance_backend_is_used_and_logged(self):
        text = canonical_json(development_examples()[0]["output"])
        with fake_server([(0, frame(text, finish="stop")),
                          (0, "data: [DONE]\n\n")]) as (url, observed):
            result = OpenAICompatibleClient(
                base_url=url, model="fixed-model", guided_decoding_backend="guidance",
            ).generate(method="CoPE", packet=packet(), max_output_tokens=4096, timeout_s=1.0)
        self.assertTrue(result.ok, result.to_dict())
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["guided_decoding_backend"], "guidance")
        self.assertEqual(result.telemetry["guided_decoding_backend"], "guidance")
        self.assertEqual(observed[0]["guided_json"], output_schema("CoPE"))

    def test_unsupported_backend_is_rejected_before_any_request(self):
        for backend in ("auto", "outlines", "xgrammar:disable-any-whitespace", "invalid"):
            with self.subTest(backend=backend), self.assertRaises(ValueError):
                OpenAICompatibleClient(base_url="http://127.0.0.1:1", model="fixed-model",
                                       guided_decoding_backend=backend)

    def test_http_error_is_distinct_and_is_not_retried(self):
        with fake_server(status=400, http_body=b"unsupported grammar") as (url, observed):
            result = call(url)
        self.assertEqual(result.status, "http_error")
        self.assertEqual(result.http_status, 400)
        self.assertIn("unsupported grammar", result.server_error)
        self.assertEqual(len(observed), 1)

    def test_server_sse_error_preserves_partial_generation(self):
        frames = [(0, frame("partial", tokens=2)),
                  (0, 'data: {"error":{"message":"engine failed"}}\n\n')]
        with fake_server(frames) as (url, _):
            result = call(url)
        self.assertEqual(result.status, "server_error")
        self.assertEqual(result.text, "partial")
        self.assertIn("engine failed", result.server_error)

    def test_length_finish_is_completed_truncation(self):
        with fake_server([(0, frame("partial", tokens=4096, finish="length")),
                          (0, "data: [DONE]\n\n")]) as (url, _):
            result = call(url)
        self.assertEqual(result.status, "truncated")
        self.assertTrue(result.request_completed)
        self.assertFalse(result.ok)

    def test_json_prefix_without_done_is_incomplete_stream(self):
        text = canonical_json(development_examples()[0]["output"])
        with fake_server([(0, frame(text, finish="stop"))]) as (url, _):
            result = call(url)
        self.assertEqual(result.status, "incomplete_stream")
        self.assertFalse(result.request_completed)

    def test_schema_invalid_response_is_retained_and_rejected(self):
        text = '{"ops":[{"op":"override_current"}]}'
        with fake_server([(0, frame(text, finish="stop")), (0, "data: [DONE]\n\n")]) as (url, _):
            result = call(url)
        self.assertEqual(result.status, "schema_validation_failure")
        self.assertTrue(result.telemetry["json_valid"])
        self.assertFalse(result.telemetry["schema_valid"])
        self.assertEqual(result.parsed, json.loads(text))

    def test_mismatched_budget_is_rejected_before_request(self):
        with fake_server() as (url, observed):
            with self.assertRaises(ValueError):
                OpenAICompatibleClient(base_url=url, model="fixed").generate(
                    method="CoPE", packet=packet(), max_output_tokens=8192, timeout_s=1.0,
                )
        self.assertEqual(observed, [])


if __name__ == "__main__":
    unittest.main()
