"""Analyze frozen repeated-v2 runs, or issue an explicit zero-cell blocker report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cope_benchmark.repeated_v2.analysis import (CHECKPOINTS, analyze_protocol, audit_cells,
    comparison_evidence, correct_secondary_family, read_records, sha256_file, write_artifacts)
from cope_benchmark.repeated_v2.claim_decision import DecisionInput, evaluate_claims
from cope_benchmark.repeated_v2.freeze import _load, _digest, validate_archived_bundle, audit_journal_directory
from cope_benchmark.repeated_v2.analysis_shards import group_formal_shards
from cope_benchmark.repeated_v2.parity_analysis import audit_prompt_parity


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest")
    parser.add_argument("--freeze", help="FREEZE.txt from the zero-call freeze tool")
    parser.add_argument("--run-dir", action="append", default=[],
        help="Shard directory with raw journal, 00 metadata and 06 events; supply all 8 for each protocol/condition")
    parser.add_argument("--blocker", action="append", default=[], help="Explicit observed BLOCKED_* reason; creates no result cells")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output_dir).resolve()
    if not any(output.is_relative_to(root / folder) for folder in ("research", "docs")):
        parser.error("output must be under this repository's research/ or docs/")
    if any(not reason.startswith("BLOCKED_") for reason in args.blocker):
        parser.error("blockers must be explicit BLOCKED_* identifiers")
    analyses, errors = [], []
    blockers = list(args.blocker)
    provenance = {"analysis_git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                  "bootstrap_replicates": 10000, "bootstrap_seed": 20260906,
                  "source_files": {}, "formal_calls_by_analyzer": 0,
                  "observed_result_cells": 0}
    comparator = None
    try:
        if args.run_dir:
            if not args.freeze or not args.manifest:
                raise ValueError("formal analysis requires the actual frozen bundle and manifest")
            bundle = _load(args.freeze)
            # Read-only postrun validation: this tool makes zero model calls. A
            # live-call identity callback is required by the runtime separately.
            validate_archived_bundle(bundle, repo_root=root)
            frozen_manifest = bundle["artifacts"]["manifest"]["entries"]
            if len(frozen_manifest) != 1 or sha256_file(args.manifest) != frozen_manifest[0]["sha256"]:
                raise ValueError("manifest bytes do not match freeze")
            provenance["source_files"][str(Path(args.freeze).resolve())] = sha256_file(args.freeze)
            provenance["source_files"][str(Path(args.manifest).resolve())] = sha256_file(args.manifest)
            comparator = bundle["primary_comparator"]["method"]
            manifest = read_records(args.manifest)
            shards=[]
            journals={}
            for run in args.run_dir:
                directory = Path(run).resolve()
                metadata_path, events_path = directory/"00_RUN_METADATA.json", directory/"06_EVENT_RESULTS.jsonl"
                metadata = _load(metadata_path)
                protocol = metadata["protocol"]
                condition = metadata["information_condition"]
                if metadata.get("phase") != "formal" or metadata.get("freeze_sha256") != bundle["bundle_sha256"]:
                    raise ValueError("run is not bound to this formal freeze")
                records = read_records(events_path)
                provenance["observed_result_cells"] += len(records)
                for path in (metadata_path, events_path):
                    provenance["source_files"][str(path)] = sha256_file(path)
                shards.append({"metadata":metadata,"records":records,"directory":directory})
            grouped=group_formal_shards(bundle,manifest,shards)
            for shard in shards:
                metadata=shard["metadata"]
                protocol,condition=metadata["protocol"],metadata["information_condition"]
                owned=set(next(s for s in bundle["shards"] if s["shard_id"]==metadata["shard_id"])["master_episode_ids"])
                expected=[(protocol,row["master_episode_id"],method,k) for row in manifest
                    if row["master_episode_id"] in owned
                    for method in row["methods"]["non_oracle"]+row["methods"]["oracle"]
                    for k in range(row["protocol_prefixes"][protocol]["event_count"]+1)]
                audit=audit_journal_directory(shard["directory"],expected_cells=expected,
                    expected_phase="formal",identities=bundle["identities"],
                    exported_results=shard["records"],freeze_sha256=bundle["bundle_sha256"])
                journals.setdefault((protocol,condition),[]).append(audit)
                for path in sorted((shard["directory"]/"journal").rglob("*.json")):
                    provenance["source_files"][str(path)]=sha256_file(path)
            config=_load(bundle["artifacts"]["config"]["entries"][0]["path"])
            if any(shard["metadata"].get("config_sha256") != _digest(config) for shard in shards):
                raise ValueError("shard configuration identity differs from frozen configuration")
            parities={}
            group_audits=[]
            for (protocol,condition),group in grouped.items():
                parity=audit_prompt_parity(journals[(protocol,condition)],identities=bundle["identities"],
                                          config=config,condition=condition)
                parities[(protocol,condition)]=parity
                audit=audit_cells(group["manifest"],group["records"],protocol=protocol,condition=condition,
                                  freeze_sha256=bundle["bundle_sha256"])
                group_audits.append(dict(protocol=protocol,condition=condition,**audit))
                errors.extend(parity["errors"])
                errors.extend(audit["errors"])
            provenance["group_integrity_audits"]=group_audits
            if errors:
                raise ValueError("submitted evidence failed integrity; no numerical analysis admitted")
            for (protocol,condition),group in grouped.items():
                parity=parities[(protocol,condition)]
                analysis=analyze_protocol(group["manifest"],group["records"],protocol=protocol,condition=condition,
                    comparator=comparator,freeze_sha256=bundle["bundle_sha256"])
                analysis["parity"]=parity
                analysis["integrity"]["errors"].extend(parity["errors"])
                analysis["integrity"]["valid"]=analysis["integrity"]["valid"] and not parity["errors"]
                analyses.append(analysis)
            provenance["holm_family"] = correct_secondary_family(analyses)
        elif not blockers:
            blockers.append("BLOCKED_FORMAL_EVIDENCE_UNAVAILABLE")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(str(exc))
    invalid = errors + [error for analysis in analyses for error in analysis["integrity"]["errors"]]
    provenance["integrity_errors"]=invalid
    primary = {a["protocol"]: a for a in analyses if a["condition"] == "evidence_matched" and a["integrity"]["valid"]}
    def evidence(protocol):
        if protocol not in primary:
            return None
        a=primary[protocol]
        return comparison_evidence(a,evidence_parity=a["parity"]["evidence_parity"],
                                   reasoner_call_parity=a["parity"]["reasoner_call_parity"])
    learned,controlled=evidence("end_to_end"),evidence("controlled")
    decision = evaluate_claims(DecisionInput(integrity_valid=False if invalid else (True if analyses else None),
        formal_complete=learned is not None, blockers=tuple(blockers), invalid_reasons=tuple(invalid),
        learned_vla=learned, controlled=controlled, controlled_complete=controlled is not None,
        controlled_integrity_valid=True if controlled is not None else None, primary_comparator=comparator))
    write_artifacts(output, analyses, decision, provenance=provenance,
        notes=("No raw result file is modified by analysis. This report records only supplied evidence.",))
    print(json.dumps({"status":decision.status,"output_dir":str(output),"formal_calls":0},sort_keys=True))
    return 0 if decision.status in ("GO", "PARTIAL_SUPPORT", "NO_GO") else 2


if __name__ == "__main__":
    raise SystemExit(main())
