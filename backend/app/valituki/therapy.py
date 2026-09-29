"""Therapy mode: after therapy starts, the therapist defines how Mieliluotsi may support the client between sessions.

Before therapy the agent runs under the approved waiting-list support protocol. After THERAPY_STARTED it switches to
"Terapian välituki" and may only operate inside the therapist's TherapistAgentConfiguration: the primary goal, the
allowed activities and guided CBT tools, a weekly between-session task ("välitehtävä"), the check-in frequency, the
tracked item and the topics it must not address. When therapy ends (THERAPY_ENDED) the therapist's maintenance plan
(AftercarePlan) takes over: mood and anxiety are followed weekly and a change goes back to the care team.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.valituki import content, insights, journey, records
from app.valituki.labels import WEEKDAYS_SHORT, frequency_text
from app.valituki.labels import fmt_date_long as labels_date
from app.valituki.models import AftercarePlan, ClientProfile, TherapistAgentConfiguration, TherapyEpisode, ValitukiState
from app.valituki.store import get_therapist, next_id, now

PROTOCOL_VERSION = 'Odotusajan tukiprotokolla demo-2 (hyväksytty 1.9.2026, placeholder)'
WAITING_CAPABILITIES = ['Check-init: mieliala ja ahdistus', 'Ohjatut KKT-harjoitukset chatissa', 'Hyväksytyt omahoitoharjoitukset',
                        'Palveluohjaus', 'Muutosten tunnistus', 'Matchingin valmistelu']
CBT_TOOLS = ('thought_record', 'experiment', 'exposure')
TOOL_TITLES = {'thought_record': 'Ajatusten tutkiminen', 'experiment': 'Käyttäytymiskoe', 'exposure': 'Altistusporras'}
BETWEEN_SESSION_PREFERENCE = ['act-values', 'act-activity-planning', 'act-small-next-step', 'act-sleep-reflection',
                              'act-paced-breathing', 'act-grounding', 'act-worry-time', 'act-support-network']


class TherapyError(ValueError):
    """The therapy-mode action is not possible (HTTP 409)."""


def episode(state: ValitukiState, client_id: str) -> Optional[TherapyEpisode]:
    items = [e for e in state.therapyEpisodes if e.clientId == client_id and e.status != 'ended']
    return items[-1] if items else None


def last_episode(state: ValitukiState, client_id: str) -> Optional[TherapyEpisode]:
    items = [e for e in state.therapyEpisodes if e.clientId == client_id]
    return items[-1] if items else None


def aftercare_plan(state: ValitukiState, client_id: str) -> Optional[AftercarePlan]:
    items = [p for p in state.aftercarePlans if p.clientId == client_id and p.active]
    return items[-1] if items else None


def active_config(state: ValitukiState, client_id: str) -> Optional[TherapistAgentConfiguration]:
    items = [c for c in state.therapistConfigs if c.clientId == client_id and c.active]
    return items[-1] if items else None


def days_for(per_week: int) -> list[int]:
    options = content.rules()['checkins']['frequencyOptions']
    if str(per_week) not in options:
        raise TherapyError('Check-in-tiheyden tulee olla 1, 2 tai 3 kertaa viikossa.')
    return list(options[str(per_week)])


def _goal_phrase(text: str) -> str:
    phrase = re.sub(r'^haluan\s+', '', text.strip().rstrip('.'), flags=re.IGNORECASE)
    phrase = re.sub(r'^pystyä hallitsemaan', 'hallita', phrase)
    phrase = re.sub(r'^pystyä käsittelemään', 'käsitellä', phrase)
    return phrase[:1].upper() + phrase[1:]


def suggested_plan(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    """A starting point for the therapist, built from the client's approved information only."""
    goals = insights.active_goals(state, client.id)
    rated = {}
    for completion in state.activityCompletions:
        if completion.clientId == client.id and completion.rating:
            rated[completion.activityId] = completion.rating
    helpful = [aid for aid, rating in sorted(rated.items()) if rating >= 4]
    low = {aid for aid, rating in rated.items() if rating <= 2}
    allowed = list(helpful)
    for activity_id in BETWEEN_SESSION_PREFERENCE:
        if len(allowed) >= 3:
            break
        if activity_id not in allowed and activity_id not in low:
            allowed.append(activity_id)
    pattern = next((i for i in insights.for_client(state, client.id, kind='pattern')), None)
    if pattern and 'anxiety' in pattern.structured.get('domains', []):
        track = 'Toimistopäiviin liittyvä ahdistus'
    elif goals:
        track = 'Vointi suhteessa päätavoitteeseen'
    else:
        track = 'Yleinen vointi'
    anxious = any({'anxiety', 'work_stress', 'panic'} & set(g.topics) for g in goals)
    used = [t for t in CBT_TOOLS if any(getattr(item, 'clientId', None) == client.id for item in
                                        {'thought_record': state.thoughtRecords, 'experiment': state.experiments,
                                         'exposure': state.ladders}[t])]
    tools = used or (list(CBT_TOOLS) if anxious else ['thought_record'])
    homework = 'thought_record' if 'thought_record' in tools else None
    note = ('Ennen palaveria: kirjaa tilanne, ajatus ja tunne 0–10 ja etsi tasapainoisempi ajatus. Tuo merkinnät tapaamiseen, '
            'jos haluat.' if anxious else 'Kirjaa yksi viikon tilanne: ajatus, tunne 0–10 ja tasapainoisempi ajatus.')
    return {'primaryGoal': _goal_phrase(goals[0].text) if goals else '', 'allowedActivityIds': allowed,
            'allowedTools': tools, 'homeworkTool': homework, 'homeworkNote': note if homework else '', 'checkInsPerWeek': 2,
            'track': track, 'doNotAddress': ''}


