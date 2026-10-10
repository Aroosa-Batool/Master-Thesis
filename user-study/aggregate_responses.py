"""Combine coded JSON exports from the sensor-comfort study into one CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


EXPECTED_STUDY_ID = "sensor-comfort-v1"


def flatten(value: Any, prefix: str = "", output: dict[str, Any] | None = None) -> dict[str, Any]:
    """Flatten nested objects using dotted keys and pipe-delimited arrays."""
    if output is None:
        output = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            flatten(child, child_prefix, output)
    elif isinstance(value, list):
        output[prefix] = "|".join(str(item) for item in value)
    else:
        output[prefix] = value
    return output


def load_records(input_directory: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    participant_codes: set[str] = set()
    paths = sorted(input_directory.glob("*.json"))
    if not paths:
        raise ValueError(f"No .json response files found in {input_directory}")

    for path in paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read {path.name}: {error}") from error

        if record.get("study_id") != EXPECTED_STUDY_ID:
            raise ValueError(f"{path.name} has unexpected study_id {record.get('study_id')!r}")
        participant_code = record.get("participant_code")
        if not isinstance(participant_code, str) or not participant_code.startswith("P-"):
            raise ValueError(f"{path.name} has an invalid participant_code")
        if participant_code in participant_codes:
            raise ValueError(f"Duplicate participant_code {participant_code} in {path.name}")
        participant_codes.add(participant_code)
        records.append(flatten(record))
    return records


def write_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    headers: list[str] = []
    for record in records:
        for key in record:
            if key not in headers:
                headers.append(key)
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_directory", type=Path, help="Directory containing JSON response files")
    parser.add_argument("output_csv", type=Path, help="New or existing CSV output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input_directory.is_dir():
        raise SystemExit(f"Input directory does not exist: {args.input_directory}")
    records = load_records(args.input_directory)
    write_csv(records, args.output_csv)
    print(f"Wrote {len(records)} response(s) to {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
