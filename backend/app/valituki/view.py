"""Read models for the three roles. The demo returns them together; a production API would authorise each role separately
(see README → Rajaukset)."""
from __future__ import annotations

from typing import Any, Optional

from app.config import settings
from app.valituki import (
    activities,
    adapters,
    ai,
    content,
    fit_profile,
    handover,
    impact,
    insights,
    intake,
    interpret,
    journey,
    labels,
    matching_flow,
    modality,
    practice,
    professional,
    therapy,
    trends,
)
from app.valituki.agents import base, orchestrator
from app.valituki.models import ClientProfile, Therapist, ValitukiState
from app.valituki.records import AGENT_LABELS
from app.valituki.safety import LEVEL_LABELS, SAFETY_CONTACTS, SAFETY_SCREEN
from app.valituki.store import days_between, get_therapist

DISCLAIMERS = [
    'Mieliluotsi ei ole terapeutti eikä tee diagnooseja.',
    'Mieliluotsi ei korvaa terveydenhuollon ammattilaista eikä tee hoitopäätöksiä.',
    'Mieliluotsi ei ole päivystyspalvelu, eikä sitä seurata jatkuvasti.',
    'Hätätilanteessa 112. Kiireellinen terveysongelma: Päivystysapu 116117.',
]
CLIENT_ORDER = ['cl-aino', 'cl-mikko', 'cl-sara', 'cl-crisis', 'cl-juha', 'cl-maria', 'cl-pekka', 'cl-leena', 'cl-noora']
SCENES = [
    {'key': 'start', 'label': '1. Sami jonossa – alkutila'},
    {'key': 'intake', 'label': '2. Alkukeskustelu tehty'},
    {'key': 'cbt', 'label': '3. Ajatusten tutkiminen chatissa'},
    {'key': 'weeks', 'label': '4. 14 päivää tukea ja harjoittelua'},
    {'key': 'change', 'label': '5. Muutos havaittu'},
    {'key': 'reviewed', 'label': '5b. Ammattilainen tarkistanut'},
    {'key': 'matches', 'label': '6. Terapeuttiehdotukset'},
    {'key': 'handover', 'label': '7. Yhteenveto hyväksytty'},
    {'key': 'therapy', 'label': '9. Terapia ja terapeutin ohjaama välituki'},
    {'key': 'aftercare', 'label': '10. Terapian jälkeinen seuranta'},
]


def therapist_public(therapist: Therapist) -> dict[str, Any]:
    return {
        'id': therapist.id, 'name': therapist.name, 'firstName': therapist.name.split()[0], 'role': therapist.professionalRole,
        'languages': [labels.LANGUAGES[x] for x in therapist.languages], 'specialties': [labels.topic(s) for s in therapist.specialties],
        'approaches': therapist.therapeuticApproaches, 'workingStyle': therapist.workingStyle,
        'levels': {'structured': therapist.structuredLevel, 'directive': therapist.directiveLevel, 'exercises': therapist.exerciseLevel,
                   'homework': therapist.homeworkLevel},
        'formats': (['Etävastaanotto'] if therapist.remote else []) + ([f'Lähivastaanotto: {", ".join(therapist.locations)}']
                                                                        if therapist.inPerson else []),
        'availableTimes': [f'{labels.WEEKDAYS_SHORT[t.weekday]} klo {t.time.replace(":", ".")}' for t in therapist.availableTimes],
        'accessibility': [labels.ACCESSIBILITY.get(a, a) for a in therapist.accessibility], 'bio': therapist.bio,
        'syntheticLabel': 'Demon kuvitteellinen terapeutti.',
    }


# --- meta ------------------------------------------------------------------------------------------------------------

def meta(state: ValitukiState) -> dict[str, Any]:
    config = content.matching_config()
    return {
        'appName': 'Mieliluotsi',
        'tagline': 'Tuki alkaa heti, vaikka terapia ei vielä ala.',
        'syntheticNotice': 'Kaikki demon henkilöt ja terveystiedot ovat täysin kuvitteellisia.',
        'notMedicalDevice': 'Hackathon-prototyyppi: ei kliinisesti validoitu, ei lääkinnällinen laite eikä tarkoitettu oikeiden '
                            'potilaiden hoitoon.',
        'disclaimers': DISCLAIMERS,
        'ai': ai.status(),
        'currentDate': state.currentDate,
        'demoStartDate': state.demoStartDate,
        'legacyEnabled': bool(settings.LEGACY_FEATURES_ENABLED),
        'labels': {
            'topics': labels.TOPICS, 'languages': labels.LANGUAGES, 'formats': labels.FORMATS, 'times': labels.TIMES,
            'weekdays': labels.WEEKDAYS, 'weekdaysShort': labels.WEEKDAYS_SHORT, 'styleDimensions': labels.STYLE_DIMENSIONS,
            'domains': labels.DOMAINS, 'moodScale': {str(k): v for k, v in labels.MOOD_SCALE.items()},
            'anxietyScale': {str(k): v for k, v in labels.ANXIETY_SCALE.items()}, 'practiceKinds': labels.PRACTICE_KINDS,
            'consents': labels.CONSENTS,
            'infoTypes': labels.INFO_TYPES, 'insightCategories': labels.INSIGHT_CATEGORIES, 'insightOrigins': labels.INSIGHT_ORIGINS,
            'contactReasons': labels.CONTACT_REASONS, 'journeyStates': journey.STATE_LABELS, 'events': journey.EVENT_LABELS,
            'safetyLevels': {str(k): v for k, v in LEVEL_LABELS.items()}, 'trendDirections': trends.DIRECTION_LABELS,
            'agents': AGENT_LABELS, 'agentDescriptions': labels.AGENT_DESCRIPTIONS, 'urgency': labels.URGENCY,
            'serviceCategories': labels.SERVICE_CATEGORIES,
        },
        'safety': {'contacts': SAFETY_CONTACTS, 'screen': SAFETY_SCREEN},
        'matching': {'version': config['version'], 'weights': config['weights'], 'labels': config['labels'], 'note': config['note']},
        'library': {**content.activity_library_meta(), 'activities': [a.model_dump() for a in content.activities()]},
        'cbt': {'version': content.cbt()['version'], 'approvalNote': content.cbt()['approvalNote'], 'tools': content.cbt()['tools'],
                'traps': practice.trap_catalog(), 'emotions': content.cbt()['emotions']},
        'adapters': adapters.describe(),
        'routes': {event: orchestrator.agents_for(event) for event in orchestrator.ROUTES},
        'checkInFrequencyOptions': [{'perWeek': int(k), 'days': v, 'label': labels.frequency_text(v)}
                                    for k, v in content.rules()['checkins']['frequencyOptions'].items()],
    }


