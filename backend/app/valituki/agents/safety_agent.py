"""SafetyAgent – deterministic safety triggers. It runs before every other agent and can interrupt the normal flow.

Level 3 shows the immediate safety information, pauses normal support until the client acknowledges it and creates a
synthetic professional alert. Level 2 asks a professional to review, level 1 schedules an additional check-in. The agent
never claims that emergency services were contacted.
"""
from __future__ import annotations

from typing import Optional

from app.valituki import journey, records
from app.valituki.agents import base
from app.valituki.models import AgentEvent, ClientProfile, SafetyLock, SafetyObservation, ValitukiState
from app.valituki.safety import LEVEL2_CLIENT_TEXT, LEVEL_LABELS, SafetyResult
from app.valituki.store import next_id, now

AGENT = 'SafetyAgent'


def raise_safety(state: ValitukiState, client: ClientProfile, result: SafetyResult, *, context: str,
                 actor: str) -> Optional[SafetyObservation]:
    """Record a safety observation for a non-zero combined level and emit SAFETY_SIGNAL."""
    level = result.final_level
    if level == 0:
        return None
    stamp = now(state)
    existing = next((o for o in state.safetyObservations if o.clientId == client.id and o.status == 'open'
                     and o.level >= level and o.createdAt[:10] == state.currentDate), None)
    if existing:
        existing.triggers.extend(result.triggers)
        existing.updatedAt = stamp
        observation, is_new = existing, False
    else:
        required = {3: 'Tarkista tilanne heti sovitun prosessin mukaisesti ja kirjaa tehdyt toimet.',
                    2: 'Tarkista havainto ja päätä yhteydenotosta.',
                    1: 'Ei vaadi toimenpiteitä; lisä-check-in on suunniteltu.'}[level]
        observation = SafetyObservation(
            id=next_id(state, 'saf'), clientId=client.id, level=level, deterministicLevel=result.deterministic_level,
            aiHint=result.ai_hint, aiLevel=result.ai_level, triggers=result.triggers, context=context, requiredHumanAction=required,
            status='open' if level >= 2 else 'info', createdAt=stamp, updatedAt=stamp, createdBy=actor,
            source='ai_hint' if result.deterministic_level < level else 'rule_based')
        state.safetyObservations.append(observation)
        is_new = True
    if level >= 3:
        from app.valituki import practice

        session = practice.active_session(state, client.id)
        if session:  # the person needs help now – the exercise does not continue on its own
            session.status = 'stopped'
            session.answers = {}
            session.endedAt = stamp
    event = journey.apply(state, client, 'SAFETY_SIGNAL', actor=actor, source='safety_engine',
                          payload={'level': level, 'observationId': observation.id, 'context': context, 'new': is_new,
                                   'deterministicLevel': result.deterministic_level, 'aiLevel': result.ai_level,
                                   'rules': sorted({t.ruleId for t in result.triggers})})
    from app.valituki.agents import orchestrator

    orchestrator.dispatch(state, event)
    return observation


def on_safety_signal(state: ValitukiState, event: AgentEvent, provider) -> None:
    client = next(c for c in state.clients if c.id == event.clientId)
    level = int(event.payload['level'])
    observation = next(o for o in state.safetyObservations if o.id == event.payload['observationId'])
    rules = ', '.join(event.payload.get('rules', []))
    is_new = bool(event.payload.get('new'))
    if level >= 2 and is_new:
        task = base.create_task(
            state, client, agent=AGENT, type='safety_review', priority='urgent' if level == 3 else 'high',
            title='Turvallisuushavainto odottaa tarkistusta' if level == 2 else 'DEMO-HÄLYTYS: välittömät turvallisuusohjeet näytetty',
            reason=f'{LEVEL_LABELS[level]}. Laukaisijat: {", ".join(sorted({t.category for t in observation.triggers}))}.',
            suggested=observation.requiredHumanAction, observation_id=observation.id,
            data={'level': level, 'rules': rules, 'context': event.payload.get('context')},
            handling_note=base.CONTACT_HANDLING if level == 2 else '')
        observation.taskId = task.id
    if level == 3:
        client.safetyLock = SafetyLock(observationId=observation.id, activatedAt=event.occurredAt)
        client.todayActivity = None
        records.notify(state, audience='coordinator', client_id=client.id, kind='safety', event=event, agent=AGENT,
                       title=f'DEMO-HÄLYTYS: {client.displayName} – välittömät turvallisuusohjeet näytetty',
                       body='Asiakkaalle näytettiin 112-, 116117- ja MIELI Kriisipuhelin -ohjeet. Mieliluotsi ei ole ottanut yhteyttä '
                            'hätäpalveluihin. Tarkista tilanne sovitun prosessin mukaisesti.')
        records.act(state, agent=AGENT, type='safety_interrupt', event=event, rule_id=rules,
                    title='Keskeytti tavallisen tuen ja näytti turvallisuusohjeet',
                    detail='Näytettiin: välitön hätätilanne 112, Päivystysapu 116117 ja MIELI Kriisipuhelin 09 2525 0111. '
                           'Ammattilaisen työjonoon syntyi synteettinen hälytys. Mieliluotsi ei ole ottanut yhteyttä hätäpalveluihin.')
    elif level == 2 and is_new:
        records.notify(state, audience='coordinator', client_id=client.id, kind='review', event=event, agent=AGENT,
                       title=f'Tarkistus pyydetty: {client.displayName}', body=f'Turvallisuushavainto (taso 2). Säännöt: {rules}.')
        records.notify(state, audience='client', client_id=client.id, kind='review', event=event, agent=AGENT, action_view='today',
                       title='Pyysin ammattilaista katsomaan tilannettasi', body=LEVEL2_CLIENT_TEXT)
        records.act(state, agent=AGENT, type='request_human_review', event=event, rule_id=rules,
                    title='Pyysi ammattilaista tarkistamaan tilanteen',
                    detail='Tämä havainto odottaa ammattilaisen tarkistusta. Mieliluotsi ei ole muuttanut hoitosi kiireellisyyttä.')
    elif level == 1:
        from app.valituki.agents import checkin

        checkin.schedule_extra(state, client, event, rules or 'SAF-L1',
                               'Vastauksessa oli merkkejä kuormituksesta, joten kuulumisia kysytään uudelleen jo huomenna.')
