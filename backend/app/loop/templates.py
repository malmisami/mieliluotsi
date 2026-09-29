"""Predefined Finnish texts. Used whenever the LLM is off, fails, or its text fails the safety check."""
from __future__ import annotations

from app.loop.models import GenomicFinding, HealthEvent


def fi_date(iso_date: str | None) -> str:
    if not iso_date:
        return '–'
    year, month, day = iso_date.split('-')
    return f'{int(day)}.{int(month)}.{year}'


def fi_value(event: HealthEvent) -> str:
    value = event.value
    if isinstance(value, float):
        value = f'{value:.1f}'.replace('.', ',')
    return f"{'' if value is None else value} {event.unit or ''}".strip()


def observation_title(finding: GenomicFinding, event: HealthEvent) -> str:
    return f'Uusi huomio: {event.displayName} ja {finding.gene}-löydös'


def observation_explanation(finding: GenomicFinding, event: HealthEvent) -> str:
    return (
        f'Uusi tulos {event.displayName} {fi_value(event)} ({fi_date(event.date)}) on merkitty viitealueen ylittäväksi. '
        f'Seurannassasi on {finding.gene}-geenin löydös, joka liittyy LDL-kolesterolin poistumiseen verenkierrosta. '
        'Tämän yhdistelmän vuoksi järjestelmä ehdottaa, että käyt tiedot läpi terveydenhuollon ammattilaisen kanssa. '
        'Voit muodostaa ammattilaiselle yhteenvedon, jossa tiedot ovat valmiiksi koottuina.'
    )


def additional_info_explanation(finding: GenomicFinding, event: HealthEvent) -> str:
    return (
        f'Uusi tieto ({event.displayName}) liittyy seurannassa olevaan {finding.gene}-löydökseen, '
        'mutta tuloksesta puuttuu viitealue tai poikkeamamerkintä. Tarkista tulos alkuperäisestä lähteestä.'
    )


def summary_intro(profile_name: str, finding: GenomicFinding, event: HealthEvent) -> str:
    return (
        f'Synteettisen demohenkilön {profile_name} seurannassa on {finding.gene}-geenin löydös '
        f'(vahvistustila: {finding.confirmationStatus}). {fi_date(event.date)} kirjattiin {event.displayName} '
        f'{fi_value(event)}, joka on merkitty viitealueen ylittäväksi. OmaGenomi Loop muodosti deterministisen '
        'säännön perusteella huomion, jossa ehdotetaan tietojen läpikäyntiä ammattilaisen kanssa. '
        'Yhteenveto kokoaa tiedot arviota varten.'
    )


def full_summary_intro(profile_name: str, findings: list[GenomicFinding], unrelated_count: int) -> str:
    finding_list = ', '.join(f'{f.gene}-löydös ({f.title})' for f in findings)
    count_text = 'yksi geneettinen löydös' if len(findings) == 1 else f'{len(findings)} geneettistä löydöstä'
    unrelated_text = (
        f' Aikajanalla on lisäksi {unrelated_count} tapahtumaa, jotka eivät liity suoraan mihinkään näistä löydöksistä.'
        if unrelated_count else ''
    )
    return (
        f'Synteettisen demohenkilön {profile_name} seurannassa on {count_text}: {finding_list}. '
        'Yhteenveto kokoaa löydökset, niihin liittyvät terveystapahtumat aikajanalta sekä puuttuvat tiedot arviota varten.'
        f'{unrelated_text}'
    )


def assessment_for_status(status: str) -> str:
    return {
        'monitoring': 'Seuranta aktiivinen. Ei uusia huomioita.',
        'no_action': 'Seuranta aktiivinen. Ei uusia huomioita.',
        'additional_information_needed': 'Uusi tieto liittyy löydökseen, mutta siitä puuttuu tietoja. Tarkista tulos.',
        'professional_review_recommended': 'Uusi huomio: tiedot kannattaa käydä läpi terveydenhuollon ammattilaisen kanssa.',
        'waiting_for_user': 'Odottaa vastaustasi: onko asia käsitelty ammattilaisen kanssa?',
        'waiting_for_professional_review': 'Yhteenveto on merkitty jaetuksi. Odottaa ammattilaisen arviota.',
        'resolved': 'Käsitelty ammattilaisen kanssa. Seuranta jatkuu.',
        'dismissed': 'Huomio todettiin epäolennaiseksi. Seuranta jatkuu.',
    }.get(status, 'Seuranta aktiivinen.')
