"""Hyvinvointikumppani: a companion agent bounded to the user's own monitoring context.

Roles: EXPLAIN, CLARIFY, PREPARE, ACT. Every ACT goes through a PendingAction (or an explicit user choice)
before a tool runs. The LLM only classifies intents, extracts structured data and phrases texts; all state
changes come from agent.py's rule engine. The automated assessment of the need for care and its urgency
(hoidon tarpeen ja kiireellisyyden arvio, terveydenhuoltolaki 51 § 3 mom. – the prototype assumes the amendment
in 2027) is made by support.assessment's rules only; the chat never asks the LLM for an urgency class.
"""
from __future__ import annotations

from datetime import date as date_cls

from app.loop import agent, companion_texts as texts, family_history, intent as intent_router, llm
from app.loop.evidence import evidence_entry, rules_for_gene, source_name
from app.loop.extraction import parse_text
from app.loop.models import (
    OPEN_OBSERVATION_STATES,
    ChatAction,
    ChatLogEntry,
    ChatMessage,
    LoopState,
    Observation,
    PendingAction,
)
from app.loop.safety import check_text
from app.loop.store import add_days, next_id
from app.loop.templates import fi_date, fi_value
from app.loop.user_context import USER_CONTEXT_KEYS, build_user_context
from app.support import assessment as support_assessment
from app.support import consent as support_consent
from app.support import continuity as support_continuity
from app.support import messages as support_messages
from app.support import plans as support_plans
from app.support import policies as support_policies
from app.support import situation as support_situation
from app.wellbeing import context as wellbeing_context
from app.wellbeing import observations as wellbeing_observations

MAX_MESSAGE_LENGTH = 1000


class CompanionError(ValueError):
    pass


# --- building blocks -------------------------------------------------------------

def _action(state: LoopState, label: str, type_: str, style: str = 'primary', **args) -> ChatAction:
    return ChatAction(id=next_id(state, 'act'), label=label, type=type_, args=args, style=style)


def _say(state: LoopState, text: str, **fields) -> ChatMessage:
    message = ChatMessage(id=next_id(state, 'msg'), role='agent', text=text, date=state.currentDate, **fields)
    state.chatMessages.append(message)
    return message


def _user_says(state: LoopState, text: str, kind: str = 'text') -> ChatMessage:
    message = ChatMessage(id=next_id(state, 'msg'), role='user', kind=kind, text=text, date=state.currentDate)
    state.chatMessages.append(message)
    return message


def _log(state: LoopState, **fields) -> ChatLogEntry:
    entry = ChatLogEntry(id=next_id(state, 'chatlog'), date=state.currentDate, **fields)
    state.chatLog.append(entry)
    return entry


def _pending(state: LoopState, type_: str, **payload) -> PendingAction:
    pending = PendingAction(id=next_id(state, 'pending'), type=type_, payload=payload, createdAt=state.currentDate)
    state.pendingActions.append(pending)
    return pending


def _active_monitoring(state: LoopState):
    return next((m for m in state.monitorings if m.active), None)


def _open_observation(state: LoopState) -> Observation | None:
    open_ones = [o for o in state.observations if o.status in OPEN_OBSERVATION_STATES]
    return max(open_ones, key=lambda o: (o.updatedAt or o.createdAt, o.id)) if open_ones else None


def _finding(state: LoopState, finding_id: str):
    return next((f for f in state.findings if f.id == finding_id), None)


def _monitoring_status(state: LoopState, monitoring_id: str) -> str | None:
    monitoring = next((m for m in state.monitorings if m.id == monitoring_id), None)
    return monitoring.status if monitoring else None


def _basis(
    state: LoopState,
    *,
    decision_by: str,
    text_source: str,
    monitoring_ids: list[str] | None = None,
    event_ids: list[str] | None = None,
    rule_ids: list[str] | None = None,
    include_user_provided: bool = True,
) -> dict:
    monitorings = [m for m in state.monitorings if m.id in (monitoring_ids or [])]
    events = [e for e in state.events if e.id in (event_ids or [])]
    user_provided = [e for e in state.events if e.confirmedByUser] if include_user_provided else []
    rules = []
    for monitoring in monitorings:
        finding = _finding(state, monitoring.findingId)
        rules += [r for r in rules_for_gene(finding.gene if finding else None) if r['id'] in (rule_ids or [])]
    fixed = texts.BASIS_FIXED_RULE if decision_by.startswith('Sääntömoottori') else texts.BASIS_FIXED
    statement = {'llm': texts.BASIS_LLM, 'template': texts.BASIS_TEMPLATE}.get(text_source, fixed)
    return {
        'monitorings': [
            {
                'id': m.id,
                'finding': support_consent.mask_genes(state, _finding(state, m.findingId).title if _finding(state, m.findingId) else m.findingId),
                'status': texts.STATUS_LABELS.get(m.status, m.status),
            }
            for m in monitorings
        ],
        'events': [texts.event_line(e) for e in events],
        'userProvided': [texts.event_line(e) for e in user_provided],
        'evidenceSource': source_name() if monitorings else None,
        'rules': [{'id': r['id'], 'name': r['name'], 'demoNotice': r.get('demoNotice_fi')} for r in rules],
        'decisionBy': decision_by,
        'textBy': {'llm': 'LLM (tarkistettu turvallisuussäännöillä)', 'template': 'Valmis tekstipohja', 'fixed': 'Kiinteä viesti'}[text_source],
        'statement': statement,
    }


def _phrase(state: LoopState, focus: dict, fallback: str) -> tuple[str, str, dict, bool]:
    """LLM phrasing from the bounded UserContext only; template on any failure or safety violation."""
    if not llm.enabled():
        return fallback, 'template', {'performed': True, 'llmText': None, 'used': 'template (LLM pois käytöstä)'}, False
    generated = llm.explain_for_chat(build_user_context(state), focus)
    if not generated:
        return fallback, 'template', {'performed': True, 'llmText': None, 'used': 'template (LLM ei vastannut)'}, True
    check = check_text(generated)
    if not check['passed']:
        return fallback, 'template', {'performed': True, 'llmText': check, 'used': 'template (LLM-teksti hylättiin)'}, False
    return generated, 'llm', {'performed': True, 'llmText': check, 'used': 'llm'}, False


def _llm_role(text_source: str, intent_method: str | None = None, extraction_method: str | None = None) -> str:
    roles = []
    if intent_method and intent_method.startswith('llm'):
        roles.append('intent classification')
    if extraction_method == 'llm':
        roles.append('structured extraction')
    if text_source == 'llm':
        roles.append('explanation text only')
    return ', '.join(roles) if roles else 'none'


# --- EXPLAIN / CLARIFY -------------------------------------------------------------

def _explain_finding(state: LoopState) -> dict:
    monitoring = _active_monitoring(state)
    if not monitoring:
        _say(state, 'Sinulla ei ole nyt aktiivisia geneettisiä seurantoja.', intent='EXPLAIN_FINDING', textSource='fixed')
        return {'toolInvoked': 'fetchStructuredFinding (ei tulosta)', 'contextUsed': ['activeGenomicFindings'], 'textSource': 'fixed'}
    if not support_consent.show_genetic_details(state):
        _say(state, texts.GENETIC_DETAILS_HIDDEN, intent='EXPLAIN_FINDING', textSource='fixed')
        return {'toolInvoked': 'respectConsent(showGeneticDetails=false)', 'contextUsed': ['consentSettings'], 'textSource': 'fixed'}
    finding = _finding(state, monitoring.findingId)
    fallback = texts.explain_finding(finding, agent.CONFIRMATION_LABELS[finding.confirmationStatus], monitoring.status)
    text, source, safety, unavailable = _phrase(state, {'task': 'explain_finding', 'findingId': finding.id}, fallback)
    _say(
        state, text, kind='explanation', intent='EXPLAIN_FINDING', textSource=source, aiUnavailable=unavailable,
        basis=_basis(state, decision_by='Ei uutta päätöstä: selitys tallennetusta löydöksestä ja seurannan tilasta',
                     text_source=source, monitoring_ids=[monitoring.id], include_user_provided=False),
    )
    return {
        'toolInvoked': 'fetchStructuredFinding + explain', 'contextUsed': ['activeGenomicFindings', 'currentMonitoringStates', 'evidenceReferences'],
        'safetyCheck': safety, 'textSource': source, 'finalState': monitoring.status,
    }


