"""Support plan state machine and versioning.

Status changes happen only through transition(); the version number counts professional-approved versions.
An agent's goal adjustment inside the approved range is recorded in the history but keeps the version.
"""
from __future__ import annotations

from typing import Optional

from app.loop.models import LoopState
from app.support.models import PlanChange, SupportPlan

TRANSITIONS: dict[str, set[str]] = {
    'candidate': {'pending_professional_review', 'rejected'},
    'pending_professional_review': {'active', 'rejected'},
    'active': {'paused', 'escalated', 'completed'},
    'paused': {'active', 'completed'},
    'escalated': {'active', 'completed'},
    'completed': set(),
    'rejected': set(),
}


class PlanStateError(ValueError):
    pass


def can_transition(plan: SupportPlan, target: str) -> bool:
    return target in TRANSITIONS.get(plan.status, set())


def transition(state: LoopState, plan: SupportPlan, target: str) -> None:
    if not can_transition(plan, target):
        raise PlanStateError(f'Tilasiirtymä {plan.status} → {target} ei ole sallittu.')
    if target == 'active' and plan.approval.status != 'approved':
        raise PlanStateError('Suunnitelmaa ei voi ottaa käyttöön ilman ammattilaisen hyväksyntää.')
    if target == 'active' and not plan.userConsent.given:
        raise PlanStateError('Suunnitelmaa ei voi ottaa käyttöön ilman käyttäjän suostumusta.')
    plan.status = target
    plan.updatedAt = state.currentDate


def add_history(
    state: LoopState, plan: SupportPlan, *, actor: str, summary: str, changes: Optional[list[str]] = None,
    actor_role: Optional[str] = None, bump: bool = False,
) -> PlanChange:
    if bump:
        plan.version += 1
    change = PlanChange(version=plan.version, date=state.currentDate, actor=actor, actorRole=actor_role,
                        summary=summary, changes=changes or [])
    plan.history.append(change)
    plan.updatedAt = state.currentDate
    return change