# --- demo ------------------------------------------------------------------------------------------------------------

# The prepared scene where each script step is the next one (steps 2 and 9 start from the scene just before them).
STEP_SCENES = {'start': 'start', 'intake': 'start', 'cbt': 'intake', 'weeks': 'cbt', 'change': 'weeks', 'matches': 'reviewed',
               'handover': 'matches', 'firstSession': 'handover', 'therapy': 'handover', 'aftercare': 'therapy'}


def presenter_steps(state: ValitukiState) -> dict[str, Any]:
    aino = next((c for c in state.clients if c.id == 'cl-aino'), None)
    if aino is None:
        return {'steps': [], 'next': None}
    phase = journey.effective_state(aino)
    session = intake.session_for(state, aino)
    checkins = [c for c in trends.completed_checkins(state, aino.id) if c.kind != 'baseline']
    decline = [o for o in state.wellbeingObservations if o.clientId == aino.id and o.kind == 'trend_decline']
    decision = matching_flow.current_decision(state, aino.id)
    record = handover.find(state, aino.id)
    config = therapy.active_config(state, aino.id)
    pattern = next((i for i in state.insights if i.clientId == aino.id and i.kind == 'pattern'), None)
    practiced = any(r.clientId == aino.id for r in state.thoughtRecords)
    configured = config is not None or any(c.clientId == aino.id for c in state.therapistConfigs)
    steps = [
        {'n': 1, 'key': 'start', 'title': 'Sami on jonossa terapiaan', 'done': aino.journeyState != 'INVITED',
         'hint': 'Asiakas → Aloita alkukeskustelu'},
        {'n': 2, 'key': 'intake', 'title': 'Alkukeskustelu ja hyväksytyt tulkinnat',
         'done': bool(session and session.status == 'completed'),
         'hint': 'Käy keskustelu (tai "Toista demokeskustelu") ja hyväksy tulkinnat'},
        {'n': 3, 'key': 'cbt', 'title': 'Ajatusten tutkiminen chatissa', 'done': practiced,
         'hint': 'Koti → Demoviesti (tai kirjoita tilanne) → "Kyllä, tutkitaan" → vastaa tai "Toista demokeskustelu"'},
        {'n': 4, 'key': 'weeks', 'title': 'Simuloi 14 päivää', 'done': len(checkins) >= 6 or bool(decline),
         'hint': 'Demo-ohjaus → Simuloi 14 päivää → Edistyminen'},
        {'n': 5, 'key': 'change', 'title': 'Voinnin muutos ja ammattilaisen tarkistus',
         'done': bool(decline) and all(o.status != 'open' for o in decline),
         'hint': 'Simuloi voinnin heikkeneminen → Ammattilainen → Sami → Merkitse tarkistetuksi'},
        {'n': 6, 'key': 'matches', 'title': 'Terapeutin vapaa aika ja matching',
         'done': bool(decision and decision.status in ('proposed_to_client', 'client_selected')),
         'hint': 'Demo-ohjaus → Avaa terapeutin vapaa aika → Asiakas → Hoitopolku'},
        {'n': 7, 'key': 'handover', 'title': 'Sami valitsee Annan ja hyväksyy yhteenvedon',
         'done': bool(record and record.status == 'approved'),
         'hint': 'Valitse Anna → Hyväksy jaettavaksi'},
        {'n': 8, 'key': 'firstSession', 'title': 'Terapeutti näkee yhteenvedon', 'done': phase in ('THERAPY_ACTIVE', 'AFTERCARE'),
         'hint': 'Terapeutti → Anna Laine → Pidä ensimmäinen tapaaminen'},
        {'n': 9, 'key': 'therapy', 'title': 'Terapeutti määrittää välituen ja välitehtävän', 'done': configured,
         'hint': 'Terapeutti → Mieliluotsi tapaamisten välillä → Tallenna'},
        {'n': 10, 'key': 'aftercare', 'title': 'Terapia päättyy – seuranta jatkuu',
         'done': phase == 'AFTERCARE' or any(p.clientId == aino.id for p in state.aftercarePlans),
         'hint': 'Demo-ohjaus → Terapia päättyy (tai Terapeutti → Päätä terapia)'},
    ]
    for step in steps:
        step['scene'] = STEP_SCENES[step['key']]
    upcoming = next((s for s in steps if not s['done']), None)
    hint = upcoming['hint'] if upcoming else 'Valmis – lopeta Konsepti-sivun viestiin.'
    if upcoming and upcoming['key'] == 'weeks' and pattern and pattern.status == 'proposed':
        hint = 'Näytä Kodin "Huomasimme jotain" ja hyväksy havainto'
    if upcoming and upcoming['key'] == 'change' and decline and any(o.status == 'open' for o in decline):
        hint = 'Vaihda Ammattilainen-näkymään → Sami → Merkitse tarkistetuksi'
    return {'steps': steps, 'next': upcoming['n'] if upcoming else None, 'nextKey': upcoming['key'] if upcoming else None,
            'hint': hint}


def demo_info(state: ValitukiState) -> dict[str, Any]:
    order = {cid: i for i, cid in enumerate(CLIENT_ORDER)}
    pending = next((p for p in state.pendingSlotOpenings if p.status == 'pending'), None)
    return {
        'currentDate': state.currentDate,
        'clients': [{'id': c.id, 'displayName': c.displayName, 'firstName': c.firstName, 'persona': c.persona,
                     'journeyState': c.journeyState, 'stateLabel': journey.label(c.journeyState), 'demoPrimary': c.demoPrimary}
                    for c in sorted(state.clients, key=lambda c: (order.get(c.id, 99), c.id))],
        'therapists': [{'id': t.id, 'name': t.name} for t in state.therapists],
        'nextSlotOpening': {'therapistName': get_therapist(state, pending.therapistId).name, 'reason': pending.reason} if pending else None,
        'scenes': SCENES,
        'presenter': presenter_steps(state),
    }


