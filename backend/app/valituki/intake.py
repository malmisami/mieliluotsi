"""Conversational intake: "Kerro omin sanoin, miksi hait apua."

Flow: service consents → the client's own words → up to six focused follow-up questions (one at a time) → "Ymmärsinkö
tilanteesi oikein?" proposal cards → explicit approval (or editing) → check-in rhythm and today's wellbeing (the baseline)
→ BASELINE_COMPLETED. AI interpretations stay proposals (IntakeProposal) until the client approves them; nothing is
stored as an insight or used in matching before that. Every free-text answer passes the Safety Engine first.
"""
from __future__ import annotations

from typing import Any, Optional

from app.valituki import fit_profile, insights, interpret, journey, records
from app.valituki.agents import orchestrator, safety_agent
from app.valituki.ai import AIProvider, DemoAIProvider
from app.valituki.labels import fmt_date
from app.valituki.models import (
    CheckIn,
    ClientProfile,
    ConsentRecord,
    ConsentScope,
    IntakeMessage,
    IntakeProposal,
    IntakeSession,
    ValitukiState,
)
from app.valituki.safety import SAFETY_REPLY, assess, evaluate_structured, evaluate_text
from app.valituki.store import next_id, now

CARD_TO_INSIGHT = {
    'working_style': ('therapist_wish', 'working_style', 'Työskentelytapa'),
    'practical': ('preference', 'practical', 'Käytännön toiveet'),
    'difficult_times': ('challenge', 'difficult_times', 'Vaikeimmat hetket'),
    'helped_before': ('helpful', 'helped_before', 'Aiemmin auttanut'),
}


class IntakeError(ValueError):
    """The intake action is not possible (HTTP 409)."""


def session_for(state: ValitukiState, client: ClientProfile) -> Optional[IntakeSession]:
    return next((s for s in state.intakes if s.id == client.intakeId), None)


def _require(state: ValitukiState, client: ClientProfile, *statuses: str) -> IntakeSession:
    session = session_for(state, client)
    if session is None or session.status not in statuses:
        raise IntakeError('Alkukeskustelu ei ole tässä vaiheessa.')
    return session


def _say(state: ValitukiState, session: IntakeSession, text: str, *, key: Optional[str] = None, source: str = 'demo',
         at: Optional[str] = None) -> None:
    session.messages.append(IntakeMessage(id=next_id(state, 'im'), role='assistant', text=text, questionKey=key,
                                          createdAt=now(state, at), source=source))


def record_consent(state: ValitukiState, client: ClientProfile, scope: dict[str, Any], actor: str) -> ConsentScope:
    new_scope = ConsentScope(**{**client.consent.model_dump(), **{k: bool(v) for k, v in scope.items() if k in ConsentScope.model_fields}})
    changed = {k: v for k, v in new_scope.model_dump().items() if getattr(client.consent, k) != v}
    stamp = now(state)
    version = sum(1 for r in state.consentRecords if r.clientId == client.id) + 1
    state.consentRecords.append(ConsentRecord(id=next_id(state, 'cons'), clientId=client.id, scope=new_scope,
                                              changed=changed or new_scope.model_dump(), version=version, createdAt=stamp,
                                              updatedAt=stamp, createdBy=actor, source='client'))
    client.consent = new_scope
    client.consentGivenAt = client.consentGivenAt or stamp
    return new_scope


def start(state: ValitukiState, client: ClientProfile, consent: dict[str, Any], actor: str, at: Optional[str] = None) -> IntakeSession:
    if client.journeyState != 'INVITED':
        raise IntakeError('Alkukeskustelu on jo aloitettu.')
    record_consent(state, client, consent, actor)
    journey.apply(state, client, 'INTAKE_STARTED', actor=actor, source='client', payload={'consent': client.consent.model_dump()}, at=at)
    stamp = now(state)
    session = IntakeSession(id=next_id(state, 'intake'), clientId=client.id, status='conversation',
                            pendingQuestionKey=interpret.OPENING_KEY, createdAt=stamp, updatedAt=stamp, createdBy=actor,
                            source='client')
    state.intakes.append(session)
    client.intakeId = session.id
    _say(state, session, f'Hei {client.firstName}! Olen Mieliluotsi – digitaalinen tuki terapiaa odottaessa. En ole terapeutti enkä '
                         'päivystyspalvelu, mutta kuljen rinnallasi odotuksen ajan ja kokoan kanssasi tiedot, joista on hyötyä, kun '
                         'terapia alkaa. Voit ohittaa minkä tahansa kysymyksen.', source='fixed')
    _say(state, session, interpret.OPENING_QUESTION, key=interpret.OPENING_KEY, source='fixed')
    return session


