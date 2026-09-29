"""Deterministic monitoring agent.

Pipeline for every new HealthEvent:
detect event -> extract structured data -> match against active monitorings -> apply rules ->
evidence check -> safety check for user-facing text -> decision -> agent log.
All clinically meaningful triggers are plain rules from the local evidence file.
"""
from __future__ import annotations

from app.loop import family_history, llm, templates
from app.loop.evidence import (
    event_type_label,
    evidence_entry,
    evidence_level_label,
    load_profile,
    rules_for_gene,
    source_name,
)
from app.loop.extraction import abnormal_flag, extract
from app.loop.models import (
    MONITORABLE_STATUSES,
    OPEN_OBSERVATION_STATES,
    AgentLogEntry,
    FollowUpTask,
    GenomicFinding,
    HealthEvent,
    LoopState,
    MissingInformation,
    Monitoring,
    Observation,
)
from app.loop.safety import DISCLAIMER_FI, check_text
from app.loop.templates import fi_date, fi_value
from app.loop.timeline import group_entries
from app.loop.store import add_days, next_id

FOLLOW_UP_DAYS = 30
PERIODIC_REVIEW_DAYS = 90

CONFIRMATION_LABELS = {
    'raw_candidate': 'Vahvistamaton ehdokaslöydös',
    'synthetic_demo_confirmed': 'Demoa varten vahvistetuksi merkitty (synteettinen)',
    'professionally_confirmed': 'Terveydenhuollon ammattilaisen vahvistama',
}

SYSTEM_DID_NOT = [
    'Ei tehnyt diagnoosia.',
    'Ei ehdottanut lääkitysmuutoksia eikä ottanut kantaa lääkitykseen.',
    'Ei laskenut eikä esittänyt riskiprosentteja.',
    'Ei lähettänyt tietoja kenellekään (ei sähköposti- tai potilastietojärjestelmäyhteyttä).',
    'Ei antanut tekoälyn muuttaa päätöstä, sääntöä tai huomion tilaa.',
]


class LoopError(ValueError):
    pass


# --- helpers ---------------------------------------------------------------

def _finding(state: LoopState, finding_id: str) -> GenomicFinding:
    finding = next((item for item in state.findings if item.id == finding_id), None)
    if not finding:
        raise LoopError('Löydöstä ei löytynyt.')
    return finding


def _monitoring(state: LoopState, monitoring_id: str) -> Monitoring:
    monitoring = next((item for item in state.monitorings if item.id == monitoring_id), None)
    if not monitoring:
        raise LoopError('Seurantaa ei löytynyt.')
    return monitoring


def _observation(state: LoopState, observation_id: str) -> Observation:
    observation = next((item for item in state.observations if item.id == observation_id), None)
    if not observation:
        raise LoopError('Huomiota ei löytynyt.')
    return observation


def _event(state: LoopState, event_id: str | None) -> HealthEvent | None:
    return next((item for item in state.events if item.id == event_id), None)


def _set_status(monitoring: Monitoring, status: str) -> None:
    monitoring.status = status
    monitoring.currentAssessment = templates.assessment_for_status(status)


def _log(state: LoopState, **fields) -> AgentLogEntry:
    entry = AgentLogEntry(id=next_id(state, 'log'), date=state.currentDate, **fields)
    state.agentLog.append(entry)
    return entry


def _event_summary(event: HealthEvent) -> dict:
    return {
        'id': event.id,
        'date': event.date,
        'type': event.type,
        'code': event.code,
        'displayName': event.displayName,
        'value': event.value,
        'unit': event.unit,
        'abnormalFlag': event.abnormalFlag,
        'source': event.source,
        'synthetic': event.synthetic,
    }


def _safe_text(generated: str | None, fallback: str) -> tuple[str, str, dict]:
    """Use LLM text only if it passes the deterministic safety check; otherwise use the template."""
    template_check = check_text(fallback)
    if generated:
        check = check_text(generated)
        if check['passed']:
            return generated, 'llm', {'llmText': check, 'templateText': template_check, 'used': 'llm'}
        return fallback, 'template', {'llmText': check, 'templateText': template_check, 'used': 'template (LLM-teksti hylättiin)'}
    reason = 'template (LLM pois käytöstä)' if not llm.enabled() else 'template (LLM-kutsu epäonnistui)'
    return fallback, 'template', {'llmText': None, 'templateText': template_check, 'used': reason}


# --- monitoring ------------------------------------------------------------

def monitoring_preview(state: LoopState, finding: GenomicFinding) -> dict:
    entry = evidence_entry(finding.id)
    existing = next((m for m in state.monitorings if m.findingId == finding.id and m.active), None)
    eligible = finding.monitoringEligible
    reason = None if eligible else 'Tätä löydöstä ei voi tässä demossa ottaa seurantaan.'
    monitored = entry['monitoredEventDescriptions'] if entry else [event_type_label(t) for t in finding.relevantEventTypes]
    has_rules = bool(rules_for_gene(finding.gene))

    notes = [
        'Kaikki seurannan tapahtumat ja löydökset ovat tässä demossa synteettisiä.',
        'Sovellus vertaa uusia terveystapahtumia löydökseen ennalta määritellyillä säännöillä.',
        'Sovellus ei tee diagnooseja, ei anna hoito- tai lääkitysohjeita eikä laske riskiprosentteja.',
        'Voit lopettaa seurannan milloin tahansa.',
    ]
    if finding.confirmationStatus not in MONITORABLE_STATUSES:
        notes.insert(0, 'Löydös on vahvistamaton ehdokaslöydös. Voit silti ottaa sen seurantaan, mutta se ei yksin osoita, että löydös pitää paikkansa.')
    if not has_rules:
        notes.insert(1 if finding.confirmationStatus not in MONITORABLE_STATUSES else 0,
                     'Tälle geenille ei ole tässä demossa määritelty sääntöjä, joten seuranta ei tuota huomioita, vaikka uusia terveystapahtumia kirjattaisiin.')

    return {
        'finding': finding.model_dump(),
        'eligible': eligible,
        'reasonNotEligible': reason,
        'alreadyMonitored': bool(existing),
        'monitoringId': existing.id if existing else None,
        'monitoredEvents': monitored,
        'confirmationStatus': finding.confirmationStatus,
        'confirmationLabel': CONFIRMATION_LABELS[finding.confirmationStatus],
        'evidenceLevel': finding.evidenceLevel,
        'evidenceLevelLabel': evidence_level_label(finding.evidenceLevel),
        'source': finding.source,
        'disclaimer': DISCLAIMER_FI,
        'responsibilityNotes': notes,
    }


