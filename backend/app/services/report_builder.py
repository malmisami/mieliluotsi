from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.loop.evidence import genomic_finding_from_match, health_area_for
from app.loop.evidence import translate_condition as _translate_condition
from app.loop.evidence import translate_significance as _translate_significance
from app.services.classification import classify_match
from app.services.ncbi_clinvar import fetch_variant_details
from app.services.session_manager import SessionManager
from app.support.relevance import classify_genetic


def _classification_explanation(finding: dict) -> str:
    category = finding['category']
    conditions = ' '.join(finding['conditions']).lower()
    if 'laskimotukos' in conditions:
        return 'Laskimotukos tarkoittaa verihyytymää laskimossa. Tämä merkintä kertoo yhteydestä tutkimus- tai tietokantatietoon, ei siitä, että henkilöllä olisi nyt tukos.'
    if category == 'clinically_significant':
        return 'Haitallinen tai todennäköisesti haitallinen variantti on variantti, jonka on arvioitu voivan häiritä geenin toimintaa. Se ei yksin varmista sairautta, vaan tulkinta riippuu myös geenistä, periytymistavasta ja henkilön muista tiedoista.'
    if category == 'uncertain_or_conflicting':
        return 'Epävarma tulkinta tarkoittaa, ettei tiedetä riittävän varmasti, vaikuttaako variantti terveyteen. Ristiriitaiset luokitukset tarkoittavat, että eri arvioissa on päädytty eri tuloksiin.'
    if category == 'risk_or_association':
        return 'Riskitekijä tarkoittaa tilastollista yhteyttä sairauteen tai ominaisuuteen. Se ei ole diagnoosi eikä yksin kerro henkilökohtaista sairastumisriskiä.'
    if category == 'pharmacogenetics':
        return 'Lääkevaste tarkoittaa, että variantti voi vaikuttaa siihen, miten elimistö käsittelee tiettyä lääkevalmistetta tai miten lääke tehoaa. Lääkettä ei pidä aloittaa, lopettaa tai vaihtaa tämän tuloksen perusteella.'
    return 'Tämä luokitus kertoo ClinVar-tietokannan tulkinnasta, mutta ei yksin osoita sairautta tai sen kehittymistä.'


def _health_area(finding: dict) -> str:
    return health_area_for(finding.get('gene'), finding['conditions'])


def _disease_observation(finding: dict) -> dict:
    category = finding['category']
    conditions = finding['conditions']
    condition_text = ', '.join(conditions).lower()
    if 'alzheimer' in condition_text:
        if category == 'risk_or_association':
            interpretation = (
                'Variantti on yhdistetty tutkimuksissa Alzheimerin taudin riskiin. '
                'Se voi muuttaa riskiä suuntaan tai toiseen, mutta ei ennusta yksin, sairastuuko henkilö.'
            )
        else:
            interpretation = (
                'ClinVar-merkintä liittyy Alzheimerin tautiin, mutta tämän yksittäisen variantin merkitys '
                'pitää tulkita yhdessä muun terveystiedon kanssa.'
            )
        return {
            'related_conditions': conditions,
            'health_area': _health_area(finding),
            'likely_observation': interpretation,
            'evidence': finding['clinical_significance'] or 'Ei ilmoitettu',
            'action_note': (
                'ClinVar ei anna tästä yksin henkilökohtaista sairastumisprosenttia. '
                'Älä tee terveyspäätöksiä tämän löydöksen perusteella ilman ammattilaisen arviota.'
            ),
        }
    if category == 'clinically_significant':
        interpretation = 'ClinVar-tulkinta on kliinisesti merkittävä; tämä on tarkistettava terveydenhuollon ammattilaisen kanssa.'
    elif category == 'uncertain_or_conflicting':
        interpretation = 'ClinVar-tulkinta on epävarma tai ristiriitainen, joten tästä ei voi tehdä luotettavaa sairauspäätelmää.'
    elif category == 'risk_or_association':
        interpretation = 'Variantti on tutkimuksissa yhdistetty riskiin tai ominaisuuteen, mutta yhteys ei ole varma sairauden ennuste.'
    elif category == 'pharmacogenetics':
        interpretation = 'Variantti voi liittyä lääkevasteeseen; lääkitystä ei pidä muuttaa tämän raportin perusteella.'
    else:
        interpretation = 'Variantista löytyi ClinVar-merkintä, mutta sen sairausmerkitys ei ole tämän aineiston perusteella selkeä.'

    return {
        'related_conditions': conditions,
        'health_area': _health_area(finding),
        'likely_observation': interpretation,
        'evidence': finding['clinical_significance'] or 'Ei ilmoitettu',
        'action_note': 'Havainto ei ole diagnoosi. Varmista merkitys ammattilaisen kanssa, jos löydös on sinulle tärkeä.',
    }


def _remote_query(finding: dict) -> str:
    return finding['rsid'] or f"{finding['chrom']}[chr]:{finding['pos']} {finding['ref']} {finding['alt']}"