def _safety_first(state: ValitukiState, client: ClientProfile, session: IntakeSession, text: str, actor: str) -> Optional[dict[str, Any]]:
    result = assess(evaluate_text(text))
    if result.final_level >= 3:
        safety_agent.raise_safety(state, client, result, context='intake', actor=actor)
        _say(state, session, SAFETY_REPLY, source='fixed')
        return {'safety': {'level': 3}}
    if result.final_level >= 1:
        safety_agent.raise_safety(state, client, result, context='intake', actor=actor)
    return None


def answer(state: ValitukiState, client: ClientProfile, text: str, provider: AIProvider, actor: str,
           at: Optional[str] = None) -> dict[str, Any]:
    session = _require(state, client, 'conversation')
    text = text.strip()[:1500]
    if not text:
        raise IntakeError('Kirjoita vastaus tai ohita kysymys.')
    key = session.pendingQuestionKey or interpret.OPENING_KEY
    session.messages.append(IntakeMessage(id=next_id(state, 'im'), role='client', text=text, questionKey=key, createdAt=now(state, at)))
    session.answers[key] = text
    session.askedKeys.append(key)
    session.updatedAt = now(state)
    interrupted = _safety_first(state, client, session, text, actor)
    if interrupted:
        return interrupted
    return _advance(state, client, session, provider, key, text)


def skip(state: ValitukiState, client: ClientProfile, provider: AIProvider, actor: str) -> dict[str, Any]:
    session = _require(state, client, 'conversation')
    key = session.pendingQuestionKey
    if key == interpret.OPENING_KEY:
        raise IntakeError('Kerro lyhyesti omin sanoin, miksi hait apua – loput kysymykset voi ohittaa.')
    if key:
        session.askedKeys.append(key)
        session.skippedKeys.append(key)
    return _advance(state, client, session, provider, key, '')


def _advance(state: ValitukiState, client: ClientProfile, session: IntakeSession, provider: AIProvider, previous: Optional[str],
             previous_answer: str) -> dict[str, Any]:
    next_key = interpret.next_question_key(session.askedKeys)
    if next_key is None:
        return summarise(state, client, session, provider)
    remaining = [k for k in interpret.PLAN if k not in session.askedKeys]
    question = provider.generate_intake_follow_up({'firstName': client.firstName, 'answers': session.answers, 'nextKey': next_key,
                                                   'remainingKeys': remaining, 'previousKey': previous, 'previousAnswer': previous_answer})
    if question.safetyHint != 'NONE':
        result = assess([], ai_hint=question.safetyHint)
        if result.final_level >= 2:
            safety_agent.raise_safety(state, client, result, context='intake', actor=records.agent_actor('SupportAgent'))
    if question.acknowledgement:
        _say(state, session, question.acknowledgement, source=question.source)
    _say(state, session, question.question, key=question.questionKey, source=question.source)
    session.pendingQuestionKey = question.questionKey
    return {'nextQuestion': question.questionKey, 'source': question.source}


def finish(state: ValitukiState, client: ClientProfile, provider: AIProvider) -> dict[str, Any]:
    session = _require(state, client, 'conversation')
    if len([k for k in session.answers if session.answers[k]]) < interpret.MIN_ANSWERS_TO_FINISH:
        raise IntakeError('Vastaa vielä ainakin yhteen kysymykseen, jotta voin koota tulkinnat.')
    return summarise(state, client, session, provider)


def summarise(state: ValitukiState, client: ClientProfile, session: IntakeSession, provider: AIProvider) -> dict[str, Any]:
    summary = provider.summarise_client_statement({'answers': session.answers, 'municipality': client.municipality,
                                                   'firstName': client.firstName})
    if summary.safetyHint != 'NONE':
        result = assess([], ai_hint=summary.safetyHint)
        if result.final_level >= 2:
            safety_agent.raise_safety(state, client, result, context='intake', actor=records.agent_actor('SupportAgent'))
    session.proposals = [IntakeProposal(id=next_id(state, 'prop'), source=summary.source, **proposal) for proposal in summary.proposals]
    session.proposalsSource = summary.source
    session.proposedAt = now(state)
    session.status = 'review'
    session.pendingQuestionKey = None
    _say(state, session, 'Kiitos, että kerroit. Kokosin kertomasi pohjalta muutaman tulkinnan. Ne ovat vasta ehdotuksia – '
                         'tallennan ne vain, jos ne kuvaavat tilannettasi.', source=summary.source)
    records.act(state, agent='SupportAgent', type='summarise_intake', client_id=client.id, rule_id='INTAKE-001',
                title='Kokosi alkukeskustelusta tulkinnat tarkistettaviksi',
                detail=f'{len(session.proposals)} ehdotusta: tavoite, työskentelytapa ja käytännön toiveet. Mitään ei tallenneta '
                       'ennen hyväksyntää.', ai_task='summariseClientStatement', ai_source=summary.source)
    return {'proposals': len(session.proposals), 'source': summary.source}


