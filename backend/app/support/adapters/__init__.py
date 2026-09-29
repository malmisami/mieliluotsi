"""Source adapters -> PersonProfile. See docs/LUVN_ADAPTER.md for the default schema and mapping."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.support.adapters.base import AdapterError
from app.support.adapters.csv_adapter import DEFAULT_MAPPINGS, CsvAdapter
from app.support.adapters.json_adapter import GeneticJsonAdapter, PersonJsonAdapter
from app.support.models import PersonProfile

PERSON_FILE = 'asiakas.json'
GENETIC_FILE = 'perimatieto.json'

__all__ = ['AdapterError', 'load_person_directory', 'preview']


def load_person_directory(directory: Path, person_id: Optional[str] = None) -> PersonProfile:
    """Read one person's records from a directory of LUVN-like exports.

    asiakas.json is required; every CSV table and the genetic report are optional (the service must work
    with whatever sources exist - DNA is never a prerequisite).
    """
    person_path = directory / PERSON_FILE
    if not person_path.exists():
        raise AdapterError(f'{PERSON_FILE} puuttuu hakemistosta {directory.name}.')
    base = PersonJsonAdapter().load(json.loads(person_path.read_text(encoding='utf-8')))
    pid = person_id or base['demographics'].personId
    profile = PersonProfile(**base)
    profile.sourceSystems.append({'adapter': PersonJsonAdapter.name, 'file': PERSON_FILE, 'rows': 1})

    csv_adapter = CsvAdapter()
    for table in DEFAULT_MAPPINGS:
        path = directory / table
        if not path.exists():
            continue
        target, items, stats = csv_adapter.load_table(path, table, person_id=pid)
        getattr(profile, target).extend(items)
        profile.sourceSystems.append({'adapter': CsvAdapter.name, 'file': table, 'rows': stats['rowsForPerson'],
                                      'rowsRead': stats['rowsRead'], 'chunks': stats['chunks']})

    genetic_path = directory / GENETIC_FILE
    if genetic_path.exists():
        profile.geneticInsights = GeneticJsonAdapter().load(json.loads(genetic_path.read_text(encoding='utf-8')), pid)
        profile.sourceSystems.append({'adapter': GeneticJsonAdapter.name, 'file': GENETIC_FILE, 'rows': len(profile.geneticInsights)})
    return profile


def preview(format_: str, content: str, table: Optional[str] = None, person_id: Optional[str] = None) -> dict[str, Any]:
    """Map pasted CSV/JSON content without saving anything - lets a developer check a mapping quickly."""
    if format_ == 'csv':
        target, items, stats = CsvAdapter().load_table(content, table or 'mittaukset.csv', person_id=person_id)
        return {'target': target, 'items': [item.model_dump() for item in items], 'stats': stats}
    if format_ == 'json':
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AdapterError(f'JSON ei ole kelvollinen: {exc.msg}') from exc
        if 'havainnot' in data:
            items = GeneticJsonAdapter().load(data, person_id or data.get('asiakasTunnus'))
            return {'target': 'geneticInsights', 'items': [item.model_dump() for item in items], 'stats': {'rowsForPerson': len(items)}}
        mapped = PersonJsonAdapter().load(data)
        return {
            'target': 'person',
            'items': {key: (value.model_dump() if hasattr(value, 'model_dump') else [v.model_dump() if hasattr(v, 'model_dump') else v for v in value])
                      for key, value in mapped.items()},
            'stats': {},
        }
    raise AdapterError('Tuettuja muotoja ovat csv ja json.')
