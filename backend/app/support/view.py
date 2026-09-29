"""Read model for the support part of the dashboard (user view, professional view, audit, consent, impact)."""
from __future__ import annotations

from typing import Any

from app.loop.models import OPEN_OBSERVATION_STATES, LoopState
from app.loop.templates import fi_date
from app.support import assessment as assessment_module
from app.support import consent, continuity, genetic_links, impact, policies, relevance, signals, situation, texts
from app.support.models import SupportPlan
from app.wellbeing import view as wellbeing_view

STAGE_LABELS = {
    'data': 'Tietolähteet', 'gate': 'Portti', 'observe': 'Havainnointi', 'compare': 'Vertailu suunnitelmaan', 'detect': 'Signaalit',
    'decide': 'Päätös', 'act': 'Agentin toimi', 'wait': 'Odotus', 'evaluate': 'Käyttäjän vastaus', 'update': 'Tilannekuva päivitetty',
    'assess': 'Hoidon tarpeen arvio (automaattinen)', 'escalate': 'Eskalaatio', 'professional_decision': 'Ammattilaisen päätös',
    'consent': 'Suostumus',
}
FLOW_STEPS = [
    ('signal', 'Havainto'), ('agent', 'Agentin toimi'), ('user', 'Käyttäjän vastaus'), ('follow', 'Seuranta'),
    ('assessment', 'Automaattinen arvio'), ('escalation', 'Eskalaatio'), ('professional', 'Ammattilaisen päätös'),
]
_CHAIN_STEP_BY_STAGE = {'detect': 'signal', 'act': 'agent', 'evaluate': 'user', 'update': 'follow', 'assess': 'assessment',
                        'escalate': 'escalation', 'professional_decision': 'professional'}


def _plan_view(state: LoopState, plan: SupportPlan) -> dict[str, Any]:
    obs = signals.evaluate(state, plan) if plan.status in ('active', 'escalated', 'paused') else {'detected': set(), 'metrics': {}, 'signals': []}
    theme = policies.theme(plan.theme)
    data = plan.model_dump()
    data.update({
        'statusLabel': texts.PLAN_STATUS_LABELS[plan.status],
        'themeTopic': theme.get('topic'),
        'allowedActionLabels': {a: policies.action_label(a) for a in theme.get('allowedActions', [])},
        'forbiddenActionLabels': {a: policies.forbidden_labels().get(a, a) for a in plan.forbiddenActions},
        'currentSignals': [{'key': k, 'label': signals.SIGNAL_LABELS.get(k, k)} for k in sorted(obs['detected'])],
        'signalDetails': obs['signals'],
        'metrics': obs['metrics'],
        'checkIns': [c.model_dump() for c in sorted(signals.plan_checkins(state, plan), key=lambda c: (c.createdAt, c.id), reverse=True)],
        'agentActions': [a.model_dump() for a in state.support.audit if a.planId == plan.id and a.stage in ('act', 'assess', 'escalate')][-12:],
        'sourceDetails': [{**s.model_dump(), 'kindLabel': consent.SOURCE_LABELS.get(s.kind, s.kind), 'inUse': consent.source_allowed(state, s.kind)}
                          for s in plan.sources],
        'assessmentIds': [a.id for a in assessment_module.newest_first([a for a in state.support.assessments if a.planId == plan.id])],
    })
    return data


def _insight_view(state: LoopState, insight) -> dict[str, Any]:
    data = insight.model_dump()
    data['categoryLabel'] = texts.CATEGORY_LABELS[insight.category]
    data['reviewStatusLabel'] = texts.REVIEW_STATUS_LABELS[insight.reviewStatus]
    data['reviewOwnerLabel'] = policies.owner_label(insight.reviewOwnerRole) if insight.reviewOwnerRole else None
    if insight.kind == 'genetic':
        data['userTitle'] = relevance.genetic_user_title(insight.gene, state.support.consent.showGeneticDetails)
        data['inUse'] = consent.genetic_allowed(state) and insight.reviewStatus == 'approved'
    else:
        data['inUse'] = insight.category == 'professionally_approved'
    return data