def update_proposal(state: ValitukiState, client: ClientProfile, proposal_id: str, changes: dict[str, Any]) -> IntakeProposal:
    session = _require(state, client, 'review')
    proposal = next((p for p in session.proposals if p.id == proposal_id), None)
    if proposal is None:
        raise IntakeError('Ehdotusta ei löytynyt.')
    if 'included' in changes:
        proposal.included = bool(changes['included'])
    if 'text' in changes and str(changes['text']).strip():
        proposal.text = str(changes['text']).strip()[:400]
        proposal.editedByClient = True
        if proposal.category == 'goal':
            proposal.structured = {**proposal.structured, 'primary': {**proposal.structured.get('primary', {}), 'text': proposal.text}}
    if isinstance(changes.get('structured'), dict):
        allowed = {'goal': {'secondary'}, 'working_style': {'structure', 'exercises', 'approach', 'homework'},
                   'practical': {'languages', 'format', 'days', 'times'}}.get(proposal.category, set())
        for key, value in changes['structured'].items():
            if key in allowed:
                proposal.structured[key] = value
        proposal.editedByClient = True
        if proposal.category == 'practical' and 'text' not in changes:
            proposal.text = interpret.practical_text({**proposal.structured})
        if proposal.category == 'working_style' and 'text' not in changes:
            proposal.text = interpret.working_style_text(proposal.structured) or proposal.text
    session.updatedAt = now(state)
    return proposal


def confirm(state: ValitukiState, client: ClientProfile, actor: str, at: Optional[str] = None) -> list[str]:
    """"Kyllä, tämä kuvaa tilannettani" – the included proposals become approved insights and the Therapy Fit Profile."""
    session = _require(state, client, 'review')
    included = [p for p in session.proposals if p.included]
    if not any(p.category == 'goal' for p in included):
        raise IntakeError('Hyväksy tai kirjoita ainakin yksi tavoite.')
    created = []
    label = f'Alkukeskustelu {fmt_date(state.currentDate)}'
    for proposal in included:
        origin = 'user_said' if proposal.editedByClient else 'ai_interpreted'
        if proposal.category == 'goal':
            primary = proposal.structured.get('primary', {'text': proposal.text, 'topics': []})
            goal = insights.create(state, client, category='goal', kind='primary_goal', title='Päätavoite', text=primary['text'],
                                   origin=origin, source_label=label, status='approved', actor=actor, source='intake', at=at,
                                   structured={'topics': primary.get('topics', []), 'hope': proposal.structured.get('hope', '')},
                                   user_words=proposal.userWords, edited=proposal.editedByClient)
            created.append(goal.id)
            for item in proposal.structured.get('secondary', []):
                secondary = insights.create(state, client, category='goal', kind='secondary_goal', title='Tavoite', text=item['text'],
                                            origin=origin, source_label=label, status='approved', actor=actor, source='intake',
                                            structured={'topics': item.get('topics', [])})
                created.append(secondary.id)
        else:
            category, kind, title = CARD_TO_INSIGHT[proposal.category]
            item = insights.create(state, client, category=category, kind=kind, title=title, text=proposal.text, origin=origin,
                                   source_label=label, status='approved', actor=actor, source='intake',
                                   structured=dict(proposal.structured), user_words=proposal.userWords, edited=proposal.editedByClient)
            created.append(item.id)
    excluded = [p.title for p in session.proposals if not p.included]
    session.status = 'rhythm'
    session.confirmedAt = now(state)
    records.audit(state, actor=actor, action='intake_confirmed', client_id=client.id,
                  detail=f'Asiakas hyväksyi {len(included)} tulkintaa' + (f'; hylkäsi: {", ".join(excluded)}' if excluded else '') + '.')
    event = journey.apply(state, client, 'INSIGHTS_APPROVED', actor=actor, source='client',
                          payload={'insightIds': created, 'reason': 'Alkukeskustelun tulkinnat hyväksyttiin'})
    orchestrator.dispatch(state, event)
    return created