def upsert_finding(state: LoopState, finding: GenomicFinding) -> GenomicFinding:
    existing = next((item for item in state.findings if item.id == finding.id), None)
    if existing:
        return existing
    state.findings.append(finding)
    return finding


def missing_information_for(state: LoopState, finding_id: str, only_missing: bool = True) -> list[MissingInformation]:
    return [
        item for item in state.missingInformation
        if item.relatedFinding == finding_id and (item.status == 'missing' or not only_missing)
    ]


def _seed_missing_information(state: LoopState, finding: GenomicFinding) -> None:
    entry = evidence_entry(finding.id) or {}
    known = {item.id for item in state.missingInformation}
    for item in entry.get('missingInformationItems', []):
        if item['id'] not in known:
            state.missingInformation.append(MissingInformation(relatedFinding=finding.id, **item))


def start_monitoring(state: LoopState, finding_id: str, preset: bool = False) -> Monitoring:
    finding = _finding(state, finding_id)
    if not finding.monitoringEligible:
        raise LoopError('Tätä löydöstä ei voi ottaa seurantaan.')
    existing = next((m for m in state.monitorings if m.findingId == finding_id and m.active), None)
    if existing:
        return existing

    monitoring = Monitoring(
        id=next_id(state, 'mon'),
        findingId=finding_id,
        consentedAt=state.currentDate,
        nextReviewAt=add_days(state.currentDate, PERIODIC_REVIEW_DAYS),
        currentAssessment=templates.assessment_for_status('monitoring'),
    )
    state.monitorings.append(monitoring)
    _seed_missing_information(state, finding)
    _log(
        state,
        kind='monitoring_started',
        watchlistMatches=[{'monitoringId': monitoring.id, 'findingId': finding.id, 'gene': finding.gene}],
        evidenceCheck={
            'confirmationStatus': finding.confirmationStatus,
            'confirmationAllowsMonitoring': True,
            'evidenceLevel': finding.evidenceLevel,
            'source': finding.source,
        },
        decision='monitoring',
        decisionDetail=(
            f'Demoprofiilin alkutilassa seuranta on aktiivinen löydökselle {finding.title}.' if preset
            else f'Käyttäjä hyväksyi seurannan löydökselle {finding.title}. Aiempia tapahtumia ei arvioida takautuvasti.'
        ),
        userApprovalStatus='preset_demo_consent' if preset else 'consent_given',
    )
    return monitoring


def stop_monitoring(state: LoopState, monitoring_id: str) -> Monitoring:
    monitoring = _monitoring(state, monitoring_id)
    if monitoring.active:
        monitoring.active = False
        monitoring.stoppedAt = state.currentDate
        _log(
            state,
            kind='monitoring_stopped',
            watchlistMatches=[{'monitoringId': monitoring.id, 'findingId': monitoring.findingId}],
            decision='monitoring_stopped',
            decisionDetail='Käyttäjä lopetti seurannan.',
            userApprovalStatus='consent_withdrawn',
        )
    return monitoring


# --- event processing --------------------------------------------------------

def add_event(state: LoopState, fields: dict | None = None, raw_text: str | None = None, source: str | None = None) -> dict:
    """Add a synthetic health event and run the agent pipeline on it."""
    fields = dict(fields or {})
    raw_text = raw_text or fields.get('rawText')
    extracted, method = extract(raw_text) if raw_text else ({}, 'structured_input')

    if fields:
        structured = {key: fields.get(key) for key in ('type', 'code', 'displayName', 'value', 'unit', 'abnormalFlag')}
        computed_flag = abnormal_flag(structured.get('code'), structured.get('value'))
        if computed_flag:
            structured['abnormalFlag'] = computed_flag
    else:
        structured = {key: extracted.get(key) for key in ('type', 'code', 'displayName', 'value', 'unit', 'abnormalFlag')}

    extracted_data = dict(extracted)
    if fields.get('gene'):
        extracted_data['gene'] = fields['gene']
    if fields and extracted:
        extracted_data['matchesStructuredInput'] = all(
            extracted.get(key) == structured.get(key) for key in ('type', 'code', 'abnormalFlag')
        )

    event = HealthEvent(
        id=next_id(state, 'evt'),
        date=state.currentDate,
        source=source or fields.get('source') or 'Synteettinen käyttäjän syöte',
        rawText=raw_text,
        extractedData=extracted_data,
        synthetic=True,
        **structured,
    )
    state.events.append(event)
    log_entries, observations, updated = _evaluate_event(state, event, method, return_updates=True)
    return {
        'updatedObservations': [item.model_dump() for item in updated],
        'event': event.model_dump(),
        'userVisibleAlert': any(entry.userVisibleAlert for entry in log_entries),
        'observations': [item.model_dump() for item in observations],
        'log': [entry.model_dump() for entry in log_entries],
    }


def add_confirmed_family_history(state: LoopState, data: dict, raw_text: str | None, extraction_method: str) -> dict:
    """Save user-confirmed family history as a HealthEvent and re-run the rule engine."""
    negative = data['condition'] == 'none_reported'
    event = HealthEvent(
        id=next_id(state, 'evt'),
        date=state.currentDate,
        type='family_history',
        code='CVD_FAMILY_HISTORY_NEGATIVE' if negative else 'CVD_FAMILY_HISTORY',
        displayName='Suvun sydän- ja verisuonisairaus' if not negative else 'Suvun sairaushistoria',
        value=family_history.display_value(data),
        source='user_reported',
        rawText=raw_text,
        extractedData=dict(data),
        structuredData={key: data[key] for key in ('relation', 'condition', 'conditionCategory', 'ageAtEvent')},
        confirmedByUser=True,
        synthetic=True,
    )
    state.events.append(event)
    log_entries, observations, updated = _evaluate_event(state, event, extraction_method, return_updates=True)
    return {'event': event, 'log': log_entries, 'created': observations, 'updated': updated}


def add_lifestyle_quiz_result(state: LoopState, structured_data: dict, raw_text: str) -> HealthEvent:
    """Persist a completed lifestyle quiz as a HealthEvent so its answers become part of the bounded
    UserContext (recentHealthEvents) that Hyvinvointikumppani's AI features can see. The event type is
    never in any finding's relevantEventTypes, so it can't match a rule or trigger a new observation -
    purely informational, self-reported input."""
    event = HealthEvent(
        id=next_id(state, 'evt'),
        date=state.currentDate,
        type='lifestyle_survey',
        code='LIFESTYLE_QUIZ',
        displayName='Elämäntapatesti',
        source='user_reported',
        rawText=raw_text,
        structuredData=structured_data,
        confirmedByUser=True,
        synthetic=True,
    )
    state.events.append(event)
    _log(
        state, kind='lifestyle_quiz_completed', decision='no_rule_change',
        decisionDetail='Käyttäjä tallensi elämäntapatestin vastaukset. Ei vaikuta sääntömoottorin päätöksiin; '
                        'vastaukset näkyvät jatkossa AI:n käyttämässä rajatussa kontekstissa.',
        userApprovalStatus='user_confirmed',
    )
    return event