def _build_clinvar_overview(findings: list[dict], remote_details: list[dict]) -> str:
    disease_names = []
    for finding in findings:
        disease_names.extend(finding['conditions'])
    unique_diseases = list(dict.fromkeys(name for name in disease_names if name))
    health_areas = list(dict.fromkeys(item['disease_observation']['health_area'] for item in findings))
    significant = [item for item in findings if item['category'] == 'clinically_significant']
    uncertain = [item for item in findings if item['category'] == 'uncertain_or_conflicting']
    remote_count = sum(len(item.get('records', [])) for item in remote_details)

    if not findings:
        return 'ClinVar-haussa ei löytynyt raportoitavia variantteja.'
    diseases = ', '.join(unique_diseases[:8]) or 'nimettyä sairautta tai ominaisuutta'
    areas = ', '.join(health_areas[:5])
    if remote_details and remote_count:
        lookup_status = f"NCBI:n ClinVar-tietokannasta löytyi tarkennuksia {remote_count} merkinnästä. "
    elif remote_details:
        lookup_status = 'NCBI:n ClinVar-tietokannasta ei löytynyt lisätietueita tällä haulla. '
    else:
        lookup_status = 'Erillistä verkkohakua ei tehty, koska käytössä ei ollut etäyhteyttä vaativaa ClinVar-tilaa. '
    return (
        f"Analyysissä löytyi {len(findings)} tietokantamerkintää. Niistä {len(significant)} on "
        f"luokiteltu kliinisesti merkittäviksi ja {len(uncertain)} epävarmoiksi tai ristiriitaisiksi. "
        f"Merkinnöissä mainitut sairaudet tai ominaisuudet ovat: {diseases}. "
        f"Laajemmin havainnot liittyvät seuraaviin terveysalueisiin: {areas}. "
        f"{lookup_status}"
        "Tämä ei ole henkilökohtainen sairastumisprosentti. Luokitus kertoo variantin "
        "tulkinnasta, mutta ei yksin kerro, sairastuuko tämä henkilö."
    )


def build_report(session_id: str) -> dict:
    state = SessionManager.get_state(session_id)
    if not state:
        raise FileNotFoundError('Session not found')

    db = SessionManager.get_session_db(session_id)
    rows = db.execute('SELECT * FROM matched_findings ORDER BY pos, rsid').fetchall()
    db.close()

    findings = []
    for row in rows:
        data = json.loads(row['data'] or '{}')
        finding = {
                'id': row['id'],
                'rsid': row['rsid'],
                'chrom': row['chrom'],
                'pos': row['pos'],
                'ref': row['ref'],
                'alt': row['alt'],
                'genotype': row['genotype'],
                'alt_allele_count': row['alt_allele_count'],
                'zygosity': row['zygosity'],
                'gene': row['gene'],
                'conditions': json.loads(row['conditions'] or '[]'),
                'clinical_significance': row['clinical_significance'],
                'clinical_significance_fi': _translate_significance(row['clinical_significance']),
                'category': classify_match(data),
                'review_status': row['review_status'],
                'review_stars': row['review_stars'],
                'variation_id': row['variation_id'],
                'match_method': row['match_method'],
                'source': row['source'],
                'source_url': row['source_url'],
                'summary_fi': row['summary_fi'],
                'limitations_fi': row['limitations_fi'],
                'inheritance_note_fi': row['inheritance_note_fi'],
                'synthetic': bool(row['synthetic']),
        }
        finding['conditions'] = [_translate_condition(condition) for condition in finding['conditions']]
        finding['classification_explanation_fi'] = _classification_explanation(finding)
        finding['disease_observation'] = _disease_observation(finding)
        finding['genomic_finding'] = genomic_finding_from_match(finding, state.get('input_source')).model_dump()
        # Gate 1: what this variant may be used for. The raw list never feeds the user's guidance directly.
        finding['relevance'] = classify_genetic(row['clinical_significance'], 'unconfirmed')
        findings.append(finding)

    raw_path = Path(state['raw_file_path']) if state.get('raw_file_path') else None
    file_size = raw_path.stat().st_size if raw_path and raw_path.exists() else 0
    sha_prefix = 'n/a'
    if raw_path and raw_path.exists():
        digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        sha_prefix = digest[:12]

    remote_details = []
    if state.get('mode') == 'clinvar':
        remote_details = [fetch_variant_details(_remote_query(finding)) for finding in findings]
        for finding, remote in zip(findings, remote_details):
            finding['clinvar_remote'] = remote

    return {
        'report_version': '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_file': {
            'name': state.get('source_display_name') or 'unknown',
            'size_bytes': file_size,
            'detected_format': '23andme_like',
            'genome_build': state.get('genome_build', 'GRCh38'),
            'synthetic': True,
            'input_source': state.get('input_source', 'quick_demo'),
            'sha256_prefix': sha_prefix,
        },
        'analysis': {
            'variants_analyzed': int(state.get('parse_rows_processed', 0)),
            'valid_rows': int(state.get('parse_rows_processed', 0)),
            'invalid_rows': 0,
            'duplicate_rows': 0,
            'position_matches': int(state.get('position_matches', 0)),
            'allele_matches': int(state.get('allele_matches', 0)),
            'clinically_significant_findings': sum(1 for item in findings if item['category'] == 'clinically_significant'),
            'uncertain_findings': sum(1 for item in findings if item['category'] == 'uncertain_or_conflicting'),
            'pharmacogenetic_findings': sum(1 for item in findings if item['category'] == 'pharmacogenetics'),
            'risk_associations': sum(1 for item in findings if item['category'] == 'risk_or_association'),
            'other_findings': sum(1 for item in findings if item['category'] == 'other'),
            'relevance_counts': {
                category: sum(1 for item in findings if item['relevance']['category'] == category)
                for category in ('needs_professional_check', 'no_practical_significance', 'uncertain_or_conflicting')
            },
            'mode': state.get('mode', 'demo'),
        },
        'findings': findings,
        'clinvar_overview_fi': _build_clinvar_overview(findings, remote_details),
        'warnings': [],
        'limitations': [
            'Tutkimus- ja demokäyttöön. Ei diagnoosi eikä lääkinnällinen laite.',
            'ClinVar interpretations may conflict or change.',
            'Genotyping arrays inspect selected sites, not the full genome.',
        ],
        'provenance': {
            'database_mode': state.get('mode', 'demo'),
            'clinvar_source': None,
            'clinvar_imported_at': None,
            'demo_manifest_version': '1.0',
        },
    }
