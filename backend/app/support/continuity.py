"""The self-care continuity engine (omahoidon jatkuvuuden moottori): keeps self-care going in everyday life between
appointments.

Four core tasks, all deterministic - rules and ready-made texts, the LLM makes no decisions:
1 remember   - goals, what was agreed with the professional, what to follow, what has been tried, what works and when
               something is checked again (read from the plans, the professional notes and the agent's own rounds)
2 reach out  - the agent contacts the user itself when an outreach rule of the plan holds, e.g. it offers a three-day
               home monitoring period when the home readings have risen (the user decides)
3 one step   - one realistic step for seven days; goal + action + feedback + adaptation + new action runs through the
               weekly check-in (interventions.py)
4 notice     - continue self-care / change the plan / a professional is needed, from the plan's rules; a professional
               is brought in through the existing automated assessment and routing (escalation.py)
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app.loop.models import HealthEvent, LoopState
from app.loop.store import add_days, next_id
from app.loop.templates import fi_date, fi_value
from app.support import assessment as assessment_module
from app.support import audit, consent, escalation, messages, policies, signals, texts
from app.support import plans as plans_module
from app.support.models import HomeMonitoringPeriod, SupportPlan

FOLLOWED = ('active', 'escalated', 'paused')
VISIBLE = (*FOLLOWED, 'pending_professional_review')
DIRECTION_ORDER = {'professional': 0, 'adjust': 1, 'continue': 2, 'paused': 3, 'pending': 4}
LOOP_ORDER = ('goal', 'action', 'feedback', 'adaptation', 'next')
CONTACT_LABELS = {
    'check_in': 'Viikkotarkistus: miten askel sujui',
    'reminder': 'Muistutus: sovitut kotimittaukset',
    'review_reminder': 'Muistutus: tarkistuspäivä',
    'show_guide': 'Hyväksytty omahoito-ohje',
    'clarifying_question': 'Tarkentava kysymys',
    'home_monitoring_offer': 'Ehdotus: kotiseuranta',
    'safety_message': 'Turvaviesti',
}
FEEDBACK_TONES = {'met': 'positive', 'partial': 'neutral', 'none': 'attention'}


class ContinuityError(ValueError):
    pass


def policy() -> dict:
    return policies.load_policies().get('continuity', {})


def _item(text: str, *, detail: Optional[str] = None, source: Optional[str] = None, date: Optional[str] = None,
          origin: str = 'plan', tone: Optional[str] = None, pending: bool = False) -> dict[str, Any]:
    return {'text': text, 'detail': detail, 'source': source, 'date': date, 'origin': origin, 'tone': tone, 'pending': pending}


def _average_text(average: Optional[dict]) -> Optional[str]:
    return f"{average['systolic']}/{average['diastolic']}" if average else None


# --- 1 remember: professional notes read with documented rules ------------------------------------------------------

def _clauses(text: str) -> list[str]:
    """Sentences and ';'-separated clauses of a note, without the closing punctuation."""
    return [part.strip().rstrip('.;').strip() for part in re.split(r'(?<=[.;])\s+', text.strip()) if part.strip().rstrip('.;').strip()]


def classify_clause(clause: str) -> Optional[str]:
    """works / barrier / agreed / tried / recheck, or None. Genetic, medication and diagnosis wording is never taken
    into the memory (the professional's decisions stay in the record, the agent does not restate them)."""
    lowered = clause.lower()
    config = policy()
    if any(pattern in lowered for pattern in config.get('noteExcludePatterns', [])):
        return None
    for rule in config.get('noteRules', []):
        if any(pattern in lowered for pattern in rule['patterns']):
            return rule['kind']
    return None


def self_care_text(text: Optional[str]) -> Optional[str]:
    """A professional's free text without the clauses the memory never restates (genetics, medication, diagnoses)."""
    if not text:
        return None
    excluded = policy().get('noteExcludePatterns', [])
    kept = [clause for clause in _clauses(text) if not any(pattern in clause.lower() for pattern in excluded)]
    return '. '.join(kept) + '.' if kept else None


def note_items(state: LoopState) -> list[dict[str, Any]]:
    """Clauses of the professional notes linked to the user's plans, newest note first. Only read when the user allows
    the professional notes as a data source."""
    support = state.support
    if not support.person or not consent.source_allowed(state, 'professionalNotes'):
        return []
    plans = [p for p in support.plans if p.status in VISIBLE]
    newest_by_plan: dict[str, str] = {}
    note_plans: dict[str, list[SupportPlan]] = {}
    for plan in plans:
        refs = sorted((s for s in plan.sources if s.kind == 'professionalNotes'), key=lambda s: (s.date or '', s.id))
        if refs:
            newest_by_plan[plan.id] = refs[-1].id
        for ref in refs:
            note_plans.setdefault(ref.id, []).append(plan)
    items = []
    for note in sorted(support.person.professionalNotes, key=lambda n: (n.date, n.id), reverse=True):
        if note.id not in note_plans:
            continue
        for clause in _clauses(note.text):
            kind = classify_clause(clause)
            if not kind:
                continue
            if kind == 'recheck':
                # an old "kontrolli" is history; only the newest note of a plan without a set review date is still ahead
                if not any(newest_by_plan.get(p.id) == note.id and not p.nextReviewAt for p in note_plans[note.id]):
                    continue
            items.append({'kind': kind, 'noteId': note.id, **_item(
                consent.mask_genes(state, texts.capitalize(clause)), date=None if kind == 'recheck' else note.date, origin='record',
                source=f'{texts.capitalize(note.authorRole)}, kirjaus {fi_date(note.date)}',
                tone='barrier' if kind == 'barrier' else ('positive' if kind == 'works' else None))})
    return items


# --- 3 one step at a time: the rounds of the continuity loop ---------------------------------------------------------

def rounds(state: LoopState, plan: SupportPlan, since_baseline: bool = False) -> list[dict[str, Any]]:
    """Completed rounds (oldest first): the step tried for seven days, the feedback, the barrier and the adaptation."""
    result = []
    escalated_chains = {e.chainId for e in state.support.escalations if e.planId == plan.id}
    for checkin in sorted(signals.plan_checkins(state, plan), key=lambda c: c.seq):
        if checkin.status != 'completed' or (since_baseline and checkin.seq <= plan.checkInBaselineSeq):
            continue
        goal_question = next((q for q in checkin.questions if q.kind == 'goal_progress' and q.answer), None)
        if not goal_question:
            continue
        barrier = next((q for q in checkin.questions if q.kind == 'barrier' and q.answer), None)
        outcome = checkin.outcome
        if checkin.chainId in escalated_chains:
            adaptation, label = 'professional', 'Ammattilainen otettiin mukaan'
        elif outcome.get('stepUp'):
            adaptation, label = 'bigger', f"Hieman isompi askel: {outcome.get('newStep') or outcome.get('newGoal')}"
        elif outcome.get('newGoal'):
            adaptation, label = 'smaller', f"Pienempi askel: {outcome.get('newStep') or outcome['newGoal']}"
        else:
            adaptation, label = 'same', 'Sama askel jatkuu'
        result.append({
            'date': checkin.createdAt, 'checkInId': checkin.id, 'planVersion': checkin.planVersion,
            'step': goal_question.context.get('step') or goal_question.context.get('goal') or '–',
            'feedback': goal_question.answer, 'feedbackLabel': goal_question.answerLabel,
            'tone': FEEDBACK_TONES.get(goal_question.answer), 'barrier': barrier.answerLabel if barrier else None,
            'adaptation': adaptation, 'adaptationLabel': label,
        })
    return result


def _step_start(state: LoopState, plan: SupportPlan) -> Optional[str]:
    if not plan.activatedAt:
        return None
    completed = [c.createdAt for c in signals.plan_checkins(state, plan) if c.status == 'completed']
    decided = (plan.lastProfessionalDecision or {}).get('date')
    return max([plan.activatedAt, *completed, *([decided] if decided else [])])


def current_step(state: LoopState, plan: SupportPlan) -> Optional[dict[str, Any]]:
    """The one step of this round and where the loop is: goal -> action -> feedback -> adaptation -> new action."""
    if not plan.goal or plan.status not in VISIBLE:
        return None
    today = state.currentDate
    owner = texts.owner_possessive(plan.owner.role)
    started = _step_start(state, plan) if plan.status != 'pending_professional_review' else None
    days = plan.checkInEveryDays
    open_checkin = signals.open_checkin(state, plan)
    if plan.status == 'pending_professional_review':
        stage = 'goal'
    elif open_checkin:
        stage = 'feedback'
    elif plan.status == 'escalated':
        stage = 'adaptation'
    else:
        stage = 'action'
    history = rounds(state, plan)
    last = history[-1] if history else None
    step = texts.goal_step(plan.goal)
    feedback_at = plan.nextCheckInAt if plan.status == 'active' else None
    day = min(days, max(1, signals.days_between(started, today) + 1)) if started and stage == 'action' else None
    target = plan.demoTarget['label'] if plan.demoTarget else plan.objective
    stage_texts = {
        'goal': target,
        'action': step + (f' – päivä {day}/{days}' if day else ''),
        'feedback': ('Vastaa viikkotarkistukseen' if open_checkin else
                     (f"Palaute annettu {fi_date(last['date'])}" if last else 'Palaute annettu') if plan.status == 'escalated' else
                     f'Kysyn {fi_date(feedback_at)}, miten meni' if feedback_at else
                     'Alkaa, kun suunnitelma on hyväksytty' if plan.status == 'pending_professional_review' else 'Tauolla'),
        'adaptation': (f'{texts.capitalize(owner)} päättää jatkosta' if plan.status == 'escalated' else
                       'Pienempi, sama tai hieman isompi askel palautteesi mukaan'),
        'next': 'Uusi askel seuraaville 7 päivälle',
    }
    current = LOOP_ORDER.index(stage)
    labels = {s['id']: s['label'] for s in policy().get('loopStages', [])}
    if plan.goal.setBy == 'agent_with_user':
        set_by = f'Sovittu kanssasi {fi_date(plan.goal.setAt)} {owner} hyväksymissä rajoissa'
    elif plan.status == 'pending_professional_review':
        set_by = f'Ehdotus – odottaa {owner} hyväksyntää'
    else:
        set_by = f'{plan.owner.label} asetti {fi_date(plan.goal.setAt)}'
    return {
        'planId': plan.id, 'planName': plan.name, 'status': plan.status, 'text': step, 'goalLabel': plan.goal.label,
        'startedAt': started, 'endsAt': add_days(started, days - 1) if started else None, 'feedbackAt': feedback_at,
        'day': day, 'days': days, 'stage': stage, 'setBy': plan.goal.setBy, 'setByLabel': set_by,
        'range': f'{plan.goal.minTimesPerWeek}–{plan.goal.maxTimesPerWeek} kertaa viikossa ({owner} hyväksymä vaihteluväli)',
        'target': target,
        'loop': [{'id': key, 'label': labels.get(key, key), 'text': stage_texts[key],
                  'state': 'done' if i < current else 'current' if i == current else 'upcoming'} for i, key in enumerate(LOOP_ORDER)],
        'rounds': list(reversed(history))[:6],
    }


# --- 2 reach out: the three-day home monitoring the agent offers on its own -------------------------------------------

def outreach_rule(plan: SupportPlan) -> Optional[dict]:
    return next((r for r in policies.theme(plan.theme).get('outreachRules', []) if r['kind'] == 'home_monitoring_offer'), None)


def plan_periods(state: LoopState, plan: SupportPlan) -> list[HomeMonitoringPeriod]:
    return [p for p in state.support.homeMonitoring if p.planId == plan.id]


def open_offer(state: LoopState, plan: Optional[SupportPlan] = None) -> Optional[HomeMonitoringPeriod]:
    """An unanswered offer whose plan is still active (while a professional is involved the agent does not push it)."""
    for period in state.support.homeMonitoring:
        owner_plan = plans_module.find(state, period.planId)
        if period.status == 'offered' and owner_plan and owner_plan.status == 'active' and (plan is None or period.planId == plan.id):
            return period
    return None


def active_period(state: LoopState, plan: Optional[SupportPlan] = None) -> Optional[HomeMonitoringPeriod]:
    return next((p for p in state.support.homeMonitoring if p.status == 'active' and (plan is None or p.planId == plan.id)), None)


def find_period(state: LoopState, period_id: str) -> HomeMonitoringPeriod:
    period = next((p for p in state.support.homeMonitoring if p.id == period_id), None)
    if not period:
        raise ContinuityError('Kotiseurantaehdotusta ei löytynyt.')
    return period


def outreach_due(state: LoopState, plan: SupportPlan, obs: dict) -> Optional[dict]:
    """OUT-BP-001: the plan's outreach rule holds - the readings have risen and no period was offered recently."""
    rule = outreach_rule(plan)
    if not rule or plan.status != 'active' or 'offer_home_monitoring' not in plan.allowedActions:
        return None
    if escalation.open_escalation(state, plan):
        return None
    params = rule.get('params', {})
    if not set(params.get('signals', ['trend_rising'])) & obs['detected']:
        return None
    for period in plan_periods(state, plan):
        if period.status in ('offered', 'active') or signals.days_between(period.offeredAt, state.currentDate) < params.get('cooldownDays', 14):
            return None
    return rule


def _offer_reason(obs: dict) -> tuple[str, str]:
    """(user text template key, one-line reason) from the measured change."""
    metrics = obs['metrics']
    average, earlier, delta = metrics.get('average'), metrics.get('earlierAverage'), metrics.get('trendDelta')
    if 'trend_rising' in obs['detected'] and average and earlier and delta is not None:
        return 'rise', (f'Kotimittausten keskiarvo on noussut: {_average_text(earlier)} → {_average_text(average)} mmHg '
                        f'({delta:+d} mmHg, {average["n"]} viimeisintä mittausta).')
    return 'above', f'Kotimittausten keskiarvo {_average_text(average)} mmHg on sovitun tavoitetason yläpuolella.'


def offer_home_monitoring(state: LoopState, plan: SupportPlan, obs: dict, chain_id: str, rule: dict) -> HomeMonitoringPeriod:
    params = rule.get('params', {})
    kind, reason = _offer_reason(obs)
    period = HomeMonitoringPeriod(
        id=next_id(state, 'hm'), planId=plan.id, planVersion=plan.version, chainId=chain_id, ruleId=rule['id'],
        offeredAt=state.currentDate, reason=reason, days=params.get('days', 3), perDay=params.get('perDay', 2),
    )
    state.support.homeMonitoring.append(period)
    metrics = obs['metrics']
    days = texts.days_genitive(period.days)
    text = (texts.HOME_MONITORING_OFFER.format(now=_average_text(metrics.get('average')), before=_average_text(metrics.get('earlierAverage')), days=days)
            if kind == 'rise' else texts.HOME_MONITORING_OFFER_ABOVE.format(now=_average_text(metrics.get('average')), days=days))
    actions = [messages.action(state, texts.HOME_MONITORING_ACCEPT, 'home_monitoring_accept', periodId=period.id),
               messages.action(state, texts.HOME_MONITORING_DECLINE, 'home_monitoring_decline', style='secondary', periodId=period.id)]
    messages.post(state, text, kind='outreach_offer', plan=plan, actions=actions,
                  basis_data=messages.basis(plan, f"Agentti otti itse yhteyttä: yhteydenottosääntö {rule['id']} ({rule['name']})",
                                            rules=[{'id': rule['id'], 'name': rule['name']}], facts=[reason]))
    state.support.contacts.append({'date': state.currentDate, 'planId': plan.id, 'kind': 'home_monitoring_offer',
                                   'label': f'Ehdotus: {days} kotiseuranta', 'urgent': False,
                                   'channel': state.support.consent.channel, 'deliveredAt': consent.delivery_time(state)})
    audit.record(state, stage='act', actor='agent', plan=plan, chain_id=chain_id, action='offer_home_monitoring',
                 rule={'id': rule['id'], 'name': rule['name']},
                 detail=f"Agentti otti itse yhteyttä ja ehdotti {days} kotiseurantaa (sääntö {rule['id']}). {reason}")
    audit.record(state, stage='wait', actor='agent', plan=plan, chain_id=chain_id, action='await_response',
                 detail='Odotetaan käyttäjän päätöstä. Kotiseuranta alkaa vain, jos käyttäjä haluaa.')
    plan.lastAgentAction = {'date': state.currentDate, 'action': 'offer_home_monitoring',
                            'label': policies.action_label('offer_home_monitoring'), 'detail': reason}
    return period


def respond(state: LoopState, period_id: str, accept: bool, via: str = 'home') -> HomeMonitoringPeriod:
    """The user decides whether the offered home monitoring starts."""
    period = find_period(state, period_id)
    if period.status != 'offered':
        raise ContinuityError('Ehdotukseen on jo vastattu.')
    plan = plans_module.find(state, period.planId)
    if not plan or plan.status != 'active':
        raise ContinuityError('Seuranta ei ole nyt käynnissä, joten kotiseurantaa ei aloiteta.')
    label = texts.HOME_MONITORING_ACCEPT if accept else texts.HOME_MONITORING_DECLINE
    if via != 'chat':
        messages.user_choice(state, label)
    period.respondedAt = state.currentDate
    audit.record(state, stage='evaluate', actor='user', plan=plan, chain_id=period.chainId, action='answer:home_monitoring',
                 user_response=label, detail=f'Vastaus kotiseurantaehdotukseen: {label}.')
    if accept:
        period.status = 'active'
        period.startsAt = state.currentDate
        period.endsAt = add_days(state.currentDate, period.days - 1)
        total = period.days * period.perDay
        guide_id = next((g for g in plan.guides if g == 'GUIDE-BP-HOME'), None)
        guide = policies.guide(guide_id)['text'] if guide_id else ''
        messages.post(state, texts.HOME_MONITORING_STARTED.format(start=fi_date(period.startsAt), end=fi_date(period.endsAt), total=total,
                                                                   guide=guide).replace('  ', ' '),
                      kind='home_monitoring', plan=plan, initiated_by_agent=False,
                      basis_data=messages.basis(plan, f'Käyttäjä hyväksyi ehdotuksen (sääntö {period.ruleId})', facts=[period.reason]))
        audit.record(state, stage='update', actor='agent', plan=plan, chain_id=period.chainId, action='schedule_check',
                     detail=f'Kotiseuranta {fi_date(period.startsAt)}–{fi_date(period.endsAt)}: {total} mittausta aamulla ja illalla. '
                            'Yhteenveto tehdään, kun mittaukset on kirjattu.')
    else:
        period.status = 'declined'
        messages.post(state, texts.HOME_MONITORING_DECLINED.format(date=fi_date(plan.nextCheckInAt)), kind='home_monitoring', plan=plan,
                      initiated_by_agent=False)
        audit.record(state, stage='update', actor='agent', plan=plan, chain_id=period.chainId, action='no_action',
                     detail='Käyttäjä ei halunnut kotiseurantaa nyt. Agentti ei ehdota sitä uudelleen 14 päivään.')
    sync_chat(state)
    return period


def _period_average(state: LoopState, period: HomeMonitoringPeriod) -> Optional[dict]:
    ids = set(period.readingIds)
    readings = [r for r in (signals.bp_reading(e) for e in state.events if e.id in ids) if r]
    if not readings:
        return None
    return {'systolic': round(sum(r[0] for r in readings) / len(readings)), 'diastolic': round(sum(r[1] for r in readings) / len(readings)),
            'n': len(readings)}


def complete_period(state: LoopState, plan: SupportPlan, period: HomeMonitoringPeriod) -> dict[str, Any]:
    """Read the period with the plan's rules: continue self-care / change the plan / a professional is needed."""
    period.status = 'completed'
    period.completedAt = state.currentDate
    rule = next((r for r in policies.theme(plan.theme).get('outreachRules', []) if r['id'] == period.ruleId), {})
    min_readings = rule.get('params', {}).get('minReadings', 4)
    total = period.days * period.perDay
    average = _period_average(state, period)
    count = average['n'] if average else 0
    limit_rule = next((r for r in plan.escalationRules if r.kind == 'home_monitoring_above'), None)
    target = plan.demoTarget or {}
    if count < min_readings:
        direction = 'incomplete'
    elif limit_rule and (average['systolic'] >= limit_rule.params['systolic'] or average['diastolic'] >= limit_rule.params['diastolic']):
        direction = 'professional'
    elif target and (average['systolic'] > target['systolic'] or average['diastolic'] > target['diastolic']):
        direction = 'adjust'
    else:
        direction = 'continue'
    period.result = {'average': average, 'direction': direction, 'total': total, 'complete': count >= total,
                     'ruleId': limit_rule.id if direction == 'professional' and limit_rule else None}
    span = f'{fi_date(period.startsAt)}–{fi_date(period.endsAt)}'
    direction_label = policy().get('directions', {}).get(direction, {}).get('label', 'Ei yhteenvetoa')
    audit.record(state, stage='update', actor='agent', plan=plan, chain_id=period.chainId, action='home_monitoring_result', outcome=direction,
                 rule={'id': limit_rule.id, 'name': limit_rule.name} if direction == 'professional' and limit_rule else None,
                 detail=(f'Kotiseuranta {span} valmis: keskiarvo {_average_text(average)} mmHg ({count}/{total} mittausta). '
                         f'Suunta: {direction_label}.' if average else f'Kotiseuranta {span}: ei mittauksia.'))
    owner = texts.owner_possessive(plan.owner.role)
    values = {'avg': _average_text(average), 'n': count, 'total': total, 'owner': owner, 'date': fi_date(plan.nextCheckInAt),
              'step': texts.goal_step(plan.goal) if plan.goal else 'sovittu askel'}
    text = texts.HOME_MONITORING_RESULT[direction].format(**values)
    facts = [f'Kotiseuranta {span}: {count}/{total} mittausta' + (f', keskiarvo {_average_text(average)} mmHg' if average else ''),
             *([f"Suunnitelman tavoitetaso: {target['label']}"] if target else [])]
    if direction == 'professional':
        if plan.status == 'active' and 'escalate' in plan.allowedActions and not escalation.open_escalation(state, plan):
            created, notice = escalation.create(
                state, plan, limit_rule, trigger='rule', chain_id=period.chainId, obs=signals.evaluate(state, plan), notify=False,
                extra_facts=[f"Kolmen päivän kotiseuranta {span}: keskiarvo {_average_text(average)} mmHg ({count} mittausta); "
                             f"suunnitelman raja {limit_rule.params['systolic']}/{limit_rule.params['diastolic']} mmHg."])
            linked = assessment_module.find(state, created.assessmentId)
            actions = [assessment_module.human_review_action(state, linked)] if linked.status == 'issued' else []
            messages.post(state, f'{text} {notice}', kind='escalation_notice', plan=plan, actions=actions, assessment=linked,
                          basis_data=messages.assessment_basis(linked, plan))
            return {'action': 'escalate', 'periodId': period.id, 'direction': direction, 'escalationId': created.id}
        text = f'{text} {texts.HOME_MONITORING_ALREADY_WITH_PROFESSIONAL}'
    messages.post(state, text, kind='home_monitoring_result', plan=plan,
                  basis_data=messages.basis(plan, 'Kotiseurannan tulos luettiin suunnitelman sääntöjen mukaan', facts=facts))
    plan.lastAgentAction = {'date': state.currentDate, 'action': 'home_monitoring_result', 'label': 'Kotiseurannan yhteenveto',
                            'detail': f'{direction_label}: keskiarvo {_average_text(average) or "–"} mmHg'}
    return {'action': 'home_monitoring_result', 'periodId': period.id, 'direction': direction}


def observe_reading(state: LoopState, plan: SupportPlan, event: HealthEvent, obs: dict, chain_id: str) -> Optional[dict[str, Any]]:
    """A new home reading: it belongs to an active home monitoring period, or it may make the outreach rule hold."""
    period = active_period(state, plan)
    if period:
        if event.id not in period.readingIds:
            period.readingIds.append(event.id)
        total = period.days * period.perDay
        if len(period.readingIds) >= total:
            return complete_period(state, plan, period)
        audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=chain_id, action='home_monitoring_reading',
                     detail=f'Kotiseuranta: {len(period.readingIds)}/{total} mittausta kirjattu. Yhteenveto tehdään, kun mittaukset on tehty.')
        return {'action': 'home_monitoring_reading', 'periodId': period.id, 'readings': len(period.readingIds), 'total': total}
    rule = outreach_due(state, plan, obs)
    if not rule:
        return None
    labels = [signals.SIGNAL_LABELS.get(key, key) for key in sorted(obs['detected'] & set(rule.get('params', {}).get('signals', [])))]
    audit.record(state, stage='detect', actor='agent', plan=plan, chain_id=chain_id,
                 signal={'detected': sorted(obs['detected']), 'trendDelta': obs['metrics'].get('trendDelta')},
                 detail=f"Havaitut signaalit: {', '.join(labels)}. {_offer_reason(obs)[1]}")
    blocked = consent.contact_block_reason(state, plan)
    if blocked:
        audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=chain_id, action='deferred', outcome='deferred',
                     detail=f"Yhteydenottosääntö {rule['id']} täyttyi, mutta yhteydenottoa ei tehty (portti 3): {blocked}")
        return {'action': 'deferred', 'blockedBy': blocked}
    audit.record(state, stage='decide', actor='agent', plan=plan, chain_id=chain_id, action='offer_home_monitoring',
                 rule={'id': rule['id'], 'name': rule['name']},
                 detail=f"{policies.action_label('offer_home_monitoring')}: yhteydenottosääntö {rule['id']} täyttyi ({rule['name'].lower()}).")
    period = offer_home_monitoring(state, plan, obs, chain_id, rule)
    return {'action': 'offer_home_monitoring', 'periodId': period.id}