def _is_relevant(finding: GenomicFinding, event: HealthEvent) -> bool:
    if event.type not in finding.relevantEventTypes:
        return False
    entry = evidence_entry(finding.id)
    if entry and event.code not in entry['relevantCodes']:
        return False
    if event.type == 'research_update':
        return event.extractedData.get('gene') == finding.gene
    return True


def _evaluate_event(state: LoopState, event: HealthEvent, method: str, return_updates: bool = False):
    active = [m for m in state.monitorings if m.active]
    matches = [(m, _finding(state, m.findingId)) for m in active if _is_relevant(_finding(state, m.findingId), event)]
    base = {'detectedEvent': _event_summary(event), 'extractedData': event.extractedData, 'extractionMethod': method}

    if not matches:
        detail = (
            'Yhteyttä aktiiviseen seurantaan ei löytynyt. Käyttäjälle ei näytetä hälytystä.'
            if active else 'Aktiivisia seurantoja ei ole. Tapahtuma kirjattiin aikajanalle.'
        )
        entry = _log(
            state,
            kind='event_evaluated',
            watchlistMatches=[],
            ruleApplied=None,
            evidenceCheck={'performed': False, 'reason': 'Ei seurantalistaosumaa'},
            safetyCheck={'performed': False, 'reason': 'Käyttäjälle ei muodostettu tekstiä'},
            decision='no_action',
            decisionDetail=detail,
            **base,
        )
        return ([entry], [], []) if return_updates else ([entry], [])

    entries: list[AgentLogEntry] = []
    created: list[Observation] = []
    updated: list[Observation] = []
    for monitoring, finding in matches:
        monitoring.lastRelevantEventId = event.id
        if event.type == 'family_history' and event.confirmedByUser:
            for item in missing_information_for(state, finding.id):
                if item.type == 'family_history':
                    item.status = 'answered'
                    item.answeredByEventId = event.id
            if state.awaitingMissingInfoId and not any(
                m.id == state.awaitingMissingInfoId and m.status == 'missing' for m in state.missingInformation
            ):
                state.awaitingMissingInfoId = None
        watch = [{'monitoringId': monitoring.id, 'findingId': finding.id, 'gene': finding.gene, 'matchedOn': f'{event.type}:{event.code}'}]
        rule = next(
            (
                r for r in rules_for_gene(finding.gene)
                if r.get('kind', 'single_event') == 'single_event' and r['eventType'] == event.type and r['eventCode'] == event.code
            ),
            None,
        )
        entry = evidence_entry(finding.id)
        evidence_check = {
            'performed': True,
            'findingInLocalEvidence': bool(entry),
            'confirmationStatus': finding.confirmationStatus,
            'requiredConfirmationStatus': rule['requiredConfirmationStatus'] if rule else None,
            'confirmationOk': bool(rule) and finding.confirmationStatus in rule['requiredConfirmationStatus'],
            'evidenceLevel': finding.evidenceLevel,
            'source': finding.source,
            'lastReviewedAt': finding.lastReviewedAt,
        }
        rule_info = None
        if rule:
            rule_info = {
                'id': rule['id'],
                'name': rule['name'],
                'condition': f"{rule['eventType']}.code == {rule['eventCode']} AND abnormalFlag == {rule['abnormalFlag']}",
                'eventAbnormalFlag': event.abnormalFlag,
                'triggered': event.abnormalFlag == rule['abnormalFlag'] and evidence_check['confirmationOk'],
            }

        if rule and event.abnormalFlag == 'unknown':
            observation, safety = _create_observation(state, monitoring, finding, event, rule, 'additional_information_needed')
            created.append(observation)
            entries.append(_log(
                state, kind='event_evaluated', watchlistMatches=watch, ruleApplied=rule_info,
                evidenceCheck=evidence_check, safetyCheck=safety,
                decision='additional_information_needed',
                decisionDetail='Tapahtuma liittyy seurantaan, mutta poikkeamamerkintä puuttuu. Pyydetään tarkistamaan tulos.',
                userVisibleAlert=True, userApprovalStatus='waiting_for_user', **base,
            ))
            continue

        handled = False
        if rule_info and rule_info['triggered']:
            handled = True
            open_observation = next(
                (o for o in state.observations if o.id == monitoring.openObservationId and o.status in OPEN_OBSERVATION_STATES),
                None,
            )
            if open_observation:
                entries.append(_log(
                    state, kind='event_evaluated', watchlistMatches=watch, ruleApplied=rule_info,
                    evidenceCheck=evidence_check, safetyCheck={'performed': False, 'reason': 'Uutta tekstiä ei muodostettu'},
                    decision=rule['resultState'],
                    decisionDetail=f'Sääntö täyttyi, mutta huomio {open_observation.id} on jo avoinna. Uutta hälytystä ei luotu.',
                    userVisibleAlert=False, userApprovalStatus='waiting_for_user', **base,
                ))
            else:
                observation, safety = _create_observation(state, monitoring, finding, event, rule, rule['resultState'])
                created.append(observation)
                task = _create_task(state, observation)
                entries.append(_log(
                    state, kind='event_evaluated', watchlistMatches=watch, ruleApplied=rule_info,
                    evidenceCheck=evidence_check, safetyCheck=safety,
                    decision=rule['resultState'],
                    decisionDetail=f'Muodostettiin huomio {observation.id} ja seurantatehtävä {task.id}. Ei diagnoosia eikä lääkitysehdotusta.',
                    userVisibleAlert=True, userApprovalStatus='waiting_for_user', **base,
                ))

        combo_entries, combo_created, combo_updated = _evaluate_combination_rules(state, monitoring, finding, event, base, watch)
        entries.extend(combo_entries)
        created.extend(combo_created)
        updated.extend(o for o in combo_updated if o not in created)
        if handled or combo_created or combo_updated:
            continue
        if combo_entries and event.type == 'family_history':
            if monitoring.status in ('monitoring', 'no_action'):
                _set_status(monitoring, 'monitoring')
            continue

        # Relevant event, but no rule fires: record context only.
        if event.type == 'research_update':
            finding.lastReviewedAt = event.date
            detail = f'Tutkimustieto kirjattiin löydökselle {finding.gene}. Luokitus ennallaan, ei toimenpiteitä.'
        elif event.type == 'medication':
            detail = 'Lääkitystieto kirjattiin taustatiedoksi. Järjestelmä ei ota kantaa lääkitykseen. Ei toimenpiteitä.'
        else:
            detail = 'Tapahtuma liittyy seurantaan, mutta mikään sääntö ei täyttynyt. Ei toimenpiteitä.'
        if monitoring.status in ('monitoring', 'no_action'):
            _set_status(monitoring, 'monitoring')
        entries.append(_log(
            state, kind='event_evaluated', watchlistMatches=watch, ruleApplied=rule_info,
            evidenceCheck=evidence_check, safetyCheck={'performed': False, 'reason': 'Käyttäjälle ei muodostettu hälytystä'},
            decision='no_action', decisionDetail=detail, **base,
        ))
    return (entries, created, updated) if return_updates else (entries, created)


