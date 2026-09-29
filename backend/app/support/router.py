"""API for support plans, the agent cycle, professional decisions, consent, audit, impact and adapters."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.loop.router import _dashboard, _finding_from_session
from app.loop.store import transaction
from app.support import (adapters, assessment, cohort, continuity, cycle, demo, genetic_links, interventions, plan_state, professional,
                         user_actions)
from app.support.models import PersonProfile

router = APIRouter(prefix='/api/support', tags=['Agenttinen hyvinvointikumppani'])

HANDLED_ERRORS = (
    cycle.CycleError, interventions.InterventionError, professional.ProfessionalError, user_actions.SettingsError,
    demo.DemoError, plan_state.PlanStateError, adapters.AdapterError, assessment.AssessmentError, genetic_links.GeneticLinkError,
    continuity.ContinuityError,
)


class MeasurementRequest(BaseModel):
    systolic: int
    diastolic: int


class AnswerRequest(BaseModel):
    questionId: str
    optionId: Optional[str] = None
    skip: bool = False


class DecisionRequest(BaseModel):
    decision: Literal['approve', 'edit', 'reject', 'request_info', 'continue', 'change_permissions', 'contact_user', 'end', 'set_review_date']
    role: str = 'nurse'
    note: Optional[str] = None
    changes: Optional[dict[str, Any]] = None
    reviewDate: Optional[str] = None
    allowedActions: Optional[list[str]] = None
    escalationAppropriate: Optional[bool] = None
    contactUser: bool = False


class PauseRequest(BaseModel):
    until: Optional[str] = None


class ReviewRequest(BaseModel):
    findingId: str
    sessionId: str


class InsightDecisionRequest(BaseModel):
    decision: Literal['approve', 'reject', 'refer', 'request_info']
    role: str = 'physician'
    note: Optional[str] = None
    ownerRole: Optional[str] = None


class PreviewRequest(BaseModel):
    format: Literal['csv', 'json']
    content: str
    table: Optional[str] = None
    personId: Optional[str] = None


class GeneticLinkRequest(BaseModel):
    sessionId: Optional[str] = None  # the user's own DNA analysis, when it has been run


class HomeMonitoringAnswer(BaseModel):
    accept: bool


class AssessmentReviewRequest(BaseModel):
    decision: Literal['confirm', 'change_urgency', 'take_over']
    role: str = 'nurse'
    note: Optional[str] = None
    newUrgency: Optional[Literal['emergency', 'same_day', 'within_3_days', 'routine', 'self_care']] = None


def _run(action) -> dict:
    """Run a state mutation in one transaction and return the full dashboard, mapping domain errors to 400."""
    with transaction() as state:
        try:
            result = action(state)
        except HANDLED_ERRORS as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {'result': result, 'dashboard': _dashboard(state)}


@router.post('/cycle')
def run_cycle():
    return _run(lambda state: cycle.run_cycle(state, 'käynnistetty demo-ohjauksesta'))


@router.post('/simulate/week')
def simulate_week():
    return _run(lambda state: cycle.simulate_days(state, 7))


@router.post('/measurements')
def add_measurement(request: MeasurementRequest):
    return _run(lambda state: cycle.add_home_measurement(state, request.systolic, request.diastolic, via='user'))


@router.post('/simulate/measurement')
def simulate_measurement():
    return _run(demo.scripted_measurement)


@router.post('/simulate/user-response')
def simulate_user_response():
    return _run(demo.scripted_user_response)


@router.post('/simulate/professional-decision')
def simulate_professional_decision():
    return _run(demo.scripted_professional_decision)


@router.post('/simulate/symptom-report')
def simulate_symptom_report():
    return _run(demo.scripted_symptom_report)


@router.post('/simulate/home-monitoring')
def simulate_home_monitoring():
    return _run(demo.scripted_home_monitoring)


# --- the self-care continuity engine: the home monitoring the agent offered on its own ------------------------------------

@router.post('/home-monitoring/{period_id}/respond')
def respond_home_monitoring(period_id: str, request: HomeMonitoringAnswer):
    """The user decides whether the offered home monitoring period starts."""
    return _run(lambda state: continuity.respond(state, period_id, request.accept, via='home').model_dump())


# --- automated assessment of the need for care and its urgency ---------------------------------------------------------

@router.post('/assessments/{assessment_id}/request-human-review')
def request_human_review(assessment_id: str):
    """The user's right to an assessment made by a healthcare professional (terveydenhuoltolaki 51 § 3 mom., assumed 2027)."""
    return _run(lambda state: assessment.view(state, assessment.request_human_review(state, assessment_id, via='home')))