def close_stale(state: LoopState) -> list[dict[str, Any]]:
    """At every agent cycle: an unanswered offer expires and a period whose last day has passed is summarised."""
    results = []
    for period in state.support.homeMonitoring:
        plan = plans_module.find(state, period.planId)
        if not plan:
            continue
        rule = next((r for r in policies.theme(plan.theme).get('outreachRules', []) if r['id'] == period.ruleId), {})
        if period.status == 'offered' and (plan.status != 'active' or signals.days_between(period.offeredAt, state.currentDate)
                                           >= rule.get('params', {}).get('offerValidDays', 7)):
            period.status = 'expired'
            audit.record(state, stage='update', actor='agent', plan=plan, chain_id=period.chainId, action='no_response', outcome='expired',
                         detail=texts.HOME_MONITORING_EXPIRED)
        elif period.status == 'active' and period.endsAt and state.currentDate > period.endsAt:
            results.append(complete_period(state, plan, period))
    sync_chat(state)
    return results


def sync_chat(state: LoopState) -> None:
    """Disable the chat buttons of an offer that was answered elsewhere or expired."""
    periods = {p.id: p for p in state.support.homeMonitoring}
    for message in state.chatMessages:
        for chat_action in message.actions:
            if chat_action.used or chat_action.type not in ('home_monitoring_accept', 'home_monitoring_decline'):
                continue
            period = periods.get(chat_action.args.get('periodId'))
            if not period or period.status != 'offered':
                chat_action.used = True


