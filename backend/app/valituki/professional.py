"""Professional (care coordinator) actions and the smart waiting-list overview.

The professional reviews what Mieliluotsi surfaced and decides what happens. Clinical urgency on the waiting list is owned
by professionals: `set_clinical_urgency` refuses any non-professional actor, and no agent calls it. The queue is a work
queue (open review requests first, then waiting time) – it is not a clinical prioritisation by AI.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from app.valituki import adapters, content, handover, insights, journey, matching_flow, records, therapy, trends
from app.valituki.agents import base, checkin, orchestrator
from app.valituki.ai import AIProvider
from app.valituki.journey import ACTIVE_STATES, JourneyError
from app.valituki.labels import URGENCY, fmt_date, frequency_text
from app.valituki.models import ClientProfile, ProfessionalNote, ValitukiState
from app.valituki.store import NotFoundError, days_between, get_client, next_id, now

COORDINATOR_NAME = 'Hoitokoordinaattori Riikka (demo)'
ACTOR = records.COORDINATOR

REVIEW_ACTIONS = {
    'mark_reviewed': 'Tarkistettu – jatketaan Mieliluotsin tuella',
    'contact': 'Ammattilainen ottaa yhteyttä',
    'no_action': 'Tarkistettu – ei toimenpiteitä',
    'frequency': 'Check-in-tiheyttä muutettiin',
}


class ProfessionalError(ValueError):
    """The professional action is not possible (HTTP 409)."""


class PermissionDenied(PermissionError):
    """Only a professional may change clinical urgency (HTTP 403)."""


def set_clinical_urgency(state: ValitukiState, client: ClientProfile, urgency: str, actor: str, reason: str = '') -> None:
    if not records.is_professional(actor):
        raise PermissionDenied('Vain ammattilainen voi muuttaa hoidon kiireellisyyttä. Mieliluotsi ei muuta sitä.')
    if urgency not in URGENCY:
        raise ProfessionalError('Tuntematon kiireellisyys.')
    episode = adapters.waiting_list.episode_for(state, client.id)
    if episode is None:
        raise NotFoundError('Jonotietoa ei löytynyt.')
    stamp = now(state)
    episode.urgencyHistory.append({'at': stamp, 'from': episode.clinicalUrgency, 'to': urgency, 'by': COORDINATOR_NAME,
                                   'reason': reason.strip()[:300]})
    episode.clinicalUrgency = urgency  # type: ignore[assignment]
    episode.urgencySetBy = COORDINATOR_NAME
    episode.urgencySetAt = stamp
    episode.updatedAt = stamp
    records.audit(state, actor=actor, action='clinical_urgency', client_id=client.id,
                  detail=f'Ammattilainen asetti hoidon kiireellisyydeksi: {URGENCY[urgency]}'
                  + (f' – {reason.strip()}' if reason.strip() else ''))


def _complete_review(state: ValitukiState, client: ClientProfile, outcome: str, provider: Optional[AIProvider]) -> bool:
    if client.journeyState != 'HUMAN_REVIEW_NEEDED' or base.open_review_items(state, client.id):
        return False
    event = journey.apply(state, client, 'HUMAN_REVIEW_COMPLETED', actor=ACTOR, source='professional', payload={'outcome': outcome})
    orchestrator.dispatch(state, event, provider)
    return True


def review_observation(state: ValitukiState, observation_id: str, action: str, note: str = '', frequency: Optional[int] = None,
                       provider: Optional[AIProvider] = None) -> dict[str, Any]:
    if action not in REVIEW_ACTIONS:
        raise ProfessionalError('Tuntematon toimenpide.')
    observation = next((o for o in state.safetyObservations if o.id == observation_id), None) or next(
        (o for o in state.wellbeingObservations if o.id == observation_id), None)
    if observation is None:
        raise NotFoundError('Havaintoa ei löytynyt.')
    if observation.status in ('reviewed', 'closed'):
        raise ProfessionalError('Havainto on jo käsitelty.')
    client = get_client(state, observation.clientId)
    outcome = REVIEW_ACTIONS[action]
    if action == 'frequency':
        set_checkin_frequency(state, client, int(frequency or 3))
        outcome = f'Check-in-tiheydeksi muutettiin {frequency_text(client.checkInDays)}'
    if action == 'contact':
        records.notify(state, audience='client', client_id=client.id, kind='contact', action_view='messages',
                       title='Ammattilainen ottaa sinuun yhteyttä',
                       body='Hoitotiimi on tarkistanut tilanteesi ja ottaa yhteyttä. Voit jatkaa Mieliluotsin käyttöä normaalisti.')
    stamp = now(state)
    observation.status = 'reviewed' if action != 'no_action' else 'closed'
    observation.reviewedBy = COORDINATOR_NAME
    observation.reviewedAt = stamp
    observation.reviewOutcome = outcome
    observation.reviewNote = note.strip()[:600] or None
    observation.updatedAt = stamp
    if observation.taskId:
        task = next((t for t in state.tasks if t.id == observation.taskId), None)
        if task and task.status in ('open', 'contact_requested'):
            task.status = 'contact_requested' if action == 'contact' else 'completed'
            task.outcome = outcome
            task.completedBy = COORDINATOR_NAME
            task.completedAt = task.updatedAt = stamp
    records.audit(state, actor=ACTOR, action='observation_reviewed', client_id=client.id,
                  detail=f'{getattr(observation, "title", "Turvallisuushavainto")}: {outcome}'
                  + (f' – {note.strip()}' if note.strip() else ''))
    completed = _complete_review(state, client, outcome, provider)
    return {'reviewCompleted': completed, 'journeyState': client.journeyState, 'outcome': outcome}


def task_action(state: ValitukiState, task_id: str, action: str, note: str = '') -> dict[str, Any]:
    task = next((t for t in state.tasks if t.id == task_id), None)
    if task is None:
        raise NotFoundError('Tehtävää ei löytynyt.')
    client = get_client(state, task.clientId)
    note = note.strip()[:600]
    if action == 'contact':
        task.status = 'contact_requested'
        task.outcome = 'Yhteydenotto sovittu' + (f': {note}' if note else '')
        records.notify(state, audience='client', client_id=client.id, kind='contact', action_view='messages',
                       title='Ammattilainen ottaa sinuun yhteyttä',
                       body='Hoitotiimi ottaa yhteyttä. Voit jatkaa Mieliluotsin käyttöä normaalisti.')
    elif action == 'complete':
        task.status = 'completed'
        task.outcome = task.outcome or ('Käsitelty' + (f': {note}' if note else ''))
    elif action == 'close':
        task.status = 'closed'
        task.outcome = 'Suljettu' + (f': {note}' if note else '')
    else:
        raise ProfessionalError('Tuntematon toimenpide.')
    task.completedBy = COORDINATOR_NAME
    task.completedAt = task.updatedAt = now(state)
    if task.observationId:
        observation = next((o for o in state.wellbeingObservations if o.id == task.observationId), None)
        if observation and observation.status == 'open' and action in ('complete', 'close'):
            observation.status = 'reviewed'
            observation.reviewedBy, observation.reviewedAt, observation.reviewOutcome = COORDINATOR_NAME, task.completedAt, task.outcome
    records.audit(state, actor=ACTOR, action=f'task_{action}', client_id=client.id, detail=f'{task.title}: {task.outcome}')
    return {'status': task.status}


def set_checkin_frequency(state: ValitukiState, client: ClientProfile, per_week: int) -> None:
    client.checkInDays = therapy.days_for(per_week)
    client.nextCheckInDate = checkin.next_due_date(client, state.currentDate)
    records.act(state, agent='CheckInAgent', type='adjust_frequency', client_id=client.id, rule_id='PRO-FREQ-001',
                title=f'Ammattilainen muutti check-in-rytmin: {frequency_text(client.checkInDays)}',
                detail=f'Seuraava check-in {fmt_date(client.nextCheckInDate)}.')


def add_note(state: ValitukiState, client: ClientProfile, text: str, include_in_handover: bool = False) -> ProfessionalNote:
    text = text.strip()
    if not text:
        raise ProfessionalError('Kirjoita merkintä.')
    stamp = now(state)
    note = ProfessionalNote(id=next_id(state, 'note'), clientId=client.id, author=COORDINATOR_NAME, text=text[:1500],
                            includeInHandover=include_in_handover, createdAt=stamp, updatedAt=stamp, createdBy=ACTOR, source='professional')
    state.notes.append(note)
    records.audit(state, actor=ACTOR, action='note_added', client_id=client.id,
                  detail='Ammattilaisen merkintä' + (' (liitetään yhteenvetoon)' if include_in_handover else ''))
    return note


def run_matching(state: ValitukiState, client: ClientProfile, provider: Optional[AIProvider] = None):
    if not matching_flow.eligible_for_run(state, client):
        raise ProfessionalError('Matching voidaan ajaa vain asiakkaalle, jonka terapeutin etsintä on käynnissä ja joka on sallinut '
                                'tietojen käytön matchingissa.')
    return matching_flow.run(state, None, provider, client_ids=[client.id])


def ensure_active(state: ValitukiState, client_id: str) -> ClientProfile:
    client = get_client(state, client_id)
    if client.journeyState == 'SERVICE_ENDED':
        raise JourneyError('Asiakkaan palvelu on päättynyt.')
    return client


# --- the smart waiting list --------------------------------------------------------------------------------------------

def bucket(state: ValitukiState, client: ClientProfile) -> Optional[str]:
    """The overview bucket of an active waiting client (precedence: contact > change > missed > matching > stable)."""
    if client.journeyState not in journey.WAITING_STATES:
        return None
    open_tasks = [t for t in state.tasks if t.clientId == client.id and t.status in ('open', 'contact_requested')]
    if any(t.type == 'contact_request' for t in open_tasks):
        return 'contactRequested'
    if base.open_review_items(state, client.id):
        return 'changeDetected'
    if any(o.clientId == client.id and o.kind == 'missed_checkins' and o.status == 'open' for o in state.wellbeingObservations):
        return 'missedCheckIns'
    if journey.effective_state(client) in ('MATCHING_READY', 'MATCH_PROPOSED'):
        return 'matchingPossible'
    return 'stable'


BUCKET_LABELS = {
    'stable': 'Tilanne vakaa',
    'changeDetected': 'Merkittävä muutos havaittu',
    'contactRequested': 'Pyytänyt yhteydenottoa',
    'matchingPossible': 'Matching mahdollista',
    'missedCheckIns': 'Check-init jääneet tekemättä',
}


def overview(state: ValitukiState) -> dict[str, Any]:
    cohort = content.cohort()
    counts = dict(cohort['baseBuckets'])
    live = {key: 0 for key in counts}
    for client in state.clients:
        key = bucket(state, client)
        if key:
            counts[key] += 1
            live[key] += 1
    return {'total': sum(counts.values()), 'buckets': [{'key': k, 'label': BUCKET_LABELS[k], 'value': v, 'live': live[k]}
                                                        for k, v in counts.items()],
            'syntheticNote': 'Demon synteettisiä esimerkkilukuja.', 'liveClients': sum(live.values()),
            'note': cohort['note'], 'samples': _samples(state, cohort), 'samplesNote': cohort.get('samplesNote', '')}


def _samples(state: ValitukiState, cohort: dict[str, Any]) -> list[dict[str, Any]]:
    """A few made-up profiles per overview card: a filtered list shows what the group looks like, not only a number."""
    today = date.fromisoformat(state.currentDate[:10])
    return [{**{k: v for k, v in sample.items() if k != 'lastCheckInDaysAgo'},
             'lastCheckIn': (today - timedelta(days=int(sample['lastCheckInDaysAgo']))).isoformat(),
             'trendArrow': trends.DIRECTION_ARROWS[sample['trend']], 'trendLabel': trends.DIRECTION_LABELS[sample['trend']]}
            for sample in cohort.get('samples', [])]


def review_status(state: ValitukiState, client: ClientProfile) -> dict[str, str]:
    if any(o.clientId == client.id and o.status == 'open' and o.level >= 3 for o in state.safetyObservations):
        return {'key': 'safety', 'label': 'Turvallisuushälytys'}
    if base.open_review_items(state, client.id):
        return {'key': 'requested', 'label': 'Tarkistus pyydetty'}
    open_tasks = [t for t in state.tasks if t.clientId == client.id and t.status in ('open', 'contact_requested')]
    if any(t.type == 'contact_request' for t in open_tasks):
        return {'key': 'contact', 'label': 'Yhteydenottopyyntö'}
    if any(t.type == 'matching_review' for t in open_tasks):
        return {'key': 'matching_review', 'label': 'Matching review requested'}
    if any(t.type in ('engagement_check', 'matching_help') for t in open_tasks):
        return {'key': 'task', 'label': 'Avoin tehtävä'}
    reviewed = [o for o in state.wellbeingObservations + state.safetyObservations  # type: ignore[operator]
                if o.clientId == client.id and o.status in ('reviewed', 'closed')]
    if reviewed:
        return {'key': 'reviewed', 'label': 'Tarkistettu'}
    return {'key': 'none', 'label': '–'}


def matching_status(state: ValitukiState, client: ClientProfile) -> str:
    decision = matching_flow.current_decision(state, client.id)
    phase = journey.effective_state(client)
    if phase == 'THERAPY_ACTIVE':
        return 'Terapia käynnissä'
    if phase == 'MATCH_ACCEPTED':
        return 'Terapeutti valittu'
    if decision and decision.status == 'held_for_review':
        return 'Ehdotukset odottavat tarkistusta'
    if phase == 'MATCH_PROPOSED':
        return 'Ehdotukset asiakkaalla'
    if phase == 'MATCHING_READY':
        return 'Matching valmis – odottaa kapasiteettia'
    if client.journeyState in ('INVITED', 'INTAKE'):
        return 'Profiili puuttuu'
    return 'Profiili rakentuu'


def next_action(state: ValitukiState, client: ClientProfile) -> str:
    status = review_status(state, client)['key']
    if status in ('safety', 'requested'):
        return 'Tarkista'
    if status == 'contact':
        return 'Ota yhteyttä'
    if status == 'matching_review':
        return 'Keskustele matchingista'
    if status == 'task':
        return 'Kevyt yhteydenotto'
    if client.journeyState == 'INVITED':
        return 'Odottaa käyttöönottoa'
    if client.journeyState == 'MATCH_PROPOSED':
        return 'Odottaa asiakkaan valintaa'
    if client.journeyState == 'MATCH_ACCEPTED':
        booking = handover.active_booking(state, client.id)
        return f'1. tapaaminen {fmt_date(booking.start) if booking else ""}'
    return 'Ei toimenpiteitä'


def queue(state: ValitukiState) -> list[dict[str, Any]]:
    rows = []
    for client in state.clients:
        referral = adapters.waiting_list.referral_for(state, client.id)
        episode = adapters.waiting_list.episode_for(state, client.id)
        completed = [c for c in trends.completed_checkins(state, client.id) if c.kind != 'baseline']
        trend = trends.evaluate(state, client)
        observations = sorted([o for o in state.wellbeingObservations if o.clientId == client.id and o.kind != 'trend_improvement']
                              + [o for o in state.safetyObservations if o.clientId == client.id and o.level >= 2],  # type: ignore[operator]
                              key=lambda o: (o.createdAt, o.id))
        latest = observations[-1] if observations else None
        latest_text = None
        if latest is not None:
            latest_text = getattr(latest, 'title', None) or 'Turvallisuushavainto'
            if getattr(latest, 'level', 0) >= 3:
                latest_text = 'DEMO-HÄLYTYS: välittömät turvallisuusohjeet'
        review = review_status(state, client)
        rows.append({
            'clientId': client.id, 'name': client.displayName, 'firstName': client.firstName, 'persona': client.persona,
            'demoPrimary': client.demoPrimary, 'journeyState': client.journeyState, 'stateLabel': journey.label(client.journeyState),
            'waitingDays': days_between(referral.soughtHelpAt, state.currentDate) if referral else None,
            'lastCheckIn': (completed[-1].completedAt or '')[:10] if completed else None,
            'trend': trend.direction, 'trendArrow': trends.DIRECTION_ARROWS[trend.direction],
            'trendLabel': trends.DIRECTION_LABELS[trend.direction],
            'latestObservation': latest_text, 'latestObservationStatus': latest.status if latest else None,
            'reviewKey': review['key'], 'reviewLabel': review['label'], 'matchingStatus': matching_status(state, client),
            'nextAction': next_action(state, client), 'urgency': URGENCY[episode.clinicalUrgency] if episode else '–',
            'mode': client.mode, 'bucket': bucket(state, client),
        })
    order = {'safety': 0, 'requested': 1, 'contact': 2, 'matching_review': 3, 'task': 4, 'reviewed': 5, 'none': 6}
    return sorted(rows, key=lambda r: (order.get(r['reviewKey'], 9), -(r['waitingDays'] or 0), r['clientId']))


def insights_for_professional(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    approved = insights.for_client(state, client.id)
    visible = [i for i in approved if i.sharing.professional]
    return {'visible': [{'id': i.id, 'category': i.category, 'kind': i.kind, 'title': i.title, 'text': i.text, 'origin': i.origin,
                         'sourceLabel': i.sourceLabel, 'matching': i.sharing.matching, 'approvedAt': i.approvedAt} for i in visible],
            'hiddenCount': len(approved) - len(visible)}


def active_clients(state: ValitukiState) -> list[ClientProfile]:
    return [c for c in state.clients if c.journeyState in ACTIVE_STATES]
