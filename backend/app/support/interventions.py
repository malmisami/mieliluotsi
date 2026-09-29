"""Micro-interventions: short adaptive check-ins (1-3 questions) chosen from the active plan, plus the rule-based
follow-up that picks the next step only from the plan's approved options."""
from __future__ import annotations

from typing import Any, Optional

from app.loop.models import LoopState
from app.loop.store import add_days, next_id
from app.loop.templates import fi_date
from app.support import assessment as assessment_module
from app.support import audit, consent, messages, plan_state, plans, policies, signals, texts
from app.support.models import CheckIn, CheckInOption, CheckInQuestion, SupportPlan


class InterventionError(ValueError):
    pass


GOAL_OPTIONS_MULTI = [('met', 'Toteutui kokonaan'), ('partial', 'Osittain'), ('none', 'Ei tällä kertaa')]
GOAL_OPTIONS_SINGLE = [('met', 'Toteutui'), ('none', 'Ei tällä kertaa')]
MEASUREMENT_OPTIONS = [('will_measure', 'Mittaan tänään'), ('no_time', 'En ole ehtinyt'), ('device_problem', 'Mittarin kanssa on ongelma')]
BARRIER_OPTIONS = [('time', 'Aika tai kiire'), ('tired', 'Väsymys'), ('weather', 'Sää tai olosuhteet'),
                   ('pain', 'Kipu tai muu vaiva'), ('other', 'Jokin muu')]