def explain_observation(state: LoopState, observation_id: str | None) -> dict:
    observation = next((o for o in state.observations if o.id == observation_id), None) if observation_id else _open_observation(state)
    if not observation:
        _say(state, texts.NO_OPEN_OBSERVATION, intent='EXPLAIN_OBSERVATION', textSource='fixed')
        result = _explain_finding(state)
        result['toolInvoked'] = 'fetchStructuredObservation (ei avointa) + ' + result['toolInvoked']
        return result

    facts = agent.observation_facts(state, observation)
    fallback = support_consent.mask_genes(state, texts.explain_observation(
        observation.title, facts['supportingEvents'], observation.connection, [r['name'] for r in facts['rules']]
    ))
    text, source, safety, unavailable = _phrase(state, {'task': 'explain_observation', 'observationId': observation.id}, fallback)
    _say(
        state, text, kind='explanation', intent='EXPLAIN_OBSERVATION', textSource=source, aiUnavailable=unavailable,
        whyNowObservationId=observation.id,
        basis=_basis(state, decision_by='Sääntömoottori', text_source=source, monitoring_ids=[observation.monitoringId],
                     event_ids=[e.id for e in facts['supportingEvents']], rule_ids=[r['id'] for r in facts['rules']]),
    )
    asked = _ask_missing_information(state, observation.findingId)
    return {
        'toolInvoked': 'fetchStructuredObservation + explain' + (f' + askMissingInformation({asked})' if asked else ''),
        'contextUsed': ['openObservations', 'recentHealthEvents', 'evidenceReferences', 'knownMissingInformation'],
        'ruleApplied': [{'id': r['id'], 'name': r['name'], 'note': 'aiemmin tehty sääntöpäätös, ei uutta arviota'} for r in facts['rules']],
        'safetyCheck': safety, 'textSource': source, 'finalState': observation.status,
    }


def _ask_missing_information(state: LoopState, finding_id: str) -> str | None:
    item = next((m for m in agent.missing_information_for(state, finding_id) if m.askable and m.question), None)
    if not item or state.awaitingMissingInfoId == item.id:
        return None
    state.awaitingMissingInfoId = item.id
    _say(
        state, f'{texts.MISSING_INFO_INTRO}\n\n{item.question}', kind='question', initiatedByAgent=True, intent='CLARIFY',
        textSource='fixed', actions=[_action(state, 'Ohita toistaiseksi', 'skip_missing', style='secondary', missingInfoId=item.id)],
    )
    return item.id


RECENT_DAYS = 90
STATUS_EVENT_TYPES = ('lab_result', 'vital_sign', 'medication', 'research_update', 'family_history', 'free_text', 'self_report')


def _days_between(earlier: str, later: str) -> int:
    return (date_cls.fromisoformat(later) - date_cls.fromisoformat(earlier)).days


def _profile_line(state: LoopState) -> str | None:
    profile = state.profile
    if not profile.get('birthYear'):
        return None
    age = int(state.currentDate[:4]) - profile['birthYear']
    return f"{profile.get('name', 'Käyttäjä')}, {age} vuotta, {profile.get('heightCm')} cm, {profile.get('weightKg')} kg."


def _event_text(event) -> str:
    value = fi_value(event)
    flag = texts.FLAG_SHORT.get(event.abnormalFlag or '')
    return f"{fi_date(event.date)} {event.displayName}{': ' + value if value else ''}{' – ' + flag if flag else ''}"


def _status(state: LoopState, intent: str) -> dict:
    """"Mikä on tilanteeni?" - a deterministic reading of the health timeline: is anything acute right now
    (open observations, due tasks, out-of-range values in the last 3 months), then the recent events."""
    today = state.currentDate
    events = sorted(state.events, key=lambda e: (e.date, e.id))
    recent = [e for e in events if 0 <= _days_between(e.date, today) <= RECENT_DAYS and e.type in STATUS_EVENT_TYPES][-6:]

    acute: list[str] = []
    for o in state.observations:
        if o.status in OPEN_OBSERVATION_STATES:
            acute.append(f"Avoin huomio: {support_consent.mask_genes(state, o.title)} ({texts.STATUS_LABELS.get(o.status, o.status)}).")
    for t in state.tasks:
        if t.status == 'open' and t.dueAt <= today:
            acute.append(f"Seurantatehtävä odottaa vastaustasi (määräpäivä {fi_date(t.dueAt)}).")
    for e in recent:
        if e.abnormalFlag in ('high', 'low'):
            acute.append(f"{e.displayName} {fi_value(e)} ({fi_date(e.date)}) – {texts.FLAG_SHORT[e.abnormalFlag]}.")

    assessment_line = None
    latest = support_assessment.newest_first(list(state.support.assessments))
    if latest:
        assessment_line = texts.STATUS_LATEST_ASSESSMENT.format(label=latest[0].urgencyLabel, date=fi_date(latest[0].createdAt))
        # an open assessment that requires contact is something to act on now, not just background
        if latest[0].status in support_assessment.OPEN_STATUSES and latest[0].urgency in ('within_3_days', 'same_day', 'emergency'):
            acute.append(assessment_line)
            assessment_line = None

    lines = [f'Tilanteesi {fi_date(today)}', '']
    plan_lines = support_situation.chat_status_lines(state)
    if plan_lines:
        lines.extend([*plan_lines, ''])
    if acute:
        lines.append(texts.STATUS_ACUTE_HEADING)
        lines.extend(f'• {a}' for a in acute)
    else:
        lines.append(texts.STATUS_NOTHING_ACUTE)
    if assessment_line:
        lines.append(assessment_line)
    lines.append('')

    if recent:
        lines.append(texts.STATUS_RECENT_HEADING)
        lines.extend(f'• {_event_text(e)}' for e in reversed(recent))
    elif events:
        lines.append(f'Viimeisen 3 kuukauden ajalta ei ole kirjattuja tapahtumia. Viimeisin: {_event_text(events[-1])}.')
    else:
        lines.append('Terveysaikajanalla ei ole vielä tapahtumia.')
    lines.append('')

    profile_line = _profile_line(state)
    active = [(m, _finding(state, m.findingId)) for m in state.monitorings if m.active]
    genes = ', '.join(support_consent.genetic_label(state, f.gene, 'perimätiedon havainto') for _, f in active if f)
    seuranta = (f"Geneettinen seuranta: {len(active)} {'löydös' if len(active) == 1 else 'löydöstä'} ({genes})."
                if active else 'Geneettisessä seurannassa ei ole löydöksiä.')
    lines.append(' '.join(x for x in (profile_line, seuranta) if x))
    lines.append(texts.STATUS_NOTE)

    _say(
        state, '\n'.join(lines), intent=intent, textSource='template',
        basis=_basis(state, decision_by='Sääntömoottorin tallentamat tiedot: aikajana, huomiot ja tehtävät (ei uutta päätöstä)',
                     text_source='template', include_user_provided=False),
    )
    return {'toolInvoked': 'summarizeTimelineStatus (template)',
            'contextUsed': ['recentHealthEvents', 'openObservations', 'followUpTasks', 'activeGenomicFindings'],
            'textSource': 'template'}


