"""What the user (and the demo) can do in Hyvinvointidata: load clearly synthetic test data, synchronize, choose the
metrics and the monitoring areas, disconnect and delete the imported data."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.loop.models import LoopState
from app.support import audit
from app.wellbeing import analysis, catalog, demo, observations, sync
from app.wellbeing.models import METRIC_IDS


class ServiceError(ValueError):
    pass


def _demo_stamp(state: LoopState) -> str:
    """The demo runs on its own clock (the demo date); the time of day is the real one."""
    return f"{state.currentDate}T{datetime.now().strftime('%H:%M')}:00"


def use_synthetic(state: LoopState) -> dict[str, Any]:
    """Connect the clearly synthetic demo source (never presented as the user's Apple Health data)."""
    store = analysis.data(state)
    if store.connection.source == 'apple_health' and store.connection.status == 'connected':
        raise ServiceError('Apple Health on yhdistetty. Katkaise yhteys ennen synteettisen testidatan käyttöä.')
    store.dailyMetrics = [r for r in store.dailyMetrics if r.source != 'synthetic_demo']
    connection = store.connection
    connection.status, connection.source = 'connected', 'synthetic_demo'
    connection.connectedAt = _demo_stamp(state)
    connection.history.append({'date': state.currentDate, 'change': 'Synteettinen testidata otettiin käyttöön (demo).'})
    result = sync.upsert_days(state, 'synthetic_demo', demo.generate(state.currentDate), device_id='synthetic-demo',
                              synced_at=_demo_stamp(state))
    audit.record(state, stage='data', actor='system', action='health_sync',
                 detail=f"Synteettinen Apple Health -muotoinen testidata ladattiin ({result['created']} päivää). Ei oikeaa käyttäjän dataa.")
    created = observations.refresh(state)
    return {**result, 'observations': [o.id for o in created]}


def sync_now(state: LoopState) -> dict[str, Any]:
    """'Synkronoi nyt': the synthetic source catches up to the demo date; Apple Health data arrives from the iPhone."""
    connection = analysis.data(state).connection
    if connection.status != 'connected':
        raise ServiceError('Apple Healthia ei ole yhdistetty.')
    if connection.source == 'synthetic_demo':
        have = {r.date for r in analysis.data(state).dailyMetrics if r.source == 'synthetic_demo'}
        missing = [d for d in demo.generate(state.currentDate) if d['date'] not in have]
        result = sync.upsert_days(state, 'synthetic_demo', missing, device_id='synthetic-demo', synced_at=_demo_stamp(state)) if missing \
            else {'created': 0, 'updated': 0, 'droppedMetrics': []}
        connection.lastSyncAt = _demo_stamp(state)
        created = observations.refresh(state)
        return {**result, 'observations': [o.id for o in created], 'message': 'Synteettinen testidata päivitettiin demopäivään asti.'}
    created = observations.refresh(state)
    return {'created': 0, 'updated': 0, 'observations': [o.id for o in created],
            'message': 'Apple Health -tiedot synkronoituvat iPhonen Hyvinvointikumppani-sovelluksesta. Avaa sovellus ja valitse Synkronoi.'}


def set_permissions(state: LoopState, permissions: dict[str, Any]) -> dict[str, bool]:
    """Which metrics are synchronized and used. A metric that is switched off is also removed from the stored data."""
    connection = analysis.data(state).connection
    for metric_id, allowed in permissions.items():
        if metric_id not in METRIC_IDS:
            raise ServiceError(f'Tuntematon mittari: {metric_id}.')
        allowed = bool(allowed)
        if connection.permissions.get(metric_id) != allowed:
            connection.permissions[metric_id] = allowed
            if not allowed:
                for record in analysis.data(state).dailyMetrics:
                    setattr(record, metric_id, None)
                    if metric_id == 'workoutMinutes':
                        record.workoutCount = None
            label = (catalog.metric(metric_id) or {}).get('label', metric_id)
            audit.record(state, stage='consent', actor='user', action='health_permission',
                         detail=f"Hyvinvointidata: {label} {'sallittiin' if allowed else 'poistettiin käytöstä ja tallennetut arvot poistettiin'}.")
    return connection.permissions


def set_monitoring(state: LoopState, areas: dict[str, Any]) -> dict[str, bool]:
    selectable = {a['id'] for a in catalog.areas() if a.get('basis') == 'user'}
    for area_id, on in areas.items():
        if area_id not in selectable:
            raise ServiceError('Tätä seuranta-aluetta ei voi valita itse (se kuuluu ammattilaisen hyväksymään suunnitelmaan).')
        analysis.data(state).monitoringAreas[area_id] = bool(on)
    observations.refresh(state)
    return analysis.data(state).monitoringAreas


def disconnect(state: LoopState) -> None:
    """Stops synchronization and the agent's use of the data. The imported data stays until the user deletes it."""
    connection = analysis.data(state).connection
    if connection.status != 'connected':
        raise ServiceError('Yhteyttä ei ole.')
    for device in connection.devices:
        device.revoked = True
    connection.status, connection.pairing = 'disconnected', None
    analysis.data(state).activeObservationId = None
    connection.history.append({'date': state.currentDate, 'change': 'Yhteys katkaistiin. Agentti ei käytä tietoja.'})
    audit.record(state, stage='consent', actor='user', action='health_disconnect',
                 detail='Apple Health -yhteys katkaistiin. Synkronointi loppui, eikä agentti käytä tietoja.')


def delete_data(state: LoopState) -> int:
    """Delete every imported daily summary and the observations derived from them."""
    store = analysis.data(state)
    count = len(store.dailyMetrics)
    store.dailyMetrics, store.observations, store.activeObservationId = [], [], None
    for device in store.connection.devices:
        device.revoked = True
    store.connection.status, store.connection.source, store.connection.lastSyncAt = 'not_connected', None, None
    store.connection.pairing = None
    store.connection.history.append({'date': state.currentDate, 'change': 'Tuodut hyvinvointitiedot poistettiin.'})
    audit.record(state, stage='consent', actor='user', action='health_delete',
                 detail=f'Tuodut hyvinvointitiedot poistettiin ({count} päivän yhteenvedot ja niistä tehdyt havainnot).')
    return count