def _create_task(state: LoopState, observation: Observation, days: int = FOLLOW_UP_DAYS, due_at: str | None = None) -> FollowUpTask:
    task = FollowUpTask(
        id=next_id(state, 'task'),
        observationId=observation.id,
        createdAt=state.currentDate,
        dueAt=due_at or add_days(state.currentDate, days),
    )
    state.tasks.append(task)
    observation.systemDid.append(f'Loi avoimen seurantatehtävän {task.id} (määräpäivä {fi_date(task.dueAt)}).')
    return task


def _latest(events: list[HealthEvent], predicate) -> HealthEvent | None:
    matching = [e for e in events if predicate(e)]
    return max(matching, key=lambda e: (e.date, e.id)) if matching else None


def _evaluate_combination_rules(
    state: LoopState, monitoring: Monitoring, finding: GenomicFinding, event: HealthEvent, base: dict, watch: list[dict]
) -> tuple[list[AgentLogEntry], list[Observation], list[Observation]]:
    entries: list[AgentLogEntry] = []
    created: list[Observation] = []
    updated: list[Observation] = []
    for rule in rules_for_gene(finding.gene):
        if rule.get('kind') != 'combination' or event.type not in rule['triggerEventTypes']:
            continue
        lab_req = rule['requires']['lab']
        fam_req = rule['requires']['familyHistory']
        latest_lab = _latest(state.events, lambda e: e.type == 'lab_result' and e.code == lab_req['eventCode'])
        lab = latest_lab if latest_lab and latest_lab.abnormalFlag == lab_req['abnormalFlag'] else None
        fam = _latest(
            state.events,
            lambda e: e.type == 'family_history'
            and (e.confirmedByUser or not fam_req['confirmedByUser'])
            and e.structuredData.get('relation') in fam_req['relations']
            and e.structuredData.get('conditionCategory') in fam_req['conditionCategories']
            and isinstance(e.structuredData.get('ageAtEvent'), int)
            and e.structuredData['ageAtEvent'] <= fam_req['maxAgeAtEvent'],
        )
        # Only the new triggering event itself may start the evaluation (e.g. a normal LDL result must not).
        if event.type == 'lab_result' and not (event.code == lab_req['eventCode'] and event.abnormalFlag == lab_req['abnormalFlag']):
            continue
        if event.type == 'family_history' and not event.confirmedByUser:
            continue
        confirmation_ok = finding.confirmationStatus in rule['requiredConfirmationStatus']
        triggered = bool(confirmation_ok and lab and fam)
        rule_info = {
            'id': rule['id'],
            'name': rule['name'],
            'condition': 'confirmed LDLR finding AND lab LDL == high AND user-confirmed first-degree family history (CVD/high cholesterol, age <= 59)',
            'checks': {
                'confirmationOk': confirmation_ok,
                'ldlHighEventId': lab.id if lab else None,
                'confirmedFamilyHistoryEventId': fam.id if fam else None,
            },
            'triggered': triggered,
            'demoNotice': rule.get('demoNotice_fi'),
        }
        evidence_check = {
            'performed': True,
            'confirmationStatus': finding.confirmationStatus,
            'confirmationOk': confirmation_ok,
            'evidenceLevel': finding.evidenceLevel,
            'source': finding.source,
        }
        if not triggered:
            if event.type == 'family_history':
                missing = [name for name, ok in (('viitealueen ylittävä LDL-tulos', lab), ('vahvistettu lähisuvun varhainen sydän- ja verisuonisairaus', fam)) if not ok]
                entries.append(_log(
                    state, kind='event_evaluated', watchlistMatches=watch, ruleApplied=rule_info, evidenceCheck=evidence_check,
                    safetyCheck={'performed': False, 'reason': 'Käyttäjälle ei muodostettu hälytystä'},
                    decision='no_action',
                    decisionDetail=f"Tieto tallennettiin. Sääntö {rule['id']} ei täyttynyt (puuttuu: {', '.join(missing)}). Seurannan tila ei muuttunut.",
                    userApprovalStatus='user_confirmed', **base,
                ))
            continue

        open_observation = next(
            (o for o in state.observations if o.id == monitoring.openObservationId and o.status in OPEN_OBSERVATION_STATES),
            None,
        )
        if open_observation and rule['id'] in open_observation.ruleIds:
            continue
        if open_observation:
            open_observation.ruleIds.append(rule['id'])
            for event_id in (lab.id, fam.id):
                if event_id not in open_observation.supportingEventIds:
                    open_observation.supportingEventIds.append(event_id)
            open_observation.connection = f"{open_observation.connection} {rule['connection_fi']}"
            open_observation.updatedAt = state.currentDate
            open_observation.summaryIntro = None  # regenerate summary text with the new facts
            open_observation.missingInformation = [m.label for m in missing_information_for(state, finding.id)]
            open_observation.systemDid.append(
                f"Arvioi seurannan uudelleen käyttäjän vahvistaman sukuhistorian jälkeen ja sovelsi synteettisen demosäännön {rule['id']}."
            )
            if open_observation.status == 'additional_information_needed':
                open_observation.status = rule['resultState']
                _set_status(monitoring, rule['resultState'])
            updated.append(open_observation)
            detail = f"Sääntö {rule['id']} täyttyi. Huomion {open_observation.id} perustelut täydennettiin. Ei diagnoosia eikä lääkitysehdotusta."
            observation = open_observation
            safety = {'performed': False, 'reason': 'Huomion teksti ennallaan; chat-teksti tarkistetaan erikseen'}
        else:
            observation, safety = _create_observation(state, monitoring, finding, lab, rule, rule['resultState'])
            observation.supportingEventIds = [lab.id, fam.id]
            _create_task(state, observation)
            created.append(observation)
            detail = f"Sääntö {rule['id']} täyttyi. Muodostettiin huomio {observation.id}. Ei diagnoosia eikä lääkitysehdotusta."
        entries.append(_log(
            state, kind='event_evaluated', watchlistMatches=watch, ruleApplied=rule_info, evidenceCheck=evidence_check,
            safetyCheck=safety, decision=rule['resultState'], decisionDetail=detail,
            userVisibleAlert=True, userApprovalStatus='user_confirmed' if event.confirmedByUser else 'waiting_for_user', **base,
        ))
    return entries, created, updated


