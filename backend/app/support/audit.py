"""Audit trail: every observation, decision, action, response, escalation and professional decision."""
from __future__ import annotations

from typing import Any, Optional

from app.loop.models import LoopState
from app.loop.store import next_id
from app.support.models import AuditEntry, SupportPlan


def record(
    state: LoopState,
    *,
    stage: str,
    actor: str,
    detail: str,
    plan: Optional[SupportPlan] = None,
    chain_id: Optional[str] = None,
    signal: Optional[dict[str, Any]] = None,
    rule: Optional[dict[str, Any]] = None,
    action: Optional[str] = None,
    llm_used: bool = False,
    llm_task: Optional[str] = None,
    outcome: Optional[str] = None,
    user_response: Optional[str] = None,
    escalated: bool = False,
    professional_decision: Optional[str] = None,
) -> AuditEntry:
    support = state.support
    entry = AuditEntry(
        id=next_id(state, 'audit'),
        seq=len(support.audit) + 1,
        date=state.currentDate,
        personId=support.person.demographics.personId if support.person else None,
        planId=plan.id if plan else None,
        planVersion=plan.version if plan else None,
        chainId=chain_id,
        stage=stage,
        actor=actor,
        signal=signal,
        rule=rule,
        action=action,
        detail=detail,
        llmUsed=llm_used,
        llmTask=llm_task,
        outcome=outcome,
        userResponse=user_response,
        escalated=escalated,
        professionalDecision=professional_decision,
    )
    support.audit.append(entry)
    return entry


def new_chain(state: LoopState) -> str:
    return next_id(state, 'chain')
