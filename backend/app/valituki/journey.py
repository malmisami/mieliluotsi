"""The client journey as an explicit, deterministic state machine.

A transition table maps (event, current state) to the next state. An event that is not allowed in the current state is
rejected, and every accepted event is stored as an `AgentEvent` with the state before and after it. State changes are
also written to the audit log. No language model takes part in any of this.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from app.valituki import records
from app.valituki.models import AgentEvent, ClientProfile, StateChange, ValitukiState
from app.valituki.store import next_id, next_seq, now

STATES: tuple[str, ...] = ('INVITED', 'INTAKE', 'WAITING_ACTIVE', 'HUMAN_REVIEW_NEEDED', 'MATCHING_READY', 'MATCH_PROPOSED',
                           'MATCH_ACCEPTED', 'THERAPY_ACTIVE', 'AFTERCARE', 'SERVICE_ENDED')

STATE_LABELS = {
    'INVITED': 'Jonossa – Mieliluotsi odottaa käyttöönottoa',
    'INTAKE': 'Alkukeskustelu kesken',
    'WAITING_ACTIVE': 'Jonossa – Mieliluotsi aktiivinen',
    'HUMAN_REVIEW_NEEDED': 'Odottaa ammattilaisen tarkistusta',
    'MATCHING_READY': 'Jonossa – terapeuttia etsitään',
    'MATCH_PROPOSED': 'Terapeuttiehdotukset valmiina',
    'MATCH_ACCEPTED': 'Terapeutti valittu – ensimmäinen tapaaminen tulossa',
    'THERAPY_ACTIVE': 'Terapia käynnissä – terapeutin ohjaama välituki',
    'AFTERCARE': 'Terapia päättynyt – seuranta jatkuu',
    'SERVICE_ENDED': 'Palvelu päättynyt',
}

EVENT_LABELS = {
    'CLIENT_ENROLLED': 'Asiakas liitettiin Mieliluotsiin',
    'INTAKE_STARTED': 'Alkukeskustelu alkoi',
    'INSIGHTS_APPROVED': 'Asiakas hyväksyi tulkinnat',
    'BASELINE_COMPLETED': 'Lähtötaso ja check-in-rytmi kirjattiin',
    'CONSENT_UPDATED': 'Suostumuksia muutettiin',
    'INSIGHT_PERMISSION_CHANGED': 'Tiedon käyttöoikeutta muutettiin',
    'CHECKIN_DUE': 'Check-in erääntyi',
    'CHECKIN_COMPLETED': 'Check-in tehtiin',
    'CHECKIN_MISSED': 'Check-in jäi tekemättä',
    'ACTIVITY_COMPLETED': 'Harjoitus tehtiin',
    'ACTIVITY_SKIPPED': 'Harjoitus ohitettiin',
    'WELLBEING_TREND_CHANGED': 'Merkittävä muutos omaan lähtötasoon',
    'PATTERN_DETECTED': 'Toistuva havainto tunnistettiin',
    'USER_REQUESTED_HUMAN': 'Asiakas pyysi yhteyttä ammattilaiseen',
    'SAFETY_SIGNAL': 'Turvallisuussignaali',
    'HUMAN_REVIEW_COMPLETED': 'Ammattilaisen tarkistus valmis',
    'MATCHING_READINESS_MET': 'Terapeutin etsintä voi alkaa',
    'THERAPIST_SLOT_OPENED': 'Terapeutilta vapautui aika',
    'MATCHES_GENERATED': 'Terapeuttiehdotukset muodostettiin',
    'MATCH_ALTERNATIVES_REQUESTED': 'Asiakas pyysi muita vaihtoehtoja',
    'MATCH_HELP_REQUESTED': 'Asiakas pyysi ammattilaista auttamaan valinnassa',
    'MATCH_SELECTED': 'Asiakas valitsi terapeutin',
    'FIRST_SESSION_BOOKED': 'Ensimmäinen tapaaminen varattiin',
    'HANDOVER_APPROVED': 'Asiakas hyväksyi yhteenvedon jaettavaksi',
    'HANDOVER_WITHDRAWN': 'Yhteenvedon jakaminen peruttiin',
    'THERAPY_STARTED': 'Terapia alkoi',
    'THERAPIST_PLAN_CONFIGURED': 'Terapeutti määritti välituen',
    'MATCH_FEEDBACK_RECEIVED': 'Yhteistyöpalaute saatiin',
    'THOUGHT_RECORD_COMPLETED': 'Ajatusten tutkiminen tehtiin',
    'EXPERIMENT_PLANNED': 'Käyttäytymiskoe suunniteltiin',
    'EXPERIMENT_REVIEWED': 'Käyttäytymiskokeen tulos kirjattiin',
    'EXPOSURE_LADDER_CREATED': 'Altistusporras koottiin',
    'EXPOSURE_STEP_COMPLETED': 'Altistusaskel tehtiin',
    'PRACTICE_TASK_COMPLETED': 'Sovittu harjoitus tehtiin',
    'THERAPY_ENDED': 'Terapia päättyi – seuranta alkoi',
    'SERVICE_ENDED': 'Palvelu päättyi',
}

# The client uses Mieliluotsi (check-ins run) in these states.
ACTIVE_STATES = ('WAITING_ACTIVE', 'HUMAN_REVIEW_NEEDED', 'MATCHING_READY', 'MATCH_PROPOSED', 'MATCH_ACCEPTED', 'THERAPY_ACTIVE',
                 'AFTERCARE')
# Waiting for therapy (the professional dashboard's "active waiting clients").
WAITING_STATES = ('WAITING_ACTIVE', 'HUMAN_REVIEW_NEEDED', 'MATCHING_READY', 'MATCH_PROPOSED', 'MATCH_ACCEPTED')
# States a review-requiring signal moves to HUMAN_REVIEW_NEEDED. In therapy the therapist is already involved: the
# signal still creates a task, but the journey state does not change. After therapy (AFTERCARE) a change goes back to
# the care team, who decide whether the client needs to return to care.
REVIEWABLE = ('WAITING_ACTIVE', 'MATCHING_READY', 'MATCH_PROPOSED', 'MATCH_ACCEPTED', 'AFTERCARE')
# Events of the client's own practice (CBT tools and agreed tasks). They never change the journey state.
PRACTICE_EVENTS = ('THOUGHT_RECORD_COMPLETED', 'EXPERIMENT_PLANNED', 'EXPERIMENT_REVIEWED', 'EXPOSURE_LADDER_CREATED',
                   'EXPOSURE_STEP_COMPLETED', 'PRACTICE_TASK_COMPLETED')
PRE_SERVICE = ('INVITED', 'INTAKE')
ALL_OPEN = PRE_SERVICE + ACTIVE_STATES

SAME = '='
RESUME = '@resume'


def _same(states: tuple[str, ...]) -> dict[str, str]:
    return {state: SAME for state in states}


TRANSITIONS: dict[str, dict[str, str]] = {
    'INTAKE_STARTED': {'INVITED': 'INTAKE'},
    'INSIGHTS_APPROVED': _same(('INTAKE',) + ACTIVE_STATES),
    'BASELINE_COMPLETED': {'INTAKE': 'WAITING_ACTIVE'},
    'CONSENT_UPDATED': _same(ALL_OPEN),
    'INSIGHT_PERMISSION_CHANGED': _same(ALL_OPEN),
    'CHECKIN_DUE': _same(ACTIVE_STATES),
    'CHECKIN_COMPLETED': _same(ACTIVE_STATES),
    'CHECKIN_MISSED': _same(ACTIVE_STATES),
    'ACTIVITY_COMPLETED': _same(ACTIVE_STATES),
    'ACTIVITY_SKIPPED': _same(ACTIVE_STATES),
    'WELLBEING_TREND_CHANGED': {**{s: 'HUMAN_REVIEW_NEEDED' for s in REVIEWABLE}, **_same(('HUMAN_REVIEW_NEEDED', 'THERAPY_ACTIVE'))},
    'PATTERN_DETECTED': _same(ACTIVE_STATES),
    'USER_REQUESTED_HUMAN': _same(ALL_OPEN),
    'SAFETY_SIGNAL': {**{s: 'HUMAN_REVIEW_NEEDED' for s in REVIEWABLE}, **_same(PRE_SERVICE + ('HUMAN_REVIEW_NEEDED', 'THERAPY_ACTIVE'))},
    'HUMAN_REVIEW_COMPLETED': {'HUMAN_REVIEW_NEEDED': RESUME},
    'MATCHING_READINESS_MET': {'WAITING_ACTIVE': 'MATCHING_READY'},
    'MATCHES_GENERATED': {'MATCHING_READY': 'MATCH_PROPOSED', **_same(('MATCH_PROPOSED', 'HUMAN_REVIEW_NEEDED'))},
    'MATCH_ALTERNATIVES_REQUESTED': _same(('MATCH_PROPOSED',)),
    'MATCH_HELP_REQUESTED': _same(('MATCHING_READY', 'MATCH_PROPOSED')),
    'MATCH_SELECTED': {'MATCH_PROPOSED': 'MATCH_ACCEPTED'},
    'FIRST_SESSION_BOOKED': _same(('MATCH_ACCEPTED',)),
    'HANDOVER_APPROVED': _same(('MATCH_ACCEPTED', 'THERAPY_ACTIVE', 'HUMAN_REVIEW_NEEDED')),
    'HANDOVER_WITHDRAWN': _same(ACTIVE_STATES),
    'THERAPY_STARTED': {'MATCH_ACCEPTED': 'THERAPY_ACTIVE', 'HUMAN_REVIEW_NEEDED': SAME},
    'THERAPIST_PLAN_CONFIGURED': _same(('THERAPY_ACTIVE', 'HUMAN_REVIEW_NEEDED')),
    'MATCH_FEEDBACK_RECEIVED': _same(('THERAPY_ACTIVE', 'HUMAN_REVIEW_NEEDED')),
    **{event: _same(ACTIVE_STATES) for event in PRACTICE_EVENTS},
    'THERAPY_ENDED': {'THERAPY_ACTIVE': 'AFTERCARE', 'HUMAN_REVIEW_NEEDED': SAME},
    'SERVICE_ENDED': {s: 'SERVICE_ENDED' for s in ALL_OPEN},
}

# Events whose state change depends on the payload. A level-1 safety signal only schedules an extra check-in.
CONDITIONS: dict[str, Callable[[dict[str, Any]], bool]] = {
    'SAFETY_SIGNAL': lambda payload: int(payload.get('level', 0)) >= 2,
    'MATCHES_GENERATED': lambda payload: int(payload.get('candidates', 0)) > 0 and not payload.get('held'),
}

# Global events that are not tied to one client (e.g. therapist capacity changes).
GLOBAL_EVENTS = ('THERAPIST_SLOT_OPENED',)


class JourneyError(Exception):
    """An event that is not allowed in the client's current state (HTTP 409)."""


