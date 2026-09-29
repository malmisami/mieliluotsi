"""Observe -> compare -> detect: read the person's situation and compare it with the active plan version.

Pure reading, no side effects. Every threshold comes from the plan (set by a professional) or the demo
policy file; nothing is generated. Sources the user has switched off are not read at all.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from app.loop.models import OPEN_OBSERVATION_STATES, HealthEvent, LoopState
from app.support import consent
from app.support.models import CheckIn, SupportPlan


def days_between(earlier: str, later: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def bp_reading(event: HealthEvent) -> Optional[tuple[int, int, str]]:
    """(systolic, diastolic, context) for a blood-pressure event, or None."""
    if event.code != 'BP':
        return None
    data = event.structuredData or {}
    systolic, diastolic = data.get('systolic'), data.get('diastolic')
    if systolic is None or diastolic is None:
        if not isinstance(event.value, str) or '/' not in event.value:
            return None
        try:
            systolic, diastolic = (int(part) for part in event.value.split('/', 1))
        except ValueError:
            return None
    context = data.get('context') or ('home' if 'koti' in f'{event.displayName} {event.source}'.lower() else 'clinic')
    return int(systolic), int(diastolic), context


def home_readings(state: LoopState, until: Optional[str] = None) -> list[tuple[HealthEvent, int, int]]:
    readings = []
    for event in sorted(state.events, key=lambda e: (e.date, e.id)):
        if until and event.date > until:
            continue
        reading = bp_reading(event)
        if reading and reading[2] == 'home':
            readings.append((event, reading[0], reading[1]))
    return readings


def plan_checkins(state: LoopState, plan: SupportPlan) -> list[CheckIn]:
    return [c for c in state.support.checkIns if c.planId == plan.id]


def open_checkin(state: LoopState, plan: SupportPlan) -> Optional[CheckIn]:
    return next((c for c in plan_checkins(state, plan) if c.status == 'open'), None)


def period_start(state: LoopState, plan: SupportPlan) -> str:
    """Measurements count from the latest completed check-in (inclusive) or from plan activation."""
    completed = [c.createdAt for c in plan_checkins(state, plan) if c.status == 'completed']
    decided = (plan.lastProfessionalDecision or {}).get('date')
    candidates = [d for d in [plan.activatedAt, decided, *completed] if d]
    return max(candidates) if candidates else state.currentDate


def goal_answers(state: LoopState, plan: SupportPlan) -> list[str]:
    """Goal answers of completed check-ins, newest first."""
    answers = []
    for checkin in sorted(plan_checkins(state, plan), key=lambda c: c.seq, reverse=True):
        if checkin.status != 'completed' or checkin.seq <= plan.checkInBaselineSeq:
            continue
        goal = next((q for q in checkin.questions if q.kind == 'goal_progress' and q.answer), None)
        if goal:
            answers.append(goal.answer)
    return answers


def goal_failures_in_row(state: LoopState, plan: SupportPlan) -> int:
    count = 0
    for answer in goal_answers(state, plan):
        if answer != 'none':
            break
        count += 1
    return count


def recent_average(state: LoopState, lookback_days: int = 21, max_n: int = 4, min_n: int = 2) -> Optional[dict]:
    today = state.currentDate
    recent = [(e, s, d) for e, s, d in home_readings(state, until=today) if 0 <= days_between(e.date, today) <= lookback_days]
    recent = recent[-max_n:]
    if len(recent) < min_n:
        return None
    return {
        'systolic': round(sum(s for _, s, _ in recent) / len(recent)),
        'diastolic': round(sum(d for _, _, d in recent) / len(recent)),
        'n': len(recent),
        'from': recent[0][0].date,
        'to': recent[-1][0].date,
    }


def _earlier_average(state: LoopState, before: str, n: int = 2) -> Optional[dict]:
    earlier = [(e, s, d) for e, s, d in home_readings(state) if e.date < before][-n:]
    if len(earlier) < n:
        return None
    return {'systolic': round(sum(s for _, s, _ in earlier) / n), 'diastolic': round(sum(d for _, _, d in earlier) / n)}


def evaluate(state: LoopState, plan: SupportPlan) -> dict[str, Any]:
    """Returns {'detected': set of signal keys, 'metrics': {...}, 'signals': [per-signal result]}."""
    today = state.currentDate
    detected: set[str] = set()
    metrics: dict[str, Any] = {'planVersion': plan.version}
    results: list[dict[str, Any]] = []
    measurements_allowed = consent.source_allowed(state, 'measurements')
    signal_defs = {s['kind']: s for s in plan.signals}

    def add(kind: str, key: Optional[str], detail: str, **values: Any) -> None:
        definition = signal_defs.get(kind, {'id': kind, 'label': kind})
        results.append({'id': definition['id'], 'kind': kind, 'label': definition['label'], 'detected': bool(key),
                        'key': key, 'detail': detail, **values})
        if key:
            detected.add(key)

    if plan.measurementCode and not measurements_allowed:
        add('source', 'source_disabled', 'Mittaukset-tietolähde ei ole käytössä käyttäjän suostumusasetuksissa.')

    if plan.measurementCode == 'BP' and measurements_allowed:
        start = period_start(state, plan)
        in_period = [r for r in home_readings(state, until=today) if r[0].date >= start]
        metrics.update({'periodStart': start, 'measurementCount': len(in_period), 'measurementsRequired': plan.measurementsPerWeek})
        if 'measurement_frequency' in signal_defs and plan.measurementsPerWeek:
            missing = len(in_period) < plan.measurementsPerWeek and days_between(start, today) >= 1
            add('measurement_frequency', 'missing_measurement' if missing else None,
                f'Kotimittauksia {len(in_period)}/{plan.measurementsPerWeek} jaksolla {start}–{today}.',
                count=len(in_period), required=plan.measurementsPerWeek)
        params = signal_defs.get('measurement_average', {}).get('params', {})
        average = recent_average(state, params.get('lookbackDays', 21), params.get('maxMeasurements', 4), params.get('minMeasurements', 2))
        metrics['average'] = average
        if 'measurement_average' in signal_defs:
            target = plan.demoTarget or {}
            above = bool(average and target and (average['systolic'] > target['systolic'] or average['diastolic'] > target['diastolic']))
            detail = (f"Keskiarvo {average['systolic']}/{average['diastolic']} mmHg ({average['n']} mittausta), tavoitetaso "
                      f"alle {target.get('systolic')}/{target.get('diastolic')} mmHg." if average else 'Keskiarvoa ei voi laskea: liian vähän mittauksia.')
            add('measurement_average', 'above_target' if above else None, detail, average=average)
        if 'measurement_trend' in signal_defs and average:
            earlier = _earlier_average(state, average['from'])
            rise = signal_defs['measurement_trend']['params'].get('riseMmHg', 3)
            delta = average['systolic'] - earlier['systolic'] if earlier else None
            metrics['trendDelta'] = delta
            metrics['earlierAverage'] = earlier
            add('measurement_trend', 'trend_rising' if delta is not None and delta >= rise else None,
                f'Muutos aiempiin mittauksiin: {delta:+d} mmHg (yläpaine).' if delta is not None else 'Vertailutietoa ei ole.', delta=delta)
        readings = home_readings(state, until=today)
        last = readings[-1][0].date if readings else None
        metrics['lastMeasurementDate'] = last
        if 'data_freshness' in signal_defs:
            max_age = signal_defs['data_freshness']['params'].get('maxAgeDays', 14)
            stale = last is None or days_between(last, today) > max_age
            add('data_freshness', 'stale_data' if stale else None,
                f'Viimeisin kotimittaus {last or "puuttuu"}; enimmäisikä {max_age} päivää.')
        if 'safety_threshold' in signal_defs:
            limits = signal_defs['safety_threshold']['params']
            handled = _handled_safety_events(state)
            over = [e for e, s, d in readings if (s >= limits['systolic'] or d >= limits['diastolic']) and e.id not in handled]
            add('safety_threshold', 'safety_threshold' if over else None,
                f"Demo-turvaraja {limits['systolic']}/{limits['diastolic']} mmHg.", eventIds=[e.id for e in over])

    if plan.measurementCode == 'LDL' and measurements_allowed and 'data_freshness' in signal_defs:
        labs = sorted((e for e in state.events if e.code == 'LDL' and e.type == 'lab_result'), key=lambda e: e.date)
        last = labs[-1].date if labs else None
        max_age = signal_defs['data_freshness']['params'].get('maxAgeDays', 365)
        metrics['lastLabDate'] = last
        add('data_freshness', 'stale_data' if (last is None or days_between(last, today) > max_age) else None,
            f'Viimeisin LDL-tulos {last or "puuttuu"}; enimmäisikä {max_age} päivää.')

    if plan.goal and 'goal_completion' in signal_defs:
        failures = goal_failures_in_row(state, plan)
        answers = goal_answers(state, plan)
        metrics['goalFailuresInRow'] = failures
        key = 'repeated_goal_failure' if failures >= 2 else ('goal_not_met' if answers and answers[0] == 'none' else None)
        add('goal_completion', key, f'Tavoite ”{plan.goal.label}”: peräkkäisiä toteutumattomia tarkistuksia {failures}.', failures=failures)
        if failures >= 1:
            detected.add('goal_not_met')

    if plan.nextReviewAt and 'review_date' in signal_defs:
        days_left = days_between(today, plan.nextReviewAt)
        before = signal_defs['review_date']['params'].get('daysBefore', 7)
        key = 'review_overdue' if days_left < 0 else ('review_due_soon' if days_left <= before else None)
        add('review_date', key, f'Tarkistuspäivä {plan.nextReviewAt} ({days_left} päivän päästä).', daysLeft=days_left)

    if 'self_report' in signal_defs and consent.source_allowed(state, 'selfReportedData'):
        since = state.support.lastCycleAt or plan.activatedAt or today
        new = [e for e in state.events if e.type == 'self_report' and e.date > since]
        add('self_report', 'new_concern' if new else None, f'Uusia omia ilmoituksia {len(new)}.', eventIds=[e.id for e in new])

    if 'contact_pattern' in signal_defs and consent.source_allowed(state, 'interactionEvents'):
        params = signal_defs['contact_pattern']['params']
        topic = _plan_topic(plan)
        contacts = [e for e in state.events if e.type == 'contact' and e.structuredData.get('channel') != 'visit'
                    and 0 <= days_between(e.date, today) <= params.get('windowDays', 60)
                    and e.structuredData.get('topic') == topic]
        add('contact_pattern', 'repeated_contact' if len(contacts) >= params.get('minContacts', 2) else None,
            f'Yhteydenottoja aiheesta {topic} {len(contacts)} kpl {params.get("windowDays", 60)} päivän aikana.')

    if 'rule_engine_observation' in signal_defs:
        observations = [o for o in state.observations if o.status in OPEN_OBSERVATION_STATES and o.findingId in plan.linkedFindingIds]
        add('rule_engine_observation', 'rule_engine_observation' if observations else None,
            f'Sääntömoottorin avoimia huomioita {len(observations)}.', observationIds=[o.id for o in observations])

    if plan.nextCheckInAt and plan.nextCheckInAt <= today and not open_checkin(state, plan):
        detected.add('checkin_due')
        metrics['checkInDue'] = plan.nextCheckInAt

    return {'detected': detected, 'metrics': metrics, 'signals': results}


def _plan_topic(plan: SupportPlan) -> str:
    from app.support.policies import theme  # local import keeps this module free of file IO at import time

    return theme(plan.theme).get('topic', '')


def _handled_safety_events(state: LoopState) -> set[str]:
    handled: set[str] = set()
    for escalation in state.support.escalations:
        if escalation.trigger == 'safety_threshold':
            handled.update(s.id for s in escalation.sources if s.kind == 'event')
    return handled


SIGNAL_LABELS = {
    'missing_measurement': 'Sovittu mittaus puuttuu',
    'above_target': 'Keskiarvo sovitun tavoitetason yläpuolella',
    'trend_rising': 'Mittausten trendi nousussa',
    'goal_not_met': 'Sovittu tavoite ei toteutunut',
    'repeated_goal_failure': 'Sama tavoite ei ole toteutunut useasti',
    'review_due_soon': 'Tarkistuspäivä lähestyy',
    'review_overdue': 'Tarkistuspäivä on ohitettu',
    'stale_data': 'Tieto on vanhentunut',
    'new_concern': 'Käyttäjä ilmoitti uuden huolen',
    'repeated_contact': 'Toistuvia yhteydenottoja samasta aiheesta',
    'safety_threshold': 'Demo-turvaraja ylittyi',
    'rule_engine_observation': 'Sääntömoottorin avoin huomio',
    'source_disabled': 'Tietolähde pois käytöstä',
    'checkin_due': 'Viikkotarkistus on ajankohtainen',
}
