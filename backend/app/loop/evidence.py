from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.config import settings
from app.loop.models import GenomicFinding

SYNTHETIC_INPUT_SOURCES = {'quick_demo', 'full_demo'}

# Shared with the DNA report (app/services/report_builder.py) so the report and the "Minun seuranta"
# table always show the same "Havainto" / "Varmuus" wording.
CONDITION_TRANSLATIONS = {
    'venous thrombosis': 'laskimotukos',
    'hyperhomocysteinemia': 'kohonnut homokysteiinipitoisuus',
    'clopidogrel response': 'klopidogreelin (verenohennuslääke) teho',
    'hyperlipoproteinemia type iii': 'rasva-aineenvaihdunnan häiriö ja kohonnut kolesteroli',
    'alzheimer disease, late onset': 'myöhäisiän Alzheimerin tauti',
    'li-fraumeni syndrome': 'Li-Fraumenin oireyhtymä (perinnöllinen syöpäalttius)',
    'hereditary breast and ovarian cancer syndrome': 'perinnöllinen rinta- ja munasarjasyöpä',
    'hypercholesterolemia (synthetic demo)': 'kohonnut LDL-kolesteroli (synteettinen demo)',
}

SIGNIFICANCE_TRANSLATIONS = {
    'pathogenic': 'haitallinen variantti',
    'likely pathogenic': 'todennäköisesti haitallinen variantti',
    'uncertain significance': 'epävarma tulkinta',
    'conflicting classifications of pathogenicity': 'ristiriitaiset luokitukset',
    'risk factor': 'riskitekijä',
    'drug response': 'lääkevaste',
}


def translate_condition(condition: str) -> str:
    return CONDITION_TRANSLATIONS.get(condition.strip().lower(), condition)


def translate_significance(significance: str | None) -> str:
    if not significance:
        return 'Ei ilmoitettu'
    return SIGNIFICANCE_TRANSLATIONS.get(significance.strip().lower(), significance)


def health_area_for(gene: str | None, conditions: list[str]) -> str:
    gene_upper = (gene or '').upper()
    text = ' '.join(conditions).lower()
    if gene_upper == 'LDLR':
        return 'rasva-aineenvaihduntaan ja LDL-kolesterolin poistumiseen verenkierrosta'
    if 'kolesterol' in text or 'lipid' in text or gene_upper == 'APOE':
        return 'rasva-aineenvaihduntaan, kolesteroliin ja joissakin tapauksissa muistiin liittyviin sairauksiin'
    if 'laskimotukos' in text or gene_upper == 'F5':
        return 'veren hyytymiseen ja laskimotukosten riskiin'
    if 'lääkevaste' in text or 'klopidogreel' in text or gene_upper == 'CYP2C19':
        return 'lääkkeiden käsittelyyn elimistössä ja lääkevasteeseen'
    if 'homokystei' in text or gene_upper == 'MTHFR':
        return 'folaatin ja homokysteiinin aineenvaihduntaan, joka liittyy verisuonten terveyteen'
    if gene_upper in {'BRCA1', 'TP53'}:
        return 'solujen kasvun säätelyyn ja joidenkin syöpien perinnölliseen riskiin'
    if 'alzheimer' in text:
        return 'muistiin ja Alzheimerin tautiin liittyvään riskiin'
    return 'geenin toimintaan tai tietokannassa mainittuun sairauteen tai ominaisuuteen'