def _focus_lines(state: LoopState) -> list[str]:
    """Combine each monitored finding with what the timeline does (or does not) show about it."""
    today = state.currentDate
    events = sorted(state.events, key=lambda e: (e.date, e.id))
    points: list[str] = []
    genes: set[str] = set()

    for m in (m for m in state.monitorings if m.active):
        finding = _finding(state, m.findingId)
        if not finding:
            continue
        gene = (finding.gene or '').upper()
        genes.add(gene)
        label = support_consent.genetic_label(state, gene, 'Perimätiedon havainto')
        focus = texts.FOCUS_BY_GENE.get(gene)
        if not focus:
            points.append(f'{support_consent.genetic_label(state, finding.title, "Perimätiedon havainto")}: havainto on seurannassa. '
                          'Ota se puheeksi seuraavalla käynnillä, jos et ole vielä tehnyt niin.')
            continue
        if 'note' in focus:
            points.append(focus['note'])
            continue
        matching = [e for e in events if e.code in focus['codes'] and e.value is not None]
        if not matching:
            points.append(f"{label}: aikajanalla ei ole yhtään mittausta, joka kertoisi {focus['metric']}. {focus['why']} "
                          'Mittaustulos antaisi seurannalle lähtötason – voit ottaa sen puheeksi seuraavalla käynnillä.')
            continue
        latest = matching[-1]
        flag = texts.FLAG_SHORT.get(latest.abnormalFlag or '', '')
        age_note = ' Mittaus on yli vuoden vanha, joten uusi mittaus voisi olla ajankohtainen.' if _days_between(latest.date, today) > 365 else ''
        points.append(f"{label}: viimeisin {latest.displayName} {fi_value(latest)} ({fi_date(latest.date)}){', ' + flag if flag else ''}. {focus['why']}{age_note}")

    # the recent trend only: readings of the last 12 months (older occupational health checks are history)
    bp = [e for e in events if e.code == 'BP' and isinstance(e.value, str) and '/' in e.value and 0 <= _days_between(e.date, today) <= 365]
    if len(bp) >= 2 and genes & texts.CARDIO_GENES:
        first, last = bp[0], bp[-1]
        trend = 'noussut hieman' if int(last.value.split('/')[0]) > int(first.value.split('/')[0]) else 'pysynyt samalla tasolla tai laskenut'
        in_range = all(e.abnormalFlag == 'normal' for e in bp)
        points.append(f"Verenpaine on {trend} ({first.value} → {last.value} mmHg){', mutta pysynyt viitealueella' if in_range else ''}. "
                      'Koska seurannassa on sydän- ja verisuoniterveyteen liittyvä löydös, kotimittauksia kannattaa jatkaa.')

    for item in state.missingInformation:
        if item.status == 'missing' and item.askable:
            points.append(f'Puuttuva tieto: {item.label.lower()}. Täydentäminen tarkentaa seurantaa – voit kertoa sen tässä keskustelussa.')

    surveys = [e for e in events if e.type == 'lifestyle_survey']
    if surveys:
        watch = [texts.LIFESTYLE_LABELS.get(k, k) for k, v in surveys[-1].structuredData.items()
                 if isinstance(v, dict) and v.get('tier') == 'watch']
        if watch:
            points.append(f"Elämäntapakyselyssä ({fi_date(surveys[-1].date)}) kehityskohteiksi nousivat: {', '.join(watch)}.")
    elif not state.support.plans:
        # with an active support plan the agent asks 1-3 plan-based questions instead of a monthly survey
        points.append('Elämäntapakysely on tekemättä. Se auttaa näkemään, miten arjen tavat tukevat seurantaasi.')
    return points


def _focus(state: LoopState, intent: str, context_used: list[str]) -> dict:
    """"Mihin minun tulisi kiinnittää huomiota?" - monitoring x timeline combined into concrete points."""
    points = _focus_lines(state)
    lines = [texts.FOCUS_INTRO, *(f'• {p}' for p in points)] if points else ['Seurannassasi ei ole nyt erityistä huomioitavaa.']
    lines.append(texts.FOCUS_NOTE)
    _say(
        state, '\n'.join(lines), intent=intent, textSource='template',
        basis=_basis(state, decision_by='Seurannan löydökset yhdistettynä aikajanan tapahtumiin (ei uutta päätöstä)',
                     text_source='template', include_user_provided=False),
    )
    return {'toolInvoked': 'summarizeFocusAreas (template)', 'contextUsed': context_used, 'textSource': 'template'}


def _overview(state: LoopState, intent: str) -> dict:
    """"Mihin kiinnittää huomiota" / holistic overview. Prefers the LLM; the template fallback combines
    monitored findings with the timeline. GET_STATUS is answered separately by _status."""
    context = build_user_context(state)
    profile = state.profile
    age = int(state.currentDate[:4]) - profile['birthYear'] if profile.get('birthYear') else None
    overview_context = {
        **context,
        'profile': {'name': profile.get('name'), 'age': age, 'heightCm': profile.get('heightCm'), 'weightKg': profile.get('weightKg')},
    }
    context_used = [*USER_CONTEXT_KEYS, 'profile']

    if llm.enabled():
        answer = llm.summarize_health_overview(overview_context)
        if answer and check_text(answer)['passed']:
            _say(
                state, answer, intent=intent, textSource='llm',
                basis=_basis(state, decision_by='LLM muodosti ennakoivan kokonaiskuvan seuranta-, aikajana- ja profiilitiedoista',
                             text_source='llm', include_user_provided=False),
            )
            return {'toolInvoked': 'summarizeHealthOverview', 'contextUsed': context_used, 'textSource': 'llm'}

    return _focus(state, intent, context_used)


# --- ADD_CONTEXT ---------------------------------------------------------------------

def _extract(text: str) -> tuple[dict | None, str]:
    if llm.enabled():
        data = family_history.validate(
            llm.extract_family_history(text, list(family_history.RELATIONS_FI), list(family_history.CONDITIONS_FI))
        )
        if data:
            return data, 'llm'
        method = 'deterministic_parser (LLM-fallback)'
    else:
        method = 'deterministic_parser'
    return family_history.validate(family_history.parse(text)), method


def _add_context(state: LoopState, text: str) -> dict:
    data, method = _extract(text)
    if data:
        pending = _pending(state, 'save_context', kind='family_history', data=data, rawText=text,
                           extractionMethod=method, missingInfoId=state.awaitingMissingInfoId)
        _confirmation_message(state, pending, family_history.describe(data), allow_edit=True)
        return {'toolInvoked': 'extractStructuredHealthEvent + askConfirmationBeforeSaving', 'extraction': {'method': method, 'data': data},
                'userConfirmation': 'pending', 'contextUsed': ['knownMissingInformation'], 'textSource': 'template', 'extractionMethod': method}

    lab = parse_text(text)
    if lab.get('code') == 'LDL' and isinstance(lab.get('value'), float):
        from app.loop.extraction import abnormal_flag

        flag = abnormal_flag('LDL', lab['value'])
        pending = _pending(state, 'save_context', kind='lab_result', data={**lab, 'abnormalFlag': flag}, rawText=text,
                           extractionMethod='deterministic_parser', missingInfoId=None)
        value = f"{lab['value']:.1f}".replace('.', ',')
        lines = ['tulos: LDL-kolesteroli', f'arvo: {value} mmol/l', f"poikkeamamerkintä (sääntö): {'viitealueen yläpuolella' if flag == 'high' else 'viitealueella'}"]
        _confirmation_message(state, pending, lines, allow_edit=False)
        return {'toolInvoked': 'extractStructuredHealthEvent + askConfirmationBeforeSaving', 'extraction': {'method': 'deterministic_parser', 'data': lab},
                'userConfirmation': 'pending', 'contextUsed': ['recentHealthEvents'], 'textSource': 'template', 'extractionMethod': 'deterministic_parser'}

    _say(state, texts.EXTRACTION_FAILED, intent='ADD_CONTEXT', textSource='fixed')
    return {'toolInvoked': 'extractStructuredHealthEvent (ei tulkintaa, ei tallennusta)', 'extraction': {'method': method, 'data': None},
            'contextUsed': ['knownMissingInformation'], 'textSource': 'fixed', 'extractionMethod': method}