def _period_view(period: Optional[HomeMonitoringPeriod]) -> Optional[dict[str, Any]]:
    if not period:
        return None
    return {**period.model_dump(), 'total': period.days * period.perDay, 'readings': len(period.readingIds),
            'title': f'{texts.capitalize(texts.days_genitive(period.days))} kotiseuranta'}


# --- 4 notice: continue self-care / change the plan / a professional is needed ---------------------------------------

def _latest_period(state: LoopState, plan: SupportPlan) -> Optional[HomeMonitoringPeriod]:
    periods = plan_periods(state, plan)
    return max(periods, key=lambda p: (p.offeredAt, p.id)) if periods else None


def _watch(state: LoopState, plan: SupportPlan, obs: dict) -> list[dict[str, Any]]:
    """What the agent follows at the same time, with a plain status per item."""
    detected, metrics = obs['detected'], obs['metrics']
    kinds = {s['kind']: s for s in obs['signals']}
    watch = []
    if plan.goal and 'goal_completion' in kinds:
        last = next(iter(reversed(rounds(state, plan, since_baseline=True))), None)
        watch.append({'label': 'Askeleen toteutuminen', 'ok': 'goal_not_met' not in detected,
                      'detail': f"{fi_date(last['date'])}: {last['feedbackLabel'].lower()}" if last else f'Ensimmäinen palaute {fi_date(plan.nextCheckInAt)}'})
    if 'measurement_average' in kinds:
        average, target = metrics.get('average'), plan.demoTarget or {}
        watch.append({'label': 'Kotimittausten keskiarvo', 'ok': 'above_target' not in detected,
                      'detail': (f"{_average_text(average)} mmHg, tavoitetaso alle {target.get('systolic')}/{target.get('diastolic')}"
                                 if average else 'Liian vähän mittauksia')})
    if 'measurement_trend' in kinds:
        delta = metrics.get('trendDelta')
        watch.append({'label': 'Kotimittausten suunta', 'ok': 'trend_rising' not in detected,
                      'detail': f'{delta:+d} mmHg aiempiin mittauksiin' if delta is not None else 'Ei vielä vertailutietoa'})
    if 'measurement_frequency' in kinds:
        watch.append({'label': 'Sovitut kotimittaukset', 'ok': 'missing_measurement' not in detected,
                      'detail': f"{metrics.get('measurementCount', 0)}/{metrics.get('measurementsRequired', plan.measurementsPerWeek)} "
                                'edellisen tarkistuksen jälkeen'})
    if 'safety_threshold' in kinds:
        limits = next((s['params'] for s in plan.signals if s['kind'] == 'safety_threshold'), {})
        watch.append({'label': 'Turvaraja', 'ok': 'safety_threshold' not in detected,
                      'detail': f"Yksittäinen mittaus alle {limits.get('systolic')}/{limits.get('diastolic')} mmHg"})
    if plan.measurementCode == 'LDL' and 'data_freshness' in kinds:
        watch.append({'label': 'LDL-tulos', 'ok': 'stale_data' not in detected,
                      'detail': f"Viimeisin tulos {fi_date(metrics.get('lastLabDate'))}"})
    if 'review_date' in kinds and plan.nextReviewAt:
        watch.append({'label': 'Tarkistuspäivä', 'ok': not detected & {'review_overdue'},
                      'detail': f"{policies.theme(plan.theme).get('reviewLabel', 'Seurannan arvio')} {fi_date(plan.nextReviewAt)}"})
    return watch


