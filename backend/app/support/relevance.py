"""Gate 1: relevance and actionability filter.

Not everything the system finds may reach the user's follow-up. Every genetic finding and every health-data
theme gets one category; only professional-approved items can ever affect an active support plan. The
user-facing wording never says "DNA-virhe" and never presents an uncertain variant as a disease or risk.
"""
from __future__ import annotations

from typing import Optional

from app.support.models import PersonProfile, SourceRef
from app.support.texts import CATEGORY_LABELS

GENERIC_GENETIC_TITLE = 'Mahdollinen perimään liittyvä tekijä'


def classify_genetic(significance: Optional[str], confirmation: Optional[str] = None, approved: bool = False) -> dict:
    """Returns {category, label, reason, userVisible}. Deterministic; the LLM never classifies variants."""
    sig = (significance or '').strip().lower()
    unconfirmed = confirmation != 'lab_confirmed'
    if approved:
        reason = 'Ammattilainen on hyväksynyt havainnon seurannan taustatiedoksi.'
        if unconfirmed:
            reason += ' Kliininen vahvistus puuttuu, joten havainto on merkitty vahvistamattomaksi.'
        return _result('professionally_approved', reason, True)
    if 'conflicting' in sig or 'uncertain' in sig:
        return _result('uncertain_or_conflicting', 'Tulkinta on epävarma tai lähteet ovat ristiriidassa. Havaintoa ei käytetä '
                       'seurannassa eikä ohjauksessa, eikä sitä tule tulkita sairaudeksi tai riskiksi.', False)
    if 'benign' in sig:
        return _result('no_practical_significance', 'Hyvänlaatuiseksi luokiteltu variantti, jolla ei ole merkitystä seurannalle.', False)
    if 'pathogenic' in sig:
        return _result('needs_professional_check', 'Havainto voi olla merkityksellinen, mutta se vaatii ammattilaisen arvion ja '
                       'kliinisen vahvistuksen ennen kuin se voi vaikuttaa seurantaan.', True)
    if 'drug response' in sig:
        return _result('needs_professional_check', 'Lääkevasteeseen liittyvä tieto on hyödyllinen vain lääkettä määrättäessä. '
                       'Agentti ei käytä sitä ohjauksessa.', True)
    if 'risk factor' in sig or 'association' in sig or 'protective' in sig:
        return _result('no_practical_significance', 'Tilastollinen yhteys, joka ei yksin muuta omahoidon seurantaa. '
                       'Ei näytetä asiakkaan näkymässä.', False)
    return _result('no_practical_significance', 'Ei tunnettua merkitystä seurannalle.', False)


def _result(category: str, reason: str, user_visible: bool) -> dict:
    return {'category': category, 'label': CATEGORY_LABELS[category], 'reason': reason, 'userVisible': user_visible}


def genetic_user_title(gene: Optional[str], show_details: bool) -> str:
    if show_details and gene:
        return f'{GENERIC_GENETIC_TITLE} ({gene}-geenin variantti)'
    return GENERIC_GENETIC_TITLE


def _sources_for_theme(profile: PersonProfile, theme: dict) -> list[SourceRef]:
    topic = theme.get('topic', '')
    keywords = [k.lower() for k in theme.get('noteKeywords', [])]
    refs: list[SourceRef] = []
    for dx in profile.diagnoses:
        if dx.code in theme['triggerDiagnosisCodes']:
            refs.append(SourceRef(kind='diagnoses', id=dx.id, label=f'Diagnoosi {dx.code} – {dx.label}', date=dx.diagnosedAt))
    for med in profile.medications:
        if med.status == 'active' and (med.purpose or '').lower() == topic:
            refs.append(SourceRef(kind='medications', id=med.id, label=f'Lääkitys: {med.name}', date=med.startedAt))
    for note in profile.professionalNotes:
        if any(k in note.text.lower() for k in keywords):
            refs.append(SourceRef(kind='professionalNotes', id=note.id, label=f'Kirjaus ({note.authorRole})', date=note.date))
    measurements = [m for m in profile.measurements if m.code == theme.get('measurementCode')]
    if measurements:
        dates = sorted(m.date for m in measurements)
        refs.append(SourceRef(kind='measurements', id=measurements[-1].id,
                              label=f"Mittaukset: {measurements[0].label} ({len(measurements)} kpl)", date=dates[-1]))
    contacts = [c for c in profile.interactionEvents if c.topic == topic]
    if contacts:
        refs.append(SourceRef(kind='interactionEvents', id=contacts[-1].id, label=f'Asiointitapahtumat aiheesta {topic} ({len(contacts)} kpl)',
                              date=max(c.date for c in contacts)))
    for report in profile.selfReportedData:
        if report.topic in theme.get('selfReportTopics', []):
            refs.append(SourceRef(kind='selfReportedData', id=report.id, label=f'Oma ilmoitus: {report.topic}', date=report.date))
    return refs


def health_data_themes(profile: PersonProfile, themes: dict) -> list[dict]:
    """Which support themes the health data supports. A theme needs a diagnosis from the source records; lone
    measurements without one are filtered out (demo policy) instead of becoming a new follow-up."""
    results = []
    for theme_id, theme in themes.items():
        diagnoses = [d for d in profile.diagnoses if d.code in theme['triggerDiagnosisCodes'] and d.status == 'active']
        sources = _sources_for_theme(profile, theme)
        if diagnoses:
            results.append({
                'themeId': theme_id, 'category': 'potentially_actionable', 'sources': sources, 'diagnosis': diagnoses[0],
                'reason': 'Terveystiedoissa on seurantaan soveltuva diagnoosi ja siihen liittyviä mittauksia tai kirjauksia. '
                          'Vaatii ammattilaisen hyväksynnän ennen käyttöönottoa.',
            })
        elif sources:
            results.append({
                'themeId': theme_id, 'category': 'no_practical_significance', 'sources': sources, 'diagnosis': None,
                'reason': 'Yksittäisiä mittauksia ilman diagnoosia tai toistuvaa poikkeamaa. Ei muodosta seurantateemaa (demo-policy).',
            })
    return results