def _confirmation_message(state: LoopState, pending: PendingAction, lines: list[str], allow_edit: bool) -> None:
    bullets = '\n'.join(f'• {line}' for line in lines)
    actions = [_action(state, 'Tallenna', 'confirm_pending', pendingId=pending.id)]
    if allow_edit:
        actions.append(_action(state, 'Muokkaa', 'edit_pending', style='secondary', pendingId=pending.id))
    actions.append(_action(state, 'Peruuta', 'cancel_pending', style='secondary', pendingId=pending.id))
    message = _say(
        state, f'Tulkitsin vastauksesi näin:\n{bullets}\n\nTallennetaanko tieto seurantaasi?', kind='confirmation',
        intent='ADD_CONTEXT', textSource='template', pendingActionId=pending.id, actions=actions,
    )
    pending.messageId = message.id


def _save_context(state: LoopState, pending: PendingAction, edited: dict | None) -> dict:
    payload = pending.payload
    status_before = {m.id: m.status for m in state.monitorings if m.active}
    if payload['kind'] == 'family_history':
        data = family_history.validate(edited) if edited is not None else payload['data']
        if not data:
            raise CompanionError('Muokattu tieto ei ole kelvollinen.')
        result = agent.add_confirmed_family_history(state, data, payload['rawText'], payload['extractionMethod'])
    else:
        lab = payload['data']
        result = agent.add_event(
            state,
            fields={'type': 'lab_result', 'code': 'LDL', 'displayName': 'LDL-kolesteroli', 'value': lab['value'], 'unit': 'mmol/l',
                    'source': 'user_reported', 'rawText': payload['rawText']},
        )
        event = next(e for e in state.events if e.id == result['event']['id'])
        event.confirmedByUser = True
        result = {'event': event, 'log': [], 'created': [agent._observation(state, o['id']) for o in result['observations']],
                  'updated': [agent._observation(state, o['id']) for o in result['updatedObservations']]}
        data = lab

    event = result['event']
    changed = result['created'] + result['updated']
    rule_log = [
        {'id': entry.ruleApplied['id'], 'triggered': entry.ruleApplied['triggered'], 'decision': entry.decision}
        for entry in (result['log'] or [e for e in state.agentLog if e.detectedEvent and e.detectedEvent.get('id') == event.id])
        if entry.ruleApplied
    ]
    monitoring = _active_monitoring(state)
    if changed:
        observation = changed[0]
        for created in result['created']:
            state.proactiveKeys.append(f'obs-new:{created.id}')
        facts = agent.observation_facts(state, observation)
        status_changed = bool(result['created']) or status_before.get(observation.monitoringId) != _monitoring_status(state, observation.monitoringId)
        text = f'{texts.RULE_UPDATED}\n\n{texts.STATE_CHANGED_PROMPT}' if status_changed else texts.RULE_UPDATED
        _say(
            state, text, kind='rule_update', intent='ADD_CONTEXT', textSource='fixed',
            actions=[_action(state, 'Näytä miksi', 'explain_observation', observationId=observation.id)],
            basis=_basis(state, decision_by='Sääntömoottori', text_source='fixed', monitoring_ids=[observation.monitoringId],
                         event_ids=[e.id for e in facts['supportingEvents']], rule_ids=[r['id'] for r in facts['rules']]),
        )
        final_state = observation.status
    else:
        _say(
            state, texts.SAVED_NO_CHANGE, kind='text', intent='ADD_CONTEXT', textSource='fixed',
            basis=_basis(state, decision_by='Sääntömoottori (sääntö ei täyttynyt)', text_source='fixed',
                         monitoring_ids=[monitoring.id] if monitoring else [], event_ids=[event.id],
                         rule_ids=[r['id'] for r in rule_log]),
        )
        final_state = monitoring.status if monitoring else None
    return {
        'toolInvoked': 'saveHealthEvent + ruleEngine.evaluate',
        'extraction': {'method': payload.get('extractionMethod'), 'data': data, 'edited': edited is not None},
        'ruleApplied': rule_log,
        'finalState': final_state,
        'extractionMethod': payload.get('extractionMethod'),
    }


# --- PREPARE / ACT ---------------------------------------------------------------------

def _request_confirmation(state: LoopState, intent: str) -> dict:
    if intent == 'CREATE_SUMMARY':
        if not any(m.active for m in state.monitorings):
            _say(state, 'Sinulla ei ole vielä seurannassa löydöksiä, joten yhteenvetoa ei voi vielä muodostaa.',
                 intent=intent, textSource='fixed')
            return {'toolInvoked': None, 'contextUsed': ['activeGenomicFindings'], 'textSource': 'fixed'}
        pending = _pending(state, 'create_summary')
        actions = [_action(state, 'Muodosta yhteenveto', 'confirm_pending', pendingId=pending.id),
                   _action(state, 'Peruuta', 'cancel_pending', style='secondary', pendingId=pending.id)]
        message = _say(state, texts.SUMMARY_CONFIRM, kind='confirmation', intent=intent, textSource='fixed',
                        pendingActionId=pending.id, actions=actions)
        pending.messageId = message.id
        return {'toolInvoked': 'askForUserConfirmation', 'userConfirmation': 'pending',
                'contextUsed': ['activeGenomicFindings', 'recentHealthEvents'], 'textSource': 'fixed'}

    observation = _open_observation(state)
    if not observation:
        extra = {'CREATE_FOLLOWUP': ' Muistutus liitetään avoimeen huomioon.',
                 'RESOLVE_TASK': ' Käsiteltäväksi merkittävää ei ole.'}[intent]
        _say(state, texts.NO_OPEN_OBSERVATION + extra, intent=intent, textSource='fixed')
        return {'toolInvoked': None, 'contextUsed': ['openObservations'], 'textSource': 'fixed'}

    if intent == 'CREATE_FOLLOWUP':
        pending = _pending(state, 'create_followup', observationId=observation.id)
        actions = [_action(state, '7 päivän kuluttua', 'confirm_pending', pendingId=pending.id, days=7),
                   _action(state, '30 päivän kuluttua', 'confirm_pending', pendingId=pending.id, days=30),
                   _action(state, 'Muu päivämäärä', 'choose_date', style='secondary', pendingId=pending.id),
                   _action(state, 'Peruuta', 'cancel_pending', style='secondary', pendingId=pending.id)]
        text = texts.REMINDER_ASK
    else:
        pending = _pending(state, 'resolve_observation', observationId=observation.id)
        actions = [_action(state, 'Kyllä', 'confirm_pending', pendingId=pending.id),
                   _action(state, 'Ei', 'cancel_pending', style='secondary', pendingId=pending.id)]
        text = texts.RESOLVE_ASK
    message = _say(state, text, kind='confirmation', intent=intent, textSource='fixed', pendingActionId=pending.id, actions=actions)
    pending.messageId = message.id
    return {'toolInvoked': 'askForUserConfirmation', 'userConfirmation': 'pending', 'contextUsed': ['openObservations', 'followUpTasks'],
            'textSource': 'fixed', 'finalState': observation.status}


def _create_full_summary(state: LoopState) -> dict:
    summary = agent.full_summary(state)
    agent.mark_full_summary_created(state)
    extra = '\n\nEhdotettuja lisäselvityksiä:\n' + '\n'.join(f'• {s}' for s in summary['suggestedNextSteps']) if summary['suggestedNextSteps'] else ''
    questions = '\n'.join(f'• {q}' for q in summary['questionsForProfessional'])
    questions_block = f"\n\nKysymyksiä, joita voit esittää vastaanotolla:\n{questions}" if questions else ''
    monitoring_ids = [m.id for m in state.monitorings if m.active]
    _say(
        state, f'{texts.SUMMARY_READY}{extra}{questions_block}',
        kind='summary_ready', intent='CREATE_SUMMARY', textSource='template',
        actions=[_action(state, 'Avaa yhteenveto', 'open_summary')],
        basis=_basis(state, decision_by='Ei uutta päätöstä: yhteenveto koottiin kaikista seurannassa olevista löydöksistä ja aikajanasta',
                     text_source=summary['introSource'] or 'template', monitoring_ids=monitoring_ids, include_user_provided=False),
    )
    return {'toolInvoked': 'createFullProfessionalSummary', 'textSource': summary['introSource'] or 'template'}