# --- client ----------------------------------------------------------------------------------------------------------

def _timeline_entries(state: ValitukiState, client: ClientProfile, *, audience: str, limit: int = 60) -> list[dict[str, Any]]:
    allowed = ('client', 'both', 'private') if audience == 'client' else ('professional', 'both', 'client')
    rows = [{'id': a.id, 'at': a.createdAt, 'seq': a.seq, 'kind': 'agent', 'agent': a.agent,
             'agentLabel': AGENT_LABELS.get(a.agent, a.agent), 'title': a.title, 'detail': a.detail, 'ruleId': a.ruleId,
             'aiTask': a.aiTask, 'aiSource': a.aiSource, 'type': a.type}
            for a in state.actions if a.clientId == client.id and a.visibility in allowed]
    you = audience == 'client'
    for event in state.events:
        if event.clientId != client.id or not event.actor.startswith('client'):
            continue
        payload = event.payload
        title = None
        if event.type == 'CHECKIN_COMPLETED':
            mood = payload.get('mood')
            title = (('Teit check-inin' if you else f'{client.firstName} teki check-inin')
                     + (f' (vointi {mood}/5)' if mood and not you else '') + (' myöhässä' if payload.get('late') else ''))
        elif event.type == 'ACTIVITY_COMPLETED':
            activity = content.activity(payload.get('activityId'))
            title = ('Teit harjoituksen' if you else f'{client.firstName} teki harjoituksen') + f': {activity.title if activity else ""}' \
                + (f' ({payload["rating"]}/5)' if payload.get('rating') else '')
        elif event.type == 'INSIGHTS_APPROVED':
            title = 'Hyväksyit tiedot' if you else f'{client.firstName} hyväksyi tiedot'
        elif event.type == 'MATCH_SELECTED':
            title = 'Valitsit terapeutin' if you else f'{client.firstName} valitsi terapeutin'
        elif event.type == 'HANDOVER_APPROVED':
            title = 'Hyväksyit yhteenvedon jaettavaksi' if you else f'{client.firstName} hyväksyi yhteenvedon jaettavaksi'
        elif event.type == 'USER_REQUESTED_HUMAN':
            title = 'Pyysit keskustelua ammattilaisen kanssa' if you else f'{client.firstName} pyysi keskustelua ammattilaisen kanssa'
        if title:
            rows.append({'id': event.id, 'at': event.occurredAt, 'seq': event.seq, 'kind': 'client', 'agent': None,
                         'agentLabel': client.firstName, 'title': title, 'detail': '', 'ruleId': None, 'aiTask': None,
                         'aiSource': None, 'type': event.type})
    rows.sort(key=lambda r: (r['at'], r['kind'] == 'agent', r['seq']), reverse=True)
    return rows[:limit]


def milestones(state: ValitukiState, client: ClientProfile) -> list[dict[str, Any]]:
    referral = adapters.waiting_list.referral_for(state, client.id)
    episode = adapters.waiting_list.episode_for(state, client.id)
    goals = insights.active_goals(state, client.id)
    session = intake.session_for(state, client)
    items: list[dict[str, Any]] = []

    def add(key: str, date: Optional[str], title: str, text: str, *, tone: str = 'default', quote: Optional[str] = None,
            status: str = 'done', note: Optional[str] = None) -> None:
        items.append({'key': key, 'date': date, 'title': title, 'text': text, 'tone': tone, 'quote': quote, 'status': status, 'note': note})

    if referral:
        add('sought_help', referral.soughtHelpAt, 'Hain apua', referral.summary or 'Terveysasemalla arvioitiin terapian tarve.',
            quote=goals[0].text if goals else None,
            note=f'Terapiajonoon {labels.fmt_date(episode.startedAt)} · arvioitu odotus {episode.estimatedWait}' if episode else None)
    if session and session.completedAt:
        engagement = next((i for i in insights.for_client(state, client.id, kind='engagement')), None)
        days = engagement.structured.get('checkInDays', client.checkInDays) if engagement else client.checkInDays
        add('started', session.completedAt, 'Mieliluotsi alkoi',
            f'{client.firstName} määritti tavoitteet ja check-in-rytmin ({labels.frequency_text(days)}).', tone='brand')
    else:
        add('started', state.currentDate, 'Mieliluotsi alkaa', 'Tuki alkaa heti, vaikka terapia ei vielä ala.', tone='brand',
            status='current')
    pattern = next((i for i in sorted(state.insights, key=lambda i: i.createdAt) if i.clientId == client.id and i.kind == 'pattern'
                    and i.status in ('proposed', 'approved')), None)
    if pattern:
        add('first_insight', pattern.createdAt, 'Ensimmäinen havainto', pattern.text, tone='insight',
            note='Hyväksyit havainnon' if pattern.status == 'approved' else 'Odottaa, tunnistatko sen omaksesi')
    helpful = next((c for c in sorted(state.activityCompletions, key=lambda c: c.createdAt) if c.clientId == client.id
                    and (c.rating or 0) >= 4), None)
    if helpful:
        activity = content.activity(helpful.activityId)
        add('helpful', helpful.createdAt, 'Toimiva keino',
            f'{activity.title if activity else helpful.activityId} arvioitiin hyödylliseksi {helpful.rating}/5.', tone='helpful')
    decline = next((o for o in sorted(state.wellbeingObservations, key=lambda o: o.createdAt) if o.clientId == client.id
                    and o.kind == 'trend_decline'), None)
    if decline:
        count = next((s.get('count') for s in decline.explanation if s.get('kind') == 'below_baseline'), 3)
        words = {2: 'Kaksi', 3: 'Kolme', 4: 'Neljä'}.get(count, str(count))
        add('change', decline.createdAt, 'Voinnissa muutos',
            f'{words} peräkkäistä check-iniä lähtötason alapuolella. Ammattilaiselle luotiin tarkistuspyyntö.', tone='change',
            note=f'Ammattilainen tarkisti {labels.fmt_date(decline.reviewedAt)}: {decline.reviewOutcome}' if decline.reviewedAt
            else 'Odottaa ammattilaisen tarkistusta. Mieliluotsi ei muuttanut hoitosi kiireellisyyttä.')
    decision = next((d for d in state.matchDecisions if d.clientId == client.id and d.status in ('proposed_to_client', 'client_selected')
                     and d.releasedAt), None)
    booking = handover.active_booking(state, client.id)
    if decision:
        shown = min(len(decision.candidateIds), decision.shownCount)
        chosen = next((c for c in state.matchCandidates if c.id == decision.selectedCandidateId), None)
        add('therapist_found', decision.releasedAt, 'Terapeutti löytyi',
            f'{labels.count_word(shown).capitalize()} sopivaa vaihtoehtoa löytyi.' if shown > 1 else 'Sopiva vaihtoehto löytyi.',
            tone='brand', note=f'Valitsit: {get_therapist(state, chosen.therapistId).name}' if chosen else 'Valinta on sinun')
    elif client.journeyState not in ('THERAPY_ACTIVE',):
        add('therapist_found', None, 'Terapeutti löytyy', 'Etsimme tilanteeseesi sopivaa terapeuttia.', status='upcoming')
    record = handover.find(state, client.id)
    if booking:
        shared = record and record.status == 'approved'
        add('first_session', booking.start, 'Ensimmäinen tapaaminen',
            'Käyttäjän hyväksymä yhteenveto jaettiin terapeutille.' if shared else 'Yhteenveto odottaa hyväksyntääsi.',
            tone='brand', status='done' if booking.status == 'completed' else 'upcoming',
            note=f'{get_therapist(state, booking.therapistId).name} · {labels.fmt_slot(booking.start)}')
    else:
        add('first_session', None, 'Ensimmäinen tapaaminen', 'Kokoat yhteenvedon, jonka terapeutti saa ennen ensimmäistä tapaamista.',
            status='upcoming')
    config = next((c for c in state.therapistConfigs if c.clientId == client.id), None)
    if config:
        therapist = get_therapist(state, config.therapistId)
        add('therapy_mode', config.createdAt, 'Terapeutin ohjaama välituki',
            f'Terapeutti {therapist.name.split()[0]} määritti, miten Mieliluotsi tukee sinua tapaamisten välillä.', tone='therapy')
    else:
        add('therapy_mode', None, 'Terapeutin ohjaama välituki', 'Terapian alettua terapeutti määrittää, miten Mieliluotsi tukee sinua.',
            status='upcoming')
    plan = therapy.aftercare_plan(state, client.id)
    if plan:
        add('aftercare', plan.createdAt, 'Seuranta terapian jälkeen',
            'Terapia päättyi. Mieliala ja ahdistus seurataan sovitussa rytmissä, ja harjoitukset jatkuvat.', tone='brand')
    else:
        add('aftercare', None, 'Seuranta terapian jälkeen',
            'Terapian jälkeen Mieliluotsi seuraa vointia ja muistuttaa terapiassa opitusta.', status='upcoming')
    done = [i for i in items if i['status'] == 'done']
    upcoming = [i for i in items if i['status'] != 'done']
    return sorted(done, key=lambda i: i['date'] or '') + upcoming


