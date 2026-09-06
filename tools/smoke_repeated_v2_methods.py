#!/usr/bin/env python3
"""Run deterministic Window 2 qualification without any external provider."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from cope_benchmark.repeated_v2.canonical import canonical_json
from cope_benchmark.repeated_v2.smoke import run_oracle_fixture_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    result = run_oracle_fixture_smoke()
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        for filename, records in (("EXACT_PROMPT_LOGS.txt", result["exact_prompt_logs"]),
                                  ("EVENT_CELLS.txt", result["rows"])):
            with (args.output_dir / filename).open('x', encoding='utf-8') as stream:
                for record in records:
                    stream.write(canonical_json(record) + '\n')
        with (args.output_dir / 'SUMMARY.csv').open('x', newline='', encoding='utf-8') as stream:
            fields = ('method','event_index','accepted','privileged','result_kind','execution_status','planning_problem_sha256')
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(result['rows'])
        (args.output_dir / 'RESULT.txt').write_text(canonical_json({k:v for k,v in result.items()
            if k not in ('rows','exact_prompt_logs')}) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','exact_prompt_logs',
        'information_parity_sha256_by_event','configuration')}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