def _create_reminder(state: LoopState, observation_id: str, days: int | None, due: str | None) -> dict:
    if due:
        try:
            date_cls.fromisoformat(due)
        except ValueError as exc:
            raise CompanionError('Päivämäärä ei ole kelvollinen.') from exc
    due_at = due or add_days(state.currentDate, int(days or 30))
    try:
        task = agent.schedule_reminder(state, observation_id, due_at)
    except agent.LoopError as exc:
        raise CompanionError(str(exc)) from exc
    _say(state, f'Muistutus on luotu: {fi_date(task.dueAt)}. Kysyn silloin, onko asia käsitelty ammattilaisen kanssa.',
         intent='CREATE_FOLLOWUP', textSource='fixed')
    return {'toolInvoked': f'createFollowUpTask({task.id}, dueAt={task.dueAt})', 'finalState': agent._observation(state, observation_id).status}


def _resolve(state: LoopState, observation_id: str) -> dict:
    try:
        observation = agent.resolve_observation(state, observation_id)
    except agent.LoopError as exc:
        raise CompanionError(str(exc)) from exc
    _say(state, 'Merkitsin huomion käsitellyksi. Seuranta jatkuu normaalisti.', intent='RESOLVE_TASK', textSource='fixed')
    return {'toolInvoked': f'resolveObservation({observation_id})', 'finalState': observation.status}


# --- safety intents ---------------------------------------------------------------------

def _diagnosis_or_medication(state: LoopState, intent: str) -> dict:
    observation = _open_observation(state)
    actions = [_action(state, 'Valmistele yhteenveto ammattilaiselle', 'request_summary')] if observation else []
    if intent == 'DIAGNOSIS_REQUEST':
        context = build_user_context(state)
        facts = [f"• Seurannassa: {f['title']} (vahvistustila: {agent.CONFIRMATION_LABELS[f['confirmationStatus']]})" for f in context['activeGenomicFindings']]
        facts += [f"• Avoin huomio: {o['title']}" for o in context['openObservations']]
        facts = [support_consent.mask_genes(state, line) for line in facts]
        facts += [f"• Puuttuva tieto: {m['question']}" for m in context['knownMissingInformation'] if m['status'] == 'missing' and m['question']]
        text = '\n'.join([texts.DIAGNOSIS, *(facts or ['• Ei avoimia huomioita.']), '', texts.DIAGNOSIS_END])
        if observation:
            text += f' {texts.OFFER_SUMMARY}'
        tool = 'doNotDiagnose + explainRelevantKnownFacts' + (' + offerProfessionalSummary' if observation else '')
        context_used = ['activeGenomicFindings', 'openObservations', 'knownMissingInformation']
    else:
        text = texts.MEDICATION + (f' {texts.OFFER_SUMMARY}' if observation else '')
        tool = 'doNotRecommendMedicationChange + directToProfessional'
        context_used = ['openObservations']
    _say(state, text, kind='safety', intent=intent, textSource='fixed', actions=actions,
         basis=_basis(state, decision_by='Kiinteä turvallisuussääntö (ei kliinistä päätöstä)', text_source='fixed', include_user_provided=False))
    return {'toolInvoked': tool, 'contextUsed': context_used, 'textSource': 'fixed',
            'safetyCheck': {'performed': True, 'rule': 'deterministic_refusal', 'llmUsed': False}}


def _emergency_rule() -> dict:
    """The policy's emergency symptom rule (TRI-EMERG-001) as a rulesApplied entry."""
    rule = next((r for r in support_assessment.automation().get('symptomRules', []) if r.get('urgency') == 'emergency'), None)
    if not rule:
        return {'id': 'TRI-EMERG', 'name': 'TRI-EMERG', 'description': texts.EMERGENCY_ASSESSMENT_REASON}
    return {'id': rule['id'], 'name': rule.get('name', rule['id']), 'description': rule.get('reason') or texts.EMERGENCY_ASSESSMENT_REASON}


def _record_emergency_assessment(state: LoopState, text: str):
    """Record the emergency as an assessment with mode 'excluded_emergency' (support.assessment.create sets the mode):
    rules only, fixed reason, no LLM. The class is always 'emergency' here, whatever the symptom table would say."""
    result = support_assessment.classify_symptoms(state, text)
    is_emergency = result['urgency'] == 'emergency' and result['rule']
    rule = result['rule'] if is_emergency else _emergency_rule()
    symptoms = result['symptoms'] if is_emergency else []
    described = f'Oirekuvaus chatissa {fi_date(state.currentDate)}' + (f": {', '.join(symptoms)}." if symptoms else '.')
    return support_assessment.create(
        state, trigger='symptom_report', urgency='emergency', reason=rule.get('description') or texts.EMERGENCY_ASSESSMENT_REASON,
        basis=[described], rules=[rule], plan=support_assessment._bp_plan(state), symptoms=symptoms,
    )


def _emergency(state: LoopState, text: str, assessment=None) -> dict:
    """Fixed, predefined 112 message (never the LLM). The emergency is also recorded as an assessment that is excluded
    from the automated assessment (mode 'excluded_emergency')."""
    state.awaitingMissingInfoId = None
    if assessment is None:
        assessment = _record_emergency_assessment(state, text)
    plan = support_plans.find(state, assessment.planId) if assessment.planId else None
    basis = support_messages.assessment_basis(assessment, plan, decision_by=texts.EMERGENCY_DECISION_BY)
    basis.update({'textBy': 'Kiinteä viesti', 'statement': texts.EMERGENCY_BASIS_STATEMENT})
    _say(state, f'{texts.EMERGENCY}\n\n{texts.EMERGENCY_NOTE}', kind='emergency', intent='EMERGENCY_OR_URGENT', textSource='fixed',
         basis=basis, assessment=support_messages.assessment_ref(assessment))
    return {'toolInvoked': f'usePredefinedSafetyMessage + recordAssessment({assessment.id}, excluded_emergency)', 'contextUsed': [],
            'textSource': 'fixed', 'finalState': assessment.mode,
            'ruleApplied': [{'id': r['id'], 'name': r['name'], 'note': 'hätätilanne: ei automaattisen arvion piirissä'} for r in assessment.rulesApplied],
            'safetyCheck': {'performed': True, 'rule': 'predefined_emergency_message', 'llmUsed': False, 'dnaRiskUsed': False}}


# --- automated assessment of the need for care and its urgency (rules decide, the LLM never sets the class) --------

def _care_need_assessment(state: LoopState, text: str) -> dict:
    """A symptom description: support.assessment classifies it with the policy's symptom table and context rules,
    records the assessment, routes it to the responsible professional when the class requires contact and posts the
    template reply (kind 'care_assessment'). An emergency class goes to the fixed 112 path instead."""
    assessment, message = support_assessment.assess_symptom_report(state, text)
    if assessment.mode == 'excluded_emergency' or message is None:
        result = _emergency(state, text, assessment=assessment)
        result['intentOverride'] = 'EMERGENCY_OR_URGENT'
        return result
    message.intent = 'CARE_NEED_ASSESSMENT'
    context = ['symptomDescription', 'automationPolicy.symptomRules', 'consentSettings']
    if assessment.planId:
        context += ['activeSupportPlans', 'homeMeasurements']
    return {
        'toolInvoked': f'assessCareNeed({assessment.id}, {assessment.urgency}, {assessment.mode})'
                       + (f' + routeToProfessional({assessment.escalationId})' if assessment.escalationId else ''),
        'contextUsed': context,
        'ruleApplied': [{'id': r['id'], 'name': r['name'], 'note': 'sääntömoottorin automaattinen arvio'} for r in assessment.rulesApplied],
        'safetyCheck': {'performed': True, 'rule': 'deterministic_symptom_rules', 'llmUsed': False, 'urgency': assessment.urgency},
        'textSource': 'template',
        'finalState': assessment.urgency,
    }


def _human_review_route(state: LoopState):
    """A plan through which a request for a professional's assessment can be routed (its user_request rule). The
    blood-pressure plan (the one symptom assessments are linked to) comes first."""
    for plan in sorted(state.support.plans, key=lambda p: p.theme != 'blood_pressure'):
        rule = next((r for r in plan.escalationRules if r.kind == 'user_request'), None)
        if rule and plan.status in ('active', 'escalated') and 'escalate' in plan.allowedActions:
            return plan, rule
    return None, None