def configure(state: ValitukiState, client: ClientProfile, therapist_id: str, plan: dict[str, Any],
              actor: str) -> TherapistAgentConfiguration:
    current = episode(state, client.id)
    if current is None or current.therapistId != therapist_id:
        raise TherapyError('Vain asiakkaan oma terapeutti voi määrittää välituen.')
    if current.status != 'active':
        raise TherapyError('Mieliluotsin voi määrittää, kun ensimmäinen tapaaminen on pidetty.')
    library = {a.id for a in content.activities()}
    allowed = [a for a in plan.get('allowedActivityIds', []) if a in library]
    if len(allowed) != len(plan.get('allowedActivityIds', [])):
        raise TherapyError('Sallituiksi voi valita vain hyväksytyn kirjaston harjoituksia.')
    primary_goal = str(plan.get('primaryGoal', '')).strip()[:200]
    if not primary_goal:
        raise TherapyError('Kirjaa päätavoite.')
    tools = [t for t in plan.get('allowedTools') or [] if t in CBT_TOOLS]
    if len(tools) != len(plan.get('allowedTools') or []):
        raise TherapyError('Sallituiksi voi valita vain hyväksyttyjä KKT-työkaluja.')
    homework = plan.get('homeworkTool') or None
    if homework is not None and homework not in CBT_TOOLS:
        raise TherapyError('Välitehtäväksi voi valita vain hyväksytyn KKT-työkalun.')
    if homework and homework not in tools:
        tools.append(homework)  # a tool given as homework is always allowed
    per_week = int(plan.get('checkInsPerWeek', 2))
    check_days = days_for(per_week)
    stamp = now(state)
    previous = active_config(state, client.id)
    if previous:
        previous.active = False
        previous.updatedAt = stamp
    config = TherapistAgentConfiguration(
        id=next_id(state, 'tcfg'), clientId=client.id, therapistId=therapist_id, primaryGoal=primary_goal,
        allowedActivityIds=allowed, allowedTools=tools, homeworkTool=homework,
        homeworkNote=str(plan.get('homeworkNote') or '').strip()[:300] if homework else '', checkInsPerWeek=per_week,
        checkInDays=check_days,
        track=str(plan.get('track', '')).strip()[:120] or 'Yleinen vointi', doNotAddress=str(plan.get('doNotAddress', '')).strip()[:400],
        version=(previous.version + 1) if previous else 1, createdAt=stamp, updatedAt=stamp, createdBy=actor, source='therapist')
    state.therapistConfigs.append(config)
    current.configurationId = config.id
    current.updatedAt = stamp
    event = journey.apply(state, client, 'THERAPIST_PLAN_CONFIGURED', actor=actor, source='therapist',
                          therapist_id=therapist_id, payload={'configurationId': config.id, 'version': config.version})
    from app.valituki.agents import orchestrator  # local import: the agents import this module

    orchestrator.dispatch(state, event)
    return config


