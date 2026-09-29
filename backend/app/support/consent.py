"""Gate 3: what the user allows - data sources, proactive contact, frequency, quiet hours, channel, pauses."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from app.loop.models import LoopState
from app.support.models import SOURCE_KINDS, SupportPlan

SOURCE_LABELS = {
    'diagnoses': 'Diagnoosit',
    'medications': 'Lääkitys',
    'careEpisodes': 'Hoitojaksot ja käynnit',
    'professionalNotes': 'Ammattilaisten kirjaukset',
    'interactionEvents': 'Asiointitapahtumat',
    'measurements': 'Mittaukset',
    'selfReportedData': 'Omat ilmoitukset',
    'geneticInsights': 'Perimätieto (vapaaehtoinen)',
    'wellbeingData': 'Hyvinvointidata: Apple Health (vapaaehtoinen)',
}
CHANNEL_LABELS = {'app': 'Sovellus', 'sms': 'Tekstiviesti (mallinnettu)', 'email': 'Sähköposti (mallinnettu)'}
DEFAULT_SEND_TIME = '09:00'


def source_allowed(state: LoopState, kind: str) -> bool:
    return state.support.consent.dataSources.get(kind, False)


def genetic_allowed(state: LoopState) -> bool:
    return source_allowed(state, 'geneticInsights')


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(':')
    return int(hours) * 60 + int(minutes)


def in_quiet_hours(state: LoopState, hhmm: str) -> bool:
    quiet = state.support.consent.quietHours
    start, end, value = _minutes(quiet.start), _minutes(quiet.end), _minutes(hhmm)
    if start == end:
        return False
    if start < end:
        return start <= value < end
    return value >= start or value < end  # window over midnight, e.g. 21:00-08:00


def delivery_time(state: LoopState) -> str:
    """The agent's messages go out at 09:00 unless that falls in the user's quiet hours."""
    if not in_quiet_hours(state, DEFAULT_SEND_TIME):
        return DEFAULT_SEND_TIME
    return state.support.consent.quietHours.end


def contacts_last_week(state: LoopState) -> int:
    since = (date.fromisoformat(state.currentDate) - timedelta(days=6)).isoformat()
    return sum(1 for c in state.support.contacts if c['date'] >= since and not c.get('urgent'))


def contact_block_reason(state: LoopState, plan: Optional[SupportPlan], urgent: bool = False) -> Optional[str]:
    """Why the agent may NOT contact the user right now (None = contact allowed)."""
    consent = state.support.consent
    if urgent:
        return None  # safety messages defined by the professional-approved plan always go through
    if not consent.proactiveContact:
        return 'Käyttäjä ei salli oma-aloitteisia yhteydenottoja.'
    if consent.pausedUntil and consent.pausedUntil >= state.currentDate:
        return f'Käyttäjä on tauottanut yhteydenotot {consent.pausedUntil} asti.'
    if plan is not None and plan.status == 'paused':
        return 'Käyttäjä on tauottanut tämän seurantateeman.'
    if contacts_last_week(state) >= consent.maxContactsPerWeek:
        return f'Viikoittainen yhteydenottoraja ({consent.maxContactsPerWeek}) on täynnä.'
    return None


def all_sources() -> tuple[str, ...]:
    return SOURCE_KINDS


def show_genetic_details(state: LoopState) -> bool:
    # an empty support state (e.g. after "delete all data") keeps the original behaviour of the genetic tools
    return state.support.consent.showGeneticDetails or state.support.person is None


def mask_genes(state: LoopState, text: Optional[str]) -> Optional[str]:
    """Replace finding titles and gene names with a neutral phrase unless the user allows genetic details."""
    if not text or show_genetic_details(state):
        return text
    for finding in state.findings:
        text = text.replace(finding.title, 'Perimätiedon havainto')
    genes = {f.gene for f in state.findings if f.gene} | {i.gene for i in state.support.insights if i.gene}
    for gene in sorted(genes, key=len, reverse=True):
        pattern = re.compile(rf'\b{re.escape(gene)}(?:-(?:geeni|löydö|demolöydö)\w*)?')

        def neutral(match: re.Match) -> str:
            before = text[:match.start()].rstrip()
            word = 'havainnon' if '-' in match.group(0) and match.group(0).endswith('n') else 'havainto'  # genitive stays genitive
            return f"{'P' if not before or before.endswith(('.', ':', chr(10))) else 'p'}erimätiedon {word}"
        text = pattern.sub(neutral, text)
    # "perimätiedon havainto (LDLR)" would otherwise become "perimätiedon havainto (perimätiedon havainto)"
    return re.sub(r'([Pp]erimätiedon havainto) \(perimätiedon havainto\)', r'\1', text)


def genetic_label(state: LoopState, gene: Optional[str], fallback: str = 'perimätiedon havainto') -> str:
    """Gene names are shown only if the user allows genetic details to be displayed."""
    return gene if (gene and show_genetic_details(state)) else fallback
