"""Adapter interface: every source (CSV table, JSON export, genetic report) is mapped into PersonProfile items.

An adapter never interprets clinical meaning; it only renames columns, converts formats (dates, decimal
commas, code systems) and records provenance. Rows are streamed in chunks and filtered by person, so a
region-wide export with tens of thousands of people is never loaded into memory at once.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Union

Source = Union[str, Path]


class AdapterError(ValueError):
    pass


@dataclass(frozen=True)
class TableMapping:
    """How one source table maps to one PersonProfile list.

    `columns` maps internal field -> source column; `value_maps` translates coded values per internal field
    (e.g. {'code': {'RR': 'BP'}}). Unknown codes are kept as-is so nothing is silently dropped.
    `defaults` fills an internal field the table does not carry (e.g. every row of a lab export is context 'lab');
    `allow_text_values` keeps a non-numeric result as text (e.g. urine screening "Negatiivinen") instead of rejecting it.
    """
    target: str
    person_column: str
    columns: dict[str, str]
    value_maps: dict[str, dict[str, str]] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    defaults: dict[str, str] = field(default_factory=dict)
    allow_text_values: bool = False


def iter_csv_chunks(source: Source, delimiter: str = ';', chunk_size: int = 500) -> Iterator[list[dict[str, str]]]:
    """Stream a CSV file (or CSV text) as lists of at most `chunk_size` rows."""
    if isinstance(source, Path):
        handle = source.open(encoding='utf-8-sig', newline='')
    else:
        handle = io.StringIO(source)
    with handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise AdapterError('CSV-tiedostosta puuttuu otsikkorivi.')
        chunk: list[dict[str, str]] = []
        for row in reader:
            chunk.append({(key or '').strip(): (value or '').strip() for key, value in row.items()})
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk


def parse_date(value: Optional[str], field_name: str) -> Optional[str]:
    """Accept ISO dates (2026-08-30) and Finnish dates (30.8.2026); return ISO."""
    if not value:
        return None
    value = value.strip()
    try:
        if '.' in value:
            day, month, year = value.split('.')
            return date(int(year), int(month), int(day)).isoformat()
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise AdapterError(f'Virheellinen päivämäärä kentässä {field_name}: {value}') from exc


def parse_number(value: Optional[str]) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        return float(value.replace(',', '.'))
    except ValueError as exc:
        raise AdapterError(f'Virheellinen numeroarvo: {value}') from exc


def parse_int(value: Optional[str]) -> Optional[int]:
    number = parse_number(value)
    return int(number) if number is not None else None


def mapped(row: dict[str, str], mapping: TableMapping, internal_field: str) -> Optional[str]:
    column = mapping.columns.get(internal_field)
    raw = row.get(column, '') if column else ''
    if raw == '':
        return mapping.defaults.get(internal_field)
    return mapping.value_maps.get(internal_field, {}).get(raw, raw)


ItemFactory = Callable[[dict[str, str], TableMapping, str], Any]
