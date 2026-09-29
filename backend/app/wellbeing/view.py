"""Read models: the Hyvinvointidata tab (trends around the personal baseline, not raw numbers) and the small block of
the main dashboard (connection and new observations for the navigation)."""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.loop.models import LoopState
from app.support import consent
from app.wellbeing import analysis, catalog, context, texts, trends
from app.wellbeing.observations import signal_lines

PERIODS = {7: '7 päivää', 30: '30 päivää', 90: '3 kuukautta', 365: '12 kuukautta'}
# "Tänään": the latest day of four key metrics and the comparison that matters for each
TODAY = [('steps', 'week', '7 pv keskiarvo'), ('sleepMinutes', 'recent', '30 pv keskiarvo'),
         ('restingHeartRate', 'recent', '30 pv keskiarvo'), ('hrvMs', 'recent', '30 pv keskiarvo')]


def _connection(state: LoopState) -> dict[str, Any]:
    connection = analysis.data(state).connection
    return {
        'status': connection.status,
        'source': connection.source,
        'sourceLabel': catalog.source_label(connection.source),
        'synthetic': connection.source == 'synthetic_demo',
        'connectedAt': connection.connectedAt,
        'lastSyncAt': connection.lastSyncAt,
        'devices': [{'id': d.id, 'name': d.name, 'pairedAt': d.pairedAt, 'lastSyncAt': d.lastSyncAt}
                    for d in connection.devices if not d.revoked],
        'pairingExpiresAt': connection.pairing.expiresAt if connection.pairing else None,
        'permissions': dict(connection.permissions),
        'history': list(reversed(connection.history))[:5],
    }


def _observation(observation) -> dict[str, Any]:
    return observation.model_dump()


def dashboard_block(state: LoopState) -> dict[str, Any]:
    store = analysis.data(state)
    return {
        'status': store.connection.status,
        'synthetic': store.connection.source == 'synthetic_demo',
        'sourceLabel': catalog.source_label(store.connection.source),
        'lastSyncAt': store.connection.lastSyncAt,
        'newObservations': sum(1 for o in store.observations if o.status == 'new'),
        'inUse': analysis.usable(state),
    }


def view(state: LoopState, period: int = 30) -> dict[str, Any]:
    period = period if period in PERIODS else 30
    store = analysis.data(state)
    areas = analysis.active_areas(state)
    base: dict[str, Any] = {
        'available': state.support.person is not None,
        'demoMode': bool(settings.HEALTH_DEMO_MODE),
        'permissionText': catalog.config().get('permissionText'),
        'consentAllowed': consent.source_allowed(state, 'wellbeingData'),
        'inUse': analysis.usable(state),
        'connection': _connection(state),
        'metrics': [{'id': m['id'], 'label': m['label'], 'unit': m.get('unit'), 'healthKit': m.get('healthKit'),
                     'permitted': store.connection.permissions.get(m['id'], False)} for m in catalog.metrics()],
        'monitoring': [{'id': a['id'], 'label': a['label'], 'active': a['active'], 'selectable': a['selectable'], 'basis': a['basisLabel'],
                        'metrics': [catalog.metric(m)['label'] for m in a['metrics'] if catalog.metric(m)]} for a in areas],
        'observations': [_observation(o) for o in sorted(store.observations, key=lambda o: (o.periodEnd, o.id), reverse=True)
                         if o.status != 'dismissed'],
        'periods': [{'days': days, 'label': label} for days, label in PERIODS.items()],
        'period': period,
        'dataRange': None,
        'today': [],
        'trends': [],
        'changes': [],
        'agentContext': context.build(state),
    }
    result = analysis.analyze(state)
    if not result['end']:
        return base
    base['dataRange'] = {'from': result['from'], 'to': result['end'], 'days': result['days']}
    for metric_id, key, comparison in TODAY:
        item = result['metrics'].get(metric_id)
        if not item:
            continue
        reference = item.get(key)
        base['today'].append({
            'metric': metric_id, 'label': item['metric']['label'],
            'date': item['latest']['date'], 'value': catalog.format_value(metric_id, item['latest']['value']),
            'comparisonLabel': comparison, 'comparison': catalog.format_value(metric_id, reference['value']) if reference else None,
            'kind': item['change']['kind'] if item['change'] else None,
        })
    monitored = {m for a in areas if a['active'] for m in a['metrics']}
    for metric in catalog.metrics():
        item = result['metrics'].get(metric['id'])
        if not item:
            continue
        points = trends.window(item['series'], result['end'], period)
        if period >= 365:
            points = trends.weekly_means(points)
        base['trends'].append({
            'metric': metric['id'], 'label': metric['label'], 'unit': metric.get('unit'), 'format': metric.get('format'),
            'monitored': metric['id'] in monitored,
            'points': [{'date': d, 'value': round(v, 1)} for d, v in points],
            'baseline': round(item['baseline']['value'], 1) if item['baseline'] else None,
            'baselineText': catalog.format_value(metric['id'], item['baseline']['value']) if item['baseline'] else None,
            'current': round(item['current']['value'], 1) if item['current'] else None,
            'currentText': catalog.format_value(metric['id'], item['current']['value']) if item['current'] else None,
            'change': item['change']['kind'] if item['change'] else None,
            'weekly': period >= 365,
        })
        if item['change']:
            signal = signal_lines(item)
            area = analysis.area_for_metric(state, metric['id'])
            template = texts.MAIN_SIGNAL_SPARSE if signal['sparse'] else texts.MAIN_SIGNAL
            base['changes'].append({
                'metric': metric['id'], 'label': metric['label'], 'kind': item['change']['kind'],
                'text': template.format(subject=signal['subject'], verb=signal['verb'], current=signal['currentText'],
                                        baseline=signal['baselineText'], days=signal['baselineDays'] or 90),
                'delta': signal['deltaText'], 'area': area['label'] if area else None,
                'consecutiveDays': item['change']['consecutiveDays'],
            })
    base['trends'].sort(key=lambda t: not t['monitored'])
    base['changes'].sort(key=lambda c: (c['area'] is None, c['kind'] != 'concern'))
    return base
