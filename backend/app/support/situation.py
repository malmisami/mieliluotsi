"""'Tilanne nyt': the user's default view. Situation and the next step first; the reasons behind each theme are a
second layer. Deterministic texts, calm tone, no risk lists, genetic details only if the user allows them."""
from __future__ import annotations

from typing import Any, Optional

from app.loop.models import OPEN_OBSERVATION_STATES, LoopState
from app.loop.templates import fi_date
from app.support import assessment as assessment_module
from app.support import consent, continuity, escalation, policies, relevance, signals, texts
from app.support.models import Escalation, SupportPlan

VISIBLE_STATUSES = ('active', 'escalated', 'paused', 'pending_professional_review')
TONES = {'active': 'calm', 'escalated': 'waiting', 'paused': 'neutral', 'pending_professional_review': 'neutral'}


def _open_checkin(state: LoopState, plan: SupportPlan):
    return signals.open_checkin(state, plan)


def _escalation_tone(open_escalation: Escalation) -> str:
    return 'urgent' if open_escalation.urgency == 'same_day' else 'waiting'


def _measurement_status(state: LoopState, plan: SupportPlan) -> Optional[dict]:
    if plan.measurementCode != 'BP' or not plan.measurementsPerWeek or plan.status not in ('active', 'escalated'):
        return None
    obs = signals.evaluate(state, plan)
    count = obs['metrics'].get('measurementCount', 0)
    return {'count': count, 'required': plan.measurementsPerWeek, 'remaining': max(0, plan.measurementsPerWeek - count),
            'since': obs['metrics'].get('periodStart'), 'average': obs['metrics'].get('average')}


def _genetic_note(state: LoopState, plan: SupportPlan) -> Optional[str]:
    if not plan.linkedFindingIds:
        return None
    if not consent.genetic_allowed(state):
        return 'Perimätietoa ei käytetä, koska olet rajannut sen pois suostumusasetuksissa.'
    show = state.support.consent.showGeneticDetails
    names = []
    for insight in state.support.insights:
        if insight.kind == 'genetic' and insight.findingId in plan.linkedFindingIds and insight.reviewStatus == 'approved':
            names.append(relevance.genetic_user_title(insight.gene, show))
    title = ', '.join(names) or relevance.GENERIC_GENETIC_TITLE
    return (f'Perimätieto: {title.lower() if not show else title}. Ammattilaisen hyväksymä taustatieto, kliininen vahvistus puuttuu. '
            'Se ei muuta tavoitteitasi eikä ohjeitasi.')


