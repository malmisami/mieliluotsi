"""Read the user's daily summaries against their personal baseline and the active monitoring areas.

Gate 3 applies: nothing is read unless Apple Health is connected, the user allows Hyvinvointidata as a data source
and the metric itself is permitted."""
from __future__ import annotations

from typing import Any, Optional

from app.loop.models import LoopState
from app.support import consent
from app.wellbeing import catalog, trends
from app.wellbeing.models import WellbeingDataState


def data(state: LoopState) -> WellbeingDataState:
    return state.support.wellbeing


def connected(state: LoopState) -> bool:
    return data(state).connection.status == 'connected'


def usable(state: LoopState) -> bool:
    """May the agent (and its LLM context) use the data at all?"""
    return state.support.person is not None and connected(state) and consent.source_allowed(state, 'wellbeingData')


def permitted_metrics(state: LoopState) -> list[str]:
    permissions = data(state).connection.permissions
    return [m['id'] for m in catalog.metrics() if permissions.get(m['id'], False)]


def rows(state: LoopState) -> list[dict[str, Any]]:
    """The connected source's daily summaries, oldest first, permitted metrics only."""
    connection = data(state).connection
    allowed = set(permitted_metrics(state))
    result = []
    for record in sorted(data(state).dailyMetrics, key=lambda r: r.date):
        if connection.source and record.source != connection.source:
            continue
        row: dict[str, Any] = {'date': record.date}
        for metric_id in allowed:
            row[metric_id] = getattr(record, metric_id, None)
        result.append(row)
    return result


def analyze(state: LoopState) -> dict[str, Any]:
    """Per metric: current level, personal baseline, 30-day mean, trend and a meaningful change (or None)."""
    daily = rows(state)
    end = daily[-1]['date'] if daily else None
    result: dict[str, Any] = {'end': end, 'from': daily[0]['date'] if daily else None, 'days': len(daily), 'metrics': {}}
    if not end:
        return result
    windows = catalog.windows()
    for metric in catalog.metrics():
        series = trends.metric_series(daily, metric['id'])
        if not series:
            continue
        current = trends.calculate_current(series, end, windows, metric.get('kind', 'daily'))
        baseline = trends.calculate_personal_baseline(series, end, windows, metric.get('kind', 'daily'))
        result['metrics'][metric['id']] = {
            'metric': metric,
            'series': series,
            'current': current,
            'baseline': baseline,
            'recent': trends.calculate_rolling_average(series, end, windows['recentDays'], min_values=windows['minCurrentValues']),
            'week': trends.calculate_rolling_average(series, end, windows['currentDays'], min_values=1),
            'trend': trends.calculate_trend(series, end, windows['recentDays']),
            'change': trends.detect_meaningful_change(metric, current, baseline, series),
            'latest': {'date': series[-1][0], 'value': series[-1][1]},
        }
    return result


def active_areas(state: LoopState) -> list[dict[str, Any]]:
    """The monitoring list: the user's own wellbeing areas and the areas of the clinician-approved support plans.
    Only metrics of an active area may lead to a proactive observation."""
    selections = data(state).monitoringAreas
    plans = {p.theme: p for p in state.support.plans if p.status in ('active', 'escalated')}
    result = []
    for area in catalog.areas():
        if area.get('basis') == 'plan':
            plan = plans.get(area.get('planTheme'))
            if plan:
                result.append({**area, 'active': True, 'selectable': False, 'planId': plan.id,
                               'basisLabel': f'{plan.approval.byRole or plan.owner.label} hyväksyi: {plan.name}'})
        else:
            result.append({**area, 'active': bool(selections.get(area['id'], area.get('defaultOn', False))), 'selectable': True,
                           'basisLabel': 'Valitsit itse'})
    return result


def area_for_metric(state: LoopState, metric_id: str) -> Optional[dict[str, Any]]:
    return next((a for a in active_areas(state) if a['active'] and metric_id in a['metrics']), None)