def _activity_payload(state: ValitukiState, client: ClientProfile) -> Optional[dict[str, Any]]:
    today = client.todayActivity
    # A step is chosen on check-in days; an unfinished one stays on offer until the next check-in replaces it.
    if today is None or (today.date != state.currentDate and today.status != 'suggested'):
        return None
    activity = content.activity(today.activityId)
    if activity is None:
        return None
    return {**activity.model_dump(), 'intro': today.intro, 'introSource': today.introSource, 'reason': today.reason,
            'status': today.status}


def _insight_row(item) -> dict[str, Any]:
    return {'id': item.id, 'category': item.category, 'kind': item.kind, 'title': item.title, 'text': item.text,
            'origin': item.origin, 'originLabel': labels.INSIGHT_ORIGINS.get(item.origin, item.origin), 'sourceLabel': item.sourceLabel,
            'date': (item.approvedAt or item.createdAt)[:10], 'status': item.status, 'sharing': item.sharing.model_dump(),
            'userWords': item.userWords, 'evidence': item.evidence, 'editedByClient': item.editedByClient, 'version': item.version,
            'editable': item.kind not in ('pattern', 'activity_helpful', 'activity_not_helpful', 'engagement')}


def _memory(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    approved = insights.for_client(state, client.id)
    groups = [{'key': key, 'label': label, 'items': [_insight_row(i) for i in approved if i.category == key]}
              for key, label in labels.INSIGHT_CATEGORIES.items()]
    profile = fit_profile.get(state, client.id)
    permissions = sorted((p for p in state.insightPermissions if p.clientId == client.id and p.previous is not None),
                         key=lambda p: p.createdAt, reverse=True)
    titles = {i.id: i.title for i in state.insights}
    record = handover.find(state, client.id)
    return {
        'groups': groups,
        'pending': [_insight_row(i) for i in insights.for_client(state, client.id, status='proposed')],
        'rejectedCount': len(insights.for_client(state, client.id, status='rejected')),
        'removedCount': len(insights.for_client(state, client.id, status='removed')),
        'consent': client.consent.model_dump(), 'consentGivenAt': client.consentGivenAt,
        'permissionHistory': [{'at': p.createdAt, 'title': titles.get(p.insightId, p.insightId), 'professional': p.professional,
                               'matching': p.matching, 'previous': p.previous} for p in permissions[:12]],
        'fitProfile': {'version': profile.version, 'changelog': [c.model_dump() for c in profile.changelog][-8:]} if profile else None,
        'handover': {'status': record.status, 'statusLabel': handover.summary_line(record)} if record else None,
        'stored': {'checkIns': len([c for c in state.checkIns if c.clientId == client.id and c.status == 'completed' and c.retained]),
                   'journal': len([c for c in state.checkIns if c.clientId == client.id and c.note]),
                   'messages': len([m for m in state.chat if m.clientId == client.id and m.retained])},
    }


def _fit_profile_view(state: ValitukiState, client: ClientProfile) -> Optional[dict[str, Any]]:
    profile = fit_profile.get(state, client.id)
    if profile is None:
        return None
    data = profile.model_dump()
    style = profile.preferredWorkingStyle
    data['styleRows'] = [{'key': key, 'label': dim['label'], 'value': dim['values'].get(style.get(key) or '', None)}
                         for key, dim in labels.STYLE_DIMENSIONS.items()] if style else []
    practical = profile.practicalPreferences
    data['practicalRows'] = [
        {'label': 'Kieli', 'value': labels.join_fi([labels.LANGUAGES[c] for c in practical.get('languages') or []], 'tai')},
        {'label': 'Vastaanotto', 'value': labels.FORMATS.get(practical.get('format') or 'either')},
        {'label': 'Ajat', 'value': labels.join_fi([labels.TIMES[t] for t in practical.get('times') or []], 'tai') or 'Ei toivetta'},
        {'label': 'Päivät', 'value': labels.join_fi([labels.WEEKDAYS[d] for d in practical.get('days') or []], 'tai') or 'Ei toivetta'},
    ] if practical else []
    return data


def _candidate_row(state: ValitukiState, cand) -> dict[str, Any]:
    therapist = get_therapist(state, cand.therapistId)
    return {'id': cand.id, 'rank': cand.rank, 'label': cand.label, 'labelText': cand.labelText, 'therapist': therapist_public(therapist),
            'reasons': cand.reasons, 'unmet': cand.unmetPreferences, 'explanation': cand.explanation,
            'explanationSource': cand.explanationSource, 'firstSlotStart': cand.firstSlotStart,
            'firstSlotText': labels.fmt_slot_title(cand.firstSlotStart), 'status': cand.status, 'dataUsed': cand.dataUsed,
            'dataNotUsed': cand.dataNotUsed}


def _handover_view(state: ValitukiState, client: ClientProfile) -> Optional[dict[str, Any]]:
    record = handover.find(state, client.id)
    if record is None:
        return None
    booking = handover.active_booking(state, client.id)
    sections = handover.build_sections(state, client, record)
    return {'id': record.id, 'status': record.status, 'statusLabel': handover.summary_line(record), 'approvedAt': record.approvedAt,
            'therapistName': get_therapist(state, booking.therapistId).name if booking else None,
            'sections': [s.model_dump() for s in sections], 'approvedKeys': [s.key for s in record.approvedSnapshot or []],
            'aiDraftSource': record.aiDraftSource, 'chatHistoryIncluded': record.edits.includeChatHistory}


def _matching_view(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    decision = matching_flow.current_decision(state, client.id)
    booking = handover.active_booking(state, client.id)
    phase = journey.effective_state(client)
    visible = decision and decision.status in ('proposed_to_client', 'client_selected')
    candidates = [_candidate_row(state, c) for c in matching_flow.decision_candidates(state, decision)[:decision.shownCount]] \
        if visible and decision else []
    if phase in ('INVITED', 'INTAKE'):
        stage = 'no_profile'
    elif client.journeyState == 'HUMAN_REVIEW_NEEDED' and phase in ('WAITING_ACTIVE', 'MATCHING_READY'):
        stage = 'on_hold'
    elif phase == 'WAITING_ACTIVE':
        stage = 'building'
    elif phase == 'MATCHING_READY':
        stage = 'searching'
    elif phase == 'MATCH_PROPOSED':
        stage = 'choose'
    elif phase == 'MATCH_ACCEPTED':
        stage = 'booked'
    elif phase == 'AFTERCARE':
        stage = 'aftercare'
    else:
        stage = 'therapy'
    therapist = get_therapist(state, booking.therapistId) if booking else None
    episode = therapy.episode(state, client.id)
    feedback = [f.model_dump() for f in state.matchFeedback if f.clientId == client.id]
    total = len(decision.candidateIds) if decision else 0
    return {
        'stage': stage,
        'decision': {'id': decision.id, 'status': decision.status, 'shownCount': min(decision.shownCount, total), 'total': total,
                     'canShowMore': decision.shownCount < total, 'helpRequested': decision.helpRequested} if decision else None,
        'candidates': candidates,
        'booking': {'start': booking.start, 'startText': labels.fmt_slot_title(booking.start), 'format': labels.FORMATS.get(booking.format),
                    'status': booking.status, 'therapist': therapist_public(therapist)} if booking and therapist else None,
        'checklist': client.preparationChecklist,
        'readiness': matching_flow.readiness(state, client) if phase in ('WAITING_ACTIVE', 'MATCHING_READY') else None,
        'handover': _handover_view(state, client),
        'feedback': {'eligible': bool(episode and episode.status == 'active'), 'given': feedback},
    }


def client_view(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    referral = adapters.waiting_list.referral_for(state, client.id)
    episode = adapters.waiting_list.episode_for(state, client.id)
    trend = trends.evaluate(state, client)
    session = intake.session_for(state, client)
    spec = content.client_spec(client.id).get('intake') or {}
    due = next((c for c in state.checkIns if c.clientId == client.id and c.status == 'due'), None)
    config = therapy.active_config(state, client.id) if client.mode == 'therapy_support' else None
    notifications = sorted((n for n in state.notifications if n.audience == 'client' and n.clientId == client.id),
                           key=lambda n: (n.createdAt, n.id), reverse=True)
    phase = journey.effective_state(client)
    review_open = [o for o in state.wellbeingObservations if o.clientId == client.id and o.kind == 'trend_decline' and o.status == 'open']
    lock = client.safetyLock
    pending_question = session.pendingQuestionKey if session and session.status == 'conversation' else None
    library = content.activities()
    allowed = {a.id for a in activities.allowed_library(state, client)} if client.journeyState in journey.ACTIVE_STATES else set()
    responses = {r['activityId']: r for r in fit_profile.self_care_responses(state, client.id)}
    return {
        'id': client.id, 'displayName': client.displayName, 'firstName': client.firstName, 'age': client.age,
        'municipality': client.municipality, 'persona': client.persona, 'journeyState': client.journeyState,
        'stateLabel': journey.label(client.journeyState), 'phase': phase, 'demoPrimary': client.demoPrimary,
        'waiting': {
            'soughtHelpAt': referral.soughtHelpAt if referral else None, 'startedAt': episode.startedAt if episode else None,
            'daysWaiting': days_between(referral.soughtHelpAt, state.currentDate) if referral else None,
            'estimatedWait': episode.estimatedWait if episode else '',
            'service': labels.SERVICE_CATEGORIES.get(referral.serviceCategory, '') if referral else '',
            'statusLabel': journey.label(client.journeyState),
            'reviewPending': bool(review_open),
            'reviewText': 'Tämä havainto odottaa ammattilaisen tarkistusta. Mieliluotsi ei ole muuttanut hoitosi kiireellisyyttä.'
            if review_open else None,
        },
        'intake': {
            'status': session.status if session else 'not_started',
            'messages': [m.model_dump() for m in session.messages] if session else [],
            'pendingQuestion': {'key': pending_question, 'text': interpret.question_text(pending_question),
                                'demoAnswer': (spec.get('answers') or {}).get(pending_question)} if pending_question else None,
            'answeredCount': len([k for k, v in session.answers.items() if v]) if session else 0,
            'canFinish': bool(session and len([v for v in session.answers.values() if v]) >= interpret.MIN_ANSWERS_TO_FINISH),
            'proposals': [p.model_dump() for p in session.proposals] if session else [],
            'proposalsSource': session.proposalsSource if session else None,
            'consentDefaults': spec.get('consent') or {'proactiveCheckins': True, 'storeHistory': True, 'professionalMonitoring': True},
            'demoAnswers': spec.get('answers'),
            'demoRhythm': spec.get('rhythm'),
            'demoMood': spec.get('baselineMood'),
            'plan': [{'key': k, 'question': interpret.question_text(k)} for k in [interpret.OPENING_KEY] + interpret.PLAN],
        },
        'checkIn': {
            'due': {'id': due.id, 'kind': due.kind, 'dueDate': due.dueDate, 'trackLabel': due.trackLabel} if due else None,
            'nextDate': client.nextCheckInDate, 'nextLabel': labels.relative_label(client.nextCheckInDate, state.currentDate)
            if client.nextCheckInDate else None, 'days': client.checkInDays, 'frequencyText': labels.frequency_text(client.checkInDays),
            'trackLabel': config.track if config else None, 'proactive': client.consent.proactiveCheckins,
            'needsBaseline': intake.needs_baseline(state, client),
        },
        'trend': {'direction': trend.direction, 'label': trends.DIRECTION_LABELS[trend.direction], 'text': trend.client_text,
                  'arrow': trends.DIRECTION_ARROWS[trend.direction], 'baseline': client.baseline,
                  'series': trends.series(state, client, include_notes=True), 'historyStored': client.consent.storeHistory},
        'today': _activity_payload(state, client),
        'mode': therapy.mode_summary(state, client),
        'modeKey': client.mode,
        'plan': {
            'goals': [{'id': g.id, 'text': g.text, 'priority': g.priority} for g in insights.active_goals(state, client.id)],
            'library': [{'id': a.id, 'title': a.title, 'description': a.description, 'estimatedDuration': a.estimatedDuration,
                         'allowed': a.id in allowed, 'response': responses.get(a.id)} for a in library],
        },
        'fitProfile': _fit_profile_view(state, client),
        'matching': _matching_view(state, client),
        'memory': _memory(state, client),
        'milestones': milestones(state, client),
        'timeline': _timeline_entries(state, client, audience='client'),
        'notifications': [n.model_dump() for n in notifications[:40]],
        'unreadCount': len([n for n in notifications if not n.read]),
        'chat': _chat(state, client),
        'guided': practice.active_view(state, client),
        'demoMessage': _demo_message(state, client),
        'practice': practice.client_view(state, client),
        'progress': {'series': (series := trends.series(state, client)), 'week': practice.week_summary(state, client, series)},
        'requests': [{'id': t.id, 'type': t.type, 'title': t.title, 'status': t.status, 'createdAt': t.createdAt,
                      'handlingNote': t.handlingNote, 'outcome': t.outcome}
                     for t in sorted(state.tasks, key=lambda t: t.createdAt, reverse=True)
                     if t.clientId == client.id and t.type in ('contact_request', 'matching_help', 'matching_review')],
        'safety': {'lockActive': bool(lock and not lock.dismissedAt)},
        'phaseFlags': {'matchingReady': phase in ('MATCHING_READY', 'MATCH_PROPOSED'), 'booked': phase == 'MATCH_ACCEPTED',
                       'therapy': phase == 'THERAPY_ACTIVE', 'aftercare': phase == 'AFTERCARE'},
        'backstage': {'match': _backstage_match(state, client), 'modality': modality.rank(state, client)},
    }


def _backstage_match(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    """The presenter's view of matching next to the phone: the whole pool, who the hard criteria excluded and how the
    shortlisted therapists scored per component (the same deterministic run the professional sees)."""
    data = _professional_matching(state, client)
    booking = handover.active_booking(state, client.id)
    if data['decision'] is None:
        # Before the first run: a live preview that changes as the client approves data and times open.
        preview = matching_flow.preview(state, client) or {'candidates': [], 'excluded': []}
        return {'therapistCount': len(state.therapists), 'ran': False, 'excluded': preview['excluded'],
                'candidates': preview['candidates'], 'readiness': data['readiness'], 'chosen': None}
    return {
        'therapistCount': len(state.therapists),
        'ran': data['decision'] is not None,
        'excluded': [{'name': e['name'], 'reason': e['failed'][0]['reason'] if e['failed'] else ''} for e in data['excluded']],
        'candidates': [{'id': c['id'], 'name': c['therapist']['name'], 'label': c['label'], 'labelText': c['labelText'],
                        'total': c['totalPoints'], 'status': c['status'],
                        'components': [{'key': x['key'], 'label': x['label'], 'score': x['score']} for x in c['components']]}
                       for c in data['candidates']],
        'readiness': data['readiness'],
        'chosen': get_therapist(state, booking.therapistId).name if booking else None,
    }


def _demo_message(state: ValitukiState, client: ClientProfile) -> Optional[str]:
    """The presenter's shortcut message (clients.json → practiceDemo), until the client has sent it once."""
    message = (content.client_spec(client.id).get('practiceDemo') or {}).get('message')
    sent = message and any(m.clientId == client.id and m.role == 'client' and m.text == message for m in state.chat)
    return None if sent else message


def _chat(state: ValitukiState, client: ClientProfile) -> list[dict[str, Any]]:
    """The conversation. An offer's buttons are live on the day it was made, until it is answered or superseded."""
    rows = []
    for message in [m for m in state.chat if m.clientId == client.id][-80:]:
        row = message.model_dump()
        row['actionable'] = bool(message.kind == 'offer' and not message.answered and message.createdAt[:10] == state.currentDate)
        rows.append(row)
    return rows


# --- professional ------------------------------------------------------------------------------------------------------

def _observation_row(o) -> dict[str, Any]:
    if hasattr(o, 'level'):
        return {'id': o.id, 'category': 'safety', 'kind': f'safety_{o.level}', 'title': f'Turvallisuushavainto – {LEVEL_LABELS[o.level]}',
                'level': o.level, 'status': o.status, 'createdAt': o.createdAt, 'agent': 'SafetyAgent',
                'ruleId': ', '.join(sorted({t.ruleId for t in o.triggers})),
                'explanation': [{'kind': t.source, 'text': f'{t.category} ({t.ruleId})'} for t in o.triggers],
                'suggestedAction': o.requiredHumanAction, 'reason': ', '.join(sorted({t.category for t in o.triggers})),
                'aiSummary': None, 'reviewedBy': o.reviewedBy, 'reviewedAt': o.reviewedAt, 'reviewOutcome': o.reviewOutcome,
                'reviewNote': o.reviewNote, 'requiresReview': o.level >= 2, 'clientAcknowledgedAt': o.clientAcknowledgedAt,
                'deterministicLevel': o.deterministicLevel, 'aiLevel': o.aiLevel}
    return {'id': o.id, 'category': 'wellbeing', 'kind': o.kind, 'title': o.title, 'level': None, 'status': o.status,
            'createdAt': o.createdAt, 'agent': o.agent, 'ruleId': o.ruleId, 'explanation': o.explanation,
            'suggestedAction': o.suggestedAction,
            'reason': o.reason, 'aiSummary': o.aiSummary, 'aiSummarySource': o.aiSummarySource, 'reviewedBy': o.reviewedBy,
            'reviewedAt': o.reviewedAt, 'reviewOutcome': o.reviewOutcome, 'reviewNote': o.reviewNote,
            'requiresReview': o.requiresHumanReview, 'clientAcknowledgedAt': None}


def _professional_matching(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    decision = matching_flow.current_decision(state, client.id)
    run = next((r for r in state.matchRuns if decision and r.id == decision.runId), None)
    candidates = []
    if decision:
        for cand in matching_flow.decision_candidates(state, decision):
            row = _candidate_row(state, cand)
            row['components'] = [c.model_dump() for c in cand.components]
            row['totalPoints'] = cand.totalPoints
            candidates.append(row)
    return {'decision': decision.model_dump() if decision else None, 'candidates': candidates,
            'excluded': run.excluded.get(client.id, []) if run else [], 'input': run.inputs.get(client.id) if run else None,
            'run': {'id': run.id, 'trigger': run.trigger, 'createdAt': run.createdAt, 'configVersion': run.configVersion} if run else None,
            'eligibleForRun': matching_flow.eligible_for_run(state, client), 'readiness': matching_flow.readiness(state, client)}


def professional_client(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    referral = adapters.waiting_list.referral_for(state, client.id)
    episode = adapters.waiting_list.episode_for(state, client.id)
    trend = trends.evaluate(state, client)
    booking = handover.active_booking(state, client.id)
    record = handover.find(state, client.id)
    observations = sorted([_observation_row(o) for o in state.wellbeingObservations if o.clientId == client.id]
                          + [_observation_row(o) for o in state.safetyObservations if o.clientId == client.id and o.level >= 2],
                          key=lambda r: r['createdAt'], reverse=True)
    config = therapy.active_config(state, client.id)
    monitoring = client.consent.professionalMonitoring
    return {
        'id': client.id, 'displayName': client.displayName, 'firstName': client.firstName, 'age': client.age,
        'municipality': client.municipality, 'persona': client.persona, 'journeyState': client.journeyState,
        'stateLabel': journey.label(client.journeyState), 'phase': journey.effective_state(client), 'mode': client.mode,
        'demoPrimary': client.demoPrimary,
        'referral': {**referral.model_dump(), 'serviceLabel': labels.SERVICE_CATEGORIES.get(referral.serviceCategory, ''),
                     'requiredLabels': [labels.topic(c) for c in referral.requiredCompetencies]} if referral else None,
        'waitingDays': days_between(referral.soughtHelpAt, state.currentDate) if referral else None,
        'urgency': {'value': episode.clinicalUrgency, 'label': labels.URGENCY[episode.clinicalUrgency], 'setBy': episode.urgencySetBy,
                    'setAt': episode.urgencySetAt, 'history': episode.urgencyHistory} if episode else None,
        'consent': client.consent.model_dump(),
        'monitoring': monitoring,
        'observations': observations if monitoring else [o for o in observations if o['category'] == 'safety'],
        'openReview': next((o for o in observations if o['status'] == 'open' and o['requiresReview']), None),
        'trend': {'direction': trend.direction, 'label': trends.DIRECTION_LABELS[trend.direction],
                  'arrow': trends.DIRECTION_ARROWS[trend.direction],
                  'text': trend.professional_text, 'baseline': client.baseline, 'recent': trend.recent,
                  'series': trends.series(state, client) if monitoring else [], 'signals': trend.signals},
        'checkIns': [{'id': c.id, 'dueDate': c.dueDate, 'kind': c.kind, 'status': c.status, 'mood': c.mood, 'anxiety': c.anxiety,
                      'changes': c.changes,
                      'completedAt': c.completedAt, 'hasNote': bool(c.note), 'trackScore': c.trackScore}
                     for c in sorted((c for c in state.checkIns if c.clientId == client.id), key=lambda c: (c.dueDate, c.id),
                                     reverse=True)][:20]
        if monitoring else [],
        'checkInSettings': {'days': client.checkInDays, 'text': labels.frequency_text(client.checkInDays), 'next': client.nextCheckInDate,
                            'paused': client.automationPaused},
        'insights': professional.insights_for_professional(state, client),
        'fitProfile': _fit_profile_view(state, client),
        'matching': _professional_matching(state, client),
        'booking': {**booking.model_dump(), 'therapistName': get_therapist(state, booking.therapistId).name,
                    'startText': labels.fmt_slot_title(booking.start)} if booking else None,
        'handover': {'status': record.status, 'statusLabel': handover.summary_line(record)} if record else None,
        'therapy': {'mode': therapy.mode_summary(state, client), 'configured': config is not None},
        'tasks': [t.model_dump() for t in sorted((t for t in state.tasks if t.clientId == client.id), key=lambda t: t.createdAt,
                                                 reverse=True)],
        'notes': [n.model_dump() for n in state.notes if n.clientId == client.id],
        'matchFeedback': [f.model_dump() for f in state.matchFeedback if f.clientId == client.id],
        'timeline': _timeline_entries(state, client, audience='professional', limit=40),
        'safetyLockActive': bool(client.safetyLock and not client.safetyLock.dismissedAt),
        'reviewStatus': professional.review_status(state, client),
    }


def _directory(state: ValitukiState) -> list[dict[str, Any]]:
    rows = []
    for therapist in state.therapists:
        free = adapters.therapist_directory.free_slots(state, therapist.id)
        rows.append({**therapist_public(therapist), 'active': therapist.active, 'inactiveReason': therapist.inactiveReason,
                     'currentCapacity': therapist.currentCapacity, 'maxCapacity': therapist.maxCapacity,
                     'ageGroups': [labels.AGE_GROUPS.get(g, g) for g in therapist.ageGroups],
                     'serviceCategories': [labels.SERVICE_CATEGORIES.get(s, s) for s in therapist.serviceCategories],
                     'exclusionCriteria': [labels.CLIENT_FLAGS.get(e, e) for e in therapist.exclusionCriteria],
                     'nextAvailableSlot': labels.fmt_slot_title(free[0].start) if free else None, 'freeSlots': len(free),
                     'clients': len([b for b in state.bookings if b.therapistId == therapist.id and b.status != 'cancelled'])})
    return rows


def professional_view(state: ValitukiState) -> dict[str, Any]:
    names = {c.id: c.displayName for c in state.clients}
    notifications = sorted((n for n in state.notifications if n.audience == 'coordinator'), key=lambda n: (n.createdAt, n.id), reverse=True)
    counts: dict[str, int] = {}
    for action in state.actions:
        counts[action.agent] = counts.get(action.agent, 0) + 1
    return {
        'coordinatorName': professional.COORDINATOR_NAME,
        'overview': professional.overview(state),
        'queue': professional.queue(state),
        'details': {c.id: professional_client(state, c) for c in state.clients},
        'notifications': [n.model_dump() for n in notifications[:40]],
        'directory': _directory(state),
        'timeline': [{**a.model_dump(), 'clientName': names.get(a.clientId or '', None), 'agentLabel': AGENT_LABELS.get(a.agent, a.agent)}
                     for a in sorted((a for a in state.actions if a.visibility != 'private'), key=lambda a: a.seq, reverse=True)[:160]],
        'audit': [{**e.model_dump(), 'clientName': names.get(e.clientId or '', None)}
                  for e in sorted(state.audit, key=lambda e: e.seq, reverse=True)[:160]],
        'agents': [{'name': name, 'label': AGENT_LABELS[name], 'description': labels.AGENT_DESCRIPTIONS[name],
                    'actions': counts.get(name, 0)} for name in AGENT_LABELS],
        'impact': impact.metrics(state),
        'openTasks': len([t for t in state.tasks if t.status in ('open', 'contact_requested')]),
    }


# --- therapist -------------------------------------------------------------------------------------------------------

def therapist_view(state: ValitukiState, therapist_id: Optional[str]) -> dict[str, Any]:
    therapist = next((t for t in state.therapists if t.id == therapist_id), None) or next(
        (t for t in state.therapists if t.id == 'th-anna'), None)
    selected = None
    if therapist:
        clients = handover.therapist_clients(state, therapist.id)
        for row in clients:
            client = next(c for c in state.clients if c.id == row['clientId'])
            episode = therapy.last_episode(state, client.id)
            config = therapy.active_config(state, client.id)
            since = episode.startedAt if episode and episode.startedAt else None
            track = [p for p in trends.series(state, client) if since and p['at'] and p['at'] >= since]
            aftercare = therapy.aftercare_plan(state, client.id)
            row['therapy'] = {
                'episodeStatus': episode.status if episode else None, 'startedAt': since,
                'endedAt': episode.endedAt if episode else None, 'sessionsHeld': episode.sessionsHeld if episode else 0,
                'config': config.model_dump() if config else None,
                'suggestedPlan': therapy.suggested_plan(state, client) if episode and episode.status == 'active' else None,
                'suggestedAftercare': therapy.suggested_aftercare(state, client) if episode and episode.status == 'active' else None,
                'aftercare': aftercare.model_dump() if aftercare else None,
                'mode': therapy.mode_summary(state, client),
                'sinceStart': [{'date': p['date'], 'mood': p['mood'], 'anxiety': p['anxiety'], 'trackScore': p['trackScore']}
                               for p in track],
                'practice': practice.therapist_summary(state, client, since),
                'canHoldFirstSession': bool(episode and episode.status == 'planned'),
            }
            row['milestones'] = milestones(state, client)
        notifications = sorted((n for n in state.notifications if n.audience == 'therapist' and n.therapistId == therapist.id),
                               key=lambda n: (n.createdAt, n.id), reverse=True)
        selected = {**therapist_public(therapist), 'currentCapacity': therapist.currentCapacity, 'maxCapacity': therapist.maxCapacity,
                    'clients': clients, 'notifications': [n.model_dump() for n in notifications[:20]]}
    return {'therapists': [{'id': t.id, 'name': t.name, 'role': t.professionalRole,
                            'clientCount': len([b for b in state.bookings if b.therapistId == t.id])} for t in state.therapists],
            'selected': selected, 'library': [{'id': a.id, 'title': a.title} for a in content.activities()],
            'tools': [{'id': t['id'], 'title': t['title'], 'kind': t['kind']} for t in content.cbt()['tools']]}


def build(state: ValitukiState, client_id: Optional[str] = None, therapist_id: Optional[str] = None) -> dict[str, Any]:
    client = next((c for c in state.clients if c.id == client_id), None)
    return {
        'meta': meta(state),
        'demo': demo_info(state),
        'client': client_view(state, client) if client else None,
        'professional': professional_view(state),
        'therapist': therapist_view(state, therapist_id),
    }


def locked(client: ClientProfile) -> bool:
    return base.safety_locked(client)