def professional_when(plan: SupportPlan) -> list[dict[str, str]]:
    """When the agent brings a professional in: the plan's escalation rules in the user's words, plus symptoms."""
    items = []
    for rule in plan.escalationRules:
        template = texts.PROFESSIONAL_WHEN.get(rule.kind)
        items.append({'id': rule.id, 'text': template.format(**rule.params) if template else rule.name})
    if 'assess_care_need' in plan.allowedActions:
        items.append({'id': 'TRI', 'text': texts.PROFESSIONAL_WHEN_SYMPTOMS})
    return items


def direction(state: LoopState, plan: SupportPlan) -> dict[str, Any]:
    config = policy().get('directions', {})
    owner = texts.owner_possessive(plan.owner.role)
    reasons: list[str] = []
    obs = signals.evaluate(state, plan) if plan.status in FOLLOWED else {'detected': set(), 'metrics': {}, 'signals': []}
    if plan.status == 'pending_professional_review':
        key = 'pending'
        reasons.append(texts.DIRECTION_REASONS['pending'].format(owner_cap=texts.capitalize(owner)))
    elif plan.status == 'paused':
        key = 'paused'
        reasons.append(texts.DIRECTION_REASONS['paused'].format(until=f' {fi_date(plan.pausedUntil)} asti' if plan.pausedUntil else ''))
    else:
        open_escalation = escalation.open_escalation(state, plan)
        last = next(iter(reversed(rounds(state, plan, since_baseline=True))), None)
        period = _latest_period(state, plan)
        if open_escalation:
            key = 'professional'
            reasons.append(texts.DIRECTION_REASONS['escalated'].format(label=open_escalation.urgencyLabel, owner=owner,
                                                                       handling=open_escalation.handlingTime))
            reasons.extend(f"Sääntö {r['id']}: {r['name']}." for r in open_escalation.rulesApplied)
        else:
            if last and last['feedback'] == 'none':
                barrier = f" (este: {last['barrier'].lower()})" if last['barrier'] else ''
                reasons.append(texts.DIRECTION_REASONS['goal_none'].format(barrier=barrier))
            decided = (plan.lastProfessionalDecision or {}).get('date')
            new_readings = not decided or (obs['metrics'].get('lastMeasurementDate') or '') > decided
            if 'trend_rising' in obs['detected'] and obs['metrics'].get('trendDelta') is not None and new_readings:
                reasons.append(texts.DIRECTION_REASONS['trend_rising'].format(delta=f"{obs['metrics']['trendDelta']:+d}"))
            if period and period.status == 'offered':
                reasons.append(texts.DIRECTION_REASONS['monitoring_offered'].format(days=texts.days_genitive(period.days)))
            elif period and period.status == 'active':
                reasons.append(texts.DIRECTION_REASONS['monitoring_active'].format(n=len(period.readingIds), total=period.days * period.perDay))
            elif period and period.status == 'completed' and period.planVersion == plan.version \
                    and period.result.get('direction') == 'adjust' and signals.days_between(period.completedAt, state.currentDate) <= 14:
                reasons.append(texts.DIRECTION_REASONS['monitoring_above'].format(avg=_average_text(period.result.get('average'))))
            if reasons:
                key = 'adjust'
            else:
                key = 'continue'
                if last and last['feedback'] in ('met', 'partial'):
                    reasons.append(texts.DIRECTION_REASONS['goal_met' if last['feedback'] == 'met' else 'goal_partial'])
                if period and period.status == 'completed' and period.result.get('direction') == 'continue':
                    reasons.append(texts.DIRECTION_REASONS['monitoring_ok'].format(avg=_average_text(period.result.get('average'))))
                if plan.version > 1 and plan.lastProfessionalDecision and not last:
                    reasons.append(texts.DIRECTION_REASONS['new_version'].format(owner_cap=texts.capitalize(owner), version=plan.version))
                if plan.measurementCode == 'LDL' and plan.nextReviewAt:
                    reasons.append(texts.DIRECTION_REASONS['lab_review'].format(date=fi_date(plan.nextReviewAt)))
                if not reasons:
                    reasons.append(texts.DIRECTION_REASONS['started' if plan.goal else 'stable'])
    labels = config.get(key, {})
    return {
        'planId': plan.id, 'planName': plan.name, 'key': key, 'label': labels.get('label', key), 'detail': labels.get('detail', ''),
        'reasons': reasons,
        'watch': _watch(state, plan, obs) if plan.status in FOLLOWED else [],
        'professionalWhen': professional_when(plan),
        'nextEvaluation': plan.nextCheckInAt if plan.status == 'active' and plan.microInterventions else plan.nextReviewAt,
    }


