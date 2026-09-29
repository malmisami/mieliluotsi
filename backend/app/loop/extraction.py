"""Health text -> structured HealthEvent fields.

The abnormal flag is always computed here deterministically from the local reference range,
never taken from the LLM.
"""
from __future__ import annotations

import re

from app.loop import llm
from app.loop.evidence import load_evidence

_NUMBER = r'(\d+(?:[.,]\d+)?)'


def _to_float(text: str) -> float:
    return float(text.replace(',', '.'))


def parse_text(raw_text: str) -> dict:
    """Rule-based parser for the demo's Finnish health texts."""
    text = raw_text.strip()
    ldl = re.search(r'LDL[\w\-]*\s*[:=]?\s*' + _NUMBER + r'\s*(mmol/l)?', text, flags=re.IGNORECASE)
    if ldl:
        return {'type': 'lab_result', 'code': 'LDL', 'displayName': 'LDL-kolesteroli', 'value': _to_float(ldl.group(1)), 'unit': 'mmol/l'}
    bp = re.search(r'verenpaine\D{0,20}(\d{2,3}\s*/\s*\d{2,3})', text, flags=re.IGNORECASE)
    if bp:
        return {'type': 'vital_sign', 'code': 'BP', 'displayName': 'Verenpaine', 'value': bp.group(1).replace(' ', ''), 'unit': 'mmHg'}
    if re.search(r'lääke|lääkitys|lääkelista', text, flags=re.IGNORECASE):
        return {'type': 'medication', 'code': 'MED_NEW', 'displayName': 'Uusi lääkitys', 'value': None, 'unit': None}
    if re.search(r'evidenssi|tutkimus|luokitus', text, flags=re.IGNORECASE):
        return {'type': 'research_update', 'code': 'EVIDENCE_REVIEW', 'displayName': 'Uusi tutkimustieto', 'value': None, 'unit': None}
    return {'type': 'free_text', 'code': 'OTHER', 'displayName': 'Terveysteksti', 'value': None, 'unit': None}


def abnormal_flag(code: str | None, value) -> str | None:
    reference = load_evidence()['reference_ranges'].get(code or '')
    if not reference:
        return None
    if not isinstance(value, (int, float)):
        return 'unknown'
    return 'high' if value > reference['high_above'] else 'normal'


def extract(raw_text: str) -> tuple[dict, str]:
    """Returns (structured fields, method). Tries the LLM first when enabled, then the parser."""
    method = 'deterministic_parser'
    data = None
    if llm.enabled():
        data = llm.extract_event(raw_text)
        if data:
            method = 'llm'
            if isinstance(data.get('value'), str) and data.get('code') == 'LDL':
                try:
                    data['value'] = _to_float(data['value'])
                except ValueError:
                    pass
    if not data:
        data = parse_text(raw_text)
        if llm.enabled():
            method = 'deterministic_parser (LLM-fallback)'
    data['abnormalFlag'] = abnormal_flag(data.get('code'), data.get('value'))
    return data, method
