#!/usr/bin/env python3

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click


CSV_HEADER = [
    "model",
    "states",
    "relevant states",
    "variables",
    "predicates default",
    "predicates all",
    "scikit default",
    "scikit all",
    "dtnest default",
    "dtnest all",
    "new default",
    "new all",
]


LOG_SUFFIXES = {
    "default": "-default.log",
    "all": "-all.log",
}


STATE_RE = re.compile(r"Number of states: (?P<states>\d+) \(relevant: (?P<relevant>\d+)\)")
VARIABLES_RE = re.compile(r"Number of variables: (?P<variables>\d+)")
PREDICATES_RE = re.compile(r"Number of predicates: (?P<predicates>\d+)")
NODE_RE = re.compile(r"number of nodes: (?P<nodes>\d+)")


@dataclass
class LogData:
    states: Optional[int] = None
    relevant_states: Optional[int] = None
    variables: Optional[int] = None
    predicates: Optional[int] = None
    new_nodes: Optional[int] = None
    dtnest_nodes: Optional[int] = None
    scikit_nodes: Optional[int] = None


def parse_log(path: Path) -> LogData:
    text = path.read_text(encoding="utf-8")

    state_match = STATE_RE.search(text)
    variables_match = VARIABLES_RE.search(text)
    predicates_match = PREDICATES_RE.search(text)

    return LogData(
        states=int(state_match.group("states")) if state_match else None,
        relevant_states=int(state_match.group("relevant")) if state_match else None,
        variables=int(variables_match.group("variables")) if variables_match else None,
        predicates=int(predicates_match.group("predicates")) if predicates_match else None,
        new_nodes=_extract_section_nodes(text, "starting dtNest", "starting Old dtNest"),
        dtnest_nodes=_extract_section_nodes(text, "starting Old dtNest", "scikit-learn"),
        scikit_nodes=_extract_section_nodes(text, "scikit-learn", None),
    )


def _extract_section_nodes(text: str, start_marker: str, end_marker: Optional[str]) -> Optional[int]:
    start = text.find(start_marker)
    if start < 0:
        return None

    section = text[start:]
    if end_marker is not None:
        end = section.find(end_marker)
        if end >= 0:
            section = section[:end]

    matches = NODE_RE.findall(section)
    if not matches:
        return None
    return int(matches[-1])


def model_name_from_path(path: Path) -> tuple[str, str]:
    for setting, suffix in LOG_SUFFIXES.items():
        if path.name.endswith(suffix):
            return path.name[: -len(suffix)], setting
    raise ValueError(f"unexpected log filename: {path.name}")


def first_non_none(*values: Optional[int]) -> Optional[int]:
    for value in values:
        if value is not None:
            return value
    return None


def collect_rows(folder: Path) -> list[list[object]]:
    by_model: dict[str, dict[str, LogData]] = {}

    for path in sorted(folder.glob("*.log")):
        model, setting = model_name_from_path(path)
        by_model.setdefault(model, {})[setting] = parse_log(path)

    rows: list[list[object]] = []
    for model in sorted(by_model):
        default_log = by_model[model].get("default")
        all_log = by_model[model].get("all")
        if default_log is None and all_log is None:
            continue

        rows.append(
            [
                model,
                first_non_none(
                    default_log.states if default_log else None,
                    all_log.states if all_log else None,
                ),
                first_non_none(
                    default_log.relevant_states if default_log else None,
                    all_log.relevant_states if all_log else None,
                ),
                first_non_none(
                    default_log.variables if default_log else None,
                    all_log.variables if all_log else None,
                ),
                default_log.predicates if default_log else None,
                all_log.predicates if all_log else None,
                default_log.scikit_nodes if default_log else None,
                all_log.scikit_nodes if all_log else None,
                default_log.dtnest_nodes if default_log else None,
                all_log.dtnest_nodes if all_log else None,
                default_log.new_nodes if default_log else None,
                all_log.new_nodes if all_log else None,
            ]
        )

    return rows


def write_csv(rows: list[list[object]], output: Optional[Path]) -> None:
    if output is None:
        csv_file = sys.stdout
        close_file = False
    else:
        csv_file = output.open("w", newline="", encoding="utf-8")
        close_file = True

    try:
        writer = csv.writer(csv_file)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)
    finally:
        if close_file:
            csv_file.close()


@click.command()
@click.argument(
    "folder",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True, readable=True),
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path, dir_okay=False, writable=True, resolve_path=True),
    default=None,
    show_default=False,
    help="CSV output path. Defaults to <folder>/results.csv",
)
def main(folder: Path, output: Optional[Path]) -> None:
    rows = collect_rows(folder)
    write_csv(rows, output)

if __name__ == "__main__":
    main()
