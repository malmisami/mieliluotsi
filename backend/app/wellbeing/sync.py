"""The API between the HealthKit bridge (iPhone) and the backend: pairing, authentication and idempotent upserts of
daily summaries. The person is always the one the paired device belongs to - never a user id from the request body.

Only hashes of the pairing code and the device token are stored. Health values are never logged."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from app.loop.models import LoopState
from app.loop.store import next_id
from app.support import audit
from app.wellbeing import catalog
from app.wellbeing.analysis import data
from app.wellbeing.models import METRIC_IDS, DailyHealthMetrics, HealthDevice, PairingCode

INTEGER_METRICS = {'steps', 'sleepMinutes', 'activeEnergyKcal', 'workoutMinutes', 'workoutCount'}


class SyncError(ValueError):
    pass


class AuthError(PermissionError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode('utf-8')).hexdigest()


# --- pairing: the web app shows a short one-time code, the iPhone exchanges it for a device token ----------------------

def create_pairing_code(state: LoopState) -> dict[str, str]:
    minutes = catalog.config().get('pairing', {}).get('codeTtlMinutes', 10)
    code = f'{secrets.randbelow(1_000_000):06d}'
    created = datetime.now(timezone.utc).replace(microsecond=0)
    data(state).connection.pairing = PairingCode(codeHash=_hash(code), createdAt=created.isoformat(),
                                                 expiresAt=(created + timedelta(minutes=minutes)).isoformat())
    audit.record(state, stage='consent', actor='user', action='health_pairing',
                 detail=f'Apple Health -yhdistämiskoodi luotiin (voimassa {minutes} min). Koodi näytetään vain käyttäjälle.')
    return {'code': code, 'expiresAt': data(state).connection.pairing.expiresAt}


def pair_device(state: LoopState, code: str, device_name: str) -> dict[str, str]:
    """Exchange the one-time code for a device token. The token is returned once; only its hash is kept."""
    connection = data(state).connection
    pairing = connection.pairing
    if not pairing or datetime.fromisoformat(pairing.expiresAt) < datetime.now(timezone.utc):
        raise AuthError('Yhdistämiskoodi puuttuu tai on vanhentunut. Luo uusi koodi Hyvinvointidata-välilehdellä.')
    if not hmac.compare_digest(pairing.codeHash, _hash((code or '').strip())):
        raise AuthError('Yhdistämiskoodi ei kelpaa.')
    token = secrets.token_urlsafe(32)
    device = HealthDevice(id=next_id(state, 'device'), name=(device_name or 'iPhone').strip()[:60] or 'iPhone',
                          tokenHash=_hash(token), pairedAt=now_iso())
    connection.devices.append(device)
    connection.pairing = None
    connection.status, connection.source, connection.connectedAt = 'connected', 'apple_health', now_iso()
    connection.history.append({'date': state.currentDate, 'change': f'Apple Health yhdistettiin laitteesta {device.name}.'})
    audit.record(state, stage='consent', actor='user', action='health_connect',
                 detail=f'Apple Health yhdistettiin (laite {device.name}). Luku vain käyttäjän HealthKitissä sallimiin tietoihin.')
    return {'deviceId': device.id, 'deviceToken': token}


def authenticate(state: LoopState, authorization: Optional[str]) -> HealthDevice:
    """The device behind a 'Bearer <token>' header. The person is the one the device was paired for."""
    if not authorization or not authorization.lower().startswith('bearer '):
        raise AuthError('Laitteen tunniste puuttuu.')
    token_hash = _hash(authorization.split(' ', 1)[1].strip())
    for device in data(state).connection.devices:
        if not device.revoked and hmac.compare_digest(device.tokenHash, token_hash):
            return device
    raise AuthError('Laitteen tunniste ei kelpaa tai yhteys on katkaistu.')


# --- validation and idempotent upsert ------------------------------------------------------------------------------------

def _number(metric_id: str, value: Any, bounds: tuple[float, float]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SyncError(f'Arvo {metric_id} ei ole luku.')
    if not bounds[0] <= value <= bounds[1]:
        raise SyncError(f'Arvo {metric_id} on sallitun vaihteluvälin ulkopuolella.')
    return int(round(value)) if metric_id in INTEGER_METRICS else round(float(value), 1)


def validate_days(days: Any, today: Optional[str] = None) -> list[dict[str, Any]]:
    """Checks the dailyMetrics list: ISO dates (not in the future), numbers inside the catalog ranges, at most one entry
    per date and a bounded size. Unknown metrics are rejected, except the catalog's future metrics under `extra`."""
    if not isinstance(days, list) or not days:
        raise SyncError('dailyMetrics puuttuu tai on tyhjä.')
    limit = catalog.config().get('pairing', {}).get('maxDaysPerSync', 400)
    if len(days) > limit:
        raise SyncError(f'Yhdessä synkronoinnissa voi olla enintään {limit} päivää.')
    ranges = {m['id']: tuple(m.get('range', [0, 1e6])) for m in catalog.metrics()}
    ranges['workoutCount'] = (0, 50)
    future = {m['id'] for m in catalog.config().get('futureMetrics', [])}
    latest_allowed = (date.fromisoformat(today) if today else date.today()) + timedelta(days=1)
    cleaned, seen = [], set()
    for entry in days:
        if not isinstance(entry, dict):
            raise SyncError('Jokaisen päivän tulee olla objekti.')
        try:
            day = date.fromisoformat(str(entry.get('date')))
        except ValueError as exc:
            raise SyncError('Päivämäärän tulee olla muotoa VVVV-KK-PP.') from exc
        if day > latest_allowed:
            raise SyncError('Päivämäärä ei voi olla tulevaisuudessa.')
        if day.isoformat() in seen:
            raise SyncError(f'Päivä {day.isoformat()} on mukana kahdesti.')
        seen.add(day.isoformat())
        values: dict[str, Any] = {'date': day.isoformat()}
        for key, value in entry.items():
            if key == 'date':
                continue
            if key == 'extra':
                if not isinstance(value, dict) or not set(value) <= future:
                    raise SyncError('Tuntematon lisämittari.')
                values['extra'] = {k: float(v) for k, v in value.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
                continue
            if key not in ranges:
                raise SyncError(f'Tuntematon mittari: {key}.')
            values[key] = _number(key, value, ranges[key])
        cleaned.append(values)
    return cleaned


def upsert_days(state: LoopState, source: str, days: list[dict[str, Any]], device_id: Optional[str] = None,
                synced_at: Optional[str] = None) -> dict[str, Any]:
    """One row per (source, date): a re-sync updates the metrics it carries and keeps the others. Metrics the user has
    not permitted are dropped before storing (data minimization)."""
    store = data(state)
    permitted = {m for m, ok in store.connection.permissions.items() if ok}
    stamp = synced_at or now_iso()
    existing = {(r.source, r.date): r for r in store.dailyMetrics}
    created = updated = 0
    dropped: set[str] = set()
    for values in days:
        key = (source, values['date'])
        fields = {}
        for metric_id, value in values.items():
            if metric_id in ('date', 'extra'):
                continue
            base = 'workoutMinutes' if metric_id == 'workoutCount' else metric_id
            if base in METRIC_IDS and base not in permitted:
                dropped.add(base)
                continue
            fields[metric_id] = value
        record = existing.get(key)
        if record:
            for metric_id, value in fields.items():
                setattr(record, metric_id, value)
            if values.get('extra'):
                record.extra.update(values['extra'])
            record.syncedAt = record.updatedAt = stamp
            record.deviceId = device_id or record.deviceId
            updated += 1
        else:
            record = DailyHealthMetrics(date=values['date'], source=source, extra=values.get('extra', {}), deviceId=device_id,
                                        syncedAt=stamp, createdAt=stamp, updatedAt=stamp, **fields)
            store.dailyMetrics.append(record)
            existing[key] = record
            created += 1
    store.dailyMetrics.sort(key=lambda r: (r.source, r.date))
    store.connection.lastSyncAt = stamp
    return {'created': created, 'updated': updated, 'droppedMetrics': sorted(dropped)}


def sync_from_device(state: LoopState, device: HealthDevice, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get('source') != 'apple_health':
        raise SyncError('Lähteen tulee olla apple_health.')
    if data(state).connection.status != 'connected':
        raise AuthError('Apple Health -yhteys on katkaistu.')
    days = validate_days(payload.get('dailyMetrics'))
    result = upsert_days(state, 'apple_health', days, device_id=device.id)
    device.lastSyncAt = data(state).connection.lastSyncAt
    audit.record(state, stage='data', actor='system', action='health_sync',
                 detail=f"Apple Health -synkronointi laitteesta {device.name}: {len(days)} päivää "
                        f"({result['created']} uutta, {result['updated']} päivitettyä). Yksittäisiä mittauksia ei tallennettu.")
    return result