def _human_assessment_request(state: LoopState, assessment_id: str | None = None) -> dict:
    """The user's right to an assessment made by a healthcare professional. The latest open assessment (or the one
    whose button was pressed) goes to support.assessment.request_human_review, which posts HUMAN_REVIEW_CONFIRMED.
    Without an assessment a plan's user_request rule creates one (trigger 'user_request') and routes it; without such
    a plan the reply names the service contact."""
    intent = 'HUMAN_ASSESSMENT_REQUEST'
    if assessment_id:
        try:
            target = support_assessment.find(state, assessment_id)
        except support_assessment.AssessmentError as exc:
            raise CompanionError(str(exc)) from exc
    else:
        candidates = [a for a in support_assessment.newest_first(list(state.support.assessments))
                      if a.status in support_assessment.OPEN_STATUSES and a.mode != 'excluded_emergency']
        target = candidates[0] if candidates else None

    if target and target.status == 'human_review_requested':
        _say(state, texts.HUMAN_REVIEW_ALREADY.format(date=fi_date(target.humanReviewRequestedAt or target.createdAt)),
             intent=intent, textSource='fixed')
        return {'toolInvoked': f'requestHumanReview({target.id}) – jo pyydetty', 'contextUsed': ['careAssessments'], 'textSource': 'fixed',
                'finalState': target.status}

    tool = ''
    if target is None:
        plan, rule = _human_review_route(state)
        if not plan:
            contact = support_policies.service_contact('NURSE_LINE')
            _say(state, texts.HUMAN_REVIEW_SERVICE_CONTACT.format(contact=f"{contact['label']}, {contact['details']}"),
                 intent=intent, textSource='fixed')
            return {'toolInvoked': 'directToServiceContact (ei suunnitelmaa, jonka kautta pyynnön voi välittää)', 'contextUsed': ['activeSupportPlans'],
                    'textSource': 'fixed'}
        target = support_assessment.create(
            state, trigger='user_request', urgency=support_assessment.from_rule_urgency(rule.urgency), reason=texts.HUMAN_REVIEW_CHAT_REASON,
            basis=[texts.HUMAN_REVIEW_CHAT_BASIS.format(date=fi_date(state.currentDate))], rules=[rule], plan=plan, sources=list(plan.sources),
        )
        tool = f'createAssessment({target.id}, user_request) + '
    try:
        support_assessment.request_human_review(state, target.id, via='chat')
    except support_assessment.AssessmentError as exc:
        raise CompanionError(str(exc)) from exc
    state.chatMessages[-1].intent = intent
    escalation = support_assessment.linked_escalation(state, target)
    return {
        'toolInvoked': f'{tool}requestHumanReview({target.id})' + (f' + routeToProfessional({escalation.id})' if escalation else ''),
        'contextUsed': ['careAssessments', 'activeSupportPlans'],
        'ruleApplied': [{'id': r['id'], 'name': r['name'], 'note': 'asiakkaan oikeus ammattilaisen tekemään arvioon'} for r in target.rulesApplied],
        'textSource': 'template',
        'finalState': target.status,
    }


# --- public API -------------------------------------------------------------------------------

def handle_user_message(state: LoopState, text: str) -> dict:
    text = text.strip()
    if not text:
        raise CompanionError('Viesti puuttuu.')
    if len(text) > MAX_MESSAGE_LENGTH:
        raise CompanionError('Viesti on liian pitkä.')
    _user_says(state, text)
    intent, method = intent_router.classify(text, awaiting_missing_info=bool(state.awaitingMissingInfoId))

    handlers = {
        'EXPLAIN_FINDING': lambda: _explain_finding(state),
        'EXPLAIN_OBSERVATION': lambda: explain_observation(state, None),
        'GET_STATUS': lambda: _status(state, 'GET_STATUS'),
        'HEALTH_OVERVIEW': lambda: _overview(state, 'HEALTH_OVERVIEW'),
        'ADD_CONTEXT': lambda: _add_context(state, text),
        'CREATE_SUMMARY': lambda: _request_confirmation(state, 'CREATE_SUMMARY'),
        'CREATE_FOLLOWUP': lambda: _request_confirmation(state, 'CREATE_FOLLOWUP'),
        'RESOLVE_TASK': lambda: _request_confirmation(state, 'RESOLVE_TASK'),
        'GENERAL_HEALTH_QUESTION': lambda: _general(state, text),
        'DIAGNOSIS_REQUEST': lambda: _diagnosis_or_medication(state, 'DIAGNOSIS_REQUEST'),
        'MEDICATION_CHANGE_REQUEST': lambda: _diagnosis_or_medication(state, 'MEDICATION_CHANGE_REQUEST'),
        'EMERGENCY_OR_URGENT': lambda: _emergency(state, text),
        'CARE_NEED_ASSESSMENT': lambda: _care_need_assessment(state, text),
        'HUMAN_ASSESSMENT_REQUEST': lambda: _human_assessment_request(state),
        'SELF_CARE_MEMORY': lambda: _continuity_answer(state, 'SELF_CARE_MEMORY'),
        'NEXT_STEP': lambda: _continuity_answer(state, 'NEXT_STEP'),
        'SELF_CARE_DIRECTION': lambda: _continuity_answer(state, 'SELF_CARE_DIRECTION'),
        'WELLBEING_DATA': lambda: _wellbeing_answer(state),
    }
    result = handlers[intent]()
    # a symptom description whose rule class is 'emergency' is answered with the fixed 112 message
    intent = result.pop('intentOverride', intent)
    state.chatMessages[-1].intent = state.chatMessages[-1].intent or intent
    _log(
        state, userMessage=text, trigger='user_message', intent=intent, intentMethod=method,
        contextUsed=result.get('contextUsed', []), extraction=result.get('extraction'),
        userConfirmation=result.get('userConfirmation', 'not_required'), toolInvoked=result.get('toolInvoked'),
        ruleApplied=result.get('ruleApplied', []), safetyCheck=result.get('safetyCheck'), finalState=result.get('finalState'),
        llmRole=_llm_role(result.get('textSource', 'fixed'), method, result.get('extractionMethod')),
    )
    return {'intent': intent, 'intentMethod': method}


# The self-care continuity engine's answers: template texts from the plans, the notes and the rounds (no LLM, no decision)
_CONTINUITY_ANSWERS = {
    'SELF_CARE_MEMORY': (support_continuity.memory_chat_text, 'recallSelfCareMemory',
                         'Omahoidon muisti: suunnitelmat, ammattilaisten kirjaukset ja vastauksesi sääntöjen perusteella (ei uutta päätöstä)'),
    'NEXT_STEP': (support_continuity.step_chat_text, 'currentSelfCareStep',
                  'Suunnitelman askel ja viikkotarkistusten palaute (ei uutta päätöstä)'),
    'SELF_CARE_DIRECTION': (support_continuity.direction_chat_text, 'selfCareDirection',
                            'Suunnitelman säännöt: jatketaanko omahoitoa, muutetaanko suunnitelmaa vai tarvitaanko ammattilaista'),
}


def _continuity_answer(state: LoopState, intent: str) -> dict:
    if not state.support.person:
        _say(state, texts.CONTINUITY_UNAVAILABLE, intent=intent, textSource='fixed')
        return {'toolInvoked': None, 'contextUsed': [], 'textSource': 'fixed'}
    build, tool, decision = _CONTINUITY_ANSWERS[intent]
    _say(state, build(state), intent=intent, textSource='template', basis=support_continuity.chat_basis(state, decision))
    return {'toolInvoked': f'{tool} (template)', 'contextUsed': ['activeSupportPlans', 'checkIns', 'professionalNotes', 'homeMonitoring'],
            'textSource': 'template'}


