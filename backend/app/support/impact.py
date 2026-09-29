"""Light impact view for the demo person (simulated from the demo state). Never presented as clinical results."""
from __future__ import annotations

from typing import Any

from app.loop.models import LoopState
from app.support import signals


def person_metrics(state: LoopState) -> dict[str, Any]:
    support = state.support
    checkins = support.checkIns
    completed = [c for c in checkins if c.status == 'completed']
    goal_answers = [c.outcome.get('goal') for c in completed if c.outcome.get('goal')]
    tasks_done = sum(1 for a in goal_answers if a in ('met', 'partial')) + sum(c.outcome.get('measurementsDone', 0) for c in completed)
    tasks_agreed = len(goal_answers) + sum(c.outcome.get('measurementsRequired', 0) for c in completed)
    escalations = support.escalations
    decided = [e for e in escalations if e.appropriate is not None]
    assessments = support.assessments
    # "signal -> action": days from a detected signal to the agent's first action in the same cycle chain
    detect_dates: dict[str, str] = {}
    delays = []
    for entry in support.audit:
        if entry.chainId and entry.stage == 'detect' and entry.signal and entry.signal.get('detected'):
            detect_dates.setdefault(entry.chainId, entry.date)
        if entry.chainId and entry.stage in ('act', 'assess', 'escalate') and entry.chainId in detect_dates:
            delays.append(signals.days_between(detect_dates.pop(entry.chainId), entry.date))
    ratings = [f['rating'] for f in support.feedback]
    by_urgency: dict[str, int] = {}
    for item in assessments:
        by_urgency[item.urgency] = by_urgency.get(item.urgency, 0) + 1
    return {
        'synthetic': True,
        'activePlans': sum(1 for p in support.plans if p.status in ('active', 'escalated', 'paused')),
        'selfCareTasksDone': tasks_done,
        'selfCareTasksAgreed': tasks_agreed,
        'reminders': sum(1 for c in support.contacts if c['kind'] in ('reminder', 'review_reminder')),
        'microInterventions': len(checkins),
        'adaptiveFollowUps': sum(1 for c in checkins for q in c.questions if q.kind in ('barrier', 'smaller_goal', 'contact_request')),
        'goalAdjustments': sum(1 for p in support.plans for h in p.history if h.actor == 'agent'),
        'escalations': len(escalations),
        'escalationsAppropriate': sum(1 for e in decided if e.appropriate),
        'escalationsDecided': len(decided),
        'resolvedWithoutEscalation': sum(1 for c in completed if c.outcome.get('goal') in ('met', 'partial') or c.outcome.get('newGoal')),
        'avgDaysSignalToAction': round(sum(delays) / len(delays), 1) if delays else None,
        'waitingForProfessional': sum(1 for p in support.plans if p.status == 'pending_professional_review')
        + sum(1 for e in escalations if e.status == 'open')
        + sum(1 for i in support.insights if i.kind == 'genetic' and i.reviewStatus in ('pending_professional_review', 'info_requested')),
        'usefulnessAvg': round(sum(ratings) / len(ratings), 1) if ratings else None,
        'usefulnessAnswers': len(ratings),
        # automated assessments of the need for care and its urgency (rules decide; professional oversight)
        'assessments': len(assessments),
        'assessmentsAutomated': sum(1 for a in assessments if a.mode == 'automated'),
        'assessmentsConfirmed': sum(1 for a in assessments if a.status == 'confirmed'),
        'assessmentsChanged': sum(1 for a in assessments if a.status in ('changed', 'human_reviewed')),
        'humanReviewRequests': sum(1 for a in assessments if a.humanReviewRequestedAt),
        'assessmentsByUrgency': by_urgency,
        'avgMinutesToAssessment': 0 if assessments else None,  # the demo assesses immediately when the rule fires ("heti")
    }
