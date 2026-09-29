"""Build support plans from the demo policies (a theme's defaults are only a proposal until a professional approves)."""
from __future__ import annotations

from typing import Optional

from app.loop.models import LoopState
from app.loop.store import next_id
from app.support import policies
from app.support.models import EscalationRule, Goal, Owner, SourceRef, SupportPlan


def goal_from(state: LoopState, data: dict, set_by: str = 'professional') -> Goal:
    return Goal(
        id=next_id(state, 'goal'), label=data['label'], activity=data['activity'], timesPerWeek=data['timesPerWeek'],
        minutes=data.get('minutes'), minTimesPerWeek=data.get('minTimesPerWeek', 1), maxTimesPerWeek=data.get('maxTimesPerWeek', 3),
        setBy=set_by, setAt=state.currentDate,
    )


def build_plan(state: LoopState, theme_id: str, sources: list[SourceRef], status: str, diagnosis_label: Optional[str] = None) -> SupportPlan:
    theme = policies.theme(theme_id)
    defaults = theme.get('defaults', {})
    return SupportPlan(
        id=next_id(state, 'plan'),
        theme=theme_id,
        name=theme['name'],
        status=status,
        priority=theme.get('priority', 'normal'),
        rationale=theme['rationaleTemplate'].format(diagnosis=diagnosis_label or '–'),
        objective=theme['objective'],
        sources=sources,
        observationDates=sorted({s.date for s in sources if s.date}),
        measurementCode=theme.get('measurementCode'),
        measurementsPerWeek=defaults.get('measurementsPerWeek', 0),
        checkInEveryDays=defaults.get('checkInEveryDays', 7),
        demoTarget=defaults.get('demoTarget'),
        goal=goal_from(state, defaults['goal']) if defaults.get('goal') else None,
        signals=list(theme.get('signals', [])),
        allowedActions=list(theme.get('allowedActions', [])),
        forbiddenActions=list(policies.forbidden_labels()),
        microInterventions=list(theme.get('microInterventions', [])),
        guides=list(theme.get('guides', [])),
        escalationRules=[EscalationRule(**rule) for rule in theme.get('escalationRules', [])],
        owner=Owner(role=theme['defaultOwnerRole'], label=policies.owner_label(theme['defaultOwnerRole'])),
        createdAt=state.currentDate,
    )


def find(state: LoopState, plan_id: str) -> Optional[SupportPlan]:
    return next((p for p in state.support.plans if p.id == plan_id), None)


def review_after_days(plan: SupportPlan) -> int:
    return policies.theme(plan.theme).get('defaults', {}).get('reviewAfterDays', 90)
