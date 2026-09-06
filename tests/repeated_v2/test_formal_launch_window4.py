from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from cope_benchmark.repeated_v2 import formal_launch
from cope_benchmark.repeated_v2.formal_launch import idle_gpu_ids, shard_command
from cope_benchmark.repeated_v2.freeze import FreezeBlocked


def test_only_idle_gpus_no_other_process_selected():
    gpus="0, GPU-zero, 0, 0\n1, GPU-one, 0, 1781\n2, GPU-two, 1, 0\n3, GPU-three, 0, 0\n"
    assert idle_gpu_ids(gpus,"GPU-three, 47123\n") == ["GPU-zero"]


@pytest.mark.parametrize("text",["0,GPU-zero,N/A,0\n","0,GPU-zero,0\n","0,GPU-zero,0,-1\n"])
def test_unknown_gpu_state_blocks(text):
    with pytest.raises(FreezeBlocked): idle_gpu_ids(text,"")


def test_all_eight_commands_use_one_continuous_shard_and_separate_paths():
    commands=[shard_command(python="python",repo_root=Path("/repo"),protocol="end_to_end",
        condition="evidence_matched",config="c",catalog="t",manifest="m",freeze="f",
        output_root=Path("/repo/research/formal"),shard_id=i) for i in range(8)]
    assert len({command[-1] for command in commands})==8
    assert all(command[command.index("--num-shards")+1]=="8" for command in commands)
    assert all("--phase" in c and "formal" in c and "--frozen-bundle" in c for c in commands)
    assert all("--checkpoint" not in c for c in commands)


def test_invalid_shard_rejected():
    with pytest.raises(ValueError):
        shard_command(python="p",repo_root=Path("/repo"),protocol="controlled",condition="evidence_matched",
            config="c",catalog="t",manifest="m",freeze="f",output_root=Path("/repo/research/f"),shard_id=True)


@pytest.fixture
def launcher_harness(tmp_path, monkeypatch):
    """Isolate launcher behavior; no freeze qualification or runtime is claimed."""
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(formal_launch, "__file__",
                        str(root / "cope_benchmark/repeated_v2/formal_launch.py"))
    paths = {}
    for role in ("config", "catalog", "manifest"):
        paths[role] = root / f"{role}.txt"
        paths[role].write_text(f"launcher-test-only {role}\n")
    bundle = {
        "identities": {"fixture": "launcher-test-only"},
        "artifacts": {role: {"entries": [{"sha256": formal_launch.sha256_file(path)}]}
                      for role, path in paths.items()},
    }
    validations, launches, waits, gpu_inspections = [], [], [], []

    def validate(value, *, repo_root):
        assert value is bundle
        assert repo_root == root
        validations.append(len(launches))

    def inspect():
        gpu_inspections.append(True)
        return ["GPU-test-zero", "GPU-test-one"]

    def spawn(command, *, cwd, env):
        assert cwd == root
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        launch = {"command": command, "env": env, "output": output}
        launches.append(launch)

        def wait():
            waits.append(launch)
            return 0

        return SimpleNamespace(wait=wait)

    monkeypatch.setattr(formal_launch, "_load", lambda path: bundle)
    monkeypatch.setattr(formal_launch, "validate_static_frozen_bundle", validate)
    monkeypatch.setattr(formal_launch, "inspect_idle_gpus", inspect)
    monkeypatch.setattr(formal_launch.subprocess, "Popen", spawn)
    monkeypatch.setenv("COPE_RUNTIME_FACTORY", "launcher_test_only:never_loaded")
    output = root / "research/formal"

    def argv(protocol="controlled", condition="evidence_matched", *extra):
        return ["--config", str(paths["config"]), "--task-catalog", str(paths["catalog"]),
                "--manifest", str(paths["manifest"]), "--frozen-bundle", str(root / "FREEZE.txt"),
                "--protocol", protocol, "--information-condition", condition,
                "--output-root", str(output), "--workers", "2", *extra]

    return SimpleNamespace(root=root, output=output, argv=argv, launches=launches,
                           waits=waits, validations=validations,
                           gpu_inspections=gpu_inspections, spawn=spawn)