SMALLER_GOAL_OPTIONS = [('accept', 'Sopii'), ('alternative', 'Ehdota muuta'), ('decline', 'Pidetään nykyinen tavoite')]
ALTERNATIVE_OPTIONS = [('accept', 'Sopii'), ('decline', 'Pidetään nykyinen tavoite')]
STEP_UP_OPTIONS = [('accept', 'Sopii'), ('decline', 'Pidetään nykyinen askel')]
WELLBEING_OPTIONS = [('good', 'Hyvin'), ('ok', 'Vaihtelevasti'), ('poor', 'Huonosti')]
CONTACT_OPTIONS = [('request', 'Kyllä, pyydän yhteydenottoa'), ('later', 'Ei nyt')]
CONCERN_OPTIONS = [('share', 'Kyllä, välitä'), ('keep', 'Ei tarvitse')]
USEFULNESS_OPTIONS = [('1', '1 – ei lainkaan'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5 – paljon')]


def _question(state: LoopState, kind: str, text: str, why: str, options: list[tuple[str, str]], optional: bool = False,
              **context: Any) -> CheckInQuestion:
    return CheckInQuestion(id=next_id(state, 'q'), kind=kind, text=text, whyAsked=why,
                           options=[CheckInOption(id=i, label=label) for i, label in options], optional=optional, context=context)


def select_questions(state: LoopState, plan: SupportPlan, obs: dict) -> list[CheckInQuestion]:
    """At most three questions, chosen from the plan's allowed micro-interventions and the detected signals."""
    allowed = set(plan.microInterventions)
    detected, metrics = obs['detected'], obs['metrics']
    questions: list[CheckInQuestion] = []
    if plan.goal and 'goal_progress' in allowed:
        # feedback on the one step of the last seven days (the continuity loop: goal, action, feedback, adaptation, new action)
        options = GOAL_OPTIONS_MULTI if plan.goal.timesPerWeek > 1 else GOAL_OPTIONS_SINGLE
        step = texts.goal_step(plan.goal)
        questions.append(_question(state, 'goal_progress', texts.GOAL_QUESTION.format(goal=plan.goal.label, step=step),
                                   texts.GOAL_WHY.format(goal=plan.goal.label), options, goal=plan.goal.label, step=step))
    if 'missing_measurement' in detected and 'measurement_status' in allowed:
        count, required = metrics.get('measurementCount', 0), metrics.get('measurementsRequired', plan.measurementsPerWeek)
        since = fi_date(metrics.get('periodStart'))
        questions.append(_question(state, 'measurement_status', texts.MEASUREMENT_QUESTION.format(since=since, count=count, required=required),
                                   texts.MEASUREMENT_WHY.format(required=required), MEASUREMENT_OPTIONS, optional=True))
    elif 'trend_rising' in detected and 'wellbeing' in allowed:
        questions.append(_question(state, 'wellbeing', texts.WELLBEING_QUESTION, texts.WELLBEING_WHY, WELLBEING_OPTIONS, optional=True))
    if 'usefulness' in allowed and len(questions) < 3:
        questions.append(_question(state, 'usefulness', texts.USEFULNESS_QUESTION, texts.USEFULNESS_WHY, USEFULNESS_OPTIONS, optional=True))
    return questions[:3]


def _post_question(state: LoopState, plan: SupportPlan, checkin: CheckIn, question: CheckInQuestion) -> None:
    actions = [messages.action(state, option.label, 'checkin_answer', checkInId=checkin.id, questionId=question.id, optionId=option.id)
               for option in question.options]
    if question.optional:
        actions.append(messages.action(state, 'Ohita kysymys', 'checkin_skip', style='secondary', checkInId=checkin.id, questionId=question.id))
    messages.post(state, f'{question.text}\n\nMiksi kysyn: {question.whyAsked}', kind='check_in', plan=plan, actions=actions)


def create_checkin(state: LoopState, plan: SupportPlan, obs: dict, chain_id: str, reason: str,
                   questions: Optional[list[CheckInQuestion]] = None) -> Optional[CheckIn]:
    questions = questions if questions is not None else select_questions(state, plan, obs)
    if not questions:
        return None
    checkin_id = next_id(state, 'checkin')
    checkin = CheckIn(
        id=checkin_id, seq=state.counters['checkin'], planId=plan.id, planVersion=plan.version, chainId=chain_id, createdAt=state.currentDate,
        deliveredAt=f'{state.currentDate} {consent.delivery_time(state)}', channel=state.support.consent.channel,
        reason=reason, signals=sorted(obs['detected']), questions=questions,
    )
    if plan.measurementsPerWeek and obs['metrics'].get('measurementCount') is not None:
        checkin.outcome['measurementsDone'] = min(obs['metrics']['measurementCount'], plan.measurementsPerWeek)
        checkin.outcome['measurementsRequired'] = plan.measurementsPerWeek
    state.support.checkIns.append(checkin)
    facts = [signals.SIGNAL_LABELS.get(key, key) for key in sorted(obs['detected'])]
    messages.post(state, texts.checkin_intro(plan.name, len(questions)), kind='check_in_intro', plan=plan,
                  basis_data=messages.basis(plan, f'Agenttisykli: {reason}', facts=facts))
    _post_question(state, plan, checkin, questions[0])
    return checkin


def create_concern_question(state: LoopState, plan: SupportPlan, obs: dict, chain_id: str) -> Optional[CheckIn]:
    event_ids = next((s.get('eventIds') for s in obs['signals'] if s['kind'] == 'self_report'), []) or []
    event = next((e for e in state.events if e.id in event_ids), None)
    if not event:
        return None
    question = _question(state, 'concern', texts.CONCERN_QUESTION.format(date=fi_date(event.date), text=event.rawText or event.displayName,
                                                                         owner=texts.owner_possessive(plan.owner.role)),
                         texts.CONCERN_WHY, CONCERN_OPTIONS, eventId=event.id)
    return create_checkin(state, plan, obs, chain_id, 'Käyttäjä kirjasi uuden huolen: yksi tarkentava kysymys.', [question])


def find_checkin(state: LoopState, checkin_id: str) -> CheckIn:
    checkin = next((c for c in state.support.checkIns if c.id == checkin_id), None)
    if not checkin:
        raise InterventionError('Tarkistusta ei löytynyt.')
    return checkin


def next_unanswered(checkin: CheckIn) -> Optional[CheckInQuestion]:
    return next((q for q in checkin.questions if not q.answer and not q.skipped), None)


def _insert_after(checkin: CheckIn, after: CheckInQuestion, question: CheckInQuestion) -> None:
    # A follow-up replaces the optional usefulness question so the conversation stays short.
    checkin.questions = [q for q in checkin.questions if not (q.kind == 'usefulness' and not q.answer and not q.skipped)]
    index = next(i for i, q in enumerate(checkin.questions) if q.id == after.id)
    checkin.questions.insert(index + 1, question)


def propose_goal(plan: SupportPlan, barrier: str) -> Optional[dict]:
    """A smaller or alternative goal inside the professional-approved range; None if nothing new can be offered."""
    goal = plan.goal
    if not goal:
        return None
    if barrier in ('weather', 'alternative'):
        activity, times, minutes = 'sisäliikunta', max(goal.minTimesPerWeek, min(goal.timesPerWeek, goal.maxTimesPerWeek)), 15
    elif barrier == 'tired':
        activity, times, minutes = goal.activity, goal.timesPerWeek, 10
    else:
        activity, times, minutes = goal.activity, max(goal.minTimesPerWeek, goal.timesPerWeek - 1), min(goal.minutes or 30, 20)
    label = texts.goal_label(activity, times, minutes)
    if label == goal.label:
        return None
    return {'label': label, 'activity': activity, 'timesPerWeek': times, 'minutes': minutes,
            'step': texts.step_label(activity, times, minutes)}


def propose_step_up(plan: SupportPlan) -> Optional[dict]:
    """A slightly bigger step after a step that was met: one more time a week, never above the professional's maximum."""
    goal = plan.goal
    if not goal or goal.timesPerWeek >= goal.maxTimesPerWeek:
        return None
    times = goal.timesPerWeek + 1
    return {'label': texts.goal_label(goal.activity, times, goal.minutes), 'activity': goal.activity, 'timesPerWeek': times,
            'minutes': goal.minutes, 'step': texts.step_label(goal.activity, times, goal.minutes)}


def _escalation_would_trigger(state: LoopState, plan: SupportPlan, checkin: CheckIn) -> bool:
    obs = signals.evaluate(state, plan)
    failures = signals.goal_failures_in_row(state, plan) + (1 if checkin.outcome.get('goal') == 'none' else 0)
    for rule in plan.escalationRules:
        if rule.kind == 'goal_failures_and_above_target' and failures >= rule.params.get('goalFailuresInRow', 2) \
                and 'above_target' in obs['detected']:
            return True
    return False


def _apply_goal(state: LoopState, plan: SupportPlan, checkin: CheckIn, proposal: dict,
                summary: str = 'Tavoite sovitettiin käyttäjän kanssa hyväksytyn vaihteluvälin sisällä.') -> None:
    old = plan.goal.label if plan.goal else '–'
    plan.goal = plans.goal_from(state, {**proposal, 'minTimesPerWeek': plan.goal.minTimesPerWeek,
                                        'maxTimesPerWeek': plan.goal.maxTimesPerWeek}, set_by='agent_with_user')
    plan_state.add_history(state, plan, actor='agent', summary=summary, changes=[f'Tavoite: {old} → {plan.goal.label}'])
    audit.record(state, stage='act', actor='agent', plan=plan, chain_id=checkin.chainId, action='adjust_goal',
                 detail=f'Tavoite muutettiin käyttäjän hyväksynnällä: {old} → {plan.goal.label}. Suunnitelman versio pysyy {plan.version}.',
                 outcome='goal_adjusted')


def _adapt(state: LoopState, plan: SupportPlan, checkin: CheckIn, question: CheckInQuestion) -> None:
    """Deterministic follow-up: never repeats the same advice; picks only from the plan's approved next steps."""
    if question.skipped:
        return
    kind, answer = question.kind, question.answer
    owner = texts.owner_possessive(plan.owner.role)
    if kind == 'goal_progress':
        checkin.outcome['goal'] = answer
        if answer == 'met' and 'step_up' in plan.microInterventions and 'adjust_goal' in plan.allowedActions:
            # the step worked: offer a slightly bigger one inside the professional's range (the user decides)
            proposal = propose_step_up(plan)
            if proposal:
                _insert_after(checkin, question, _question(
                    state, 'step_up', texts.STEP_UP_QUESTION.format(goal=proposal['step']),
                    texts.STEP_UP_WHY.format(owner=owner, max_times=texts.times_per_week(plan.goal.maxTimesPerWeek)),
                    STEP_UP_OPTIONS, proposal=proposal))
                audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=checkin.chainId, action='propose_small_goal',
                             detail=f'Askel toteutui. Ehdotetaan hieman isompaa askelta hyväksytyn vaihteluvälin sisällä: {proposal["label"]}.')
            else:
                checkin.outcome['goalProposalSkipped'] = 'at_maximum'
        if answer == 'none' and 'barrier' in plan.microInterventions:
            failures = signals.goal_failures_in_row(state, plan) + 1
            text = texts.BARRIER_QUESTION_AGAIN if failures >= 2 else texts.BARRIER_QUESTION
            _insert_after(checkin, question, _question(state, 'barrier', text, texts.BARRIER_WHY, BARRIER_OPTIONS, optional=True))
            audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=checkin.chainId, action='clarifying_question',
                         detail='Tavoite ei toteutunut. Pienin riittävä jatkotoimi: yksi esteeseen liittyvä tarkentava kysymys.')
    elif kind == 'barrier':
        checkin.outcome['barrier'] = answer
        if answer == 'pain':
            if 'show_service_contact' in plan.allowedActions:
                _insert_after(checkin, question, _question(state, 'contact_request', texts.CONTACT_QUESTION.format(owner=owner),
                                                           texts.CONTACT_WHY, CONTACT_OPTIONS, reason='pain'))
            audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=checkin.chainId, action='show_service_contact',
                         detail='Esteenä kipu tai vaiva: agentti tekee hoidon tarpeen arvion ja tarjoaa ammattilaisen yhteydenottoa.')
        elif _escalation_would_trigger(state, plan, checkin):
            checkin.outcome['goalProposalSkipped'] = 'escalation_rule'
            audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=checkin.chainId, action='escalate',
                         detail='Kiireellisyyssääntö täyttyy tämän tarkistuksen jälkeen. Tavoitetta ei enää pienennetä, vaan agentti tekee '
                                'automaattisen hoidon tarpeen arvion ja ohjaa tilanteen ammattilaiselle.')
        else:
            proposal = propose_goal(plan, answer)
            if proposal and 'adjust_goal' in plan.allowedActions:
                _insert_after(checkin, question, _question(
                    state, 'smaller_goal', texts.SMALLER_GOAL_QUESTION.format(goal=proposal['step'], hint=texts.GOAL_HINTS.get(answer, '')),
                    texts.SMALLER_GOAL_WHY.format(owner=owner, min_times=texts.times_per_week(plan.goal.minTimesPerWeek)),
                    SMALLER_GOAL_OPTIONS, proposal=proposal))
                audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=checkin.chainId, action='propose_small_goal',
                             detail=f'Este: {question.answerLabel}. Ehdotetaan pienempää tavoitetta: {proposal["label"]}.')
            else:
                checkin.outcome['goalProposalSkipped'] = 'at_minimum'
    elif kind == 'step_up':
        proposal = question.context['proposal']
        if answer == 'accept':
            _apply_goal(state, plan, checkin, proposal, summary='Askelta kasvatettiin käyttäjän kanssa hyväksytyn vaihteluvälin sisällä.')
            checkin.outcome.update({'newGoal': proposal['label'], 'newStep': proposal['step'], 'stepUp': True})
        else:
            checkin.outcome['keptGoal'] = plan.goal.label if plan.goal else None
    elif kind == 'smaller_goal':
        proposal = question.context['proposal']
        if answer == 'accept':
            _apply_goal(state, plan, checkin, proposal)
            checkin.outcome.update({'newGoal': proposal['label'], 'newStep': proposal['step']})
        elif answer == 'alternative' and not question.context.get('isAlternative'):
            alternative = propose_goal(plan, 'alternative')
            if alternative:
                _insert_after(checkin, question, _question(
                    state, 'smaller_goal', texts.SMALLER_GOAL_QUESTION.format(goal=alternative['step'], hint=texts.GOAL_HINTS['alternative']),
                    texts.SMALLER_GOAL_WHY.format(owner=owner, min_times=texts.times_per_week(plan.goal.minTimesPerWeek)),
                    ALTERNATIVE_OPTIONS, proposal=alternative, isAlternative=True))
            else:
                checkin.outcome['keptGoal'] = plan.goal.label
        else:
            checkin.outcome['keptGoal'] = plan.goal.label if plan.goal else None
    elif kind == 'measurement_status':
        checkin.outcome['measurement'] = answer
    elif kind == 'wellbeing':
        checkin.outcome['wellbeing'] = answer
        if answer == 'poor' and 'show_service_contact' in plan.allowedActions:
            _insert_after(checkin, question, _question(state, 'contact_request', texts.CONTACT_QUESTION.format(owner=owner),
                                                       texts.CONTACT_WHY, CONTACT_OPTIONS, reason='wellbeing'))
    elif kind == 'contact_request':
        checkin.outcome['contactRequested'] = answer == 'request'
    elif kind == 'concern':
        checkin.outcome['concernShared'] = answer == 'share'
    elif kind == 'usefulness':
        checkin.outcome['usefulness'] = int(answer)
        state.support.feedback.append({'date': state.currentDate, 'planId': plan.id, 'checkInId': checkin.id, 'rating': int(answer)})