def label(state_name: Optional[str]) -> str:
    return STATE_LABELS.get(state_name or '', state_name or '–')


def allowed_events(state_name: str) -> list[str]:
    return sorted(event for event, table in TRANSITIONS.items() if state_name in table)


def is_allowed(client: ClientProfile, event_type: str) -> bool:
    return client.journeyState in TRANSITIONS.get(event_type, {})


def effective_state(client: ClientProfile) -> str:
    """The journey phase the client is in, looking through a pending professional review."""
    if client.journeyState == 'HUMAN_REVIEW_NEEDED' and client.resumeState:
        return client.resumeState
    return client.journeyState


def record_event(state: ValitukiState, event_type: str, *, actor: str, source: str,
                 payload: Optional[dict[str, Any]] = None, client_id: Optional[str] = None,
                 therapist_id: Optional[str] = None, before: Optional[str] = None,
                 after: Optional[str] = None, at: Optional[str] = None) -> AgentEvent:
    event = AgentEvent(id=next_id(state, 'evt'), seq=next_seq(state, 'event'), type=event_type, clientId=client_id,
                       therapistId=therapist_id, occurredAt=now(state, at), actor=actor, source=source,
                       payload=payload or {}, stateBefore=before, stateAfter=after)
    state.events.append(event)
    return event