# --- 1 remember: the memory itself --------------------------------------------------------------------------------------

def _frequency(per_week: int) -> str:
    if per_week >= 14:
        return 'aamulla ja illalla joka päivä'
    if per_week == 7:
        return 'kerran päivässä'
    return f'{texts.times_per_week(per_week)} viikossa'


def memory(state: LoopState) -> dict[str, Any]:
    sections: dict[str, list[dict]] = {key: [] for key in texts.MEMORY_TITLES}
    plans = sorted((p for p in state.support.plans if p.status in VISIBLE), key=lambda p: (p.goal is None, p.createdAt))
    for plan in plans:
        pending = plan.status == 'pending_professional_review'
        owner = texts.owner_possessive(plan.owner.role)
        approved = f'{plan.approval.byRole}, {fi_date(plan.approval.at)}' if plan.approval.status == 'approved' else None
        proposal = f'Ehdotus – odottaa {owner} hyväksyntää'
        # goals
        if plan.demoTarget:
            sections['goals'].append(_item(plan.demoTarget['label'], detail=plan.demoTarget.get('setBy'),
                                           source=proposal if pending else approved or plan.owner.label, pending=pending))
        if plan.goal:
            source = (proposal if pending else f'Sovittu kanssasi {fi_date(plan.goal.setAt)} {owner} hyväksymissä rajoissa'
                      if plan.goal.setBy == 'agent_with_user' else f'{plan.owner.label}, {fi_date(plan.goal.setAt)}')
            sections['goals'].append(_item(f'Liikunta: {plan.goal.label}', source=source, pending=pending))
        if not plan.goal and not plan.demoTarget:
            sections['goals'].append(_item(policies.theme(plan.theme).get('userGoal', plan.objective),
                                           source=proposal if pending else approved or plan.owner.label, pending=pending))
        # agreed
        decision = plan.lastProfessionalDecision or {}
        if approved:
            updated = f", päivitetty {fi_date(decision['date'])}" if plan.version > 1 and decision.get('date') else ''
            sections['agreed'].append(_item(f'{plan.name}, versio {plan.version}', detail=self_care_text(plan.approval.note),
                                            source=f'{plan.approval.byRole} hyväksyi {fi_date(plan.approval.at)}{updated}'))
        for instruction in plan.professionalInstructions:
            sections['agreed'].append(_item(instruction.rstrip('.'),
                                            source=f"{decision.get('byRole') or plan.owner.label}, {fi_date(decision.get('date'))}"))
        # what you follow
        period = active_period(state, plan)
        if period:
            sections['monitor'].append(_item(f'Kotiseuranta {fi_date(period.startsAt)}–{fi_date(period.endsAt)} aamulla ja illalla',
                                             detail=f'{len(period.readingIds)}/{period.days * period.perDay} mittausta', origin='agent'))
        if plan.measurementCode == 'BP' and plan.measurementsPerWeek:
            average = signals.recent_average(state)
            sections['monitor'].append(_item(f'Verenpaine kotona {_frequency(plan.measurementsPerWeek)}',
                                             detail=f"Viimeisin keskiarvo {_average_text(average)} mmHg ({average['n']} mittausta)" if average else None,
                                             source=proposal if pending else plan.name, pending=pending))
        elif plan.measurementCode == 'LDL':
            labs = sorted((e for e in state.events if e.code == 'LDL' and e.type == 'lab_result'), key=lambda e: (e.date, e.id))
            sections['monitor'].append(_item('LDL-kolesteroli laboratoriossa',
                                             detail=f'Viimeisin {fi_value(labs[-1])} ({fi_date(labs[-1].date)})' if labs else None,
                                             source=plan.name, pending=pending))
        # when it is checked again
        if plan.status == 'active' and plan.nextCheckInAt and plan.microInterventions:
            sections['recheck'].append(_item('Viikkotarkistus: miten askel sujui', date=plan.nextCheckInAt, source=plan.name))
        if period:
            sections['recheck'].append(_item('Kotiseurannan yhteenveto', date=period.endsAt, source=plan.name, origin='agent'))
        open_escalation = escalation.open_escalation(state, plan)
        if open_escalation:
            sections['recheck'].append(_item(f'{texts.capitalize(owner)} ottaa yhteyttä {open_escalation.handlingTime}',
                                             date=open_escalation.createdAt, source=f'Automaattinen arvio: {open_escalation.urgencyLabel}'))
        if plan.nextReviewAt:
            sections['recheck'].append(_item(policies.theme(plan.theme).get('reviewLabel', f'{plan.name}: tarkistus'), date=plan.nextReviewAt,
                                             source=approved and f'Sovittu: {approved}' or plan.name))
        # tried / works from the agent's own rounds and home monitoring periods (newest first)
        for item in reversed(rounds(state, plan)):
            detail = item['feedbackLabel'] + (f", este: {item['barrier'].lower()}" if item['barrier'] else '')
            sections['tried'].append(_item(texts.capitalize(item['step']), detail=detail, date=item['date'], origin='agent', tone=item['tone']))
            if item['feedback'] == 'met':
                sections['works'].append(_item(f"{texts.capitalize(item['step'])} onnistui", date=item['date'], origin='agent', tone='positive'))
            if item['barrier']:
                sections['works'].append(_item(item['barrier'], detail=f"Este viikkotarkistuksessa {fi_date(item['date'])}", date=item['date'],
                                               origin='user', tone='barrier'))
        for done in sorted((p for p in plan_periods(state, plan) if p.status == 'completed'), key=lambda p: p.completedAt or '', reverse=True):
            average = done.result.get('average')
            sections['tried'].append(_item(f'Kotiseuranta {fi_date(done.startsAt)}–{fi_date(done.endsAt)}',
                                           detail=f'Keskiarvo {_average_text(average)} mmHg' if average else 'Ei mittauksia',
                                           date=done.completedAt, origin='agent'))
    for note in note_items(state):
        kind = note.pop('kind')
        note.pop('noteId', None)
        sections['works' if kind in ('works', 'barrier') else kind].append(note)
    sections['recheck'].sort(key=lambda item: item['date'] or '9999')
    sections['works'].sort(key=lambda item: (item['tone'] == 'barrier', -int((item['date'] or '0').replace('-', ''))))
    seen: set[str] = set()
    for key, items in sections.items():  # the same clause from two linked plans is shown once
        unique = []
        for item in items:
            signature = f"{key}|{item['text']}" if item['tone'] == 'barrier' else f"{key}|{item['text']}|{item['date']}"
            if signature not in seen:
                seen.add(signature)
                unique.append(item)
        sections[key] = unique
    return {
        'sections': [{'key': key, 'title': title, 'items': sections[key], 'empty': texts.MEMORY_EMPTY[key]}
                     for key, title in texts.MEMORY_TITLES.items()],
        'notesAllowed': consent.source_allowed(state, 'professionalNotes'),
        'notesNotice': None if consent.source_allowed(state, 'professionalNotes') else texts.MEMORY_NOTES_OFF,
        'notice': policy().get('notice'),
    }


