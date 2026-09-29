"""Agent messages to the user. The chat is one interface of the agent: everything the agent says proactively
is also a chat message, with a 'Mihin tämä perustuu?' basis pointing to the plan, version and rule."""
from __future__ import annotations

from typing import Any, Optional

from app.loop.models import ChatAction, ChatMessage, LoopState
from app.loop.store import next_id
from app.support.models import CareAssessment, SupportPlan
from app.support.texts import PLAN_STATUS_LABELS

BASIS_STATEMENT = (
    'Viesti on valmis, ennalta hyväksytty tekstipohja. Päätöksen yhteydenotosta teki agenttisykli '
    'ammattilaisen hyväksymän seurantasuunnitelman sääntöjen mukaan. Kielimalli ei tehnyt päätöstä.'
)
# automated assessment of the need for care and its urgency: the rule engine decides, the LLM never sets the class
ASSESSMENT_DECISION_BY = 'Sääntömoottori – automaattinen hoidon tarpeen arvio'
ASSESSMENT_STATEMENT = (
    'Hoidon tarpeen ja kiireellisyyden arvion teki sääntömoottori ammattilaisen hyväksymän suunnitelman ja demo-policyn '
    'sääntöjen mukaan. Kielimalli ei tehnyt arviota.'
)
EVIDENCE_SOURCE = 'Synteettiset demo-policyt (data/support/policies.json)'
CHANNEL_NOTES = {'sms': 'Lähetetty myös tekstiviestinä (mallinnettu).', 'email': 'Lähetetty myös sähköpostina (mallinnettu).'}


def action(state: LoopState, label: str, type_: str, style: str = 'primary', **args: Any) -> ChatAction:
    return ChatAction(id=next_id(state, 'act'), label=label, type=type_, args=args, style=style)


def basis(plan: SupportPlan, decision: str, rules: Optional[list[dict]] = None, facts: Optional[list[str]] = None) -> dict:
    return {
        'monitorings': [{'id': plan.id, 'finding': f'{plan.name} (versio {plan.version})', 'status': PLAN_STATUS_LABELS[plan.status]}],
        'events': facts or [],
        'userProvided': [],
        'evidenceSource': EVIDENCE_SOURCE,
        'rules': [{'id': r['id'], 'name': r['name'], 'demoNotice': 'Synteettinen demosääntö, ei hoitosuositus.'} for r in (rules or [])],
        'decisionBy': decision,
        'textBy': 'Valmis tekstipohja',
        'statement': BASIS_STATEMENT,
    }


def assessment_basis(assessment: CareAssessment, plan: Optional[SupportPlan] = None, decision_by: Optional[str] = None) -> dict:
    """'Mihin tämä perustuu?' for messages that carry an automated care-need assessment: rules and facts of the
    assessment, decided by the rule engine (never the LLM)."""
    monitorings = [{'id': plan.id, 'finding': f'{plan.name} (versio {plan.version})', 'status': PLAN_STATUS_LABELS[plan.status]}] if plan else []
    return {
        'monitorings': monitorings,
        'events': list(assessment.basis),
        'userProvided': [f'Kuvatut oireet: {", ".join(assessment.symptoms)}'] if assessment.symptoms else [],
        'evidenceSource': EVIDENCE_SOURCE,
        'rules': [{'id': r.get('id'), 'name': r.get('name') or r.get('id'), 'demoNotice': 'Synteettinen demosääntö, ei hoitosuositus.'}
                  for r in assessment.rulesApplied],
        'decisionBy': decision_by or ASSESSMENT_DECISION_BY,
        'textBy': 'Valmis tekstipohja',
        'statement': ASSESSMENT_STATEMENT,
        'assessmentId': assessment.id,
        'urgency': assessment.urgency,
        'urgencyLabel': assessment.urgencyLabel,
        'legalNotice': assessment.legalNotice,
    }


def assessment_ref(assessment: Optional[CareAssessment]) -> Optional[dict]:
    """The small assessment block a chat message carries so the client can show the urgency badge."""
    if not assessment:
        return None
    return {'id': assessment.id, 'urgency': assessment.urgency, 'urgencyLabel': assessment.urgencyLabel, 'mode': assessment.mode,
            'status': assessment.status}


def post(
    state: LoopState, text: str, *, kind: str, plan: Optional[SupportPlan] = None, actions: Optional[list[ChatAction]] = None,
    basis_data: Optional[dict] = None, initiated_by_agent: bool = True, assessment: Optional[CareAssessment] = None,
) -> ChatMessage:
    channel = state.support.consent.channel
    if initiated_by_agent and channel in CHANNEL_NOTES:
        text = f'{text}\n\n{CHANNEL_NOTES[channel]}'
    message = ChatMessage(
        id=next_id(state, 'msg'), role='agent', kind=kind, text=text, date=state.currentDate,
        initiatedByAgent=initiated_by_agent, intent='SUPPORT_PLAN', actions=actions or [], basis=basis_data,
        textSource='fixed' if kind == 'safety_threshold' else 'template', assessment=assessment_ref(assessment),
    )
    state.chatMessages.append(message)
    return message


def user_choice(state: LoopState, label: str) -> ChatMessage:
    message = ChatMessage(id=next_id(state, 'msg'), role='user', kind='action_choice', text=label, date=state.currentDate)
    state.chatMessages.append(message)
    return message
