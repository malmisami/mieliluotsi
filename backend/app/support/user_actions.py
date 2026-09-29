"""Gate 3 in action: the user changes consent / communication settings or pauses a theme."""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

from app.loop import agent as rule_engine
from app.loop.models import LoopState
from app.loop.store import add_days
from app.loop.templates import fi_date
from app.support import audit, consent, messages, plan_state, plans, texts
from app.support.models import SOURCE_KINDS, QuietHours

_TIME = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')


class SettingsError(ValueError):
    pass


def _genetic_finding_ids(state: LoopState) -> set[str]:
    return {i.findingId for i in state.support.insights if i.kind == 'genetic' and i.findingId and i.reviewStatus == 'approved'}


def update_consent(state: LoopState, changes: dict[str, Any]) -> list[str]:
    settings = state.support.consent
    lines: list[str] = []
    genetic_before = settings.dataSources.get('geneticInsights', False)
    for kind, allowed in (changes.get('dataSources') or {}).items():
        if kind not in SOURCE_KINDS:
            raise SettingsError(f'Tuntematon tietolähde: {kind}')
        if bool(allowed) != settings.dataSources.get(kind, False):
            settings.dataSources[kind] = bool(allowed)
            lines.append(f"{consent.SOURCE_LABELS[kind]}: {'käyttö sallittu' if allowed else 'ei käytössä'}")
    if 'proactiveContact' in changes and bool(changes['proactiveContact']) != settings.proactiveContact:
        settings.proactiveContact = bool(changes['proactiveContact'])
        lines.append('Oma-aloitteiset yhteydenotot: ' + ('sallittu' if settings.proactiveContact else 'ei sallittu'))
    if 'maxContactsPerWeek' in changes:
        value = changes['maxContactsPerWeek']
        if not isinstance(value, int) or not 0 <= value <= 14:
            raise SettingsError('Yhteydenottojen enimmäismäärä on 0–14 viikossa.')
        if value != settings.maxContactsPerWeek:
            settings.maxContactsPerWeek = value
            lines.append(f'Yhteydenottoja enintään {value} viikossa')
    if changes.get('quietHours'):
        start, end = changes['quietHours'].get('start'), changes['quietHours'].get('end')
        if not (isinstance(start, str) and isinstance(end, str) and _TIME.match(start) and _TIME.match(end)):
            raise SettingsError('Hiljaiset ajat muodossa HH:MM.')
        if (start, end) != (settings.quietHours.start, settings.quietHours.end):
            settings.quietHours = QuietHours(start=start, end=end)
            lines.append(f'Hiljaiset ajat {start}–{end}')
    if 'channel' in changes:
        if changes['channel'] not in consent.CHANNEL_LABELS:
            raise SettingsError('Tuntematon yhteydenottokanava.')
        if changes['channel'] != settings.channel:
            settings.channel = changes['channel']
            lines.append(f'Kanava: {consent.CHANNEL_LABELS[settings.channel]}')
    if 'showGeneticDetails' in changes and bool(changes['showGeneticDetails']) != settings.showGeneticDetails:
        settings.showGeneticDetails = bool(changes['showGeneticDetails'])
        lines.append('Perimätiedon yksityiskohdat: ' + ('näytetään' if settings.showGeneticDetails else 'piilotetaan'))
    if 'automatedAssessment' in changes and bool(changes['automatedAssessment']) != settings.automatedAssessment:
        # explicit consent to the automated assessment of the need for care (terveydenhuoltolaki 51 § 3 mom., assumed 2027)
        settings.automatedAssessment = bool(changes['automatedAssessment'])
        if settings.automatedAssessment:
            settings.automatedAssessmentInformedAt = state.currentDate
            lines.append('Automaattinen hoidon tarpeen arvio: nimenomainen suostumus annettu')
        else:
            lines.append('Automaattinen hoidon tarpeen arvio: suostumus peruttu – jo tehdyt arviot pysyvät voimassa, uudet arviot ovat '
                         'esiarvioita, jotka ammattilainen tekee')
    if 'pausedUntil' in changes:
        value = changes['pausedUntil']
        if value:
            try:
                value = date.fromisoformat(value).isoformat()
            except ValueError as exc:
                raise SettingsError('Tauon päättymispäivä ei ole kelvollinen.') from exc
            if value < state.currentDate:
                raise SettingsError('Tauon päättymispäivän tulee olla tänään tai myöhemmin.')
        if value != settings.pausedUntil:
            settings.pausedUntil = value or None
            lines.append(f'Kaikki yhteydenotot tauolla {fi_date(value)} asti' if value else 'Yhteydenottojen tauko päättyi')
    if not lines:
        return lines
    settings.updatedAt = state.currentDate
    settings.history.append({'date': state.currentDate, 'change': '; '.join(lines)})
    audit.record(state, stage='consent', actor='user', detail='Portti 3: käyttäjä muutti asetuksia – ' + '; '.join(lines) + '.')

    genetic_after = settings.dataSources.get('geneticInsights', False)
    finding_ids = _genetic_finding_ids(state)
    if genetic_before and not genetic_after:
        for monitoring in [m for m in state.monitorings if m.active and m.findingId in finding_ids]:
            rule_engine.stop_monitoring(state, monitoring.id)
        audit.record(state, stage='consent', actor='agent', detail='Perimätieto poistettiin käytöstä: geneettinen seuranta pysäytettiin ja '
                     'perimätieto rajattiin pois agentin ja kielimallin kontekstista.')
    elif genetic_after and not genetic_before:
        for finding_id in finding_ids:
            if any(f.id == finding_id for f in state.findings):
                rule_engine.start_monitoring(state, finding_id)
        audit.record(state, stage='consent', actor='agent', detail='Perimätieto palautettiin käyttöön ammattilaisen aiemmin hyväksymien havaintojen osalta.')
    return lines