# --- 2 reach out: what the agent did and will do on its own ----------------------------------------------------------------

def outreach(state: LoopState) -> dict[str, Any]:
    support = state.support
    settings = support.consent
    today = state.currentDate
    recent = [{'date': c['date'], 'kind': c['kind'], 'label': CONTACT_LABELS.get(c['kind'], c.get('label', 'Yhteydenotto'))}
              for c in reversed(support.contacts)][:5]
    upcoming: list[dict[str, Any]] = []
    rules: list[dict[str, str]] = []
    for plan in support.plans:
        if plan.status != 'active':
            continue
        if plan.nextCheckInAt and plan.microInterventions and 'check_in' in plan.allowedActions:
            upcoming.append({'date': plan.nextCheckInAt, 'label': f'Kysyn, miten askel sujui ({plan.name.lower()})'})
        if plan.nextReviewAt and 'reminder' in plan.allowedActions:
            before = next((s.get('params', {}).get('daysBefore', 7) for s in plan.signals if s['kind'] == 'review_date'), 7)
            upcoming.append({'date': max(today, add_days(plan.nextReviewAt, -before)),
                             'label': f"Muistutan: {policies.theme(plan.theme).get('reviewLabel', plan.name)} {fi_date(plan.nextReviewAt)}"})
        period = active_period(state, plan)
        if period:
            upcoming.append({'date': period.endsAt, 'label': 'Kokoan kotiseurannan yhteenvedon'})
        rule = outreach_rule(plan)
        if rule and 'offer_home_monitoring' in plan.allowedActions:
            rules.append({'id': rule['id'], 'text': f"{rule['name']}: ehdotan {texts.days_genitive(rule['params'].get('days', 3))} kotiseurantaa"})
    rules.extend([{'id': 'CHECK-IN', 'text': 'Viikkotarkistus: kysyn, miten askel sujui'},
                  {'id': 'REMINDER', 'text': 'Muistutus, jos sovittu mittaus puuttuu tai tarkistuspäivä lähestyy'}])
    return {
        'recent': recent,
        'upcoming': sorted(upcoming, key=lambda u: u['date'])[:5],
        'rules': rules,
        'offer': _period_view(open_offer(state)),
        'active': _period_view(active_period(state)),
        'settings': {
            'proactive': settings.proactiveContact, 'channel': consent.CHANNEL_LABELS[settings.channel],
            'maxPerWeek': settings.maxContactsPerWeek, 'usedThisWeek': consent.contacts_last_week(state),
            'quietHours': f'{settings.quietHours.start}–{settings.quietHours.end}', 'pausedUntil': settings.pausedUntil,
        },
    }