def plan_card(state: LoopState, plan: SupportPlan) -> dict[str, Any]:
    theme = policies.theme(plan.theme)
    owner = texts.owner_possessive(plan.owner.role)
    measurement = _measurement_status(state, plan)
    open_escalation = escalation.open_escalation(state, plan)
    topic = theme.get('userTopic', plan.name.lower())
    if plan.status == 'pending_professional_review':
        sentence = f'Ehdotus uudeksi seurannaksi. {plan.owner.label} käy sen läpi ennen käyttöönottoa – sinun ei tarvitse tehdä mitään.'
    elif plan.status == 'paused':
        sentence = f'Seuraamme kanssasi {topic}, mutta seuranta on nyt tauolla' + (f' {fi_date(plan.pausedUntil)} asti.' if plan.pausedUntil else '.')
    elif open_escalation:
        sentence = f'Seuraamme kanssasi {topic}. Arvio: {open_escalation.urgencyLabel} – {owner} ottaa yhteyttä {open_escalation.handlingTime}.'
    elif measurement:
        if plan.professionalInstructions:
            task = plan.professionalInstructions[0].rstrip('.')
            sentence = f'Seuraamme kanssasi {topic}. Seuraava tehtäväsi: {task[:1].lower() + task[1:]}.'
        elif measurement['remaining']:
            sentence = (f'Seuraamme kanssasi {topic}. Seuraava tehtäväsi on tehdä '
                        f'{texts.count_phrase(measurement["remaining"], "kotimittaus", "kotimittausta")} ennen seuraavaa tarkistusta.')
        else:
            sentence = f'Seuraamme kanssasi {topic}. Sovitut kotimittaukset on tehty – hienoa!'
    elif plan.measurementCode == 'LDL':
        sentence = f'Seuraamme kanssasi {topic}. Suunnitelman seuraava arviointi on {fi_date(plan.nextReviewAt)}. Sinun ei tarvitse tehdä nyt mitään.'
    else:
        sentence = f'Seuraamme kanssasi {topic}.'
    if plan.goal and plan.status in ('active', 'escalated'):
        sentence += f' Tavoitteena on {plan.goal.label}.'

    progress = []
    if measurement:
        progress.append({'label': 'Kotimittaukset edellisen tarkistuksen jälkeen', 'value': measurement['count'], 'target': measurement['required']})
    filtered = [i for i in state.support.insights if not i.userVisible]
    allowed_labels = [policies.action_label(a) for a in plan.allowedActions]
    forbidden = policies.forbidden_labels()
    return {
        'id': plan.id,
        'name': plan.name,
        'status': plan.status,
        'statusLabel': texts.PLAN_STATUS_LABELS[plan.status],
        'tone': _escalation_tone(open_escalation) if open_escalation else TONES.get(plan.status, 'neutral'),
        'sentence': sentence,
        'progress': progress,
        'goal': plan.goal.label if plan.goal else None,
        'goalSetBy': plan.goal.setBy if plan.goal else None,
        'nextCheckInAt': plan.nextCheckInAt if plan.status == 'active' else None,
        'nextReviewAt': plan.nextReviewAt,
        'approvedBy': plan.approval.byRole if plan.approval.status == 'approved' else None,
        'approvedAt': plan.approval.at if plan.approval.status == 'approved' else None,
        'version': plan.version,
        'instructions': plan.professionalInstructions,
        'canPause': plan.status == 'active',
        'canResume': plan.status == 'paused',
        'why': {
            'rationale': plan.rationale,
            'objective': plan.objective,
            'sources': [
                {'label': s.label, 'date': s.date, 'kind': s.kind, 'kindLabel': consent.SOURCE_LABELS.get(s.kind, s.kind),
                 'inUse': consent.source_allowed(state, s.kind)}
                for s in plan.sources
            ],
            'approval': (f"{plan.approval.byRole} hyväksyi {fi_date(plan.approval.at)}" if plan.approval.status == 'approved'
                         else f'Odottaa vastuuammattilaisen ({plan.owner.label}) hyväksyntää'),
            'owner': plan.owner.label,
            'userConsent': f"Suostumus annettu {fi_date(plan.userConsent.at)} ({plan.userConsent.how})" if plan.userConsent.given else 'Suostumusta ei ole annettu',
            'target': plan.demoTarget,
            'agentMay': allowed_labels,
            'agentMayNot': list(forbidden.values()),
            'escalationRules': [{'name': r.name, 'urgency': r.urgencyLabel, 'handlingTime': r.handlingTime} for r in plan.escalationRules],
            'rightsSentence': texts.RIGHTS_SENTENCE,
            'history': [c.model_dump() for c in plan.history[-6:]],
            'geneticNote': _genetic_note(state, plan),
            'filteredNote': (f'Tiedoistasi löytyi myös {len(filtered)} havaintoa, joilla ei ole käytännön merkitystä seurannallesi '
                             'tai joiden tulkinta on epävarma. Niitä ei käytetä seurannassa eikä ohjauksessa.') if filtered else None,
            'demoNotice': policies.load_policies()['notice_fi'],
        },
    }


def _progress(state: LoopState) -> list[str]:
    lines = []
    readings = signals.home_readings(state, until=state.currentDate)[-3:]
    for event, systolic, diastolic in reversed(readings):
        lines.append(f'Kotimittaus {systolic}/{diastolic} mmHg ({fi_date(event.date)})')
    done = [c for c in state.support.checkIns if c.status == 'completed']
    if done:
        last = max(done, key=lambda c: (c.createdAt, c.id))
        goal = last.outcome.get('goal')
        goal_text = {'met': 'tavoite toteutui', 'partial': 'tavoite toteutui osittain', 'none': 'tavoite ei toteutunut'}.get(goal, 'vastaukset kirjattu')
        extra = f" – uusi tavoite: {last.outcome['newGoal']}" if last.outcome.get('newGoal') else ''
        lines.insert(0, f'Viikkotarkistus {fi_date(last.createdAt)}: {goal_text}{extra}')
    return lines