def _chains(state: LoopState) -> list[dict[str, Any]]:
    """Group audit entries into agent episodes and map them to the demo-friendly flow steps."""
    chains: dict[str, dict[str, Any]] = {}
    for entry in state.support.audit:
        if not entry.chainId:
            continue
        chain = chains.setdefault(entry.chainId, {'id': entry.chainId, 'planId': entry.planId, 'date': entry.date, 'steps': {}, 'entries': 0})
        chain['entries'] += 1
        step = _CHAIN_STEP_BY_STAGE.get(entry.stage)
        if entry.stage == 'decide' and entry.action == 'no_action':
            step = 'agent'
        if step and step not in chain['steps']:
            chain['steps'][step] = {'date': entry.date, 'text': entry.detail}
    plan_names = {p.id: p.name for p in state.support.plans}
    result = []
    for chain in chains.values():
        if len(chain['steps']) < 2:
            continue
        result.append({**chain, 'plan': plan_names.get(chain['planId']),
                       'flow': [{'key': key, 'label': label, **chain['steps'].get(key, {})} for key, label in FLOW_STEPS]})
    return list(reversed(result))[:30]


def _legacy_entries(state: LoopState) -> list[dict[str, Any]]:
    """The genetic rule engine's own log, shown in the same audit view."""
    return [
        {'id': e.id, 'date': e.date, 'stage': 'observe' if e.kind == 'event_evaluated' else 'update', 'actor': 'agent',
         'detail': e.decisionDetail, 'rule': ({'id': e.ruleApplied.get('id'), 'name': e.ruleApplied.get('name')} if e.ruleApplied else None),
         'action': e.decision, 'llmUsed': bool(e.extractionMethod and e.extractionMethod.startswith('llm')), 'source': 'genetic_rule_engine'}
        for e in state.agentLog
    ]


def _automation_policy() -> dict[str, Any]:
    """The published description of the automation's operating principles (one of the conditions of the assumed 51 § 3 mom.)."""
    block = assessment_module.automation()
    return {
        'name': block.get('name'),
        'legalBasis': block.get('legalBasis'),
        'responsiblePerson': block.get('responsiblePerson'),
        'version': block.get('version'),
        'principles': list(block.get('principles', [])),
        'urgencyClasses': [dict(c) for c in block.get('urgencyClasses', [])],
        'symptomRules': [{'id': r['id'], 'name': r.get('name', r['id']), 'urgency': r['urgency'], 'reason': r['reason'],
                          'patterns': list(r.get('patterns', [])), 'default': bool(r.get('default'))} for r in block.get('symptomRules', [])],
        'contextRules': [{'id': r['id'], 'description': r['description']} for r in block.get('contextRules', [])],
        'sampling': dict(block.get('sampling', {})),
        'whatStaysHuman': list(block.get('whatStaysHuman', [])),
        'rightsSentence': texts.RIGHTS_SENTENCE,
        'legalNotice': texts.LEGAL_NOTICE,
    }


