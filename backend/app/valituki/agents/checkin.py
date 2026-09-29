"""CheckInAgent – scheduled check-ins and missing check-in follow-up.

A missed check-in is a reason to send a gentle reminder, never a clinical conclusion. Several consecutive missed
check-ins create a low-priority, non-clinical engagement task ("kevyt yhteydenotto").
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from app.valituki import content, journey, practice, records, therapy
from app.valituki.agents import base
from app.valituki.labels import allative, fmt_date, frequency_text
from app.valituki.models import AgentEvent, CheckIn, ClientProfile, ValitukiState, WellbeingObservation
from app.valituki.store import add_days, next_id, now

AGENT = 'CheckInAgent'
WEEKDAY_GENITIVE = ['maanantain', 'tiistain', 'keskiviikon', 'torstain', 'perjantain', 'lauantain', 'sunnuntain']


def _policy() -> dict:
    return content.rules()['checkins']


def next_due_date(client: ClientProfile, after: str) -> Optional[str]:
    if not client.checkInDays:
        return None
    day = date.fromisoformat(after[:10]) + timedelta(days=1)
    for _ in range(8):
        if day.weekday() in client.checkInDays:
            return day.isoformat()
        day += timedelta(days=1)
    return None


def schedule_extra(state: ValitukiState, client: ClientProfile, event: Optional[AgentEvent], rule_id: str, reason: str) -> bool:
    tomorrow = add_days(state.currentDate, 1)
    has_due = any(c.clientId == client.id and c.status == 'due' and c.dueDate >= state.currentDate for c in state.checkIns)
    if has_due or (client.nextCheckInDate and client.nextCheckInDate <= tomorrow):
        return False
    client.nextCheckInDate = tomorrow
    client.nextCheckInKind = 'extra'
    records.act(state, agent=AGENT, type='schedule_extra_checkin', event=event, client_id=client.id, rule_id=rule_id,
                title='Sopi lyhyen lisä-check-inin huomiselle', detail=reason)
    return True


# --- daily rules (run by the orchestrator's tick) ------------------------------------------------------------------------

def mark_missed(state: ValitukiState, client: ClientProfile, provider, at: str) -> None:
    from app.valituki.agents import orchestrator

    for checkin in [c for c in state.checkIns if c.clientId == client.id and c.status == 'due' and c.dueDate < state.currentDate]:
        practice.expire_checkin(state, client)
        checkin.status = 'missed'
        checkin.updatedAt = now(state, at)
        event = journey.apply(state, client, 'CHECKIN_MISSED', actor=records.agent_actor(AGENT), source='rule_based', at=at,
                              payload={'checkInId': checkin.id, 'dueDate': checkin.dueDate, 'kind': checkin.kind})
        orchestrator.dispatch(state, event, provider)


def create_due(state: ValitukiState, client: ClientProfile, provider, at: str) -> None:
    from app.valituki.agents import orchestrator

    if client.automationPaused or not client.consent.proactiveCheckins or not client.nextCheckInDate:
        return
    if client.nextCheckInDate > state.currentDate:
        return
    if any(c.clientId == client.id and c.status == 'due' for c in state.checkIns):
        return
    stamp = now(state, at)
    config = therapy.active_config(state, client.id) if client.mode == 'therapy_support' else None
    checkin = CheckIn(id=next_id(state, 'chk'), clientId=client.id, kind=client.nextCheckInKind, dueDate=state.currentDate,
                      status='due', mode=client.mode, trackLabel=config.track if config else None, createdAt=stamp,
                      updatedAt=stamp, createdBy=records.agent_actor(AGENT), source='rule_based')
    state.checkIns.append(checkin)
    client.nextCheckInDate = next_due_date(client, state.currentDate)
    client.nextCheckInKind = 'routine'
    event = journey.apply(state, client, 'CHECKIN_DUE', actor=records.agent_actor(AGENT), source='rule_based',
                          payload={'checkInId': checkin.id, 'kind': checkin.kind})
    orchestrator.dispatch(state, event, provider)


# --- event handlers ------------------------------------------------------------------------------------------------------

def on_baseline(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    client.nextCheckInDate = next_due_date(client, state.currentDate)
    client.nextCheckInKind = 'routine'
    records.act(state, agent=AGENT, type='create_plan', event=event, rule_id='PLAN-001',
                title='Mieliluotsi loi odotusajan tukisuunnitelman',
                detail=f'Check-in {frequency_text(client.checkInDays)}, ensimmäinen {fmt_date(client.nextCheckInDate)}. '
                       'Yksi hyväksytty harjoitus kerrallaan – minkä tahansa voi ohittaa.')


def on_due(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    checkin = next(c for c in state.checkIns if c.id == event.payload['checkInId'])
    extra = checkin.kind == 'extra'
    greeting = f'Hei {client.firstName}' if client.communicationStyle == 'brief' else f'Hei {client.firstName}, mukava kuulla sinusta'
    body = (f'{greeting}! Miten voit tänään? Check-in vie alle minuutin.' if not extra else
            f'{greeting}. Kysyn kuulumisia tavallista aiemmin, koska vointisi on ollut viime päivinä hieman tavanomaista '
            'matalampi. Check-in vie alle minuutin.')
    if checkin.trackLabel:
        body += f' Mukana on terapeuttisi pyytämä seurantakysymys: {checkin.trackLabel.lower()}.'
    records.notify(state, audience='client', client_id=client.id, kind='checkin', action_view='checkin', event=event, agent=AGENT,
                   title='Miten voit tänään?' if not extra else 'Lyhyt lisä-check-in', body=body)
    records.act(state, agent=AGENT, type='send_checkin', event=event, rule_id='CHK-DUE-001' if not extra else _policy()['extraRuleId'],
                title='Mieliluotsi lähetti check-inin' if not extra else 'Mieliluotsi lähetti lisä-check-inin', detail=body)
    open_in_chat(state, client, checkin, provider)


def open_in_chat(state: ValitukiState, client: ClientProfile, checkin: CheckIn, provider) -> None:
    """Wysa-style: the check-in starts as a conversation in the chat. An exercise in progress is never interrupted."""
    if base.safety_locked(client):
        return
    greeting = f'Hei {client.firstName}' if client.communicationStyle == 'brief' else f'Hei {client.firstName}, mukava kuulla sinusta'
    intro = (f'{greeting}! On lyhyen check-inin aika – se vie alle minuutin.' if checkin.kind != 'extra' else
             f'{greeting}. Kysyn kuulumisia tavallista aiemmin, koska vointisi on ollut viime päivinä hieman tavanomaista '
             'matalampi.')
    active = practice.active_session(state, client.id)
    if active is not None and active.tool != 'checkin':
        practice.offer(state, client, 'Check-in odottaa – teetkö sen, kun harjoitus on valmis?',
                       [('start:checkin', 'Tee check-in'), ('dismiss', 'Myöhemmin')], group='checkin_due')
        return
    practice.start(state, client, 'checkin', provider, records.agent_actor(AGENT), context={'checkInId': checkin.id},
                   started_from='agent', intro=intro)


def consecutive_missed(state: ValitukiState, client_id: str) -> int:
    streak = 0
    for checkin in sorted((c for c in state.checkIns if c.clientId == client_id and c.status != 'due'),
                          key=lambda c: (c.dueDate, c.completedAt or '', c.id), reverse=True):
        if checkin.status != 'missed':
            break
        streak += 1
    return streak


def on_missed(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    checkin = next(c for c in state.checkIns if c.id == event.payload['checkInId'])
    policy = _policy()
    day_name = WEEKDAY_GENITIVE[date.fromisoformat(checkin.dueDate).weekday()]
    records.act(state, agent=AGENT, type='notice_missing', event=event, rule_id=policy['reminderRuleId'],
                at=event.occurredAt[11:16], title='Mieliluotsi huomasi, että check-in puuttuu',
                detail=f'{day_name.capitalize()} {"lisä-" if checkin.kind == "extra" else ""}check-in jäi tekemättä. '
                       'Puuttuva check-in ei kerro voinnista, eikä sitä tulkita muutokseksi.')
    if client.automationPaused or not client.consent.proactiveCheckins:
        return
    body = 'Check-in jäi väliin – ei haittaa. Voit tehdä sen silloin, kun sinulle sopii.'
    records.notify(state, audience='client', client_id=client.id, kind='checkin', action_view='checkin', event=event, agent=AGENT,
                   title='Pieni muistutus', body=body)
    checkin.reminderSentAt = now(state)
    records.act(state, agent=AGENT, type='send_reminder', event=event, rule_id=policy['reminderRuleId'],
                title=f'Lähetimme {allative(client.firstName)} muistutuksen', detail=body)

    streak = consecutive_missed(state, client.id)
    if streak >= int(policy['missedForEngagementReview']) and not any(
            o.clientId == client.id and o.kind == 'missed_checkins' and o.status == 'open' for o in state.wellbeingObservations):
        stamp = now(state)
        observation = WellbeingObservation(
            id=next_id(state, 'obs'), clientId=client.id, kind='missed_checkins', agent=AGENT, ruleId=policy['engagementRuleId'],
            title='Check-init jääneet toistuvasti väliin',
            reason=f'{streak} peräkkäistä check-iniä on jäänyt tekemättä. Tämä ei ole kliininen havainto eikä kerro voinnista.',
            clientText='Check-inejä on jäänyt väliin. Pyysin hoitotiimiä katsomaan, sopiiko rytmi sinulle.',
            explanation=[{'kind': 'missed', 'text': f'{streak} peräkkäistä check-iniä jäi tekemättä'}],
            underlyingData={'consecutiveMissed': streak}, requiresHumanReview=False,
            suggestedAction='Harkitse kevyttä yhteydenottoa ja kysy, sopiiko check-in-rytmi.', status='open', createdAt=stamp,
            updatedAt=stamp, createdBy=records.agent_actor(AGENT), source='rule_based')
        state.wellbeingObservations.append(observation)
        task = base.create_task(state, client, agent=AGENT, type='engagement_check', priority='low',
                                title='Kevyt yhteydenotto: check-init jääneet väliin', reason=observation.reason,
                                suggested=observation.suggestedAction, data=observation.underlyingData,
                                observation_id=observation.id)
        observation.taskId = task.id
        records.act(state, agent=AGENT, type='engagement_task', event=event, rule_id=policy['engagementRuleId'],
                    title='Pyysi hoitotiimiä tarkistamaan check-in-rytmin',
                    detail='Useampi check-in jäi peräkkäin väliin. Tämä ei tarkoita, että voinnissa olisi jotain huolestuttavaa.')


def on_therapy_ended(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    plan = next((p for p in reversed(state.aftercarePlans) if p.clientId == client.id and p.active), None)
    if plan is None:
        return
    client.checkInDays = list(plan.checkInDays)
    client.nextCheckInDate = next_due_date(client, state.currentDate)
    client.nextCheckInKind = 'routine'
    for due in [c for c in state.checkIns if c.clientId == client.id and c.status == 'due']:
        due.trackLabel = None
    records.act(state, agent=AGENT, type='reschedule', event=event, rule_id='AFTERCARE-CHK-001',
                title='Siirsi check-init seurantarytmiin',
                detail=f'Mieliala ja ahdistus {frequency_text(client.checkInDays)} – muutokset huomataan ajoissa.')


def on_plan_configured(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    config = therapy.active_config(state, client.id)
    if config is None:
        return
    client.checkInDays = list(config.checkInDays)
    client.nextCheckInDate = next_due_date(client, state.currentDate)
    client.nextCheckInKind = 'routine'
    for due in [c for c in state.checkIns if c.clientId == client.id and c.status == 'due']:
        due.trackLabel = config.track
    records.act(state, agent=AGENT, type='reschedule', event=event, rule_id='THERAPY-CHK-001',
                title='Päivitti check-in-rytmin terapeutin määrityksen mukaan',
                detail=f'Check-in {frequency_text(client.checkInDays)}. Mukana seurantakysymys: {config.track}.')