def _wellbeing_answer(state: LoopState) -> dict:
    """Hyvinvointidata in the chat: the LLM may phrase it from the bounded context (checked), otherwise the template."""
    context = build_user_context(state)
    decision = 'Hyvinvointidatan yhteenveto omaan tasoon verrattuna (sääntöpohjainen, ei uutta päätöstä)'
    if llm.enabled() and context.get('wellbeingData'):
        answer = llm.explain_wellbeing_trends(context)
        if answer and check_text(answer)['passed']:
            _say(state, answer, intent='WELLBEING_DATA', textSource='llm',
                 basis=_basis(state, decision_by=decision, text_source='llm', include_user_provided=False))
            return {'toolInvoked': 'explainWellbeingTrends', 'contextUsed': ['wellbeingData', 'activeSupportPlans'], 'textSource': 'llm'}
    _say(state, wellbeing_context.chat_summary(state), intent='WELLBEING_DATA', textSource='template',
         basis=_basis(state, decision_by=decision, text_source='template', include_user_provided=False))
    return {'toolInvoked': 'summarizeWellbeingData (template)', 'contextUsed': ['wellbeingData'], 'textSource': 'template'}


def _general(state: LoopState, text: str) -> dict:
    if llm.enabled():
        answer = llm.answer_general_health_question(text)
        if answer and check_text(answer)['passed']:
            _say(
                state, answer, intent='GENERAL_HEALTH_QUESTION', textSource='llm',
                basis=_basis(state, decision_by='LLM vastasi yleiseen terveyskysymykseen (ei henkilökohtaista neuvontaa, ei pääsyä seurantatietoihin)',
                             text_source='llm', include_user_provided=False),
            )
            return {'toolInvoked': 'answerGeneralHealthQuestion', 'contextUsed': [], 'textSource': 'llm'}
    _say(state, texts.GENERAL, intent='GENERAL_HEALTH_QUESTION', textSource='fixed')
    return {'toolInvoked': 'scopeLimitMessage', 'contextUsed': [], 'textSource': 'fixed'}


def _find_action(state: LoopState, action_id: str) -> tuple[ChatMessage, ChatAction]:
    for message in state.chatMessages:
        for action in message.actions:
            if action.id == action_id:
                return message, action
    raise CompanionError('Toimintoa ei löytynyt.')


def handle_action(state: LoopState, action_id: str, args: dict | None = None) -> dict:
    message, action = _find_action(state, action_id)
    if action.used:
        raise CompanionError('Tämä valinta on jo tehty.')
    args = args or {}
    if action.type == 'open_summary':
        return {'type': 'open_summary'}  # client-side view, no state change
    if action.type in ('edit_pending', 'choose_date') and not args:
        raise CompanionError('Tämä valinta tarvitsee lisätiedot lomakkeelta.')

    grouped = action.type in ('confirm_pending', 'edit_pending', 'choose_date', 'cancel_pending', 'task_response', 'skip_missing', 'dismiss',
                              'checkin_answer', 'checkin_skip', 'home_monitoring_accept', 'home_monitoring_decline',
                              'discuss_health_observation', 'dismiss_health_observation', 'health_reasons', 'health_reason', 'health_follow')
    if grouped:
        for sibling in message.actions:
            sibling.used = True
    else:
        action.used = True
    label = action.label if action.type not in ('edit_pending', 'choose_date') else f'{action.label} (tiedot lomakkeelta)'
    _user_says(state, label, kind='action_choice')

    log = {'trigger': 'user_action', 'userMessage': f'[valinta] {label}', 'intent': message.intent}
    result: dict = {}
    if action.type == 'explain_observation':
        result = explain_observation(state, action.args.get('observationId'))
    elif action.type == 'request_summary':
        result = _request_confirmation(state, 'CREATE_SUMMARY')
        log['intent'] = 'CREATE_SUMMARY'
    elif action.type == 'skip_missing':
        state.awaitingMissingInfoId = None
        _say(state, texts.SKIPPED_QUESTION, intent='CLARIFY', textSource='fixed')
        result = {'toolInvoked': 'skipMissingInformation', 'userConfirmation': 'NO'}
    elif action.type == 'dismiss':
        result = {'toolInvoked': None}
    elif action.type == 'request_human_assessment':
        result = _human_assessment_request(state, action.args.get('assessmentId'))
        log['intent'] = 'HUMAN_ASSESSMENT_REQUEST'
        result['userConfirmation'] = 'YES'
    elif action.type in ('checkin_answer', 'checkin_skip'):
        from app.support import interventions  # local import: the support package reads the chat's state

        try:
            answered = interventions.answer(state, action.args['checkInId'], action.args['questionId'], action.args.get('optionId'),
                                            skip=action.type == 'checkin_skip', via='chat')
        except interventions.InterventionError as exc:
            raise CompanionError(str(exc)) from exc
        log['intent'] = 'SUPPORT_PLAN_CHECK_IN'
        result = {'toolInvoked': f"answerCheckIn({action.args['checkInId']})", 'userConfirmation': 'YES',
                  'contextUsed': ['activeSupportPlans', 'openCheckIns'], 'finalState': 'completed' if answered['completed'] else 'open'}
    elif action.type in ('home_monitoring_accept', 'home_monitoring_decline'):
        # the continuity engine's own offer: the user decides whether the short home monitoring starts
        try:
            period = support_continuity.respond(state, action.args['periodId'], accept=action.type == 'home_monitoring_accept', via='chat')
        except support_continuity.ContinuityError as exc:
            raise CompanionError(str(exc)) from exc
        log['intent'] = 'SUPPORT_PLAN_OUTREACH'
        result = {'toolInvoked': f"respondHomeMonitoring({period.id})", 'userConfirmation': 'YES',
                  'contextUsed': ['activeSupportPlans', 'homeMonitoring'], 'finalState': period.status}
    elif action.type in ('discuss_health_observation', 'dismiss_health_observation', 'health_reasons', 'health_reason', 'health_follow'):
        # Hyvinvointidata: the agent's own observation discussed in the chat (data, interpretation, next action)
        observation_id = action.args['observationId']
        try:
            if action.type == 'discuss_health_observation':
                wellbeing_observations.discuss(state, observation_id, via='chat')
            elif action.type == 'dismiss_health_observation':
                wellbeing_observations.dismiss(state, observation_id, via='chat')
            elif action.type == 'health_reasons':
                wellbeing_observations.ask_reasons(state, observation_id)
            else:
                wellbeing_observations.follow_up(state, observation_id, action.args.get('reason'))
        except wellbeing_observations.ObservationError as exc:
            raise CompanionError(str(exc)) from exc
        log['intent'] = 'WELLBEING_DATA'
        result = {'toolInvoked': f'{action.type}({observation_id})', 'userConfirmation': 'YES',
                  'contextUsed': ['wellbeingData', 'activeSupportPlans'], 'textSource': 'template'}
    elif action.type == 'reminder':
        result = _create_reminder(state, action.args['observationId'], action.args.get('days'), None)
        result['userConfirmation'] = 'YES'
    elif action.type == 'task_response':
        response = action.args['response']
        try:
            task = agent.respond_to_task(state, action.args['taskId'], response)
        except agent.LoopError as exc:
            raise CompanionError(str(exc)) from exc
        _say(state, texts.TASK_RESPONSE_REPLIES[response].format(date=fi_date(task.dueAt)), intent='RESOLVE_TASK', textSource='fixed')
        observation = agent._observation(state, task.observationId)
        result = {'toolInvoked': f'respondToFollowUpTask({task.id}, {response})', 'userConfirmation': 'YES', 'finalState': observation.status}
    elif action.type in ('confirm_pending', 'edit_pending', 'choose_date', 'cancel_pending'):
        pending = next((p for p in state.pendingActions if p.id == action.args['pendingId']), None)
        if not pending or pending.status != 'pending':
            raise CompanionError('Vahvistettavaa toimintoa ei löytynyt.')
        if action.type == 'cancel_pending':
            pending.status = 'cancelled'
            _say(state, texts.CANCELLED, intent=message.intent, textSource='fixed')
            result = {'toolInvoked': None, 'userConfirmation': 'NO'}
        else:
            pending.status = 'confirmed'
            if pending.type == 'save_context':
                result = _save_context(state, pending, args.get('data') if action.type == 'edit_pending' else None)
            elif pending.type == 'create_summary':
                result = _create_full_summary(state)
            elif pending.type == 'create_followup':
                result = _create_reminder(state, pending.payload['observationId'], action.args.get('days'), args.get('date'))
            elif pending.type == 'resolve_observation':
                result = _resolve(state, pending.payload['observationId'])
            result['userConfirmation'] = 'YES'
    else:
        raise CompanionError('Tuntematon toiminto.')

    _log(
        state, **log, contextUsed=result.get('contextUsed', []), extraction=result.get('extraction'),
        userConfirmation=result.get('userConfirmation', 'not_required'), toolInvoked=result.get('toolInvoked'),
        ruleApplied=result.get('ruleApplied', []), safetyCheck=result.get('safetyCheck'), finalState=result.get('finalState'),
        llmRole=_llm_role(result.get('textSource', 'fixed'), None, result.get('extractionMethod')),
    )
    return {'type': action.type}


