"""API of Hyvinvointidata. The HealthKit bridge on the iPhone uses /pair and /sync with its own device token; the web
app uses the rest. Every mutation of the web app returns the full dashboard like the other APIs."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.loop.router import _dashboard
from app.loop.store import transaction
from app.wellbeing import observations, service, sync, view

router = APIRouter(prefix='/api/health', tags=['Hyvinvointidata'])
HANDLED = (service.ServiceError, sync.SyncError, observations.ObservationError)


class PairRequest(BaseModel):
    code: str
    deviceName: Optional[str] = None


class PermissionsRequest(BaseModel):
    permissions: dict[str, bool]


class MonitoringRequest(BaseModel):
    areas: dict[str, bool]


def _run(action) -> dict:
    with transaction() as state:
        try:
            result = action(state)
        except HANDLED as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {'result': result, 'dashboard': _dashboard(state)}


@router.get('/summary')
def summary(period: int = Query(30, ge=7, le=365)):
    with transaction() as state:
        return view.view(state, period)


# --- the HealthKit bridge (iPhone) ------------------------------------------------------------------------------------

@router.post('/pairing-code')
def pairing_code():
    """A one-time code the user types into the iPhone app. Shown once, stored only as a hash."""
    with transaction() as state:
        return sync.create_pairing_code(state)


@router.post('/devices/pair')
def pair(request: PairRequest):
    with transaction() as state:
        try:
            return sync.pair_device(state, request.code, request.deviceName or 'iPhone')
        except sync.AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post('/sync')
def sync_daily(payload: dict[str, Any], authorization: Optional[str] = Header(None)):
    """Daily summaries from the paired iPhone. The person is the one the device token belongs to; any user id in the
    body is ignored. Idempotent: the same source and date update the same row."""
    with transaction() as state:
        try:
            device = sync.authenticate(state, authorization)
            result = sync.sync_from_device(state, device, payload)
        except sync.AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except sync.SyncError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        created = observations.refresh(state)
        return {**result, 'lastSyncAt': state.support.wellbeing.connection.lastSyncAt, 'observations': len(created)}


# --- the web app -------------------------------------------------------------------------------------------------------

@router.post('/demo/synthetic')
def use_synthetic():
    if not settings.HEALTH_DEMO_MODE:
        raise HTTPException(status_code=403, detail='Synteettinen testidata on käytössä vain demo- ja kehitystilassa.')
    return _run(service.use_synthetic)


@router.post('/sync-now')
def sync_now():
    return _run(service.sync_now)


@router.put('/permissions')
def permissions(request: PermissionsRequest):
    return _run(lambda state: service.set_permissions(state, request.permissions))


@router.put('/monitoring')
def monitoring(request: MonitoringRequest):
    return _run(lambda state: service.set_monitoring(state, request.areas))


@router.post('/disconnect')
def disconnect():
    return _run(service.disconnect)


@router.delete('/data')
def delete_data():
    return _run(service.delete_data)


@router.post('/observations/{observation_id}/discuss')
def discuss(observation_id: str):
    return _run(lambda state: observations.discuss(state, observation_id).model_dump())


@router.post('/observations/{observation_id}/dismiss')
def dismiss(observation_id: str):
    return _run(lambda state: observations.dismiss(state, observation_id).model_dump())