def _create_observation(
    state: LoopState, monitoring: Monitoring, finding: GenomicFinding, event: HealthEvent, rule: dict, status: str
) -> tuple[Observation, dict]:
    if status == 'additional_information_needed':
        fallback = templates.additional_info_explanation(finding, event)
    else:
        fallback = templates.observation_explanation(finding, event)
    decision = {
        'finding': {'gene': finding.gene, 'title': finding.title, 'confirmationStatus': finding.confirmationStatus},
        'event': _event_summary(event),
        'rule': {'id': rule['id'], 'name': rule['name']},
        'state': status,
        'connection': rule['connection_fi'],
    }
    text, text_source, safety = _safe_text(llm.explain_decision(decision), fallback)
    observation = Observation(
        id=next_id(state, 'obs'),
        monitoringId=monitoring.id,
        findingId=finding.id,
        eventId=event.id,
        ruleId=rule['id'],
        status=status,
        createdAt=state.currentDate,
        title=templates.observation_title(finding, event),
        explanation=text,
        explanationSource=text_source,
        connection=rule['connection_fi'],
        missingInformation=[m.label for m in missing_information_for(state, finding.id)],
        ruleIds=[rule['id']],
        supportingEventIds=[event.id],
        systemDid=[
            f'Tunnisti uuden tapahtuman: {event.displayName} {fi_value(event)} ({fi_date(event.date)}), poikkeamamerkintä: {event.abnormalFlag}.',
            f'Yhdisti tapahtuman aktiiviseen seurantaan ({finding.gene}-löydös).',
            f"Sovelsi deterministisen säännön {rule['id']}.",
            'Tarkisti löydöksen vahvistustilan ja evidenssitason paikallisesta evidenssitiedostosta.',
            'Tarkisti käyttäjälle näytettävän tekstin turvallisuussäännöillä.',
        ],
        systemDidNot=list(SYSTEM_DID_NOT),
    )
    state.observations.append(observation)
    monitoring.openObservationId = observation.id
    _set_status(monitoring, status)
    return observation, {'performed': True, **safety}


# --- time and follow-up -------------------------------------------------------

def _base_open_status(observation: Observation) -> str:
    return 'waiting_for_professional_review' if observation.sharedAt else 'professional_review_recommended'


def advance_time(state: LoopState, days: int) -> dict:
    previous = state.currentDate
    state.currentDate = add_days(state.currentDate, days)
    due_tasks = []
    for task in state.tasks:
        if task.status != 'open' or task.dueAt > state.currentDate:
            continue
        observation = _observation(state, task.observationId)
        if observation.remindersDisabled:
            continue
        task.status = 'awaiting_response'
        observation.status = 'waiting_for_user'
        monitoring = _monitoring(state, observation.monitoringId)
        _set_status(monitoring, 'waiting_for_user')
        due_tasks.append(task)
        _log(
            state, kind='follow_up_due',
            watchlistMatches=[{'monitoringId': monitoring.id, 'findingId': monitoring.findingId}],
            decision='waiting_for_user',
            decisionDetail=f'Seurantatehtävä {task.id} erääntyi. Kysytään, onko asia käsitelty ammattilaisen kanssa.',
            userVisibleAlert=True, userApprovalStatus='waiting_for_user',
        )

    for monitoring in state.monitorings:
        if monitoring.active and monitoring.nextReviewAt <= state.currentDate:
            monitoring.nextReviewAt = add_days(monitoring.nextReviewAt, PERIODIC_REVIEW_DAYS)
            _log(
                state, kind='periodic_review',
                watchlistMatches=[{'monitoringId': monitoring.id, 'findingId': monitoring.findingId}],
                decision='no_action',
                decisionDetail=f'Määräaikainen tarkistus tehty. Seuraava tarkistus {fi_date(monitoring.nextReviewAt)}.',
            )

    _log(
        state, kind='time_advanced', decision='no_action',
        decisionDetail=f'Demon aikaa siirrettiin {days} päivää ({fi_date(previous)} → {fi_date(state.currentDate)}).',
    )
    return {'currentDate': state.currentDate, 'dueTasks': [task.model_dump() for task in due_tasks]}


def respond_to_task(state: LoopState, task_id: str, response: str) -> FollowUpTask:
    task = next((item for item in state.tasks if item.id == task_id), None)
    if not task:
        raise LoopError('Seurantatehtävää ei löytynyt.')
    if task.status not in ('open', 'awaiting_response'):
        raise LoopError('Seurantatehtävä on jo suljettu.')
    observation = _observation(state, task.observationId)
    monitoring = _monitoring(state, observation.monitoringId)
    task.userResponse = response

    if response == 'yes':
        task.status = 'completed'
        observation.status = 'resolved'
        monitoring.openObservationId = None
        _set_status(monitoring, 'resolved')
        detail = 'Käyttäjä kertoi, että asia on käsitelty ammattilaisen kanssa. Huomio merkittiin käsitellyksi.'
    elif response == 'not_yet':
        task.status = 'open'
        task.dueAt = add_days(state.currentDate, FOLLOW_UP_DAYS)
        observation.status = _base_open_status(observation)
        _set_status(monitoring, observation.status)
        detail = f'Asiaa ei ole vielä käsitelty. Uusi muistutus {fi_date(task.dueAt)}.'
    elif response == 'no_reminder':
        task.status = 'cancelled'
        observation.remindersDisabled = True
        observation.status = _base_open_status(observation)
        _set_status(monitoring, observation.status)
        detail = 'Käyttäjä ei halua muistutuksia. Huomio jää avoimeksi ilman muistutuksia.'
    elif response == 'not_relevant':
        task.status = 'completed'
        observation.status = 'dismissed'
        monitoring.openObservationId = None
        _set_status(monitoring, 'dismissed')
        detail = 'Käyttäjän mukaan löydös todettiin epäolennaiseksi. Huomio suljettiin, seuranta jatkuu.'
    else:
        raise LoopError('Tuntematon vastaus.')

    _log(
        state, kind='user_response',
        watchlistMatches=[{'monitoringId': monitoring.id, 'findingId': monitoring.findingId}],
        decision=observation.status, decisionDetail=detail, userApprovalStatus=f'user_answered:{response}',
    )
    return task