def apply(state: ValitukiState, client: ClientProfile, event_type: str, *, actor: str, source: str,
          payload: Optional[dict[str, Any]] = None, therapist_id: Optional[str] = None,
          at: Optional[str] = None) -> AgentEvent:
    """Validate the event against the transition table, record it and change the client's state."""
    payload = payload or {}
    table = TRANSITIONS.get(event_type)
    before = client.journeyState
    if table is None or before not in table:
        raise JourneyError(f'Tapahtuma "{EVENT_LABELS.get(event_type, event_type)}" ei ole sallittu vaiheessa "{label(before)}".')
    target = table[before]
    if target == SAME or (event_type in CONDITIONS and not CONDITIONS[event_type](payload)):
        after = before
    elif target == RESUME:
        after = client.resumeState or 'WAITING_ACTIVE'
    else:
        after = target

    event = record_event(state, event_type, actor=actor, source=source, payload=payload, client_id=client.id,
                         therapist_id=therapist_id, before=before, after=after, at=at)
    if after != before:
        if after == 'HUMAN_REVIEW_NEEDED':
            client.resumeState = before
        elif before == 'HUMAN_REVIEW_NEEDED':
            client.resumeState = None
        client.journeyState = after  # type: ignore[assignment]
        client.updatedAt = event.occurredAt
        client.stateHistory.append(StateChange(at=event.occurredAt, fromState=before, toState=after, eventId=event.id,
                                               eventType=event_type))
        records.audit(state, actor=actor, action='journey_transition', client_id=client.id, event_id=event.id,
                      detail=f'{label(before)} → {label(after)} ({EVENT_LABELS.get(event_type, event_type)})',
                      data={'from': before, 'to': after, 'event': event_type})
    return event


def set_resume_state(client: ClientProfile, target: str) -> None:
    """While a professional review is pending, a later phase change is remembered and applied after the review."""
    if client.journeyState == 'HUMAN_REVIEW_NEEDED':
        client.resumeState = target


def enroll(state: ValitukiState, client: ClientProfile, *, actor: str, source: str) -> AgentEvent:
    """CLIENT_ENROLLED creates the journey in INVITED."""
    client.journeyState = 'INVITED'
    event = record_event(state, 'CLIENT_ENROLLED', actor=actor, source=source, client_id=client.id, before=None,
                         after='INVITED')
    client.stateHistory.append(StateChange(at=event.occurredAt, fromState=None, toState='INVITED', eventId=event.id,
                                           eventType='CLIENT_ENROLLED'))
    records.audit(state, actor=actor, action='journey_transition', client_id=client.id, event_id=event.id,
                  detail=f'– → {label("INVITED")} ({EVENT_LABELS["CLIENT_ENROLLED"]})',
                  data={'from': None, 'to': 'INVITED', 'event': 'CLIENT_ENROLLED'})
    return event