def _closing_text(plan: SupportPlan, checkin: CheckIn, escalation_notice: Optional[str]) -> str:
    outcome = checkin.outcome
    owner = texts.owner_possessive(plan.owner.role)
    parts = [texts.CLOSING_THANKS]
    if outcome.get('goal') == 'met':
        parts.append(texts.CLOSING_GOAL_MET)
    elif outcome.get('goal') == 'partial':
        parts.append(texts.CLOSING_GOAL_PARTIAL)
    step = texts.goal_step(plan.goal) if plan.goal else None
    if outcome.get('newGoal'):
        parts.append(texts.CLOSING_NEW_GOAL.format(goal=outcome.get('newStep') or outcome['newGoal']))
    elif outcome.get('keptGoal'):
        parts.append(texts.CLOSING_KEEP_GOAL.format(goal=step or outcome['keptGoal']))
    elif outcome.get('goal') == 'met' and step:
        parts.append(texts.CLOSING_KEEP_GOAL.format(goal=step))
    contact = policies.service_contact(policies.theme(plan.theme).get('serviceContact', 'NURSE_LINE'))
    if outcome.get('measurement') == 'no_time':
        parts.append(texts.CLOSING_NO_TIME)
    if outcome.get('measurement') == 'device_problem':
        parts.append(texts.CLOSING_DEVICE.format(contact=f"{contact['label']}, {contact['details']}"))
    if outcome.get('wellbeing') == 'poor' and not outcome.get('contactRequested'):
        parts.append(texts.CLOSING_WELLBEING.format(contact=f"{contact['label']}, {contact['details']}"))
    if 'concernShared' in outcome:
        parts.append(texts.CLOSING_CONCERN_SHARED.format(owner=owner) if outcome['concernShared'] else texts.CLOSING_CONCERN_KEPT)
    if escalation_notice:
        parts.append(escalation_notice)
    elif plan.nextCheckInAt:
        parts.append(texts.CLOSING_NEXT_CHECK.format(date=fi_date(plan.nextCheckInAt)))
    return ' '.join(parts)