def resolve_observation(state: LoopState, observation_id: str, via: str = 'chat') -> Observation:
    observation = _observation(state, observation_id)
    if observation.status not in OPEN_OBSERVATION_STATES:
        raise LoopError('Huomio on jo käsitelty.')
    monitoring = _monitoring(state, observation.monitoringId)
    for task in state.tasks:
        if task.observationId == observation.id and task.status in ('open', 'awaiting_response'):
            task.status = 'completed'
            task.userResponse = 'yes'
    observation.status = 'resolved'
    observation.updatedAt = state.currentDate
    monitoring.openObservationId = None
    _set_status(monitoring, 'resolved')
    _log(
        state, kind='user_response',
        watchlistMatches=[{'monitoringId': monitoring.id, 'findingId': monitoring.findingId}],
        decision='resolved', decisionDetail=f'Käyttäjä vahvisti ({via}), että asia on käsitelty. Huomio merkittiin käsitellyksi.',
        userApprovalStatus='user_confirmed',
    )
    return observation


def schedule_reminder(state: LoopState, observation_id: str, due_at: str) -> FollowUpTask:
    """Create a follow-up task, or move the existing open task to the chosen date."""
    observation = _observation(state, observation_id)
    if observation.status not in OPEN_OBSERVATION_STATES:
        raise LoopError('Huomio on jo käsitelty.')
    if due_at <= state.currentDate:
        raise LoopError('Muistutuksen päivämäärän tulee olla tulevaisuudessa.')
    observation.remindersDisabled = False
    task = next((t for t in state.tasks if t.observationId == observation.id and t.status in ('open', 'awaiting_response')), None)
    if task:
        task.dueAt = due_at
        task.status = 'open'
        detail = f'Seurantatehtävän {task.id} muistutus siirrettiin päivälle {fi_date(due_at)}.'
    else:
        task = _create_task(state, observation, due_at=due_at)
        detail = f'Luotiin seurantatehtävä {task.id} (muistutus {fi_date(due_at)}).'
    if observation.status == 'waiting_for_user':
        observation.status = _base_open_status(observation)
        _set_status(_monitoring(state, observation.monitoringId), observation.status)
    _log(
        state, kind='reminder_created',
        watchlistMatches=[{'monitoringId': observation.monitoringId, 'findingId': observation.findingId}],
        decision=observation.status, decisionDetail=detail, userApprovalStatus='user_confirmed',
    )
    return task


def mark_summary_created(state: LoopState, observation_id: str) -> Observation:
    observation = _observation(state, observation_id)
    observation.summaryCreatedAt = state.currentDate
    _log(
        state, kind='summary_created',
        watchlistMatches=[{'monitoringId': observation.monitoringId, 'findingId': observation.findingId}],
        decision=observation.status,
        decisionDetail='Käyttäjä hyväksyi ammattilaisyhteenvedon muodostamisen. Tietoja ei lähetetty mihinkään.',
        userApprovalStatus='user_confirmed',
    )
    return observation


def share_observation(state: LoopState, observation_id: str) -> Observation:
    observation = _observation(state, observation_id)
    if observation.status not in OPEN_OBSERVATION_STATES:
        raise LoopError('Huomio on jo käsitelty.')
    observation.sharedAt = state.currentDate
    if observation.status != 'waiting_for_user':
        observation.status = 'waiting_for_professional_review'
        _set_status(_monitoring(state, observation.monitoringId), 'waiting_for_professional_review')
    _log(
        state, kind='summary_shared',
        watchlistMatches=[{'monitoringId': observation.monitoringId, 'findingId': observation.findingId}],
        decision=observation.status,
        decisionDetail='Käyttäjä hyväksyi ammattilaisyhteenvedon ja merkitsi sen jaetuksi. Tietoja ei lähetetty mihinkään järjestelmään.',
        userApprovalStatus='approved_by_user',
    )
    return observation


# --- read models ---------------------------------------------------------------

def _rule_views(finding: GenomicFinding | None, observation: Observation) -> list[dict]:
    rules = {r['id']: r for r in rules_for_gene(finding.gene if finding else None)}
    ids = observation.ruleIds or [observation.ruleId]
    return [
        {'id': r['id'], 'name': r['name'], 'description': r['description'], 'demoNotice': r.get('demoNotice_fi')}
        for r in (rules.get(rule_id) for rule_id in ids) if r
    ]


def observation_facts(state: LoopState, observation: Observation) -> dict:
    """Structured facts behind an observation: the only basis for explanations and summaries."""
    finding = next((f for f in state.findings if f.id == observation.findingId), None)
    supporting_ids = observation.supportingEventIds or [observation.eventId]
    supporting = [e for e in state.events if e.id in supporting_ids]
    confirmed_family = [
        e for e in state.events if e.type == 'family_history' and e.confirmedByUser
    ]
    previous = [
        e for e in state.events
        if finding and e.id not in supporting_ids and e.date <= (observation.updatedAt or observation.createdAt)
        and _is_relevant(finding, e) and e.type != 'research_update'
    ]
    is_open = observation.status in OPEN_OBSERVATION_STATES
    return {
        'finding': finding,
        'rules': _rule_views(finding, observation),
        'supportingEvents': supporting,
        'previousEvents': previous,
        'confirmedFamilyHistory': confirmed_family,
        'missingInformation': [m.label for m in missing_information_for(state, finding.id)] if (finding and is_open) else observation.missingInformation,
    }