def complete(state: ValitukiState, client: ClientProfile, rhythm: dict[str, Any], mood: Optional[int], actor: str,
             provider: Optional[AIProvider] = None, at: Optional[str] = None, anxiety: Optional[int] = None) -> dict[str, Any]:
    """Check-in rhythm and message style. Today's wellbeing – the first point of the client's own baseline – comes with it or
    right after, from the home screen (record_baseline)."""
    session = _require(state, client, 'rhythm')
    days = sorted({int(d) for d in rhythm.get('checkInDays', []) if 0 <= int(d) <= 6})
    if not days:
        raise IntakeError('Valitse check-in-rytmi.')
    _check_scales(mood, anxiety, required=False)
    client.checkInDays = days
    client.communicationStyle = 'warm' if rhythm.get('communicationStyle') == 'warm' else 'brief'
    stamp = now(state, at)
    baseline = _baseline_checkin(state, client, mood, anxiety, actor, stamp) if mood is not None else None
    tone = 'lyhyet ja asialliset' if client.communicationStyle == 'brief' else 'lämpimät ja kannustavat'
    insights.create(state, client, category='preference', kind='engagement', title='Check-in-rytmi ja viestien sävy',
                    text=f'Check-in {len(days)}× viikossa, {tone} viestit.',
                    origin='user_said', source_label=f'Alkukeskustelu {fmt_date(state.currentDate)}', status='approved', actor=actor,
                    source='intake', structured={'checkInDays': days, 'communicationStyle': client.communicationStyle})
    session.status = 'completed'
    session.completedAt = stamp
    fit_profile.rebuild(state, client, agent='NavigationAgent', reason='Check-in-rytmi ja viestien sävy lisättiin', visible=False)
    event = journey.apply(state, client, 'BASELINE_COMPLETED', actor=actor, source='client',
                          payload={'mood': int(mood) if mood is not None else None, 'checkInDays': days,
                                   'checkInId': baseline.id if baseline else None})
    orchestrator.dispatch(state, event, provider)
    if mood is not None:
        _assess_mood(state, client, int(mood), actor)
    return {'journeyState': client.journeyState, 'baseline': client.baseline}


def needs_baseline(state: ValitukiState, client: ClientProfile) -> bool:
    """The intake is done but "Miten voit tänään?" is still unanswered – the home screen asks it."""
    session = session_for(state, client)
    return bool(session and session.status == 'completed' and client.baseline is None
                and not any(c.clientId == client.id and c.kind == 'baseline' for c in state.checkIns))


def record_baseline(state: ValitukiState, client: ClientProfile, mood: int, actor: str, anxiety: Optional[int] = None,
                    at: Optional[str] = None) -> dict[str, Any]:
    """Today's wellbeing on the home screen right after the intake: the first point of the client's own baseline."""
    if not needs_baseline(state, client):
        raise IntakeError('Lähtötaso on jo kirjattu.')
    _check_scales(mood, anxiety, required=True)
    _baseline_checkin(state, client, mood, anxiety, actor, now(state, at))
    _assess_mood(state, client, int(mood), actor)
    return {'baseline': client.baseline}


def _check_scales(mood: Optional[int], anxiety: Optional[int], *, required: bool) -> None:
    if (mood is None and required) or (mood is not None and not 1 <= int(mood) <= 5):
        raise IntakeError('Valitse vointi asteikolla 1–5.')
    if anxiety is not None and not 1 <= int(anxiety) <= 5:
        raise IntakeError('Valitse ahdistus asteikolla 1–5.')


def _baseline_checkin(state: ValitukiState, client: ClientProfile, mood: Optional[int], anxiety: Optional[int], actor: str,
                      stamp: str) -> CheckIn:
    retained = client.consent.storeHistory
    baseline = CheckIn(id=next_id(state, 'chk'), clientId=client.id, kind='baseline', dueDate=state.currentDate, status='completed',
                       completedAt=stamp, mood=int(mood) if mood is not None else None,
                       anxiety=int(anxiety) if anxiety is not None and retained else None,
                       retained=retained, createdAt=stamp, updatedAt=stamp, createdBy=actor, source='client')
    state.checkIns.append(baseline)
    from app.valituki import trends

    trends.update_baseline(state, client)
    return baseline


def _assess_mood(state: ValitukiState, client: ClientProfile, mood: int, actor: str) -> None:
    result = assess(evaluate_structured(mood=mood))
    if result.final_level:
        safety_agent.raise_safety(state, client, result, context='checkin', actor=actor)


def run_scripted(state: ValitukiState, client: ClientProfile, script: dict[str, Any], actor: str,
                 provider: Optional[AIProvider] = None, baseline: bool = True) -> None:
    """Replays a whole intake through the same functions the UI uses (seed data and demo shortcuts). Without `baseline`
    today's wellbeing is left for the home screen (record_baseline) – the live demo asks it after the first conversation."""
    provider = provider or DemoAIProvider()
    answers = script['answers']
    if client.journeyState == 'INVITED':
        start(state, client, script.get('consent', {}), actor)
    session = session_for(state, client)
    while session and session.status == 'conversation':
        key = session.pendingQuestionKey or interpret.OPENING_KEY
        if answers.get(key):
            answer(state, client, answers[key], provider, actor)
        else:
            skip(state, client, provider, actor)
    if session and session.status == 'review':
        confirm(state, client, actor)
    if session and session.status == 'rhythm':
        complete(state, client, script.get('rhythm', {'checkInDays': [0, 2, 5]}),
                 int(script.get('baselineMood', 3)) if baseline else None, actor, provider,
                 anxiety=script.get('baselineAnxiety') if baseline else None)
