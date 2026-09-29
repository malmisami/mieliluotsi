"""Gate 2: the professional approves, edits, rejects or updates a plan; decisions flow back into the plan version.

The professional also decides on genetic findings sent for review. Not every path needs a physician: a plan's
owner can be a nurse, public health nurse, physician or another named professional.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from app.loop import agent as rule_engine
from app.loop.models import GenomicFinding, LoopState
from app.loop.store import add_days, next_id
from app.loop.templates import fi_date
from app.support import assessment as assessment_module
from app.support import audit, consent, escalation as escalation_module, messages, plan_state, plans, policies, relevance, signals, texts
from app.support.models import Approval, Insight, Owner, SourceRef, SupportPlan


class ProfessionalError(ValueError):
    pass


DECISION_LABELS = {
    'approve': 'Hyväksy suunnitelma',
    'edit': 'Muokkaa suunnitelmaa',
    'reject': 'Hylkää ehdotus',
    'request_info': 'Pyydä lisätietoa',
    'continue': 'Jatka nykyistä seurantaa',
    'change_permissions': 'Muuta agentin toimintavaltuuksia',
    'contact_user': 'Ota yhteyttä käyttäjään',
    'end': 'Päätä seuranta',
    'set_review_date': 'Aseta uusi tarkistuspäivä',
}
ALLOWED_IN_STATUS = {
    'approve': {'pending_professional_review'},
    'edit': {'pending_professional_review', 'active', 'escalated', 'paused'},
    'reject': {'pending_professional_review', 'candidate'},
    'request_info': {'pending_professional_review'},
    'continue': {'active', 'escalated'},
    'change_permissions': {'pending_professional_review', 'active', 'escalated', 'paused'},
    'contact_user': {'pending_professional_review', 'active', 'escalated', 'paused'},
    'end': {'active', 'escalated', 'paused'},
    'set_review_date': {'active', 'escalated', 'paused'},
}
INSIGHT_DECISIONS = {
    'approve': 'Hyväksy seurannan taustatiedoksi',
    'reject': 'Ei käytetä seurannassa',
    'refer': 'Ohjaa toiselle ammattilaiselle',
    'request_info': 'Pyydä lisätietoa',
}


def _int(value: Any, low: int, high: int, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ProfessionalError(f'{name}: anna kokonaisluku.') from exc
    if not low <= number <= high:
        raise ProfessionalError(f'{name}: sallittu vaihteluväli on {low}–{high}.')
    return number


def _apply_changes(state: LoopState, plan: SupportPlan, changes: dict) -> list[str]:
    lines: list[str] = []
    if 'measurementsPerWeek' in changes:
        value = _int(changes['measurementsPerWeek'], 0, 28, 'Kotimittaukset tarkistusvälillä')
        if value != plan.measurementsPerWeek:
            lines.append(f'Kotimittaukset tarkistusvälillä: {plan.measurementsPerWeek} → {value}')
            plan.measurementsPerWeek = value
    if 'checkInEveryDays' in changes:
        value = _int(changes['checkInEveryDays'], 3, 90, 'Tarkistusväli')
        if value != plan.checkInEveryDays:
            lines.append(f'Tarkistusväli: {plan.checkInEveryDays} → {value} päivää')
            plan.checkInEveryDays = value
    if 'demoTarget' in changes and changes['demoTarget']:
        systolic = _int(changes['demoTarget'].get('systolic'), 100, 180, 'Tavoitetaso (yläpaine)')
        diastolic = _int(changes['demoTarget'].get('diastolic'), 60, 110, 'Tavoitetaso (alapaine)')
        old = plan.demoTarget or {}
        if (old.get('systolic'), old.get('diastolic')) != (systolic, diastolic):
            lines.append(f"Tavoitetaso: {old.get('systolic')}/{old.get('diastolic')} → {systolic}/{diastolic} mmHg")
            plan.demoTarget = {'systolic': systolic, 'diastolic': diastolic, 'label': f'Kotimittausten keskiarvo alle {systolic}/{diastolic} mmHg',
                               'setBy': 'Ammattilaisen asettama demo-arvo, ei hoitosuositus'}
    if changes.get('goal'):
        data = dict(changes['goal'])
        times = _int(data.get('timesPerWeek'), 1, 14, 'Tavoite (kertaa viikossa)')
        minutes = _int(data['minutes'], 5, 120, 'Tavoite (minuuttia)') if data.get('minutes') else None
        activity = str(data.get('activity') or (plan.goal.activity if plan.goal else 'kävely'))[:40]
        label = str(data.get('label') or texts.goal_label(activity, times, minutes))[:120]
        low = _int(data.get('minTimesPerWeek', max(1, times - 1)), 1, times, 'Tavoitteen alaraja')
        high = _int(data.get('maxTimesPerWeek', times + 1), times, 21, 'Tavoitteen yläraja')
        if not plan.goal or plan.goal.label != label:
            lines.append(f"Tavoite: {plan.goal.label if plan.goal else '–'} → {label}")
        plan.goal = plans.goal_from(state, {'label': label, 'activity': activity, 'timesPerWeek': times, 'minutes': minutes,
                                            'minTimesPerWeek': low, 'maxTimesPerWeek': high})
    if changes.get('ownerRole'):
        role = changes['ownerRole']
        if role not in policies.load_policies()['ownerRoles']:
            raise ProfessionalError('Tuntematon vastuuammattilaisen rooli.')
        if role != plan.owner.role:
            lines.append(f'Vastuuammattilainen: {plan.owner.label} → {policies.owner_label(role)}')
            plan.owner = Owner(role=role, label=policies.owner_label(role))
    if changes.get('priority'):
        if changes['priority'] not in ('low', 'normal', 'high'):
            raise ProfessionalError('Tuntematon prioriteetti.')
        if changes['priority'] != plan.priority:
            lines.append(f"Prioriteetti: {plan.priority} → {changes['priority']}")
            plan.priority = changes['priority']
    if 'goalFailuresInRow' in changes:
        value = _int(changes['goalFailuresInRow'], 1, 6, 'Eskalaatiosäännön raja')
        for rule in plan.escalationRules:
            if rule.kind == 'goal_failures_and_above_target' and rule.params.get('goalFailuresInRow') != value:
                lines.append(f"Eskalaatiosääntö {rule.id}: peräkkäisiä toteutumattomia tarkistuksia {rule.params.get('goalFailuresInRow')} → {value}")
                rule.params = {**rule.params, 'goalFailuresInRow': value}
    if changes.get('reviewInDays'):
        days = _int(changes['reviewInDays'], 1, 365, 'Tarkistus päivien päästä')
        new_date = add_days(state.currentDate, days)
        lines.append(f'Tarkistuspäivä: {fi_date(plan.nextReviewAt)} → {fi_date(new_date)}')
        plan.nextReviewAt = new_date
    if 'instructions' in changes:
        instructions = [str(item).strip()[:200] for item in (changes['instructions'] or []) if str(item).strip()][:5]
        if instructions != plan.professionalInstructions:
            lines.append('Ohjeet asiakkaalle: ' + (' / '.join(instructions) if instructions else 'poistettu'))
            plan.professionalInstructions = instructions
    return lines


def _apply_permissions(plan: SupportPlan, allowed: list[str]) -> list[str]:
    ceiling = set(policies.theme(plan.theme).get('allowedActions', []))
    unknown = set(allowed) - ceiling
    if unknown:
        raise ProfessionalError('Toimenpide ei kuulu tämän teeman sallittuihin toimiin: ' + ', '.join(sorted(unknown)))
    added = [a for a in allowed if a not in plan.allowedActions]
    removed = [a for a in plan.allowedActions if a not in allowed]
    plan.allowedActions = [a for a in policies.theme(plan.theme)['allowedActions'] if a in allowed]
    lines = []
    if added:
        lines.append('Agentin sallitut toimet, lisätty: ' + ', '.join(policies.action_label(a) for a in added))
    if removed:
        lines.append('Agentin sallitut toimet, poistettu: ' + ', '.join(policies.action_label(a) for a in removed))
    return lines


def _resolve_escalation(state: LoopState, plan: SupportPlan, label: str, role_label: str, note: Optional[str],
                        appropriate: Optional[bool]) -> Optional[str]:
    open_escalation = escalation_module.open_escalation(state, plan)
    if not open_escalation:
        return None
    open_escalation.status = 'resolved'
    open_escalation.resolvedAt = state.currentDate
    open_escalation.appropriate = appropriate
    open_escalation.decision = {'label': label, 'byRole': role_label, 'date': state.currentDate, 'note': note, 'appropriate': appropriate}
    if appropriate is not None:
        # "Oliko automaattinen kiireellisyysarvio oikea?" confirms or changes the assessment behind the routing
        assessment_module.review_from_plan_decision(state, open_escalation.assessmentId, appropriate=appropriate, role_label=role_label, note=note)
    return open_escalation.chainId


def _link_health_insight(state: LoopState, plan: SupportPlan, category: str, review_status: str, reason: str) -> None:
    for insight in state.support.insights:
        if insight.linkedPlanId == plan.id and insight.kind == 'health_data':
            insight.category = category
            insight.reviewStatus = review_status
            insight.reason = reason


def activation_message(state: LoopState, plan: SupportPlan, repeated_contact: bool) -> str:
    # one realistic step for the first seven days (the continuity loop starts here), plus the agreed measurements
    measurements = (f"{texts.count_phrase(plan.measurementsPerWeek, 'kotimittaus', 'kotimittausta')} viikossa"
                    if plan.measurementsPerWeek else None)
    step = texts.goal_step(plan.goal) if plan.goal else None
    text = texts.plan_activated(plan.name, texts.owner_possessive(plan.owner.role), measurements, plan.nextCheckInAt, step)
    if repeated_contact and plan.guides:
        guide = policies.guide(plan.guides[0])
        text += f"\n\n{texts.guide_attached(guide['title'])}\n{guide['title']}: {guide['text']}"
    return text


def decide(
    state: LoopState, plan_id: str, decision: str, *, role: str = 'nurse', note: Optional[str] = None,
    changes: Optional[dict] = None, review_date: Optional[str] = None, allowed_actions: Optional[list[str]] = None,
    escalation_appropriate: Optional[bool] = None, contact_user: bool = False,
) -> SupportPlan:
    plan = plans.find(state, plan_id)
    if not plan:
        raise ProfessionalError('Seurantasuunnitelmaa ei löytynyt.')
    if decision not in DECISION_LABELS:
        raise ProfessionalError('Tuntematon päätös.')
    label = DECISION_LABELS[decision]
    if plan.status not in ALLOWED_IN_STATUS[decision]:
        raise ProfessionalError(f'Päätös ”{label}” ei ole mahdollinen, kun suunnitelman tila on ”{texts.PLAN_STATUS_LABELS[plan.status]}”.')
    if role not in policies.load_policies()['ownerRoles']:
        raise ProfessionalError('Tuntematon ammattilaisen rooli.')
    role_label = policies.owner_label(role)
    note = (note or '').strip()[:500] or None
    open_escalation = escalation_module.open_escalation(state, plan)
    chain_id = open_escalation.chainId if open_escalation else audit.new_chain(state)
    change_lines = _apply_changes(state, plan, changes or {})
    if allowed_actions is not None:
        change_lines += _apply_permissions(plan, allowed_actions)
    if review_date:
        try:
            parsed = date.fromisoformat(review_date).isoformat()
        except ValueError as exc:
            raise ProfessionalError('Tarkistuspäivä ei ole kelvollinen.') from exc
        if parsed <= state.currentDate:
            raise ProfessionalError('Tarkistuspäivän tulee olla tulevaisuudessa.')
        change_lines.append(f'Tarkistuspäivä: {fi_date(plan.nextReviewAt)} → {fi_date(parsed)}')
        plan.nextReviewAt = parsed

    owner = texts.owner_possessive(plan.owner.role)
    notice: Optional[str] = None
    if decision == 'approve':
        plan.approval = Approval(status='approved', byRole=role_label, at=state.currentDate, note=note)
        plan_state.add_history(state, plan, actor='professional', actor_role=role_label, bump=bool(change_lines),
                               summary='Hyväksytty muutoksin' if change_lines else 'Hyväksytty',
                               changes=change_lines or ['Suunnitelma hyväksyttiin ehdotetuin asetuksin.'])
        plan_state.transition(state, plan, 'active')
        plan.activatedAt = state.currentDate
        plan.nextCheckInAt = add_days(state.currentDate, plan.checkInEveryDays)
        plan.nextReviewAt = plan.nextReviewAt or add_days(state.currentDate, plans.review_after_days(plan))
        _link_health_insight(state, plan, 'professionally_approved', 'approved',
                             f'{role_label} hyväksyi seurantasuunnitelman {fi_date(state.currentDate)}.')
        repeated = 'repeated_contact' in signals.evaluate(state, plan)['detected']
        notice = activation_message(state, plan, repeated)
        if repeated and plan.guides:
            state.support.contacts.append({'date': state.currentDate, 'planId': plan.id, 'kind': 'show_guide', 'urgent': False,
                                           'label': 'Hyväksytty ohje liitettiin suunnitelmaan', 'deliveredAt': consent.delivery_time(state)})
    elif decision == 'edit':
        if not change_lines:
            raise ProfessionalError('Muutoksia ei annettu.')
        plan_state.add_history(state, plan, actor='professional', actor_role=role_label, bump=True,
                               summary='Suunnitelmaa muokattiin', changes=change_lines)
        if plan.status == 'escalated':
            _resolve_escalation(state, plan, label, role_label, note, escalation_appropriate)
            plan_state.transition(state, plan, 'active')
        if plan.status == 'active':
            plan.nextCheckInAt = add_days(state.currentDate, plan.checkInEveryDays)
            instructions = ' '.join(plan.professionalInstructions) or 'Uudet asetukset näkyvät Tilanne nyt -näkymässä.'
            notice = texts.DECISION_NOTICES['edit'].format(owner_cap=texts.capitalize(owner), version=plan.version, instructions=instructions)
    elif decision == 'reject':
        plan.approval = Approval(status='rejected', byRole=role_label, at=state.currentDate, note=note)
        plan_state.transition(state, plan, 'rejected')
        plan_state.add_history(state, plan, actor='professional', actor_role=role_label, summary='Ehdotus hylättiin', changes=[note or 'Ei perustelua.'])
        _link_health_insight(state, plan, 'potentially_actionable', 'rejected', 'Ammattilainen ei ottanut seurantaa käyttöön.')
        notice = texts.DECISION_NOTICES['reject'].format(plan=plan.name, owner=owner)
    elif decision == 'request_info':
        if not note:
            raise ProfessionalError('Kirjoita, mitä lisätietoa tarvitaan.')
        plan.approval = Approval(status='info_requested', byRole=role_label, at=state.currentDate, note=note)
        plan_state.add_history(state, plan, actor='professional', actor_role=role_label, summary='Lisätietoa pyydettiin', changes=[note])
        notice = texts.DECISION_NOTICES['request_info'].format(owner_cap=texts.capitalize(owner), note=note)
    elif decision == 'continue':
        was_escalated = plan.status == 'escalated'
        if was_escalated:
            _resolve_escalation(state, plan, label, role_label, note, escalation_appropriate)
            plan_state.transition(state, plan, 'active')
        plan.nextCheckInAt = add_days(state.currentDate, plan.checkInEveryDays)
        plan_state.add_history(state, plan, actor='professional', actor_role=role_label, summary='Jatketaan nykyisellä suunnitelmalla',
                               changes=[note] if note else [])
        # the notice only claims a confirmed (or changed) automated assessment when the professional answered the question
        key = 'continue' if was_escalated and escalation_appropriate else ('continue_changed' if was_escalated and escalation_appropriate is False
                                                                          else 'continue_plain')
        notice = texts.DECISION_NOTICES[key].format(owner_cap=texts.capitalize(owner))
    elif decision == 'change_permissions':
        if allowed_actions is None or not change_lines:
            raise ProfessionalError('Valitse muutetut toimintavaltuudet.')
        plan_state.add_history(state, plan, actor='professional', actor_role=role_label, bump=True,
                               summary='Agentin toimintavaltuuksia muutettiin', changes=change_lines)
        notice = texts.DECISION_NOTICES['change_permissions'].format(owner_cap=texts.capitalize(owner), version=plan.version)
    elif decision == 'contact_user':
        contact_user = True
        plan_state.add_history(state, plan, actor='professional', actor_role=role_label, summary='Ammattilainen ottaa yhteyttä',
                               changes=[note] if note else [])
    elif decision == 'end':
        _resolve_escalation(state, plan, label, role_label, note, escalation_appropriate)
        plan_state.transition(state, plan, 'completed')
        plan_state.add_history(state, plan, actor='professional', actor_role=role_label, summary='Seuranta päätettiin', changes=[note] if note else [])
        notice = texts.DECISION_NOTICES['end'].format(plan=plan.name, owner=owner)
    elif decision == 'set_review_date':
        if not review_date and not (changes or {}).get('reviewInDays'):
            raise ProfessionalError('Valitse uusi tarkistuspäivä.')
        plan_state.add_history(state, plan, actor='professional', actor_role=role_label, bump=True,
                               summary='Tarkistuspäivä muutettiin', changes=change_lines)
        notice = texts.DECISION_NOTICES['set_review_date'].format(date=fi_date(plan.nextReviewAt))

    if contact_user:
        channel = consent.CHANNEL_LABELS.get(state.support.consent.channel, 'sovellus')
        contact_text = texts.DECISION_NOTICES['contact_user'].format(owner_cap=texts.capitalize(owner), channel=f'puhelin tai {channel.lower()}')
        notice = f'{notice} {contact_text}' if notice else contact_text
    if notice and decision in ('edit', 'continue') and plan.status == 'active':
        notice += ' ' + texts.CLOSING_NEXT_CHECK.format(date=fi_date(plan.nextCheckInAt))
    if decision in ('approve', 'edit', 'continue', 'end', 'change_permissions'):
        # what the professional has now reviewed is not counted again by the escalation rules
        plan.checkInBaselineSeq = state.counters.get('checkin', 0)
    plan.lastProfessionalDecision = {'decision': decision, 'label': label, 'byRole': role_label, 'date': state.currentDate,
                                     'note': note, 'version': plan.version, 'changes': change_lines}
    audit.record(state, stage='professional_decision', actor='professional', plan=plan, chain_id=chain_id,
                 professional_decision=label, outcome=plan.status,
                 detail=f"{role_label}: {label}." + (f' {note}' if note else '') + (' Muutokset: ' + '; '.join(change_lines) if change_lines else '')
                        + (f' Automaattinen kiireellisyysarvio oli oikea: {"kyllä" if escalation_appropriate else "ei"}.'
                           if escalation_appropriate is not None else ''))
    if notice:
        messages.post(state, notice, kind='plan_update', plan=plan,
                      basis_data=messages.basis(plan, f'Ammattilaisen päätös ({role_label}): {label}', facts=change_lines))
    return plan


# --- genetic findings sent for professional review -------------------------------------------------------------

def find_insight(state: LoopState, insight_id: str) -> Insight:
    insight = next((i for i in state.support.insights if i.id == insight_id), None)
    if not insight:
        raise ProfessionalError('Havaintoa ei löytynyt.')
    return insight


def request_review(state: LoopState, finding: GenomicFinding, significance: Optional[str]) -> Insight:
    """The user asks a professional to review a DNA-analysis finding. Gate 1 decides whether that is possible."""
    existing = next((i for i in state.support.insights if i.kind == 'genetic' and i.findingId == finding.id), None)
    if existing and existing.reviewStatus in ('approved', 'pending_professional_review'):
        return existing
    classified = relevance.classify_genetic(significance, 'unconfirmed')
    if classified['category'] != 'needs_professional_check':
        raise ProfessionalError('Tätä havaintoa ei ohjata ammattilaisen arvioon: ' + classified['reason'])
    if not consent.genetic_allowed(state):
        raise ProfessionalError('Perimätiedon käyttö ei ole sallittu suostumusasetuksissa.')
    insight = existing or Insight(
        id=next_id(state, 'ins'), kind='genetic', title=f'{finding.gene or "Tuntematon geeni"}: {finding.variant}',
        userTitle=relevance.GENERIC_GENETIC_TITLE, category=classified['category'], reason=classified['reason'],
        userVisible=True, sources=[SourceRef(kind='geneticInsights', id=finding.id, label='DNA-analyysin havainto', date=state.currentDate)],
        findingId=finding.id, gene=finding.gene, variant=finding.variant, significance=significance, confirmation='unconfirmed',
        origin='dna_analysis', createdAt=state.currentDate,
    )
    insight.reviewStatus = 'pending_professional_review'
    insight.reviewOwnerRole = 'physician'
    if not existing:
        state.support.insights.append(insight)
    rule_engine.upsert_finding(state, finding)
    audit.record(state, stage='gate', actor='user', detail=f'Käyttäjä pyysi ammattilaisen arviota perimätiedon havainnosta ({insight.category}). '
                 'Havainto ei vaikuta seurantaan ennen arviota.', outcome='pending_professional_review')
    return insight


def _plan_for_gene(state: LoopState, gene: Optional[str]) -> Optional[SupportPlan]:
    lipid_genes = {'LDLR', 'APOE', 'PCSK9', 'APOB'}
    if gene in lipid_genes:
        return next((p for p in state.support.plans if p.theme == 'lipids' and p.status in ('active', 'escalated', 'paused')), None)
    return None


def decide_insight(state: LoopState, insight_id: str, decision: str, *, role: str = 'physician', note: Optional[str] = None,
                   owner_role: Optional[str] = None) -> Insight:
    insight = find_insight(state, insight_id)
    if decision not in INSIGHT_DECISIONS:
        raise ProfessionalError('Tuntematon päätös.')
    if insight.reviewStatus not in ('pending_professional_review', 'info_requested'):
        raise ProfessionalError('Havainto ei odota ammattilaisen arviota.')
    role_label = policies.owner_label(role)
    note = (note or '').strip()[:500] or None
    if decision == 'approve':
        insight.category = 'professionally_approved'
        insight.reviewStatus = 'approved'
        insight.reason = relevance.classify_genetic(insight.significance, insight.confirmation, approved=True)['reason']
        plan = _plan_for_gene(state, insight.gene)
        if plan and insight.findingId:
            insight.linkedPlanId = plan.id
            if insight.findingId not in plan.linkedFindingIds:
                plan.linkedFindingIds.append(insight.findingId)
                plan_state.add_history(state, plan, actor='professional', actor_role=role_label, bump=True,
                                       summary='Perimätiedon havainto liitettiin taustatiedoksi', changes=[f'{insight.title} (vahvistamaton)'])
        # the approved finding may now be monitored by the genetic rule engine (if the user allows genetic data)
        if insight.findingId and consent.genetic_allowed(state) and any(f.id == insight.findingId for f in state.findings):
            rule_engine.start_monitoring(state, insight.findingId)
    elif decision == 'reject':
        insight.reviewStatus = 'rejected'
    elif decision == 'refer':
        target = owner_role or 'genetics'
        if target not in policies.load_policies()['ownerRoles']:
            raise ProfessionalError('Tuntematon ammattilaisen rooli.')
        insight.reviewOwnerRole = target
    elif decision == 'request_info':
        insight.reviewStatus = 'info_requested'
    insight.decision = {'decision': decision, 'label': INSIGHT_DECISIONS[decision], 'byRole': role_label, 'date': state.currentDate,
                        'note': note, 'ownerRole': insight.reviewOwnerRole}
    audit.record(state, stage='professional_decision', actor='professional', professional_decision=INSIGHT_DECISIONS[decision],
                 detail=f'{role_label}: {INSIGHT_DECISIONS[decision]} – perimätiedon havainto {insight.title}.' + (f' {note}' if note else ''),
                 outcome=insight.reviewStatus)
    return insight


def gate_monitoring(state: LoopState, finding: GenomicFinding, significance: Optional[str]) -> dict:
    """Legacy "Lisää seurantaan": a genetic finding may start monitoring only after professional approval."""
    approved = any(i.findingId == finding.id and i.reviewStatus == 'approved' for i in state.support.insights)
    if approved:
        if not consent.genetic_allowed(state):
            raise ProfessionalError('Perimätiedon käyttö ei ole sallittu suostumusasetuksissa.')
        rule_engine.upsert_finding(state, finding)
        return {'status': 'monitoring', 'monitoring': rule_engine.start_monitoring(state, finding.id)}
    insight = request_review(state, finding, significance)
    return {'status': insight.reviewStatus, 'insight': insight}