def sync_proactive(state: LoopState) -> None:
    """Agent-initiated messages for relevant state changes. Idempotent via proactiveKeys."""
    keys = set(state.proactiveKeys)

    def add_key(key: str) -> None:
        keys.add(key)
        state.proactiveKeys.append(key)

    if 'greeting' not in keys:
        add_key('greeting')
        _say(state, texts.GREETING, kind='greeting', initiatedByAgent=True, textSource='fixed')

    for observation in state.observations:
        key = f'obs-new:{observation.id}'
        if observation.status in OPEN_OBSERVATION_STATES and key not in keys:
            add_key(key)
            _say(
                state, texts.PROACTIVE_NEW_OBSERVATION, kind='proactive', initiatedByAgent=True, intent='EXPLAIN_OBSERVATION', textSource='fixed',
                actions=[_action(state, 'Näytä miksi', 'explain_observation', observationId=observation.id),
                         _action(state, 'Ei nyt', 'dismiss', style='secondary')],
                basis=_basis(state, decision_by='Sääntömoottori', text_source='fixed', monitoring_ids=[observation.monitoringId],
                             event_ids=observation.supportingEventIds or [observation.eventId], rule_ids=observation.ruleIds or [observation.ruleId],
                             include_user_provided=False),
            )
            _log(state, trigger='proactive:new_observation', intent='EXPLAIN_OBSERVATION', toolInvoked='proactiveMessage',
                 contextUsed=['openObservations'], ruleApplied=[{'id': r, 'note': 'sääntömoottorin päätös'} for r in (observation.ruleIds or [observation.ruleId])],
                 finalState=observation.status)

    for task in state.tasks:
        key = f'task-due:{task.id}:{task.dueAt}'
        if task.status == 'awaiting_response' and key not in keys:
            add_key(key)
            _say(
                state, texts.PROACTIVE_TASK_DUE, kind='proactive', initiatedByAgent=True, intent='RESOLVE_TASK', textSource='fixed',
                actions=[
                    _action(state, 'Kyllä', 'task_response', taskId=task.id, response='yes'),
                    _action(state, 'Ei vielä', 'task_response', style='secondary', taskId=task.id, response='not_yet'),
                    _action(state, 'En halua muistutuksia tästä', 'task_response', style='secondary', taskId=task.id, response='no_reminder'),
                    _action(state, 'Löydös todettiin epäolennaiseksi', 'task_response', style='secondary', taskId=task.id, response='not_relevant'),
                ],
            )
            _log(state, trigger='proactive:follow_up_due', intent='RESOLVE_TASK', toolInvoked='proactiveMessage',
                 contextUsed=['followUpTasks'], finalState=_monitoring_status(state, agent._observation(state, task.observationId).monitoringId))

    # Disable buttons that no longer apply (e.g. answered in Minun seuranta).
    tasks = {t.id: t for t in state.tasks}
    observations = {o.id: o for o in state.observations}
    pendings = {p.id: p for p in state.pendingActions}
    for message in state.chatMessages:
        for action in message.actions:
            if action.used:
                continue
            if action.type == 'task_response' and tasks.get(action.args.get('taskId')) and tasks[action.args['taskId']].status != 'awaiting_response':
                action.used = True
            elif 'pendingId' in action.args and pendings.get(action.args['pendingId']) and pendings[action.args['pendingId']].status != 'pending':
                action.used = True
            elif action.type == 'reminder' and observations.get(action.args.get('observationId')) and observations[action.args['observationId']].status not in OPEN_OBSERVATION_STATES:
                action.used = True
            elif action.type == 'skip_missing' and state.awaitingMissingInfoId != action.args.get('missingInfoId'):
                action.used = True


def knowledge_card(state: LoopState) -> dict:
    context = build_user_context(state)
    active = context['activeGenomicFindings']
    missing = [m for m in state.missingInformation if m.status == 'missing' and any(f['id'] == m.relatedFinding for f in active)]
    observation = _open_observation(state)
    tasks = sorted(context['followUpTasks'], key=lambda t: t['dueAt'])
    if observation and observation.status == 'waiting_for_user':
        next_task = 'Vastaa jatkokysymykseen: onko asia käsitelty ammattilaisen kanssa?'
    elif observation and observation.status in ('professional_review_recommended', 'waiting_for_professional_review'):
        next_task = 'Ammattilaisen arvio perimätiedon huomiosta' + (f" (muistutus {fi_date(tasks[0]['dueAt'])})" if tasks else '')
    elif observation:
        next_task = 'Täydennä puuttuva tieto'
    else:
        next_task = None
    relevant_ids = {m.lastRelevantEventId for m in state.monitorings if m.active and m.lastRelevantEventId}
    relevant = [e for e in state.events if e.id in relevant_ids]
    latest = max(relevant, key=lambda e: (e.date, e.id)) if relevant else None
    plans = [p for p in state.support.plans if p.status in ('active', 'escalated', 'paused')]
    return {
        'activePlans': len(plans),
        'activePlansLabel': f'{len(plans)} seurantasuunnitelma käynnissä' if len(plans) == 1 else f'{len(plans)} seurantasuunnitelmaa käynnissä',
        'planStates': [{'name': p.name, 'status': p.status, 'version': p.version} for p in plans],
        'activeMonitorings': len(active),
        'activeMonitoringsLabel': f"{len(active)} geneettinen löydös seurannassa" if len(active) == 1 else f'{len(active)} geneettistä löydöstä seurannassa',
        'openObservations': len(context['openObservations']),
        'openObservationsLabel': f"{len(context['openObservations'])} avoin huomio" if len(context['openObservations']) == 1 else f"{len(context['openObservations'])} avointa huomiota",
        'missingInformation': [m.label for m in missing],
        'nextTask': next_task,
        'latestRelevantEvent': texts.event_line(latest) if latest else None,
        'monitoringStates': [
            {'finding': support_consent.genetic_label(state, f['title'], 'Perimätiedon havainto'), 'status': m['status']}
            for m, f in zip(context['currentMonitoringStates'], active)
        ],
    }


def view(state: LoopState) -> dict:
    return {
        'messages': [m.model_dump() for m in state.chatMessages],
        'pendingActions': [p.model_dump() for p in state.pendingActions if p.status == 'pending'],
        'chatLog': [entry.model_dump() for entry in reversed(state.chatLog)],
        'knowledge': knowledge_card(state),
        'userContext': build_user_context(state),
        'awaitingMissingInfoId': state.awaitingMissingInfoId,
        'unansweredProactive': sum(
            1 for m in state.chatMessages if m.initiatedByAgent and m.actions and not any(a.used for a in m.actions)
        ),
        'disclaimers': {'whyNow': texts.WHY_NOW_DISCLAIMER, 'aiUnavailable': texts.AI_UNAVAILABLE},
        'familyHistoryOptions': {'relations': family_history.RELATIONS_FI, 'conditions': family_history.CONDITIONS_FI},
    }