def professional_summary(state: LoopState, observation_id: str) -> dict:
    observation = _observation(state, observation_id)
    finding = _finding(state, observation.findingId)
    event = _event(state, observation.eventId)
    monitoring = _monitoring(state, observation.monitoringId)
    rule = next((r for r in rules_for_gene(finding.gene) if r['id'] == observation.ruleId), {})
    profile = state.profile
    facts = observation_facts(state, observation)
    entry = evidence_entry(finding.id) or {}

    if observation.summaryIntro is None:
        fallback = templates.summary_intro(profile['name'], finding, event)
        if facts['confirmedFamilyHistory']:
            fallback += ' Käyttäjä on vahvistanut sukuhistoriaa koskevan tiedon, joka on eritelty alla.'
        llm_facts = {
            'person': profile['id'],
            'finding': finding.model_dump(),
            'events': [_event_summary(e) for e in facts['supportingEvents']],
            'userConfirmedFamilyHistory': [e.structuredData for e in facts['confirmedFamilyHistory']],
            'rules': [r['name'] for r in facts['rules']],
            'connection': observation.connection,
            'missingInformation': facts['missingInformation'],
        }
        text, source, _ = _safe_text(llm.draft_summary(llm_facts), fallback)
        observation.summaryIntro = text
        observation.summaryIntroSource = source

    return {
        'synthetic': True,
        'syntheticPersonName': profile['name'],
        'generatedAt': state.currentDate,
        'observationId': observation.id,
        'status': observation.status,
        'sharedAt': observation.sharedAt,
        'intro': observation.summaryIntro,
        'introSource': observation.summaryIntroSource,
        'finding': finding.model_dump(),
        'confirmationStatus': finding.confirmationStatus,
        'confirmationLabel': CONFIRMATION_LABELS[finding.confirmationStatus],
        'evidenceLevel': finding.evidenceLevel,
        'evidenceLevelLabel': evidence_level_label(finding.evidenceLevel),
        'event': event.model_dump() if event else None,
        'dates': {
            'findingLastReviewedAt': finding.lastReviewedAt,
            'monitoringConsentedAt': monitoring.consentedAt,
            'eventDate': event.date if event else None,
            'observationCreatedAt': observation.createdAt,
        },
        'source': finding.source,
        'rule': {'id': rule.get('id'), 'name': rule.get('name'), 'description': rule.get('description')},
        'rules': facts['rules'],
        'relevantEvents': [e.model_dump() for e in facts['supportingEvents']],
        'userConfirmedFamilyHistory': [e.model_dump() for e in facts['confirmedFamilyHistory']],
        'reason': observation.connection,
        'missingInformation': facts['missingInformation'],
        'questionsForProfessional': entry.get('questionsForProfessional', []),
        'summaryCreatedAt': observation.summaryCreatedAt,
        'disclaimer': DISCLAIMER_FI,
        'limitations': [
            'Kaikki tiedot ovat synteettisiä ja tarkoitettu vain demokäyttöön.',
            'Löydöksen vahvistus on synteettinen demovahvistus, ei laboratorion tai ammattilaisen vahvistus.',
            'Yhteenveto ei sisällä diagnoosia, hoitosuositusta, lääkitysohjetta eikä riskiprosenttia.',
        ],
    }


def _summary_relevant(finding: GenomicFinding, event: HealthEvent) -> bool:
    """Looser than _is_relevant(): used only to group timeline events for full_summary(), never to
    trigger a rule decision. Skips the research_update extractedData.gene check that seeded demo events
    (which have no extractedData) would otherwise always fail."""
    if event.type not in finding.relevantEventTypes:
        return False
    entry = evidence_entry(finding.id)
    return not (entry and event.code not in entry['relevantCodes'])


def _finding_metrics(related_events: list[HealthEvent]) -> list[dict]:
    """Quantitative measurements (non-null unit) among a finding's related timeline events, grouped by
    code and sorted chronologically - the closest thing to a trend this deterministic demo supports.
    Never invents a data point: a finding with no matching lab_result/vital_sign events yet reports none."""
    by_code: dict[str, list[HealthEvent]] = {}
    for event in related_events:
        if event.unit:
            by_code.setdefault(event.code or event.displayName, []).append(event)
    return [
        {
            'code': code,
            'label': events[0].displayName,
            'unit': events[0].unit,
            'points': [{'date': e.date, 'value': e.value, 'abnormalFlag': e.abnormalFlag} for e in sorted(events, key=lambda e: e.date)],
        }
        for code, events in by_code.items()
    ]


_NEXT_STEP_SUGGESTIONS = {
    'prior_lab_results': 'harkitse ajantasaista laboratoriokoetta (esim. verikoetta), jotta tulosta voi verrata aiempiin',
    'professional_confirmation': 'harkitse ammattilaisen (esim. laboratorio tai perinnöllisyyslääkäri) tekemää vahvistusta löydökselle',
}


def full_summary(state: LoopState) -> dict:
    """A professional-facing summary spanning ALL actively monitored findings and the FULL health
    timeline - unlike professional_summary(), which is scoped to one triggered observation. Groups
    timeline events by which finding they relate to (and which don't relate to any), and suggests
    additional next steps (e.g. a lab test) drawn only from already-tracked missing information."""
    profile = state.profile
    active_monitorings = [m for m in state.monitorings if m.active]
    findings = [f for f in state.findings if any(m.findingId == f.id for m in active_monitorings)]
    if not findings:
        raise LoopError('Ei seurannassa olevia löydöksiä, joista yhteenvedon voisi muodostaa.')

    events_sorted = sorted(state.events, key=lambda e: (e.date, e.id))
    events_by_finding: dict[str, list[HealthEvent]] = {f.id: [] for f in findings}
    unrelated_events: list[HealthEvent] = []
    for event in events_sorted:
        related = [f.id for f in findings if _summary_relevant(f, event)]
        for finding_id in related:
            events_by_finding[finding_id].append(event)
        if not related:
            unrelated_events.append(event)

    finding_views = []
    suggested_next_steps: list[str] = []
    all_missing: list[str] = []
    questions: list[str] = []
    for finding in findings:
        monitoring = next(m for m in active_monitorings if m.findingId == finding.id)
        missing_items = missing_information_for(state, finding.id)
        entry = evidence_entry(finding.id) or {}
        related_events = events_by_finding[finding.id]
        finding_views.append({
            'finding': finding.model_dump(),
            'confirmationLabel': CONFIRMATION_LABELS[finding.confirmationStatus],
            'evidenceLevelLabel': evidence_level_label(finding.evidenceLevel),
            'monitoringStatus': monitoring.status,
            'relatedEvents': [e.model_dump() for e in related_events],
            'trackedMetrics': _finding_metrics(related_events),
            'hasDefinedMetric': bool(entry),
            'missingInformation': [m.label for m in missing_items],
        })
        all_missing.extend(m.label for m in missing_items)
        for item in missing_items:
            suggestion = _NEXT_STEP_SUGGESTIONS.get(item.type)
            if suggestion:
                suggested_next_steps.append(f'{finding.title}: {item.label} – {suggestion}.')
        for question in entry.get('questionsForProfessional', []):
            if question not in questions:
                questions.append(question)

    llm_facts = {
        'person': profile['id'],
        'findings': [f.model_dump() for f in findings],
        'relatedEventsByFinding': {fid: [_event_summary(e) for e in evs] for fid, evs in events_by_finding.items()},
        'unrelatedEvents': [_event_summary(e) for e in unrelated_events],
        'missingInformation': all_missing,
    }
    # the results of one lab order (e.g. "Lipidit", 7 results) count as one timeline entry
    unrelated_entries = group_entries([e.model_dump() for e in unrelated_events])
    fallback = templates.full_summary_intro(profile['name'], findings, len(unrelated_entries))
    text, source, _ = _safe_text(llm.draft_full_summary(llm_facts), fallback)

    return {
        'synthetic': True,
        'syntheticPersonName': profile['name'],
        'generatedAt': state.currentDate,
        'intro': text,
        'introSource': source,
        'findings': finding_views,
        'unrelatedEvents': [e.model_dump() for e in unrelated_events],
        'suggestedNextSteps': suggested_next_steps,
        'missingInformation': sorted(set(all_missing)),
        'questionsForProfessional': questions,
        'disclaimer': DISCLAIMER_FI,
        'limitations': [
            'Kaikki tiedot ovat synteettisiä ja tarkoitettu vain demokäyttöön.',
            'Yhteenveto kokoaa kaikki seurannassa olevat löydökset ja koko terveystapahtumien aikajanan; se ei ole sidottu yhteen huomioon.',
            'Yhteenveto ei sisällä diagnoosia, hoitosuositusta, lääkitysohjetta eikä riskiprosenttia.',
        ],
    }