def _normalize_conditions(value) -> list[str]:
    """Accepts a JSON-encoded string (raw DB row) or an already-parsed list (report_builder)."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return [str(item) for item in parsed] if isinstance(parsed, list) else [value]
    return []


@lru_cache(maxsize=1)
def load_evidence() -> dict:
    """Small local evidence file, read once per process (never the full ClinVar file)."""
    return json.loads(Path(settings.LOOP_EVIDENCE_PATH).read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def load_profile() -> dict:
    return json.loads(Path(settings.LOOP_PROFILE_PATH).read_text(encoding='utf-8'))


def evidence_entry(finding_id: str) -> dict | None:
    return next((item for item in load_evidence()['findings'] if item['id'] == finding_id), None)


def rules_for_gene(gene: str | None) -> list[dict]:
    return [rule for rule in load_evidence()['rules'] if rule['gene'] == gene]


def evidence_level_label(level: str) -> str:
    return load_evidence()['evidence_levels'].get(level, level)


def event_type_label(event_type: str) -> str:
    return load_evidence()['event_type_labels'].get(event_type, event_type)


def source_name() -> str:
    return load_evidence()['source']['name']


def finding_from_evidence(entry: dict, confirmed: bool = True) -> GenomicFinding:
    """`confirmed=False` renders the same known variant as an unconfirmed candidate (see
    genomic_finding_from_match) while keeping its identity (id) stable, so the same physical
    variant is never tracked as two different findings depending on where it was seen."""
    conditions = [translate_condition(c) for c in entry.get('conditions', [])]
    return GenomicFinding(
        id=entry['id'],
        gene=entry['gene'],
        variant=entry['variant'],
        title=entry['title'],
        description=entry['description'],
        classification=entry['classification'],
        confirmationStatus=entry['confirmationStatus'] if confirmed else 'raw_candidate',
        evidenceLevel=entry['evidenceLevel'] if confirmed else 'not_assessed',
        monitoringEligible=entry['monitoringEligible'],
        relevantEventTypes=entry['relevantEventTypes'] if confirmed else [],
        source=source_name(),
        lastReviewedAt=entry.get('lastReviewedAt') if confirmed else None,
        synthetic=True,
        relatedConditions=conditions,
        healthArea=health_area_for(entry['gene'], conditions),
    )


def _matching_evidence(gene: str | None, rsid: str | None, alt: str | None) -> dict | None:
    for entry in load_evidence()['findings']:
        match = entry['match']
        if match['gene'] == gene and match['rsid'] == rsid and match['alt'] == alt:
            return entry
    return None


def genomic_finding_from_match(finding: dict, input_source: str | None) -> GenomicFinding:
    """Turn one DNA-analysis finding into a structured GenomicFinding.

    Confirmation status is decided here on the server: only a synthetic demo input that matches
    an entry in the local evidence file becomes synthetic_demo_confirmed. Everything else stays a
    raw_candidate. A variant that matches a known evidence entry always keeps that entry's id
    (regardless of confirmation status), so the same physical variant is never split into two
    separate findings - and two separate monitorings - depending on where it was seen. Any finding
    can be put under monitoring, but the rule engine only ever produces a clinically meaningful
    observation for confirmed findings with a curated rule (see evidence.json).
    """
    entry = _matching_evidence(finding.get('gene'), finding.get('rsid'), finding.get('alt'))
    if entry:
        is_synthetic_input = input_source in SYNTHETIC_INPUT_SOURCES and bool(finding.get('synthetic'))
        return finding_from_evidence(entry, confirmed=is_synthetic_input)

    gene = finding.get('gene')
    rsid = finding.get('rsid') or f"{finding.get('chrom')}:{finding.get('pos')}"
    conditions = [translate_condition(c) for c in _normalize_conditions(finding.get('conditions'))]
    return GenomicFinding(
        id=f"gf-candidate-{(gene or 'unknown').lower()}-{rsid}",
        gene=gene,
        variant=f"{rsid} (chr{finding.get('chrom')}:{finding.get('pos')} {finding.get('ref')}>{finding.get('alt')})",
        title=f"{gene or 'Tuntematon geeni'}: DNA-analyysin ehdokaslöydös",
        description=finding.get('summary_fi') or '',
        classification=finding.get('clinical_significance_fi') or translate_significance(finding.get('clinical_significance')),
        confirmationStatus='raw_candidate',
        evidenceLevel='not_assessed',
        monitoringEligible=True,
        relevantEventTypes=[],
        source=finding.get('source') or 'DNA-analyysi',
        lastReviewedAt=None,
        synthetic=bool(finding.get('synthetic')),
        relatedConditions=conditions,
        healthArea=health_area_for(gene, conditions),
    )
