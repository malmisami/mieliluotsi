"""Initial demo state: read the synthetic person through the adapters, filter everything through gate 1 and
create the plans described in data/support/demo_setup.json."""
from __future__ import annotations

import logging

from app.loop.models import HealthEvent, LoopState
from app.loop.store import next_id
from app.support import audit, plans, policies, relevance
from app.support.adapters import AdapterError, load_person_directory
from app.support.adapters.projection import profile_events
from app.support.models import Approval, ConsentSettings, Insight, Owner, PlanChange, SourceRef, UserConsent
from app.support.texts import CATEGORY_LABELS

logger = logging.getLogger(__name__)


def bootstrap_support(state: LoopState) -> None:
    setup = policies.load_setup()
    try:
        profile = load_person_directory(policies.setup_path(setup['personSourceDir']), setup['personId'])
    except (AdapterError, OSError):
        logger.exception('Synthetic person data could not be loaded; support plans are unavailable')
        return
    support = state.support
    support.person = profile
    support.consent = ConsentSettings(**setup.get('consent', {}), updatedAt=state.currentDate,
                                      history=[{'date': state.currentDate, 'change': 'Alkuasetukset vastaanotoilla annettujen suostumusten mukaan (synteettinen).'}])
    record = setup.get('automatedAssessmentConsent')
    if support.consent.automatedAssessment:
        # explicit consent to the automated care-need assessment (terveydenhuoltolaki 51 § 3 mom., assumed in force 2027)
        support.consent.automatedAssessmentInformedAt = state.currentDate
        if record:
            support.consent.history.insert(0, {'date': record.get('date', state.currentDate), 'change': record['historyLine']})
            profile.consents.append({'id': record.get('recordId', 'SUO-AUTO'), 'date': record.get('date'), 'target': record['target'],
                                     'status': record.get('status', 'annettu'), 'channel': record.get('channel')})
    support.lastCycleAt = state.currentDate
    audit.record(state, stage='data', actor='system',
                 detail='Tietolähteet luettiin adaptereilla: ' + ', '.join(f"{s['file']} ({s['rows']} riviä)" for s in profile.sourceSystems) + '.')

    for raw in profile_events(profile):
        state.events.append(HealthEvent(id=next_id(state, 'evt'), synthetic=True, **raw))

    themes = policies.load_policies()['themes']
    theme_results = {r['themeId']: r for r in relevance.health_data_themes(profile, themes)}
    theme_insights: dict[str, Insight] = {}
    for theme_id, result in theme_results.items():
        insight = Insight(
            id=next_id(state, 'ins'), kind='health_data', title=themes[theme_id]['name'], userTitle=themes[theme_id]['name'],
            category=result['category'], reason=result['reason'], userVisible=result['category'] != 'no_practical_significance',
            sources=result['sources'], origin='rules', createdAt=state.currentDate,
        )
        support.insights.append(insight)
        theme_insights[theme_id] = insight
        audit.record(state, stage='gate', actor='system', outcome=result['category'],
                     detail=f"Portti 1 (relevanssi): {themes[theme_id]['name']} – {CATEGORY_LABELS[result['category']]}. {result['reason']}")

    approvals = {a['findingId']: a for a in setup.get('geneticApprovals', [])}
    genetic_insights: dict[str, Insight] = {}
    for item in profile.geneticInsights:
        approval = approvals.get(item.findingId) if item.findingId else None
        classified = relevance.classify_genetic(item.significance, item.confirmation, approved=bool(approval))
        insight = Insight(
            id=next_id(state, 'ins'), kind='genetic', title=f'{item.gene}: {item.variant}', userTitle=relevance.GENERIC_GENETIC_TITLE,
            category=classified['category'], reason=classified['reason'], userVisible=classified['userVisible'],
            sources=[SourceRef(kind='geneticInsights', id=item.id, label=f'Perimätieto ({item.gene})', date=item.reportedAt)],
            findingId=item.findingId, gene=item.gene, variant=item.variant, significance=item.significance,
            confirmation=item.confirmation, reviewStatus='approved' if approval else 'not_requested',
            reviewOwnerRole=approval['byRole'] if approval else None,
            decision={'decision': 'approve', 'label': 'Hyväksy seurannan taustatiedoksi', 'byRole': policies.owner_label(approval['byRole']),
                      'date': approval['at'], 'note': approval['note']} if approval else None,
            origin='source_record', createdAt=item.reportedAt or state.currentDate,
        )
        support.insights.append(insight)
        if item.findingId:
            genetic_insights[item.findingId] = insight
        audit.record(state, stage='gate', actor='system', outcome=classified['category'],
                     detail=f"Portti 1 (relevanssi): perimätiedon havainto ({item.gene}) – {classified['label']}."
                            + ('' if classified['userVisible'] else ' Ei näytetä asiakkaan näkymässä eikä käytetä ohjauksessa.'))

    for spec in setup.get('plans', []):
        result = theme_results.get(spec['theme'])
        sources = list(result['sources']) if result else []
        diagnosis = result.get('diagnosis') if result else None
        plan = plans.build_plan(state, spec['theme'], sources, status=spec['status'],
                                diagnosis_label=f'{diagnosis.code} {diagnosis.label}' if diagnosis else None)
        plan.userConsent = UserConsent(given=True, at=spec.get('userConsentAt'), how=spec.get('userConsentHow'))
        insight = theme_insights.get(spec['theme'])
        if spec['status'] == 'active':
            role = spec['approvedByRole']
            plan.owner = Owner(role=role, label=policies.owner_label(role))
            plan.approval = Approval(status='approved', byRole=policies.owner_label(role), at=spec['approvedAt'], note=spec.get('approvalNote'))
            plan.createdAt = plan.activatedAt = spec['approvedAt']
            plan.nextReviewAt, plan.nextCheckInAt = spec.get('nextReviewAt'), spec.get('nextCheckInAt')
            plan.history.append(PlanChange(version=1, date=spec['approvedAt'], actor='professional', actorRole=policies.owner_label(role),
                                           summary='Hyväksytty', changes=[spec.get('approvalNote') or 'Suunnitelma hyväksyttiin.']))
            for finding_id in spec.get('linkedFindingIds', []):
                plan.linkedFindingIds.append(finding_id)
                if finding_id in genetic_insights:
                    genetic_insights[finding_id].linkedPlanId = plan.id
            if insight:
                insight.category, insight.reviewStatus = 'professionally_approved', 'approved'
                insight.reason = f"{policies.owner_label(role)} hyväksyi seurantasuunnitelman."
        else:
            plan.history.append(PlanChange(version=1, date=state.currentDate, actor='system', summary='Järjestelmän ehdotus',
                                           changes=['Ehdotus muodostettiin terveystietojen perusteella (portti 1: mahdollisesti toimintakelpoinen).']))
            if insight:
                insight.reviewStatus = 'pending_professional_review'
                insight.reviewOwnerRole = plan.owner.role
        if insight:
            insight.linkedPlanId = plan.id
        support.plans.append(plan)
        audit.record(state, stage='gate', actor='system', plan=plan, outcome=plan.status,
                     detail=(f'Portti 2: {plan.name} on {plan.approval.byRole}n hyväksymä (versio {plan.version}).' if plan.status == 'active'
                             else f'Portti 2: {plan.name} odottaa vastuuammattilaisen ({plan.owner.label}) hyväksyntää.'))