def suggested_aftercare(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    """A starting point for the maintenance plan, from the client's approved information and practice only."""
    config = active_config(state, client.id)
    tools = list(config.allowedTools) if config and config.allowedTools else list(CBT_TOOLS)
    helpful = sorted({content.activity(c.activityId).title for c in state.activityCompletions  # type: ignore[union-attr]
                      if c.clientId == client.id and (c.rating or 0) >= 4 and content.activity(c.activityId)})
    parts = []
    if any(r.clientId == client.id for r in state.thoughtRecords):
        parts.append('jatka ajatusten tutkimista, kun jännitys nousee')
    if any(lad.clientId == client.id for lad in state.ladders):
        parts.append('pidä yllä altistusportaan askeleita – välttäminen ruokkii jännitystä')
    if helpful:
        parts.append('hyödyksi koettu: ' + ', '.join(helpful).lower())
    maintenance = ('Terapiassa opittua: ' + '; '.join(parts) + '.') if parts else 'Jatka terapiassa opittuja keinoja omaan tahtiin.'
    return {'checkInsPerWeek': 1, 'allowedTools': tools, 'maintenance': maintenance,
            'warningSigns': 'Jos uni heikkenee ja välttelet taas palavereja useamman viikon ajan, ota yhteyttä hoitotiimiin.'}


def end_therapy(state: ValitukiState, client: ClientProfile, therapist_id: str, plan: dict[str, Any], actor: str) -> AftercarePlan:
    """THERAPY_ENDED: the episode ends and the maintenance plan starts ("Seuranta terapian jälkeen")."""
    current = episode(state, client.id)
    if current is None or current.therapistId != therapist_id:
        raise TherapyError('Vain asiakkaan oma terapeutti voi päättää terapian.')
    if current.status != 'active':
        raise TherapyError('Terapia ei ole käynnissä.')
    per_week = int(plan.get('checkInsPerWeek', 1))
    check_days = days_for(per_week)
    tools = [t for t in plan.get('allowedTools') or [] if t in CBT_TOOLS]
    stamp = now(state)
    current.status = 'ended'
    current.endedAt = stamp
    current.updatedAt = stamp
    config = active_config(state, client.id)
    if config:
        config.active = False
        config.updatedAt = stamp
    for previous in [p for p in state.aftercarePlans if p.clientId == client.id and p.active]:
        previous.active = False
    for task in [t for t in state.practiceTasks if t.clientId == client.id and t.kind == 'homework' and t.status == 'open']:
        task.status = 'skipped'
    record = AftercarePlan(id=next_id(state, 'afc'), clientId=client.id, therapistId=therapist_id, checkInsPerWeek=per_week,
                           checkInDays=check_days, allowedTools=tools, maintenance=str(plan.get('maintenance') or '').strip()[:600],
                           warningSigns=str(plan.get('warningSigns') or '').strip()[:300], createdAt=stamp, updatedAt=stamp,
                           createdBy=actor, source='therapist')
    state.aftercarePlans.append(record)
    event = journey.apply(state, client, 'THERAPY_ENDED', actor=actor, source='therapist', therapist_id=therapist_id,
                          payload={'aftercarePlanId': record.id, 'sessions': current.sessionsHeld})
    from app.valituki.agents import orchestrator  # local import: the agents import this module

    orchestrator.dispatch(state, event)
    return record


def mode_summary(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    if client.mode == 'aftercare_support':
        plan = aftercare_plan(state, client.id)
        last = last_episode(state, client.id)
        therapist = get_therapist(state, plan.therapistId) if plan else None
        first_name = therapist.name.split()[0] if therapist else 'Terapeutti'
        return {'mode': 'aftercare_support', 'title': 'Seuranta terapian jälkeen', 'configured': True,
                'controlledBy': f'Ylläpitosuunnitelma (terapeutti {therapist.name if therapist else ""})'.strip(),
                'therapistName': therapist.name if therapist else None, 'therapistFirstName': first_name,
                'statement': f'Terapia päättyi {labels_date(last.endedAt) if last and last.endedAt else ""}. Mieliluotsi seuraa '
                             'mielialaa ja ahdistusta, ja muutoksesta hoitotiimi saa tiedon.',
                'checkIns': frequency_text(client.checkInDays), 'maintenance': plan.maintenance if plan else '',
                'warningSigns': plan.warningSigns if plan else '',
                'allowedTools': [{'id': t, 'title': TOOL_TITLES[t]} for t in (plan.allowedTools if plan else [])],
                'capabilities': [f'Mieliala ja ahdistus {frequency_text(client.checkInDays)}', 'Omat KKT-harjoitukset',
                                 'Ylläpitosuunnitelma', 'Hoitotiimi saa tiedon, jos vointi laskee', 'Turvallisuusohjeet']}
    if client.mode != 'therapy_support':
        return {'mode': 'waiting_support', 'title': 'Mieliluotsi', 'controlledBy': 'Hyväksytty odotusajan tukiprotokolla',
                'protocol': PROTOCOL_VERSION, 'capabilities': WAITING_CAPABILITIES, 'configured': True,
                'checkIns': frequency_text(client.checkInDays)}
    config = active_config(state, client.id)
    current = episode(state, client.id)
    therapist = get_therapist(state, current.therapistId) if current else None
    first_name = therapist.name.split()[0] if therapist else 'Terapeutti'
    base = {'mode': 'therapy_support', 'title': 'Terapian välituki',
            'therapistName': therapist.name if therapist else None, 'therapistFirstName': first_name}
    if config is None:
        return {**base, 'configured': False, 'controlledBy': f'Terapeutti {therapist.name if therapist else ""}'.strip(),
                'statement': f'Terapeutti {first_name} määrittää, miten Mieliluotsi tukee sinua tapaamisten välillä. Siihen asti '
                             'Mieliluotsi jatkaa vain check-inejä ja turvallisuusohjeita.',
                'checkIns': frequency_text(client.checkInDays), 'capabilities': ['Check-init', 'Turvallisuusohjeet']}
    activities = [a for a in content.activities() if a.id in config.allowedActivityIds]
    return {**base, 'configured': True, 'controlledBy': f'Terapeutti {therapist.name if therapist else ""}'.strip(),
            'statement': f'Terapeutti {first_name} on määrittänyt tämän suunnitelman.',
            'configuredAt': config.createdAt, 'version': config.version, 'primaryGoal': config.primaryGoal,
            'allowedActivities': [{'id': a.id, 'title': a.title} for a in activities], 'checkInsPerWeek': config.checkInsPerWeek,
            'allowedTools': [{'id': t, 'title': TOOL_TITLES[t]} for t in config.allowedTools],
            'homework': {'tool': config.homeworkTool, 'title': TOOL_TITLES[config.homeworkTool], 'note': config.homeworkNote}
            if config.homeworkTool else None,
            'checkIns': frequency_text(config.checkInDays), 'checkInDays': [WEEKDAYS_SHORT[d] for d in config.checkInDays],
            'track': config.track, 'doNotAddress': config.doNotAddress,
            'capabilities': ['Check-init terapeutin rytmissä', 'Vain terapeutin sallimat harjoitukset ja KKT-työkalut',
                             f'Seuranta: {config.track}', 'Turvallisuusohjeet']}


def start_episode(state: ValitukiState, client: ClientProfile, booking) -> TherapyEpisode:
    stamp = now(state)
    item = TherapyEpisode(id=next_id(state, 'thep'), clientId=client.id, therapistId=booking.therapistId, bookingId=booking.id,
                          status='planned', firstSessionAt=booking.start, createdAt=stamp, updatedAt=stamp,
                          createdBy=records.agent_actor('NavigationAgent'), source='appointment_adapter')
    state.therapyEpisodes.append(item)
    return item