def pause_plan(state: LoopState, plan_id: str, until: Optional[str] = None) -> None:
    plan = plans.find(state, plan_id)
    if not plan:
        raise SettingsError('Seurantasuunnitelmaa ei löytynyt.')
    if until:
        try:
            until = date.fromisoformat(until).isoformat()
        except ValueError as exc:
            raise SettingsError('Päivämäärä ei ole kelvollinen.') from exc
        if until <= state.currentDate:
            raise SettingsError('Tauon päättymispäivän tulee olla tulevaisuudessa.')
    try:
        plan_state.transition(state, plan, 'paused')
    except plan_state.PlanStateError as exc:
        raise SettingsError(str(exc)) from exc
    plan.pausedUntil = until
    plan_state.add_history(state, plan, actor='user', summary='Käyttäjä tauotti seurannan', changes=[f'Tauko {fi_date(until)} asti' if until else 'Tauko toistaiseksi'])
    audit.record(state, stage='consent', actor='user', plan=plan, detail=f'Portti 3: käyttäjä tauotti seurannan ({plan.name}).', outcome='paused')
    messages.post(state, texts.PLAN_PAUSED.format(plan=plan.name, until=f'{fi_date(until)} asti' if until else 'toistaiseksi'),
                  kind='plan_update', plan=plan, initiated_by_agent=False)


def resume_plan(state: LoopState, plan_id: str, automatic: bool = False) -> None:
    plan = plans.find(state, plan_id)
    if not plan:
        raise SettingsError('Seurantasuunnitelmaa ei löytynyt.')
    try:
        plan_state.transition(state, plan, 'active')
    except plan_state.PlanStateError as exc:
        raise SettingsError(str(exc)) from exc
    plan.pausedUntil = None
    if not plan.nextCheckInAt or plan.nextCheckInAt <= state.currentDate:
        plan.nextCheckInAt = add_days(state.currentDate, plan.checkInEveryDays)
    plan_state.add_history(state, plan, actor='user' if not automatic else 'agent',
                           summary='Seuranta jatkuu' + (' (tauko päättyi)' if automatic else ''))
    audit.record(state, stage='consent', actor='agent' if automatic else 'user', plan=plan, outcome='active',
                 detail=f'Seuranta jatkuu ({plan.name}).' + (' Käyttäjän asettama tauko päättyi.' if automatic else ''))
    messages.post(state, texts.PLAN_RESUMED.format(plan=plan.name, date=fi_date(plan.nextCheckInAt)), kind='plan_update', plan=plan,
                  initiated_by_agent=automatic)


def resume_expired_pauses(state: LoopState) -> None:
    for plan in state.support.plans:
        if plan.status == 'paused' and plan.pausedUntil and plan.pausedUntil < state.currentDate:
            resume_plan(state, plan.id, automatic=True)
