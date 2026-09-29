"""Linking health records to DNA-analysis findings (Terveystiedot, on the user's request).

A link says which health care records - diagnoses, laboratory orders, measurements, medication, visits and their
notes - belong to the same health theme as a DNA-analysis finding, e.g. elevated cholesterol. It is informational:

- deterministic rules from the demo policy (data/support/policies.json -> geneticLinking), no LLM;
- gate 3: nothing is linked unless the user allows genetic data to be used, and gene names and conditions are shown
  only when the user allows genetic details;
- gate 2: a link never changes the follow-up; only a professional-approved finding may act as background information;
- DNA findings that relate to no stored health record are not linked and not named (e.g. hereditary cancer genes).
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.loop.evidence import translate_condition, translate_significance
from app.loop.models import HealthEvent, LoopState
from app.support import audit, consent, policies, relevance, texts
from app.support.models import GeneticLinkFinding, GeneticLinking, GeneticLinkTheme, Insight

RSID = re.compile(r'rs\d+', re.IGNORECASE)
# user-reported and demo events are not health care records; they are never linked
NOT_RECORDS = {'self_report', 'family_history', 'lifestyle_survey', 'research_update', 'free_text'}
VISIT_TEXT_TYPES = ('care_episode', 'professional_note', 'contact')


class GeneticLinkError(ValueError):
    pass


def themes() -> list[dict[str, Any]]:
    return policies.load_policies().get('geneticLinking', {}).get('themes', [])


def _key(gene: Optional[str], variant: Optional[str]) -> str:
    match = RSID.search(variant or '')
    return f"{(gene or '').upper()}:{match.group(0).lower() if match else (variant or '').strip().lower()}"


# --- DNA findings: the source record insights plus the user's own DNA analysis --------------------------------------

def _profile_conditions(state: LoopState, gene: Optional[str], variant: Optional[str]) -> list[str]:
    person = state.support.person
    if not person:
        return []
    key = _key(gene, variant)
    item = next((g for g in person.geneticInsights if _key(g.gene, g.variant) == key), None)
    return list(item.conditions) if item else []


def _session_findings(session_id: str) -> list[dict[str, Any]]:
    from app.services.session_manager import SessionManager  # local import: the analysis store is optional here

    try:
        db = SessionManager.get_session_db(session_id)
    except FileNotFoundError as exc:
        raise GeneticLinkError(texts.GENETIC_LINK_SESSION_MISSING) from exc
    try:
        rows = db.execute('SELECT rsid, chrom, pos, ref, alt, gene, conditions, clinical_significance '
                          'FROM matched_findings ORDER BY pos, rsid').fetchall()
    finally:
        db.close()
    findings = []
    for row in rows:
        variant = f"{row['rsid'] or ''} (chr{row['chrom']}:{row['pos']} {row['ref']}>{row['alt']})".strip()
        findings.append({
            'gene': row['gene'], 'variant': variant, 'conditions': json.loads(row['conditions'] or '[]'),
            'significance': row['clinical_significance'], 'origin': 'dna_analysis', 'insight': None,
        })
    return findings


def collect_findings(state: LoopState, session_id: Optional[str] = None) -> list[dict[str, Any]]:
    """One entry per variant. The support insight wins over a plain analysis row because it carries the gate status."""
    by_key: dict[str, dict[str, Any]] = {}
    for insight in state.support.insights:
        if insight.kind != 'genetic':
            continue
        by_key.setdefault(_key(insight.gene, insight.variant), {
            'gene': insight.gene, 'variant': insight.variant, 'conditions': _profile_conditions(state, insight.gene, insight.variant),
            'significance': insight.significance, 'origin': insight.origin, 'insight': insight,
        })
    if session_id:
        for finding in _session_findings(session_id):
            key = _key(finding['gene'], finding['variant'])
            if key in by_key:
                if not by_key[key]['conditions']:
                    by_key[key]['conditions'] = finding['conditions']
                continue
            by_key[key] = finding
    for key, finding in by_key.items():
        finding['key'] = key
        finding['conditions'] = [translate_condition(c) for c in finding['conditions'] if c]
    return list(by_key.values())


def _in_theme(finding: dict[str, Any], theme: dict[str, Any]) -> bool:
    gene = (finding.get('gene') or '').upper()
    if gene and gene in theme.get('genes', []):
        return True
    known_gene = any(gene in t.get('genes', []) for t in themes())
    if known_gene:
        return False  # a gene listed under another theme belongs there
    text = ' '.join(finding['conditions']).lower()
    return any(k in text for k in theme.get('conditionKeywords', []))


def _theme_conditions(finding: dict[str, Any], theme: dict[str, Any]) -> list[str]:
    keywords = theme.get('conditionKeywords', [])
    return [c for c in finding['conditions'] if any(k in c.lower() for k in keywords)]


def _status(state: LoopState, insight: Optional[Insight], significance: Optional[str]) -> tuple[str, str, bool]:
    """(gate 1 category, user-facing status, used in the follow-up)."""
    labels = texts.GENETIC_LINK_STATUS
    if insight is not None:
        if insight.reviewStatus == 'approved':
            if not consent.genetic_allowed(state):
                return insight.category, labels['not_allowed'], False
            plan = next((p for p in state.support.plans if p.id == insight.linkedPlanId), None)
            return insight.category, labels['approved'] + (f': {plan.name}' if plan else ''), True
        if insight.reviewStatus in ('pending_professional_review', 'info_requested'):
            return insight.category, labels['pending'], False
        if insight.reviewStatus == 'rejected':
            return insight.category, labels['rejected'], False
        category = insight.category
    else:
        category = relevance.classify_genetic(significance)['category']
    return category, labels.get(category, labels['no_practical_significance']), False


# --- health care records of a theme ---------------------------------------------------------------------------------

def _is_record(event: HealthEvent) -> bool:
    if event.type in NOT_RECORDS:
        return False
    return not (event.type == 'vital_sign' and (event.structuredData or {}).get('context') == 'home')


def _event_in_theme(event: HealthEvent, theme: dict[str, Any]) -> bool:
    code = (event.code or '').upper()
    structured = event.structuredData or {}
    if event.type == 'diagnosis':
        return any(code.startswith(prefix) for prefix in theme.get('diagnosisPrefixes', []))
    if event.type == 'lab_result':
        return code in theme.get('labCodes', [])
    if event.type == 'vital_sign':
        return code in theme.get('vitalCodes', [])
    if event.type == 'medication':
        purpose = str(structured.get('purpose') or '').lower()
        name = str(event.value or '').lower()
        if theme.get('allMedications'):
            return structured.get('status') == 'active'  # a drug-response finding concerns every medication in use
        return purpose in theme.get('medicationPurposes', []) or any(k in name for k in theme.get('medicationKeywords', []))
    if event.type in VISIT_TEXT_TYPES:
        text = ' '.join(str(part) for part in (event.rawText, structured.get('topic'), event.displayName) if part).lower()
        return any(k in text for k in theme.get('textKeywords', []))
    return False


def theme_events(state: LoopState, theme: dict[str, Any]) -> list[HealthEvent]:
    return sorted((e for e in state.events if _is_record(e) and _event_in_theme(e, theme)), key=lambda e: (e.date, e.id))


def record_count(state: LoopState, events: list[HealthEvent]) -> int:
    """Records as the Terveystiedot view shows them: one lab order, or one visit with its notes, is one record."""
    visit_dates = {e.date for e in state.events if e.type == 'care_episode'}
    keys = set()
    for event in events:
        structured = event.structuredData or {}
        if event.type == 'lab_result' and structured.get('panelId'):
            keys.add(f"lab:{structured['panelId']}")
        elif event.type in VISIT_TEXT_TYPES and event.date in visit_dates and (
                event.type != 'contact' or structured.get('channel') == 'visit'):
            keys.add(f'visit:{event.date}')
        else:
            keys.add(event.id)
    return len(keys)


def _plan_for(state: LoopState, theme: dict[str, Any]):
    theme_id = theme.get('healthThemeId')
    candidates = [p for p in state.support.plans if theme_id and p.theme == theme_id and p.status not in ('rejected', 'completed')]
    return candidates[0] if candidates else None


# --- linking ----------------------------------------------------------------------------------------------------------

def link(state: LoopState, session_id: Optional[str] = None) -> GeneticLinking:
    if not state.support.person:
        raise GeneticLinkError('Terveystietoja ei ole ladattu. Palauta demo alkutilaan.')
    if not consent.genetic_allowed(state):
        raise GeneticLinkError(texts.GENETIC_LINK_NOT_ALLOWED)
    findings = collect_findings(state, session_id)
    if not findings:
        raise GeneticLinkError(texts.GENETIC_LINK_NO_FINDINGS)

    linked: list[GeneticLinkTheme] = []
    health_only: list[str] = []
    linked_keys: set[str] = set()
    # every DNA finding gets a theme card, also when no stored health record relates to it
    for theme in themes():
        members = [f for f in findings if f['key'] not in linked_keys and _in_theme(f, theme)]
        events = theme_events(state, theme)
        if members:
            linked.append(_theme_link(state, theme, members, events))
            linked_keys.update(f['key'] for f in members)
        elif events and theme.get('healthThemeId'):
            health_only.append(theme['label'])  # a follow-up theme of the health data without any DNA finding
    rest = [f for f in findings if f['key'] not in linked_keys]
    if rest:
        other = policies.load_policies().get('geneticLinking', {}).get('other', {'id': 'other', 'label': 'Muut DNA-analyysin havainnot', 'reason': ''})
        linked.append(_theme_link(state, other, rest, []))
    linked.sort(key=lambda t: not t.eventIds)  # themes with health records first, policy order kept

    result = GeneticLinking(
        linkedAt=state.currentDate, sessionId=session_id, themes=linked, healthOnlyThemes=health_only,
        findingCount=len(findings), unlinkedFindingCount=sum(len(t.findings) for t in linked if not t.eventIds),
    )
    state.support.geneticLinking = result
    audit.record(state, stage='data', actor='agent', action='link_genetics', detail=_audit_detail(result), outcome='linked')
    return result


def _theme_link(state: LoopState, theme: dict[str, Any], members: list[dict[str, Any]], events: list[HealthEvent]) -> GeneticLinkTheme:
    plan = _plan_for(state, theme) if events else None
    link_findings = []
    for finding in members:
        category, status, used = _status(state, finding['insight'], finding['significance'])
        link_findings.append(GeneticLinkFinding(
            key=finding['key'], gene=finding['gene'], variant=finding['variant'], conditions=_theme_conditions(finding, theme),
            significanceLabel=translate_significance(finding['significance']) if finding['significance'] else None,
            origin=finding['origin'], insightId=finding['insight'].id if finding['insight'] else None,
            category=category, statusLabel=status, used=used,
        ))
    link_findings.sort(key=lambda f: (not f.used, f.gene or ''))
    return GeneticLinkTheme(
        id=theme['id'], label=theme['label'], reason=theme.get('reason', ''), eventIds=[e.id for e in events],
        recordCount=record_count(state, events), findings=link_findings,
        planId=plan.id if plan else None, planName=plan.name if plan else None,
    )


def unlink(state: LoopState) -> dict[str, Any]:
    if state.support.geneticLinking is None:
        raise GeneticLinkError('Terveystietoja ei ole linkitetty DNA-analyysiin.')
    state.support.geneticLinking = None
    audit.record(state, stage='data', actor='user', action='unlink_genetics', outcome='unlinked',
                 detail='Käyttäjä purki terveystietojen linkityksen DNA-analyysiin. Seurantaan ei tullut muutoksia.')
    return {'unlinked': True}


def _audit_detail(result: GeneticLinking) -> str:
    """No gene names: the audit is shown to the client as well."""
    parts = []
    for theme in result.themes:
        if not theme.eventIds:
            continue
        used = sum(1 for f in theme.findings if f.used)
        parts.append(f'{theme.label}: {theme.recordCount} terveystietomerkintää ja {len(theme.findings)} perimätiedon havaintoa, '
                     f'joista {used} on hyväksytty seurannan taustatiedoksi')
    linked = '; '.join(parts) + '.' if parts else 'Terveystiedoista ei löytynyt DNA-analyysin havaintoihin liittyviä merkintöjä.'
    if result.unlinkedFindingCount:
        linked += f' {result.unlinkedFindingCount} havainnolle ei löytynyt liittyviä terveystietoja.'
    return (f'Terveystiedot linkitettiin DNA-analyysiin käyttäjän pyynnöstä sääntöjen perusteella. {linked} '
            'Linkitys ei ole diagnoosi eikä muuta seurantaa.')


def _finding_label(finding: GeneticLinkFinding, details: bool) -> str:
    kind = finding.significanceLabel or texts.GENETIC_LINK_MASKED
    kind = kind.replace('variantti', 'muutos')
    if details and finding.gene:
        return f'{finding.gene}: {kind}'
    return kind[:1].upper() + kind[1:]


def key_measurements(state: LoopState, theme: GeneticLinkTheme) -> list[dict[str, Any]]:
    """The specific measurements the theme's DNA findings relate to (e.g. LDLR -> LDL-kolesteroli): one series per
    measurement, oldest first, in the order of the policy mapping."""
    mapping = policies.load_policies().get('geneticLinking', {}).get('keyMeasurements', {})
    codes: list[str] = []
    for finding in sorted(theme.findings, key=lambda f: not f.used):  # the finding in use first
        for code in mapping.get((finding.gene or '').upper(), []):
            if code not in codes:
                codes.append(code)
    linked = set(theme.eventIds)
    series: dict[str, dict[str, Any]] = {}
    for event in sorted(state.events, key=lambda e: (e.date, e.id)):
        code = (event.code or '').upper()
        if event.id not in linked or code not in codes or event.type not in ('lab_result', 'vital_sign'):
            continue
        structured = event.structuredData or {}
        row = series.setdefault(code, {'code': code, 'label': event.displayName, 'unit': event.unit,
                                       'referenceRange': structured.get('referenceRange'), 'values': []})
        row['values'].append({
            'eventId': event.id, 'date': event.date,
            'value': structured.get('resultText') or (str(event.value).replace('.', ',') if event.value is not None else '–'),
            'flag': event.abnormalFlag if event.abnormalFlag in ('high', 'low') else None,
        })
    return [series[code] for code in codes if code in series]


def view(state: LoopState) -> Optional[dict[str, Any]]:
    """Client-safe view: gene names and conditions only with the user's permission, nothing when use is not allowed."""
    result = state.support.geneticLinking
    if result is None:
        return None
    if not consent.genetic_allowed(state):
        return {'linkedAt': result.linkedAt, 'suspended': True, 'themes': [], 'healthOnlyThemes': [], 'findingCount': 0,
                'unlinkedFindingCount': 0, 'note': texts.GENETIC_LINK_NOTE}
    details = consent.show_genetic_details(state)
    themes_view = []
    for theme in result.themes:
        themes_view.append({
            **theme.model_dump(exclude={'findings'}),
            'keyMeasurements': key_measurements(state, theme),
            'findings': [{
                'key': f.key if details else f'{theme.id}-{index + 1}',  # the stored key carries the gene name
                # the classification says what the finding is; the gene name only with the user's permission
                'label': _finding_label(f, details),
                'variant': f.variant if details else None,
                'conditions': f.conditions if details else [],
                'significanceLabel': f.significanceLabel if details else None,
                'originLabel': texts.GENETIC_LINK_ORIGIN.get(f.origin, f.origin),
                'statusLabel': f.statusLabel,
                'used': f.used,
            } for index, f in enumerate(theme.findings)],
        })
    return {
        'linkedAt': result.linkedAt, 'suspended': False, 'themes': themes_view, 'healthOnlyThemes': result.healthOnlyThemes,
        'findingCount': result.findingCount, 'unlinkedFindingCount': result.unlinkedFindingCount, 'note': texts.GENETIC_LINK_NOTE,
    }
