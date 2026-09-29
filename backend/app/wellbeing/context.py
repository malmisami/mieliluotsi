"""The compact Hyvinvointidata block of the agent's context. Never the history: current level (7 days), the personal
baseline, the recent changes in absolute units, the active monitoring areas and the observation being discussed.
Nothing when the data is not connected or the user has not allowed it (gate 3)."""
from __future__ import annotations

from typing import Any, Optional

from app.loop.models import LoopState
from app.loop.templates import fi_date
from app.wellbeing import analysis, catalog, texts


def build(state: LoopState) -> Optional[dict[str, Any]]:
    if not analysis.usable(state):
        return None
    result = analysis.analyze(state)
    if not result['end']:
        return None
    current, baseline, changes = {}, {}, []
    for metric_id, item in result['metrics'].items():
        if item['current']:
            current[item['metric']['label']] = catalog.format_value(metric_id, item['current']['value'])
        if item['baseline']:
            baseline[item['metric']['label']] = catalog.format_value(metric_id, item['baseline']['value'])
        if item['change']:
            area = analysis.area_for_metric(state, metric_id)
            changes.append({'metric': item['metric']['label'], 'change': catalog.format_delta(metric_id, item['change']['delta']),
                            'kind': item['change']['kind'], 'monitoringArea': area['label'] if area else None})
    active = next((o for o in analysis.data(state).observations if o.id == analysis.data(state).activeObservationId), None)
    return {
        'source': catalog.source_label(analysis.data(state).connection.source),
        'synthetic': analysis.data(state).connection.source == 'synthetic_demo',
        'period': f"viimeiset 7 päivää ({fi_date(result['end'])} asti) verrattuna omaan 90 päivän tasoon",
        'current': current,
        'personalBaseline': baseline,
        'recentChanges': changes,
        'monitoringAreas': [{'label': a['label'], 'metrics': [catalog.metric(m)['label'] for m in a['metrics'] if catalog.metric(m)],
                             'basis': a['basisLabel']} for a in analysis.active_areas(state) if a['active']],
        'observationUnderDiscussion': {'title': active.title, 'summary': active.summary, 'area': active.areaLabel} if active else None,
        'note': 'Päivittäiset yhteenvedot, ei yksittäisiä mittauksia. Muutos ei ole diagnoosi.',
    }


def chat_summary(state: LoopState) -> str:
    """The template answer to "Mitä hyvinvointidatani kertoo?" (the same facts the LLM would get)."""
    from app.support import consent  # local import keeps this module light

    connection = analysis.data(state).connection
    if connection.status != 'connected':
        return texts.CHAT_SUMMARY_NONE
    if not consent.source_allowed(state, 'wellbeingData'):
        return texts.CHAT_SUMMARY_NOT_ALLOWED
    result = analysis.analyze(state)
    lines = [texts.CHAT_SUMMARY_INTRO.format(source=catalog.source_label(connection.source))]
    for metric_id, item in result['metrics'].items():
        if not item['current'] or not item['baseline']:
            continue
        change = f" ({catalog.format_delta(metric_id, item['change']['delta'])})" if item['change'] else ''
        lines.append(f"• {item['metric']['label']}: {catalog.format_value(metric_id, item['current']['value'])}, oma tasosi "
                     f"{catalog.format_value(metric_id, item['baseline']['value'])}{change}")
    if not any(item['change'] for item in result['metrics'].values()):
        lines.append(texts.CHAT_SUMMARY_NO_CHANGES)
    observations = [o for o in analysis.data(state).observations if o.status != 'dismissed']
    if observations:
        latest = observations[-1]
        lines.extend(['', f'{latest.title}: {latest.summary} {latest.areaNote}'])
    lines.extend(['', texts.CHAT_SUMMARY_NOTE])
    return '\n'.join(lines)