def mark_full_summary_created(state: LoopState) -> None:
    active_monitorings = [m for m in state.monitorings if m.active]
    _log(
        state, kind='summary_created',
        watchlistMatches=[{'monitoringId': m.id, 'findingId': m.findingId} for m in active_monitorings],
        decision='full_summary',
        decisionDetail='Käyttäjä hyväksyi kaikki löydökset ja koko terveysaikajanan kattavan ammattilaisyhteenvedon muodostamisen. '
                        'Tietoja ei lähetetty mihinkään.',
        userApprovalStatus='user_confirmed',
    )


def dashboard(state: LoopState) -> dict:
    events_by_id = {event.id: event for event in state.events}
    findings_by_id = {finding.id: finding for finding in state.findings}
    active = [m for m in state.monitorings if m.active]
    open_observations = [o for o in state.observations if o.status in OPEN_OBSERVATION_STATES]
    review_dates = [m.nextReviewAt for m in active] + [t.dueAt for t in state.tasks if t.status in ('open', 'awaiting_response')]

    def enrich_observation(observation: Observation) -> dict:
        finding = findings_by_id.get(observation.findingId)
        event = events_by_id.get(observation.eventId)
        rule = next((r for r in rules_for_gene(finding.gene if finding else None) if r['id'] == observation.ruleId), {})
        task = next(
            (t for t in reversed(state.tasks) if t.observationId == observation.id and t.status in ('open', 'awaiting_response')),
            None,
        ) or next((t for t in reversed(state.tasks) if t.observationId == observation.id and t.status != 'cancelled'), None)
        facts = observation_facts(state, observation)
        return {
            **observation.model_dump(),
            'missingInformation': facts['missingInformation'],
            'rules': facts['rules'],
            'supportingEvents': [e.model_dump() for e in facts['supportingEvents']],
            'previousEvents': [e.model_dump() for e in facts['previousEvents']],
            'confirmedFamilyHistory': [e.model_dump() for e in facts['confirmedFamilyHistory']],
            'finding': finding.model_dump() if finding else None,
            'event': event.model_dump() if event else None,
            'rule': {'id': rule.get('id'), 'name': rule.get('name'), 'description': rule.get('description')},
            'source': finding.source if finding else source_name(),
            'evidenceLevelLabel': evidence_level_label(finding.evidenceLevel) if finding else None,
            'confirmationLabel': CONFIRMATION_LABELS[finding.confirmationStatus] if finding else None,
            'task': task.model_dump() if task else None,
            'disclaimer': DISCLAIMER_FI,
        }

    monitorings = []
    for monitoring in state.monitorings:
        finding = findings_by_id[monitoring.findingId]
        entry = evidence_entry(finding.id) or {}
        latest = events_by_id.get(monitoring.lastRelevantEventId)
        monitorings.append({
            **monitoring.model_dump(),
            'finding': finding.model_dump(),
            'confirmationLabel': CONFIRMATION_LABELS[finding.confirmationStatus],
            'evidenceLevelLabel': evidence_level_label(finding.evidenceLevel),
            'monitoredEvents': entry.get('monitoredEventDescriptions', [event_type_label(t) for t in finding.relevantEventTypes]),
            'latestRelevantEvent': latest.model_dump() if latest else None,
            'observations': [enrich_observation(o) for o in state.observations if o.monitoringId == monitoring.id],
        })

    monitored_ids = {m.findingId for m in active}
    templates_profile = load_profile()['eventTemplates']
    return {
        'synthetic': True,
        'syntheticNotice': 'Kaikki OmaGenomi Loopin henkilöt, löydökset ja terveystapahtumat ovat synteettisiä.',
        'disclaimer': DISCLAIMER_FI,
        'profile': state.profile,
        'currentDate': state.currentDate,
        'llm': llm.status(),
        'counts': {
            'activeMonitorings': len(active),
            'openObservations': len(open_observations),
            'nextReviewDate': min(review_dates) if review_dates else None,
        },
        'findings': [
            {**f.model_dump(), 'monitored': f.id in monitored_ids, 'confirmationLabel': CONFIRMATION_LABELS[f.confirmationStatus]}
            for f in state.findings
        ],
        'monitorings': monitorings,
        'observations': [enrich_observation(o) for o in state.observations],
        'openObservationIds': [o.id for o in open_observations],
        'pendingQuestions': [
            {**t.model_dump(), 'question': 'Onko asia käsitelty ammattilaisen kanssa?', 'observation': enrich_observation(_observation(state, t.observationId))}
            for t in state.tasks if t.status == 'awaiting_response'
        ],
        'tasks': [t.model_dump() for t in state.tasks],
        'events': [e.model_dump() for e in sorted(state.events, key=lambda e: (e.date, e.id))],
        'eventTypeLabels': {
            key: event_type_label(key)
            for key in ('lab_result', 'vital_sign', 'medication', 'research_update', 'free_text', 'family_history', 'lifestyle_survey',
                        'diagnosis', 'care_episode', 'professional_note', 'contact', 'self_report')
        },
        'agentLog': [entry.model_dump() for entry in reversed(state.agentLog)],
        'demoTemplates': [{'key': key, 'label': value['label_fi']} for key, value in templates_profile.items() if not value.get('hiddenInUi')],
    }