# --- the read model and the chat answers ------------------------------------------------------------------------------------

def _sorted_directions(state: LoopState, plans: list[SupportPlan]) -> list[dict[str, Any]]:
    """The one that needs the most attention first; on a tie the plan with a step of its own (the self-care in progress)."""
    has_step = {p.id: p.goal is not None for p in plans}
    return sorted((direction(state, p) for p in plans), key=lambda d: (DIRECTION_ORDER.get(d['key'], 9), not has_step.get(d['planId'])))


def build(state: LoopState) -> dict[str, Any]:
    if not state.support.person:
        return {'available': False}
    config = policy()
    visible = [p for p in state.support.plans if p.status in VISIBLE]
    directions = _sorted_directions(state, visible)
    steps = [s for s in (current_step(state, p) for p in sorted(visible, key=lambda p: ('pending' in p.status, p.createdAt))) if s]
    latest = [p for p in state.support.homeMonitoring if p.status == 'completed']
    return {
        'available': True,
        'name': config.get('name'),
        'tagline': config.get('tagline'),
        'coreTasks': list(config.get('coreTasks', [])),
        'memory': memory(state),
        'outreach': outreach(state),
        'step': steps[0] if steps else None,
        'steps': steps,
        'direction': directions[0] if directions else None,
        'directions': directions,
        'homeMonitoring': {
            'offer': _period_view(open_offer(state)),
            'active': _period_view(active_period(state)),
            'latest': _period_view(max(latest, key=lambda p: (p.completedAt or '', p.id)) if latest else None),
        },
    }


