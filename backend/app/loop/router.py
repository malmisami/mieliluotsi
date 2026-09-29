from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.loop import agent, companion
from app.loop.evidence import genomic_finding_from_match, load_profile
from app.loop.models import GenomicFinding
from app.loop.store import clear_state, load_state, reset_state, transaction
from app.loop.summary_html import render_full_summary_html, render_summary_html
from app.services.session_manager import SessionManager
from app.support import cycle as support_cycle
from app.support import interventions as support_interventions
from app.support import professional as support_professional
from app.support import view as support_view

router = APIRouter(prefix='/api/loop', tags=['OmaGenomi Loop'])


class FindingRef(BaseModel):
    findingId: str
    sessionId: str | None = None


class DemoEventRequest(BaseModel):
    template: Literal['irrelevant_bp', 'high_ldl', 'new_medication', 'research_update']


class FreeTextRequest(BaseModel):
    text: str


class AdvanceTimeRequest(BaseModel):
    days: int = 30


class TaskResponseRequest(BaseModel):
    response: Literal['yes', 'not_yet', 'no_reminder', 'not_relevant']


class ChatMessageRequest(BaseModel):
    text: str


class ChatActionRequest(BaseModel):
    args: dict = {}


class LifestyleQuizRequest(BaseModel):
    structuredData: dict
    rawText: str


def _dashboard(state) -> dict:
    """Every mutation ends here: the companion reacts to state changes, then the full view is returned."""
    companion.sync_proactive(state)
    support_interventions.sync_chat(state)
    return {**agent.dashboard(state), 'companion': companion.view(state), 'support': support_view.view(state)}