def test_all_protocol_conditions_share_root_without_reusing_group(launcher_harness, capsys):
    harness = launcher_harness
    for protocol in ("controlled", "end_to_end"):
        for condition in ("evidence_matched", "token_matched"):
            assert formal_launch.main(harness.argv(protocol, condition)) == 0
            report = json.loads(capsys.readouterr().out)
            assert report["status"] == "FORMAL_SHARDS_COMPLETED"
            group = harness.launches[-8:]
            assert {item["output"].name for item in group} == {
                f"shard_{index:02d}" for index in range(8)}
            assert all(item["output"].parent == harness.output / protocol / condition
                       for item in group)
            assert all("--resume" not in item["command"] for item in group)
            expected_devices = {""} if protocol == "controlled" else {
                "GPU-test-zero", "GPU-test-one"}
            assert {item["env"]["CUDA_VISIBLE_DEVICES"] for item in group} == expected_devices
    assert len(harness.launches) == len(harness.waits) == 32
    assert len({item["output"] for item in harness.launches}) == 32


@pytest.mark.parametrize("protocol", ["controlled", "end_to_end"])
@pytest.mark.parametrize("condition", ["evidence_matched", "token_matched"])
def test_existing_group_requires_resume_and_retains_artifacts(
        launcher_harness, capsys, protocol, condition):
    harness = launcher_harness
    group = harness.output / protocol / condition
    group.mkdir(parents=True)
    retained = group / "retained_result.txt"
    retained.write_bytes(b"existing result bytes\n")
    assert formal_launch.main(harness.argv(protocol, condition)) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["reasons"] == ["BLOCKED_EXISTING_OUTPUT_REQUIRES_VERIFIED_RESUME"]
    assert harness.launches == harness.waits == []
    assert retained.read_bytes() == b"existing result bytes\n"


@pytest.mark.parametrize("failed_spawn", [2, 4])
def test_partial_spawn_failure_waits_for_every_started_child(
        launcher_harness, monkeypatch, capsys, failed_spawn):
    harness = launcher_harness
    attempts = []

    def fail_later_spawn(command, *, cwd, env):
        attempts.append(command)
        if len(attempts) == failed_spawn:
            raise OSError("test-only spawn failure")
        return harness.spawn(command, cwd=cwd, env=env)

    monkeypatch.setattr(formal_launch.subprocess, "Popen", fail_later_spawn)
    assert formal_launch.main(harness.argv("controlled", "evidence_matched", "--workers", "4")) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "BLOCKED_FORMAL_LAUNCH"
    assert report["reasons"] == ["test-only spawn failure"]
    assert len(attempts) == failed_spawn
    assert len(harness.launches) == failed_spawn - 1
    assert harness.waits == harness.launches
    assert harness.launches[0]["output"].is_dir()


@pytest.mark.parametrize("protocol", ["controlled", "end_to_end"])
def test_plan_only_validates_inputs_without_runtime_or_gpu_calls(
        launcher_harness, monkeypatch, capsys, protocol):
    harness = launcher_harness
    monkeypatch.delenv("COPE_RUNTIME_FACTORY")

    def forbidden(*args, **kwargs):
        pytest.fail("plan-only attempted runtime launch or GPU inspection")

    monkeypatch.setattr(formal_launch.subprocess, "Popen", forbidden)
    monkeypatch.setattr(formal_launch, "inspect_idle_gpus", forbidden)
    assert formal_launch.main(harness.argv(protocol, "evidence_matched", "--plan-only")) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "FROZEN_LAUNCH_PLAN_ONLY"
    assert report["formal_calls"] == 0
    assert len(report["commands"]) == 8
    assert {command[command.index("--shard-index") + 1] for command in report["commands"]} == {
        str(index) for index in range(8)}
    assert harness.validations == [0]
    assert not harness.output.exists()