def _complete(state: LoopState, plan: SupportPlan, checkin: CheckIn) -> None:
    from app.support import escalation  # local import: escalation builds its summary from check-ins

    period_metrics = signals.evaluate(state, plan)['metrics']  # the period this check-in closes, before it rolls over
    checkin.status = 'completed'
    plan.nextCheckInAt = add_days(state.currentDate, plan.checkInEveryDays)
    plan.lastAgentAction = {'date': state.currentDate, 'action': 'check_in', 'label': 'Viikkotarkistus tehty',
                            'detail': ', '.join(f'{q.text.split("?")[0][:60]}: {q.answerLabel or "ohitettu"}' for q in checkin.questions)}
    audit.record(state, stage='update', actor='agent', plan=plan, chain_id=checkin.chainId, action='schedule_check',
                 detail=f'Tarkistus valmis ({len(checkin.questions)} kysymystä). Tilannekuva päivitetty. Seuraava tarkistus {fi_date(plan.nextCheckInAt)}.',
                 outcome=', '.join(f'{k}={v}' for k, v in checkin.outcome.items()))
    obs = signals.evaluate(state, plan)
    notice, linked = None, None
    created = escalation.check_and_create(state, plan, obs, chain_id=checkin.chainId, notify=False, period_metrics=period_metrics)
    if not created and checkin.outcome.get('contactRequested'):
        created = escalation.create_user_request(state, plan, checkin, notify=False)
    if created:
        notice = created[1]
        linked = assessment_module.find(state, created[0].assessmentId) if created[0].assessmentId else None
    checkin.closingMessage = _closing_text(plan, checkin, notice)
    # the automated assessment behind the routing: the user can always ask for a professional's assessment instead
    actions = [assessment_module.human_review_action(state, linked)] if linked and linked.status == 'issued' else []
    messages.post(state, checkin.closingMessage, kind='escalation_notice' if notice else 'check_in_done', plan=plan, actions=actions,
                  assessment=linked,
                  basis_data=messages.basis(plan, 'Agenttisykli: vastausten arviointi sääntöjen mukaan'
                                            + (' ja automaattinen hoidon tarpeen arvio' if notice else ''),
                                            rules=[{'id': r.id, 'name': r.name} for r in plan.escalationRules if notice],
                                            facts=[f'{q.text} → {q.answerLabel or "ohitettu"}' for q in checkin.questions]))


