"""Normalized daily health summaries (never raw HealthKit samples), the Apple Health connection and the observations
the agent derives from them.

One DailyHealthMetrics row per (source, date): a re-sync of the same day updates the row instead of adding a new one.
The fields are summaries of the day (sum, average or the latest value, see the metric catalog in policies.json:
wellbeingData.metrics); a metric the user has not shared, or that the device does not record, stays None.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

HealthSource = Literal['apple_health', 'synthetic_demo']
# the metrics of the first version; new ones (blood pressure, respiratory rate, blood oxygen, walking heart rate,
# glucose, body temperature, menstrual cycle) go to `extra` once they are added to the catalog
METRIC_IDS = ('steps', 'sleepMinutes', 'restingHeartRate', 'hrvMs', 'activeEnergyKcal', 'workoutMinutes', 'weightKg', 'vo2Max')


class DailyHealthMetrics(BaseModel):
    date: str
    source: HealthSource
    steps: Optional[int] = None
    sleepMinutes: Optional[int] = None
    restingHeartRate: Optional[float] = None
    hrvMs: Optional[float] = None
    activeEnergyKcal: Optional[int] = None
    workoutMinutes: Optional[int] = None
    workoutCount: Optional[int] = None
    weightKg: Optional[float] = None
    vo2Max: Optional[float] = None
    extra: dict[str, float] = {}
    deviceId: Optional[str] = None
    syncedAt: str  # when this row was last written by a synchronization
    createdAt: str
    updatedAt: str


class HealthDevice(BaseModel):
    """A paired iPhone (the HealthKit bridge). Only a hash of its token is stored."""
    id: str
    name: str
    tokenHash: str
    pairedAt: str
    lastSyncAt: Optional[str] = None
    revoked: bool = False


class PairingCode(BaseModel):
    codeHash: str
    createdAt: str
    expiresAt: str


class HealthConnection(BaseModel):
    status: Literal['not_connected', 'connected', 'disconnected'] = 'not_connected'
    source: Optional[HealthSource] = None
    connectedAt: Optional[str] = None
    lastSyncAt: Optional[str] = None
    # which metrics the user allows to be synchronized and used (explicit, per metric)
    permissions: dict[str, bool] = Field(default_factory=lambda: {metric: True for metric in METRIC_IDS})
    devices: list[HealthDevice] = []
    pairing: Optional[PairingCode] = None
    history: list[dict[str, Any]] = []  # connected / disconnected / data deleted, with dates (no health values)


class HealthObservation(BaseModel):
    """A meaningful change the rules found in the user's own data, tied to an active monitoring area. The texts keep
    data, interpretation and the next action apart and never name a disease."""
    id: str
    kind: Literal['change', 'positive']
    areaId: str
    areaLabel: str
    title: str
    summary: str
    areaNote: str
    signals: list[dict[str, Any]] = []  # {metric, label, unit, current, baseline, delta, relative, consecutiveDays, text}
    why: dict[str, Any] = {}  # "Miksi näen tämän?": reason, period, signal lines, rule
    priority: Literal['high', 'normal', 'low'] = 'normal'
    status: Literal['new', 'discussed', 'dismissed'] = 'new'
    createdAt: str
    periodEnd: str  # the last day of data the observation is based on
    messageId: Optional[str] = None  # the agent's proactive chat message, when one was sent
    followUpAt: Optional[str] = None  # agreed follow-up after a discussion
    outcome: Optional[str] = None  # what the discussion led to (self-monitoring, a step, a professional's assessment)


class WellbeingDataState(BaseModel):
    connection: HealthConnection = Field(default_factory=HealthConnection)
    dailyMetrics: list[DailyHealthMetrics] = []
    # user-selected wellbeing monitoring areas (the clinician-approved ones come from the active support plans)
    monitoringAreas: dict[str, bool] = {}
    observations: list[HealthObservation] = []
    activeObservationId: Optional[str] = None  # the observation the user is discussing with the agent now