def view(state: LoopState) -> dict[str, Any]:
    support = state.support
    if not support.person:
        return {'available': False, 'currentDate': state.currentDate}
    person = support.person.demographics
    age = int(state.currentDate[:4]) - person.birthYear if person.birthYear else None
    plans = [_plan_view(state, p) for p in support.plans]
    insights = [_insight_view(state, i) for i in support.insights]
    open_escalations = [e for e in support.escalations if e.status == 'open']
    urgency_order = {'same_day': 0, 'soon': 1, 'routine': 2}
    today = state.currentDate
    return {
        'available': True,
        'currentDate': today,
        'person': {'id': person.personId, 'name': person.displayName, 'age': age, 'region': person.region,
                   'sourceSystems': support.person.sourceSystems},
        'situation': situation.build(state),
        # the self-care continuity engine: remember, reach out, one step at a time, notice when self-care is not enough
        'continuity': continuity.build(state),
        # Hyvinvointidata (Apple Health): connection and new observations; the trends load from /api/health/summary
        'wellbeing': wellbeing_view.dashboard_block(state),
        'plans': plans,
        'openCheckIns': [c.model_dump() for c in support.checkIns if c.status == 'open'],
        'escalations': [e.model_dump() for e in sorted(support.escalations, key=lambda e: (e.status != 'open', urgency_order[e.urgency], e.createdAt))],
        # every automated care-need assessment, newest first (all of them are audited and visible to the professional)
        'assessments': [assessment_module.view(state, a) for a in assessment_module.newest_first(support.assessments)],
        'insights': insights,
        # health records linked to DNA findings on the user's request (client-safe: gene names only with permission)
        'geneticLinking': genetic_links.view(state),
        'userInsights': [i for i in insights if i['userVisible'] and i['kind'] == 'genetic'],
        'consent': {
            **support.consent.model_dump(),
            'sourceLabels': consent.SOURCE_LABELS,
            'channelLabels': consent.CHANNEL_LABELS,
            'deliveryTime': consent.delivery_time(state),
            'contactsLastWeek': consent.contacts_last_week(state),
            'records': support.person.consents,
        },
        'professional': {
            'pendingPlanIds': [p.id for p in support.plans if p.status == 'pending_professional_review'],
            'escalationIds': [e.id for e in sorted(open_escalations, key=lambda e: urgency_order[e.urgency])],
            # oversight of the automated assessments: linked to an open escalation, sampled, or requested by the user
            'assessmentReviewIds': assessment_module.oversight_ids(state),
            'humanReviewRequestIds': assessment_module.human_review_request_ids(state),
            'reviewDuePlanIds': [p.id for p in support.plans if p.status in ('active', 'escalated', 'paused') and p.nextReviewAt
                                 and signals.days_between(today, p.nextReviewAt) <= 14],
            'activePlanIds': [p.id for p in support.plans if p.status in ('active', 'escalated', 'paused')],
            'closedPlanIds': [p.id for p in support.plans if p.status in ('completed', 'rejected')],
            # a health-data theme is reviewed as a plan proposal; this queue holds genetic findings only
            'insightReviewIds': [i.id for i in support.insights if i.kind == 'genetic' and i.reviewStatus in ('pending_professional_review', 'info_requested')],
            'filteredInsightIds': [i.id for i in support.insights if not i.userVisible],
            'sharedObservationIds': [o.id for o in state.observations if o.sharedAt and o.status in OPEN_OBSERVATION_STATES],
            'ownerRoles': policies.load_policies()['ownerRoles'],
            'decisionLabels': {
                'approve': 'Hyväksy suunnitelma', 'edit': 'Muokkaa suunnitelmaa', 'reject': 'Hylkää ehdotus', 'request_info': 'Pyydä lisätietoa',
                'continue': 'Jatka nykyistä seurantaa', 'change_permissions': 'Muuta agentin toimintavaltuuksia',
                'contact_user': 'Ota yhteyttä käyttäjään', 'end': 'Päätä seuranta', 'set_review_date': 'Aseta uusi tarkistuspäivä',
            },
            'assessmentDecisionLabels': dict(texts.ASSESSMENT_REVIEW_LABELS),
            'assessmentQuestion': 'Oliko automaattinen kiireellisyysarvio oikea?',
        },
        'audit': {
            # detailMasked: the same line without gene names, for the client's view when genetic details are hidden
            'entries': [{**a.model_dump(), 'stageLabel': STAGE_LABELS.get(a.stage, a.stage), 'detailMasked': consent.mask_genes(state, a.detail)}
                        for a in reversed(support.audit)],
            'chains': _chains(state),
            'legacy': [{**e, 'detailMasked': consent.mask_genes(state, e['detail'])} for e in reversed(_legacy_entries(state))],
        },
        'impact': impact.person_metrics(state),
        'policy': {
            'notice': policies.load_policies()['notice_fi'],
            'actions': {k: v['label'] for k, v in policies.load_policies()['actions'].items()},
            'forbidden': policies.forbidden_labels(),
            'categoryLabels': texts.CATEGORY_LABELS,
            'statusLabels': texts.PLAN_STATUS_LABELS,
            'automation': _automation_policy(),
            'urgencyLabels': assessment_module.urgency_labels(),
            'assessmentStatusLabels': dict(texts.ASSESSMENT_STATUS_LABELS),
            'assessmentModeLabels': dict(texts.ASSESSMENT_MODE_LABELS),
        },
        'demo': {
            'openQuestion': bool([c for c in support.checkIns if c.status == 'open']),
            'pendingProfessional': bool([p for p in support.plans if p.status in ('pending_professional_review', 'escalated')]),
            'nextMeasurement': _next_scripted_measurement(state),
            'lastCycleAt': fi_date(support.lastCycleAt) if support.lastCycleAt else None,
            'symptomReport': policies.load_setup().get('script', {}).get('symptomReport'),
            'homeMonitoringOffer': bool(continuity.open_offer(state)),
            'homeMonitoringActive': bool(continuity.active_period(state)),
        },
    }


def _next_scripted_measurement(state: LoopState):
    script = policies.load_setup().get('script', {}).get('measurements', [])
    index = state.support.scriptCursor.get('measurements', 0)
    if not script:
        return None
    systolic, diastolic = script[index % len(script)]
    return f'{systolic}/{diastolic}'