def answer(state: LoopState, checkin_id: str, question_id: str, option_id: Optional[str] = None, skip: bool = False,
           via: str = 'home') -> dict:
    checkin = find_checkin(state, checkin_id)
    if checkin.status != 'open':
        raise InterventionError('Tarkistus on jo päättynyt.')
    question = next((q for q in checkin.questions if q.id == question_id), None)
    if not question:
        raise InterventionError('Kysymystä ei löytynyt.')
    if question.answer or question.skipped:
        raise InterventionError('Kysymykseen on jo vastattu.')
    current = next_unanswered(checkin)
    if current and current.id != question.id:
        raise InterventionError('Vastaa ensin aiempaan kysymykseen.')
    plan = plans.find(state, checkin.planId)
    if not plan:
        raise InterventionError('Seurantasuunnitelmaa ei löytynyt.')
    if skip:
        if not question.optional:
            raise InterventionError('Tätä kysymystä ei voi ohittaa.')
        question.skipped = True
        label = 'Ohitettu'
    else:
        option = next((o for o in question.options if o.id == option_id), None)
        if not option:
            raise InterventionError('Vastausvaihtoehtoa ei löytynyt.')
        question.answer, question.answerLabel = option.id, option.label
        label = option.label
    question.answeredAt = state.currentDate
    if via != 'chat':
        messages.user_choice(state, label)
    audit.record(state, stage='evaluate', actor='user', plan=plan, chain_id=checkin.chainId, action=f'answer:{question.kind}',
                 user_response=label, detail=f'Vastaus kysymykseen ”{question.text}”: {label}.')
    _adapt(state, plan, checkin, question)
    following = next_unanswered(checkin)
    if following:
        _post_question(state, plan, checkin, following)
    else:
        _complete(state, plan, checkin)
    return {'checkIn': checkin.model_dump(), 'completed': checkin.status == 'completed'}


