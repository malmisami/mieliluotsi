"""The only data the companion LLM may see: a bounded, structured UserContext.

No raw DNA file, genotype rows, free-text originals or profile details are included.
"""
from __future__ import annotations

from app.loop.evidence import rules_for_gene, source_name
from app.loop.models import OPEN_OBSERVATION_STATES, LoopState
from app.support import consent
from app.wellbeing import context as wellbeing_context

USER_CONTEXT_KEYS = (
    'activeSupportPlans',
    'activeGenomicFindings',
    'currentMonitoringStates',
    'recentHealthEvents',
    'openObservations',
    'followUpTasks',
    'evidenceReferences',
    'knownMissingInformation',
    'wellbeingData',
)

RECENT_EVENT_LIMIT = 5


def _allowed_event(state: LoopState, event) -> bool:
    kind = (event.extractedData or {}).get('sourceKind')
    return consent.source_allowed(state, kind) if kind and state.support.person else True


def build_user_context(state: LoopState) -> dict:
    """Gate 3 applies here too: sources the user has switched off never reach the LLM, and gene names are
    left out unless the user allows genetic details to be shown."""
    genetic_ok = consent.genetic_allowed(state) or state.support.person is None
    show_genes = consent.show_genetic_details(state)
    active = [m for m in state.monitorings if m.active] if genetic_ok else []
    findings = {f.id: f for f in state.findings}
    active_findings = [findings[m.findingId] for m in active if m.findingId in findings]
    active_ids = {f.id for f in active_findings}

    allowed_events = [e for e in state.events if _allowed_event(state, e)]
    recent = sorted(allowed_events, key=lambda e: (e.date, e.id))[-RECENT_EVENT_LIMIT:]
    return {
        'activeSupportPlans': [
            {
                'id': p.id,
                'name': p.name,
                'status': p.status,
                'version': p.version,
                'objective': p.objective,
                'goal': p.goal.label if p.goal else None,
                'nextCheckInAt': p.nextCheckInAt,
                'allowedActions': p.allowedActions,
            }
            for p in state.support.plans
            if p.status in ('active', 'escalated', 'paused')
        ],
        'activeGenomicFindings': [
            {
                'id': f.id,
                'gene': f.gene if show_genes else None,
                'title': f.title if show_genes else 'Perimätiedon havainto',
                'classification': f.classification,
                'confirmationStatus': f.confirmationStatus,
                'evidenceLevel': f.evidenceLevel,
                'synthetic': f.synthetic,
            }
            for f in active_findings
        ],
        'currentMonitoringStates': [
            {
                'monitoringId': m.id,
                'findingId': m.findingId,
                'status': m.status,
                'nextReviewAt': m.nextReviewAt,
                'openObservationId': m.openObservationId,
            }
            for m in active
        ],
        'recentHealthEvents': [
            {
                'id': e.id,
                'date': e.date,
                'type': e.type,
                'code': e.code,
                'displayName': e.displayName,
                'value': e.value,
                'unit': e.unit,
                'abnormalFlag': e.abnormalFlag,
                'structuredData': e.structuredData,
                'confirmedByUser': e.confirmedByUser,
                'source': e.source,
            }
            for e in recent
        ],
        'openObservations': [
            {
                'id': o.id,
                'title': consent.mask_genes(state, o.title),
                'status': o.status,
                'createdAt': o.createdAt,
                # rule ids name the gene, so they are left out when genetic details are hidden
                'ruleIds': (o.ruleIds or [o.ruleId]) if show_genes else [],
                'supportingEventIds': o.supportingEventIds or [o.eventId],
                'connection': consent.mask_genes(state, o.connection),
            }
            for o in state.observations
            if o.status in OPEN_OBSERVATION_STATES and o.findingId in active_ids
        ],
        'followUpTasks': [
            {'id': t.id, 'observationId': t.observationId, 'dueAt': t.dueAt, 'status': t.status}
            for t in state.tasks
            if t.status in ('open', 'awaiting_response')
        ],
        'evidenceReferences': [
            {
                'source': source_name(),
                'gene': f.gene if show_genes else None,
                'rules': [{'id': r['id'], 'name': r['name']} if show_genes else {'name': consent.mask_genes(state, r['name'])}
                          for r in rules_for_gene(f.gene)],
                'synthetic': True,
            }
            for f in active_findings
        ],
        'knownMissingInformation': [
            {
                'id': item.id,
                'relatedFinding': item.relatedFinding,
                'type': item.type,
                'question': item.question,
                'status': item.status,
            }
            for item in state.missingInformation
            if item.relatedFinding in active_ids
        ],
        # Hyvinvointidata (Apple Health): a compact summary against the personal baseline - never the daily history,
        # and nothing when the data is not connected or the user has not allowed it
        'wellbeingData': wellbeing_context.build(state),
    }
