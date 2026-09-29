"""PersonProfile -> timeline HealthEvents, so every source is visible on one timeline with its date and origin.

The rule engine's existing event vocabulary is kept (lab_result/LDL, vital_sign/BP ...) so old rules work
unchanged. Imported history is never evaluated retroactively.
"""
from __future__ import annotations

from typing import Any, Optional

from app.loop.extraction import abnormal_flag
from app.support.models import PersonProfile

CHANNEL_LABELS = {'digital': 'digipalvelu', 'phone': 'puhelin', 'visit': 'vastaanotto'}
CONTEXT_LABELS = {'home': 'kotimittaus', 'clinic': 'vastaanotto', 'lab': 'laboratorio'}
SOURCE_FLAG = {'H': 'high', 'L': 'low'}
LAB_FIELDS = ('panelId', 'panelName', 'abbreviation', 'referenceRange', 'resultText')


def _event(date: str, type_: str, code: str, display: str, source: str, kind: str, source_id: str, **extra: Any) -> dict:
    return {
        'date': date, 'type': type_, 'code': code, 'displayName': display, 'source': source,
        'extractedData': {'sourceKind': kind, 'sourceId': source_id}, **extra,
    }


def profile_events(profile: PersonProfile) -> list[dict]:
    events: list[dict] = []
    for dx in profile.diagnoses:
        if dx.diagnosedAt:
            events.append(_event(dx.diagnosedAt, 'diagnosis', dx.code, f'Diagnoosi: {dx.label}', dx.source, 'diagnoses', dx.id,
                                 value=dx.code, structuredData={'status': dx.status}))
    for med in profile.medications:
        if med.startedAt:
            events.append(_event(med.startedAt, 'medication', 'MED_RECORD', 'Lääkitys lääkelistalla', med.source, 'medications', med.id,
                                 value=med.name, structuredData={'purpose': med.purpose, 'status': med.status}))
    for episode in profile.careEpisodes:
        events.append(_event(episode.date, 'care_episode', 'VISIT', episode.kind, episode.source, 'careEpisodes', episode.id,
                             rawText=episode.summary, structuredData={'professionalRole': episode.professionalRole}))
    for note in profile.professionalNotes:
        events.append(_event(note.date, 'professional_note', 'NOTE', f'Kirjaus ({note.authorRole})', note.source, 'professionalNotes',
                             note.id, rawText=note.text, structuredData={'authorRole': note.authorRole}))
    for contact in profile.interactionEvents:
        events.append(_event(contact.date, 'contact', 'CONTACT', f'Asiointi: {contact.topic}', contact.source, 'interactionEvents',
                             contact.id, value=CHANNEL_LABELS.get(contact.channel, contact.channel), rawText=contact.summary,
                             structuredData={'channel': contact.channel, 'topic': contact.topic}))
    for report in profile.selfReportedData:
        events.append(_event(report.date, 'self_report', 'SELF_REPORT', f'Oma ilmoitus: {report.topic}', 'user_reported',
                             'selfReportedData', report.id, rawText=report.text, confirmedByUser=True,
                             structuredData={'topic': report.topic}))
    for measurement in profile.measurements:
        events.append(_measurement_event(measurement.model_dump()))
    # every result knows the size of its order, so a summary can say "6 tulosta, lisäksi 1 löydöksen kohdalla"
    order_sizes: dict[str, int] = {}
    for event in events:
        order_id = event.get('structuredData', {}).get('panelId')
        if order_id:
            order_sizes[order_id] = order_sizes.get(order_id, 0) + 1
    for event in events:
        order_id = event.get('structuredData', {}).get('panelId')
        if order_id:
            event['structuredData']['panelSize'] = order_sizes[order_id]
    return sorted(events, key=lambda e: e['date'])


def _measurement_event(m: dict) -> dict:
    code = m['code']
    if code == 'BP':
        context = m.get('context') or 'home'
        return _event(m['date'], 'vital_sign', 'BP', f"Verenpaine ({CONTEXT_LABELS.get(context, context)})", m['source'],
                      'measurements', m['id'], value=m['value'], unit=m.get('unit') or 'mmHg', abnormalFlag=None,
                      structuredData={'systolic': m['systolic'], 'diastolic': m['diastolic'], 'context': context})
    flag: Optional[str] = abnormal_flag(code, m['value']) or SOURCE_FLAG.get(m.get('flag') or '')
    if flag is None and isinstance(m['value'], (int, float)):
        flag = 'normal'
    structured: dict[str, Any] = {'context': m.get('context')}
    # a lab order groups several results (e.g. "Lipidit", 7 results); the timeline shows them as one entry
    for key in LAB_FIELDS:
        if m.get(key) is not None:
            structured[key] = m[key]
    return _event(m['date'], 'lab_result' if m.get('context') == 'lab' else 'vital_sign', code, m['label'], m['source'],
                  'measurements', m['id'], value=m['value'], unit=m.get('unit'), abnormalFlag=flag,
                  structuredData=structured)