def open_checkins(state: LoopState) -> list[CheckIn]:
    return [c for c in state.support.checkIns if c.status == 'open']


def answer_scripted(state: LoopState, script: dict) -> dict:
    """Demo helper: answer the next open question with the scripted (worst-path) answer."""
    checkin = next(iter(open_checkins(state)), None)
    if not checkin:
        raise InterventionError('Avoimia tarkistuskysymyksiä ei ole. Käynnistä agenttikierros tai simuloi seuraava viikko.')
    question = next_unanswered(checkin)
    option_id = script.get(question.kind)
    if option_id not in {o.id for o in question.options}:
        option_id = question.options[0].id
    return answer(state, checkin.id, question.id, option_id, via='demo')


def expire_stale(state: LoopState, plan: SupportPlan) -> None:
    """An unanswered check-in older than the plan's interval is closed as 'no response' before a new one is sent."""
    for checkin in signals.plan_checkins(state, plan):
        if checkin.status == 'open' and signals.days_between(checkin.createdAt, state.currentDate) >= plan.checkInEveryDays:
            checkin.status = 'cancelled'
            checkin.outcome['noResponse'] = True
            audit.record(state, stage='evaluate', actor='agent', plan=plan, chain_id=checkin.chainId, action='no_response',
                         detail='Tarkistukseen ei vastattu tarkistusvälin aikana. Kirjattu vastaamattomaksi.', outcome='no_response')


def sync_chat(state: LoopState) -> None:
    """Disable chat buttons for check-in questions that were answered elsewhere (e.g. in Tilanne nyt)."""
    checkins = {c.id: c for c in state.support.checkIns}
    for message in state.chatMessages:
        for chat_action in message.actions:
            if chat_action.used or chat_action.type not in ('checkin_answer', 'checkin_skip'):
                continue
            checkin = checkins.get(chat_action.args.get('checkInId'))
            question = next((q for q in checkin.questions if q.id == chat_action.args.get('questionId')), None) if checkin else None
            if not checkin or checkin.status != 'open' or not question or question.answer or question.skipped:
                chat_action.used = True
    assessment_module.sync_chat(state)
    from app.support import continuity  # local import: continuity builds on the check-in rounds of this module

    continuity.sync_chat(state)