def _escalation_headline(state: LoopState, esc: Escalation) -> tuple[str, str]:
    owner_cap = texts.capitalize(texts.owner_possessive(esc.ownerRole))
    linked = next((a for a in state.support.assessments if a.id == esc.assessmentId), None)
    if linked and linked.mode == 'professional_required':
        return (f'Tein tilanteestasi esiarvion: {esc.urgencyLabel}. {owner_cap} tekee hoidon tarpeen arvion ja ottaa yhteyttä '
                f'{esc.handlingTime}. Tämä ei vaadi sinulta nyt muuta.'), _escalation_tone(esc)
    return (f'Arvioin tilanteesi automaattisesti: {esc.urgencyLabel}. {owner_cap} ottaa yhteyttä {esc.handlingTime}. '
            'Tämä ei vaadi sinulta nyt muuta.'), _escalation_tone(esc)


def build(state: LoopState) -> dict[str, Any]:
    support = state.support
    if not support.person:
        return {'available': False}
    plans = [p for p in support.plans if p.status in VISIBLE_STATUSES]
    active = [p for p in plans if p.status in ('active', 'escalated', 'paused')]
    pending = [p for p in plans if p.status == 'pending_professional_review']
    open_checkins = [c for c in support.checkIns if c.status == 'open']
    open_escalations = [e for e in support.escalations if e.status == 'open']
    safety = next((e for e in open_escalations if e.trigger == 'safety_threshold'), None)
    legacy_questions = [t for t in state.tasks if t.status == 'awaiting_response']
    legacy_observations = [o for o in state.observations if o.status in OPEN_OBSERVATION_STATES]
    # the continuity engine: an offer the agent made on its own, or the home monitoring the user accepted
    offer = continuity.open_offer(state)
    period = continuity.active_period(state)

    if safety:
        headline, tone = 'Automaattinen arvio: kiireellinen, samana päivänä. Toimi alla olevan ohjeen mukaan.', 'urgent'
    elif open_checkins:
        plan = next(p for p in support.plans if p.id == open_checkins[0].planId)
        headline, tone = f'Hyvinvointikumppani kysyy kuulumisia: {plan.name.lower()}. Vastaaminen vie hetken.', 'attention'
    elif open_escalations:
        headline, tone = _escalation_headline(state, open_escalations[0])
    elif offer:
        headline, tone = (f'Hyvinvointikumppani ehdottaa {texts.days_genitive(offer.days)} kotiseurantaa, koska kotimittausten taso on '
                          'noussut. Päätös on sinun.'), 'attention'
    elif period:
        headline, tone = (f'Kotiseuranta on käynnissä {fi_date(period.startsAt)}–{fi_date(period.endsAt)}: mittaa aamulla ja illalla. '
                          'Kokoan tuloksista yhteenvedon.'), 'attention'
    elif legacy_questions:
        headline, tone = 'Sinulle on jatkokysymys aiemmasta huomiosta.', 'attention'
    elif active:
        headline, tone = 'Seuranta etenee suunnitelman mukaan. Tilanne ei vaadi sinulta nyt välitöntä toimintaa.', 'calm'
    elif pending:
        headline, tone = 'Seurantasuunnitelmasi odottaa ammattilaisen hyväksyntää. Sinun ei tarvitse tehdä mitään.', 'calm'
    else:
        headline, tone = 'Sinulla ei ole nyt aktiivisia seurantoja.', 'calm'

    next_step: dict[str, Any]
    if safety:
        next_step = {'kind': 'safety', 'title': 'Mittaa uudelleen levättyäsi ja ota tarvittaessa yhteyttä',
                     'detail': 'Ohje on keskustelussa ja alla. Vastuuammattilainen on saanut tiedon. Voit aina pyytää ammattilaisen tekemän arvion.'}
    elif open_checkins:
        checkin = open_checkins[0]
        next_step = {'kind': 'answer_checkin', 'title': 'Vastaa viikkotarkistukseen', 'checkInId': checkin.id,
                     'detail': f'Lyhyt tarkistus ({len(checkin.questions)} kysymystä). Voit ohittaa vapaaehtoiset kysymykset.'}
    elif offer:
        next_step = {'kind': 'answer_offer', 'title': f'Vastaa ehdotukseen: {texts.days_genitive(offer.days)} kotiseuranta',
                     'detail': f'{offer.reason} Mittaisit aamulla ja illalla. Päätös on sinun.', 'periodId': offer.id, 'planId': offer.planId}
    elif period:
        total = period.days * period.perDay
        next_step = {'kind': 'record_measurement', 'planId': period.planId, 'periodId': period.id,
                     'title': f'Kotiseuranta: mittaa aamulla ja illalla ({len(period.readingIds)}/{total} mittausta)',
                     'detail': f'{fi_date(period.startsAt)}–{fi_date(period.endsAt)}. Kokoan yhteenvedon, kun mittaukset on tehty.'}
    elif legacy_questions:
        next_step = {'kind': 'legacy_followup', 'title': 'Vastaa jatkokysymykseen', 'detail': 'Onko aiempi huomio käsitelty ammattilaisen kanssa?'}
    else:
        next_step = {'kind': 'none', 'title': 'Ei avoimia tehtäviä', 'detail': 'Voit jatkaa arkea tavalliseen tapaan.'}
        for plan in active:
            measurement = _measurement_status(state, plan)
            if escalation.open_escalation(state, plan):
                next_step = {'kind': 'wait', 'title': f'Ei tehtäviä – arvio on tehty ja {texts.owner_possessive(plan.owner.role)} ottaa yhteyttä',
                             'detail': 'Voit pyytää ammattilaisen tekemän arvion milloin tahansa.', 'planId': plan.id}
                break
            if plan.professionalInstructions and plan.status == 'active':
                next_step = {'kind': 'record_measurement' if measurement else 'instructions', 'title': plan.professionalInstructions[0],
                             'detail': ' '.join(plan.professionalInstructions[1:]) or f'Suunnitelman versio {plan.version}.', 'planId': plan.id}
                break
            if measurement and measurement['remaining'] and plan.status == 'active':
                goal = f' Tavoite: {plan.goal.label}.' if plan.goal else ''
                next_step = {'kind': 'record_measurement', 'planId': plan.id,
                             'title': f"Tee {texts.count_phrase(measurement['remaining'], 'kotimittaus', 'kotimittausta')} ennen seuraavaa tarkistusta",
                             'detail': f"Kirjattu {measurement['count']}/{measurement['required']} edellisen tarkistuksen jälkeen.{goal}"}
                break
    check_dates = [p.nextCheckInAt for p in active if p.nextCheckInAt and p.status == 'active']
    latest_assessment = assessment_module.latest_for_home(state)
    return {
        'available': True,
        'headline': headline,
        'tone': tone,
        'noImmediateAction': not safety,
        'nextStep': next_step,
        # the newest automated care-need assessment still under the professional's oversight (client card + rights)
        'assessment': assessment_module.view(state, latest_assessment) if latest_assessment else None,
        'whatStaysHuman': list(assessment_module.automation().get('whatStaysHuman', [])),
        'plans': [plan_card(state, p) for p in sorted(plans, key=lambda p: ('pending' in p.status, p.createdAt))],
        'latestProgress': _progress(state),
        'nextCheck': min(check_dates) if check_dates else None,
        'legacyOpenObservationIds': [o.id for o in legacy_observations],
        # the genetic rule engine's open observations, worded according to the user's genetic-details consent
        'legacyObservations': [
            {'id': o.id, 'title': consent.mask_genes(state, o.title), 'status': o.status, 'createdAt': o.createdAt,
             'explanation': consent.mask_genes(state, o.explanation), 'sharedAt': o.sharedAt}
            for o in legacy_observations
        ],
        'safetyEscalationId': safety.id if safety else None,
    }


def chat_status_lines(state: LoopState) -> list[str]:
    """Plan-aware opening lines for the chat's "Mikä on tilanteeni?" answer."""
    situation = build(state)
    if not situation.get('available'):
        return []
    lines = [situation['headline'], f"Seuraava askel: {situation['nextStep']['title']}."]
    for card in situation['plans']:
        lines.append(f"• {card['name']} ({card['statusLabel'].lower()}): {card['sentence']}")
    if situation['nextCheck']:
        lines.append(f"Seuraava tarkistus: {fi_date(situation['nextCheck'])}.")
    return lines