def memory_chat_text(state: LoopState) -> str:
    lines = [texts.CHAT_MEMORY_INTRO]
    for section in memory(state)['sections']:
        if not section['items']:
            continue
        lines.extend(['', section['title']])
        for item in section['items'][:4]:
            when = f"{fi_date(item['date'])}: " if section['key'] == 'recheck' and item['date'] else ''
            label = 'Haaste: ' if item['tone'] == 'barrier' else ''
            detail = f" – {item['detail'][:1].lower()}{item['detail'][1:]}" if item['detail'] and section['key'] in ('monitor', 'tried') else ''
            source = f" ({item['source']})" if item['source'] and section['key'] not in ('recheck', 'monitor') else ''
            lines.append(f'• {when}{label}{item["text"]}{detail}{source}')
    lines.extend(['', texts.CHAT_MEMORY_NOTE])
    return '\n'.join(lines)


def step_chat_text(state: LoopState) -> str:
    visible = sorted((p for p in state.support.plans if p.status in FOLLOWED), key=lambda p: p.createdAt)
    step = next((s for s in (current_step(state, p) for p in visible) if s), None)
    if not step or not step['startedAt']:
        return texts.CHAT_STEP_NONE
    plan = plans_module.find(state, step['planId'])
    lines = [texts.CHAT_STEP.format(step=step['text'], start=fi_date(step['startedAt']), end=fi_date(step['endsAt']),
                                    feedback=fi_date(step['feedbackAt']), owner=texts.owner_possessive(plan.owner.role))]
    if step['rounds']:
        last = step['rounds'][0]
        lines.append(f"Edellinen kierros {fi_date(last['date'])}: {last['step']} – {last['feedbackLabel'].lower()}. {last['adaptationLabel']}.")
    period = active_period(state, plan)
    if period:
        lines.append(f'Lisäksi kotiseuranta on käynnissä {fi_date(period.startsAt)}–{fi_date(period.endsAt)}: '
                     f'{len(period.readingIds)}/{period.days * period.perDay} mittausta.')
    return '\n\n'.join(lines)


def direction_chat_text(state: LoopState) -> str:
    visible = [p for p in state.support.plans if p.status in VISIBLE]
    directions = _sorted_directions(state, visible)
    lines = [texts.CHAT_DIRECTION_INTRO]
    for item in directions:
        lines.append(f"• {item['planName']}: {item['label']}. {' '.join(item['reasons'])}")
    followed = [d for d in directions if d['key'] != 'pending'] or directions
    main = max(followed, key=lambda d: len(d['professionalWhen'])) if followed else None
    if main:
        lines.extend(['', texts.DIRECTION_PROFESSIONAL_WHEN, *(f"• {rule['text']} ({rule['id']})" for rule in main['professionalWhen'])])
    lines.extend(['', texts.CHAT_DIRECTION_NOTE])
    return '\n'.join(lines)


def chat_basis(state: LoopState, decision_by: str) -> dict[str, Any]:
    """'Mihin tämä perustuu?' for the continuity answers in the chat: the plans behind them, never an LLM decision."""
    plans = [p for p in state.support.plans if p.status in VISIBLE]
    notes = consent.source_allowed(state, 'professionalNotes')
    return {
        'monitorings': [{'id': p.id, 'finding': f'{p.name} (versio {p.version})', 'status': texts.PLAN_STATUS_LABELS[p.status]} for p in plans],
        'events': ['Ammattilaisten kirjaukset (sallittu tietolähde)' if notes else 'Ammattilaisten kirjauksia ei käytetty (suostumus)',
                   'Viikkotarkistusten vastauksesi ja kotiseurannat'],
        'userProvided': [],
        'evidenceSource': messages.EVIDENCE_SOURCE,
        'rules': [],
        'decisionBy': decision_by,
        'textBy': 'Valmis tekstipohja',
        'statement': ('Vastaus koottiin valmiista tekstipohjista suunnitelmiesi, ammattilaisten kirjausten ja vastaustesi perusteella '
                      'sääntöjen mukaan. Kielimalli ei tehnyt päätöksiä.'),
    }