def _raise(exc: agent.LoopError):
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _finding_from_session(session_id: str, match_id: str, with_significance: bool = False):
    state = SessionManager.get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail='Analyysi-istuntoa ei löytynyt. Aja analyysi uudelleen.')
    db = SessionManager.get_session_db(session_id)
    row = db.execute('SELECT * FROM matched_findings WHERE id = ?', (match_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail='Löydöstä ei löytynyt analyysistä.')
    finding = genomic_finding_from_match(dict(row), state.get('input_source'))
    return (finding, row['clinical_significance']) if with_significance else finding


def _resolve_finding(state, ref: FindingRef) -> tuple[GenomicFinding, str | None]:
    """The finding plus its raw classification, which gate 1 uses to decide whether it may go to review."""
    if ref.sessionId:
        return _finding_from_session(ref.sessionId, ref.findingId, with_significance=True)
    finding = next((item for item in state.findings if item.id == ref.findingId), None)
    if not finding:
        raise HTTPException(status_code=404, detail='Löydöstä ei löytynyt.')
    insight = next((i for i in state.support.insights if i.findingId == finding.id), None)
    return finding, insight.significance if insight else finding.classification


@router.get('/state')
def get_state():
    with transaction() as state:
        return _dashboard(state)


@router.post('/monitoring/preview')
def preview_monitoring(ref: FindingRef):
    state = load_state()
    return agent.monitoring_preview(state, _resolve_finding(state, ref)[0])


@router.post('/monitorings')
def create_monitoring(ref: FindingRef):
    """Gate 2: a genetic finding starts monitoring only after a professional has approved it; otherwise the
    request becomes a professional review item and nothing affects the user's follow-up yet."""
    with transaction() as state:
        finding, significance = _resolve_finding(state, ref)
        if not finding.monitoringEligible:
            raise HTTPException(status_code=400, detail='Tätä löydöstä ei voi ottaa seurantaan.')
        try:
            result = support_professional.gate_monitoring(state, finding, significance)
        except (agent.LoopError, support_professional.ProfessionalError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        monitoring = result.get('monitoring')
        insight = result.get('insight')
        return {
            'status': result['status'],
            'monitoring': monitoring.model_dump() if monitoring else None,
            'insight': insight.model_dump() if insight else None,
            'dashboard': _dashboard(state),
        }


@router.post('/monitorings/{monitoring_id}/stop')
def stop_monitoring(monitoring_id: str):
    with transaction() as state:
        try:
            agent.stop_monitoring(state, monitoring_id)
        except agent.LoopError as exc:
            _raise(exc)
        return {'dashboard': _dashboard(state)}


@router.post('/demo/events')
def add_demo_event(request: DemoEventRequest):
    template = dict(load_profile()['eventTemplates'][request.template])
    template.pop('label_fi', None)
    template.pop('hiddenInUi', None)
    with transaction() as state:
        result = agent.add_event(state, fields=template)
        _observe(state, result)
        return {**result, 'dashboard': _dashboard(state)}


def _observe(state, result: dict) -> None:
    """New data is observed by the support agent too (it contacts the user only if a safety rule requires it)."""
    event = next((e for e in state.events if e.id == result['event']['id']), None)
    if event:
        result['supportAgent'] = support_cycle.observe_event(state, event)


@router.post('/events/free-text')
def add_free_text_event(request: FreeTextRequest):
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail='Teksti puuttuu.')
    if len(text) > 2000:
        raise HTTPException(status_code=413, detail='Teksti on liian pitkä.')
    with transaction() as state:
        result = agent.add_event(state, raw_text=text, source='Synteettinen vapaamuotoinen terveysteksti')
        _observe(state, result)
        return {**result, 'dashboard': _dashboard(state)}


@router.post('/lifestyle-quiz')
def submit_lifestyle_quiz(request: LifestyleQuizRequest):
    if len(request.rawText) > 4000:
        raise HTTPException(status_code=413, detail='Vastausten yhteenveto on liian pitkä.')
    with transaction() as state:
        agent.add_lifestyle_quiz_result(state, request.structuredData, request.rawText)
        return {'dashboard': _dashboard(state)}


@router.post('/demo/advance-time')
def advance_time(request: AdvanceTimeRequest):
    if not 1 <= request.days <= 365:
        raise HTTPException(status_code=400, detail='Päivien määrän tulee olla 1–365.')
    with transaction() as state:
        result = support_cycle.simulate_days(state, request.days)
        return {**result, 'dashboard': _dashboard(state)}


@router.post('/demo/reset')
def reset_demo():
    reset_state()
    with transaction() as state:
        return {'dashboard': _dashboard(state)}


@router.post('/data/clear')
def clear_all_data():
    clear_state()
    with transaction() as state:
        return {'dashboard': _dashboard(state)}


@router.post('/companion/messages')
def companion_message(request: ChatMessageRequest):
    with transaction() as state:
        try:
            result = companion.handle_user_message(state, request.text)
        except companion.CompanionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {**result, 'dashboard': _dashboard(state)}


@router.post('/companion/actions/{action_id}')
def companion_action(action_id: str, request: ChatActionRequest):
    with transaction() as state:
        try:
            result = companion.handle_action(state, action_id, request.args)
        except companion.CompanionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {**result, 'dashboard': _dashboard(state)}


@router.post('/tasks/{task_id}/respond')
def respond_task(task_id: str, request: TaskResponseRequest):
    with transaction() as state:
        try:
            task = agent.respond_to_task(state, task_id, request.response)
        except agent.LoopError as exc:
            _raise(exc)
        return {'task': task.model_dump(), 'dashboard': _dashboard(state)}


@router.get('/observations/{observation_id}/summary')
def get_summary(observation_id: str):
    with transaction() as state:
        try:
            return agent.professional_summary(state, observation_id)
        except agent.LoopError as exc:
            _raise(exc)


@router.get('/observations/{observation_id}/summary.html', response_class=HTMLResponse)
def get_summary_html(observation_id: str):
    with transaction() as state:
        try:
            summary = agent.professional_summary(state, observation_id)
        except agent.LoopError as exc:
            _raise(exc)
    return HTMLResponse(render_summary_html(summary))


@router.get('/summary/full')
def get_full_summary():
    with transaction() as state:
        try:
            return agent.full_summary(state)
        except agent.LoopError as exc:
            _raise(exc)


@router.get('/summary/full.html', response_class=HTMLResponse)
def get_full_summary_html():
    with transaction() as state:
        try:
            summary = agent.full_summary(state)
        except agent.LoopError as exc:
            _raise(exc)
    return HTMLResponse(render_full_summary_html(summary))


@router.post('/observations/{observation_id}/share')
def share_observation(observation_id: str):
    with transaction() as state:
        try:
            agent.share_observation(state, observation_id)
        except agent.LoopError as exc:
            _raise(exc)
        return {'dashboard': _dashboard(state)}
