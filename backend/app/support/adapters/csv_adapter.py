"""CSV adapter for LUVN-like tabular exports (semicolon-separated, Finnish column names)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.support.adapters.base import (
    AdapterError,
    Source,
    TableMapping,
    iter_csv_chunks,
    mapped,
    parse_date,
    parse_int,
    parse_number,
)
from app.support.models import Diagnosis, InteractionEvent, Measurement, Medication

MEASUREMENT_LABELS = {
    'BP': 'Verenpaine',
    'LDL': 'LDL-kolesteroli',
    'GLU': 'Verensokeri (paastoarvo)',
    'WEIGHT': 'Paino',
}

# Documented default mapping (see docs/LUVN_ADAPTER.md). A real LUVN export would get its own mapping here.
DEFAULT_MAPPINGS: dict[str, TableMapping] = {
    'diagnoosit.csv': TableMapping(
        target='diagnoses',
        person_column='asiakas_tunnus',
        columns={'code': 'dg_koodi', 'label': 'dg_nimi', 'diagnosedAt': 'dg_pvm', 'status': 'tila', 'source': 'lahde'},
        value_maps={'status': {'aktiivinen': 'active', 'päättynyt': 'resolved'}},
        required=('code', 'label'),
    ),
    'laakitys.csv': TableMapping(
        target='medications',
        person_column='asiakas_tunnus',
        columns={'name': 'valmiste', 'purpose': 'kayttotarkoitus', 'startedAt': 'aloitus_pvm', 'status': 'tila', 'source': 'lahde'},
        value_maps={'status': {'käytössä': 'active', 'lopetettu': 'stopped'}},
        required=('name',),
    ),
    'mittaukset.csv': TableMapping(
        target='measurements',
        person_column='asiakas_tunnus',
        columns={
            'date': 'pvm', 'code': 'mittaus', 'value': 'arvo', 'unit': 'yksikko', 'systolic': 'systolinen',
            'diastolic': 'diastolinen', 'context': 'ymparisto', 'flag': 'viite_lippu', 'source': 'lahde',
        },
        value_maps={
            'code': {'RR': 'BP', 'LDL': 'LDL', 'GLU': 'GLU', 'PAINO': 'WEIGHT'},
            'context': {'koti': 'home', 'vastaanotto': 'clinic', 'laboratorio': 'lab'},
        },
        required=('date', 'code'),
    ),
    # Laboratory export: one row per result; the order id groups the results of one request (e.g. "Lipidit", 7 results).
    'laboratoriotulokset.csv': TableMapping(
        target='measurements',
        person_column='asiakas_tunnus',
        columns={
            'date': 'naytteenotto_pvm', 'panelId': 'pyynto_tunnus', 'panelName': 'tutkimus', 'abbreviation': 'lyhenne',
            'label': 'analyysi', 'code': 'koodi', 'value': 'tulos', 'unit': 'yksikko', 'referenceRange': 'viitearvot',
            'flag': 'poikkeama', 'source': 'lahde',
        },
        required=('date', 'code', 'label'),
        defaults={'context': 'lab'},
        allow_text_values=True,
    ),
    'asioinnit.csv': TableMapping(
        target='interactionEvents',
        person_column='asiakas_tunnus',
        columns={'date': 'pvm', 'channel': 'kanava', 'topic': 'aihe', 'summary': 'kuvaus', 'source': 'lahde'},
        value_maps={'channel': {'digipalvelu': 'digital', 'puhelin': 'phone', 'vastaanotto': 'visit'}},
        required=('date', 'topic'),
    ),
}


def _item(row: dict[str, str], mapping: TableMapping, item_id: str) -> Any:
    for field_name in mapping.required:
        if not mapped(row, mapping, field_name):
            raise AdapterError(f'Pakollinen kenttä puuttuu ({mapping.columns[field_name]}).')
    source = mapped(row, mapping, 'source') or 'Tuntematon lähde'
    if mapping.target == 'diagnoses':
        return Diagnosis(
            id=item_id, code=mapped(row, mapping, 'code'), label=mapped(row, mapping, 'label'),
            diagnosedAt=parse_date(mapped(row, mapping, 'diagnosedAt'), 'diagnosedAt'),
            status=mapped(row, mapping, 'status') or 'active', source=source,
        )
    if mapping.target == 'medications':
        return Medication(
            id=item_id, name=mapped(row, mapping, 'name'), purpose=mapped(row, mapping, 'purpose'),
            startedAt=parse_date(mapped(row, mapping, 'startedAt'), 'startedAt'),
            status=mapped(row, mapping, 'status') or 'active', source=source,
        )
    if mapping.target == 'measurements':
        code = mapped(row, mapping, 'code')
        systolic = parse_int(mapped(row, mapping, 'systolic'))
        diastolic = parse_int(mapped(row, mapping, 'diastolic'))
        raw_value = mapped(row, mapping, 'value')
        try:
            value: Any = parse_number(raw_value)
        except AdapterError:
            if not mapping.allow_text_values:
                raise
            value = raw_value  # a qualitative lab result such as "Negatiivinen" stays text
        if code == 'BP':
            if systolic is None or diastolic is None:
                raise AdapterError('Verenpainemittauksesta puuttuu ylä- tai alapaine.')
            value = f'{systolic}/{diastolic}'
        return Measurement(
            id=item_id, date=parse_date(mapped(row, mapping, 'date'), 'date'), code=code,
            label=mapped(row, mapping, 'label') or MEASUREMENT_LABELS.get(code, code), value=value, unit=mapped(row, mapping, 'unit'),
            systolic=systolic, diastolic=diastolic, context=mapped(row, mapping, 'context'),
            flag=mapped(row, mapping, 'flag'), source=source,
            panelId=mapped(row, mapping, 'panelId'), panelName=mapped(row, mapping, 'panelName'),
            abbreviation=mapped(row, mapping, 'abbreviation'), referenceRange=mapped(row, mapping, 'referenceRange'),
            resultText=raw_value if 'referenceRange' in mapping.columns else None,
        )
    if mapping.target == 'interactionEvents':
        return InteractionEvent(
            id=item_id, date=parse_date(mapped(row, mapping, 'date'), 'date'), channel=mapped(row, mapping, 'channel') or 'unknown',
            topic=mapped(row, mapping, 'topic'), summary=mapped(row, mapping, 'summary'), source=source,
        )
    raise AdapterError(f'Tuntematon kohdetaulu: {mapping.target}')


class CsvAdapter:
    name = 'luvn_csv'

    def __init__(self, mappings: Optional[dict[str, TableMapping]] = None, delimiter: str = ';', chunk_size: int = 500):
        self.mappings = mappings or DEFAULT_MAPPINGS
        self.delimiter = delimiter
        self.chunk_size = chunk_size

    def mapping_for(self, table: str) -> TableMapping:
        mapping = self.mappings.get(table)
        if not mapping:
            raise AdapterError(f'Taululle {table} ei ole määritelty mäppäystä.')
        return mapping

    def load_table(self, source: Source, table: str, person_id: Optional[str] = None) -> tuple[str, list[Any], dict]:
        """Returns (target list name, items, stats). Rows of other people are skipped chunk by chunk."""
        mapping = self.mapping_for(table)
        items: list[Any] = []
        stats = {'rowsRead': 0, 'rowsForPerson': 0, 'chunks': 0}
        prefix = Path(table).stem.upper()[:3]
        for chunk in iter_csv_chunks(source, self.delimiter, self.chunk_size):
            stats['chunks'] += 1
            for row in chunk:
                stats['rowsRead'] += 1
                if person_id and row.get(mapping.person_column) != person_id:
                    continue
                stats['rowsForPerson'] += 1
                items.append(_item(row, mapping, f'{prefix}-{stats["rowsRead"]:04d}'))
        return mapping.target, items, stats