@router.post('/assessments/{assessment_id}/review')
def review_assessment(assessment_id: str, request: AssessmentReviewRequest):
    """Professional oversight: confirm the automated assessment, change its urgency class or make the assessment."""
    return _run(lambda state: assessment.view(state, assessment.professional_review(
        state, assessment_id, request.decision, role=request.role, note=request.note, new_urgency=request.newUrgency)))


# --- linking health records to DNA-analysis findings (Terveystiedot) ----------------------------------------------------

@router.post('/genetic-links')
def link_genetics(request: GeneticLinkRequest):
    """Link health care records to DNA-analysis findings by health theme (rules only; gates 2 and 3 apply)."""
    def action(state):
        genetic_links.link(state, request.sessionId)
        return genetic_links.view(state)
    return _run(action)


@router.delete('/genetic-links')
def unlink_genetics():
    return _run(genetic_links.unlink)


@router.post('/checkins/{checkin_id}/answer')
def answer_checkin(checkin_id: str, request: AnswerRequest):
    return _run(lambda state: interventions.answer(state, checkin_id, request.questionId, request.optionId, request.skip, via='home'))


@router.post('/plans/{plan_id}/decision')
def plan_decision(plan_id: str, request: DecisionRequest):
    return _run(lambda state: professional.decide(
        state, plan_id, request.decision, role=request.role, note=request.note, changes=request.changes, review_date=request.reviewDate,
        allowed_actions=request.allowedActions, escalation_appropriate=request.escalationAppropriate, contact_user=request.contactUser,
    ).model_dump())


@router.post('/plans/{plan_id}/pause')
def pause_plan(plan_id: str, request: PauseRequest):
    return _run(lambda state: user_actions.pause_plan(state, plan_id, request.until))


@router.post('/plans/{plan_id}/resume')
def resume_plan(plan_id: str):
    return _run(lambda state: user_actions.resume_plan(state, plan_id))


@router.put('/consent')
def update_consent(changes: dict[str, Any]):
    return _run(lambda state: user_actions.update_consent(state, changes))


@router.post('/insights/request-review')
def request_review(request: ReviewRequest):
    with transaction() as state:
        finding, significance = _finding_from_session(request.sessionId, request.findingId, with_significance=True)
        try:
            insight = professional.request_review(state, finding, significance)
        except HANDLED_ERRORS as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {'result': insight.model_dump(), 'dashboard': _dashboard(state)}


@router.post('/insights/{insight_id}/decision')
def insight_decision(insight_id: str, request: InsightDecisionRequest):
    return _run(lambda state: professional.decide_insight(state, insight_id, request.decision, role=request.role, note=request.note,
                                                          owner_role=request.ownerRole).model_dump())


@router.get('/cohort')
def cohort_page(page: int = Query(1, ge=1), pageSize: int = Query(25, ge=1, le=cohort.MAX_PAGE_SIZE),
                status: Optional[str] = None, theme: Optional[str] = None, ageBand: Optional[str] = None):
    return cohort.page(page, pageSize, status or None, theme or None, ageBand or None)


@router.get('/impact/cohort')
def cohort_impact():
    return cohort.aggregate()


@router.post('/adapters/preview')
def adapter_preview(request: PreviewRequest):
    if len(request.content) > 200_000:
        raise HTTPException(status_code=413, detail='Esikatseltava sisältö on liian suuri (enintään 200 000 merkkiä).')
    try:
        return adapters.preview(request.format, request.content, request.table, request.personId)
    except (adapters.AdapterError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/schema/person-profile')
def person_profile_schema():
    return PersonProfile.model_json_schema()
