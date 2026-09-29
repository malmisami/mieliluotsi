"""JSON adapters: the person/record export and the (optional) genetic report."""
from __future__ import annotations

from typing import Any

from app.support.adapters.base import AdapterError, parse_date
from app.support.models import CareEpisode, Demographics, GeneticInsight, ProfessionalNote, SelfReport

ROLE_LABELS = {'lääkäri': 'lääkäri', 'sairaanhoitaja': 'sairaanhoitaja', 'terveydenhoitaja': 'terveydenhoitaja', 'fysioterapeutti': 'fysioterapeutti'}


def _require(data: dict, key: str, where: str) -> Any:
    if key not in data or data[key] in (None, ''):
        raise AdapterError(f'Kenttä {key} puuttuu ({where}).')
    return data[key]


class PersonJsonAdapter:
    """Maps a LUVN-like person export (asiakas.json) to demographics, care episodes, notes, self-reports and consents."""
    name = 'luvn_person_json'

    def load(self, data: dict) -> dict[str, Any]:
        person = _require(data, 'henkilo', 'juuri')
        demographics = Demographics(
            personId=_require(person, 'asiakasTunnus', 'henkilo'),
            displayName=person.get('nimi') or 'Nimetön asiakas',
            birthYear=person.get('syntymavuosi'),
            sex=person.get('sukupuoli'),
            region=person.get('alue'),
        )
        return {
            'demographics': demographics,
            'careEpisodes': [
                CareEpisode(
                    id=_require(item, 'tunnus', 'hoitojaksot'), date=parse_date(_require(item, 'pvm', 'hoitojaksot'), 'pvm'),
                    kind=item.get('tyyppi') or 'Hoitokäynti', unit=item.get('yksikko'),
                    professionalRole=ROLE_LABELS.get(item.get('ammattilainen') or '', item.get('ammattilainen')),
                    summary=item.get('kuvaus'), source=item.get('yksikko') or 'Hoitojaksot',
                )
                for item in data.get('hoitojaksot', [])
            ],
            'professionalNotes': [
                ProfessionalNote(
                    id=_require(item, 'tunnus', 'kirjaukset'), date=parse_date(_require(item, 'pvm', 'kirjaukset'), 'pvm'),
                    authorRole=item.get('laatija') or 'ammattilainen', text=_require(item, 'teksti', 'kirjaukset'),
                    source='Ammattilaisen kirjaus (synteettinen)',
                )
                for item in data.get('kirjaukset', [])
            ],
            'selfReportedData': [
                SelfReport(
                    id=_require(item, 'tunnus', 'omailmoitukset'), date=parse_date(_require(item, 'pvm', 'omailmoitukset'), 'pvm'),
                    topic=item.get('aihe') or 'muu', text=_require(item, 'teksti', 'omailmoitukset'), source='user_reported',
                )
                for item in data.get('omailmoitukset', [])
            ],
            'consents': [
                {
                    'id': item.get('tunnus'), 'date': parse_date(item.get('pvm'), 'pvm'), 'target': item.get('kohde'),
                    'status': item.get('tila'), 'channel': item.get('kanava'),
                }
                for item in data.get('suostumukset', [])
            ],
        }


class GeneticJsonAdapter:
    """Maps a genetic report export (perimatieto.json). Classification is kept verbatim; gate 1 interprets it."""
    name = 'genetic_json'

    def load(self, data: dict, person_id: str) -> list[GeneticInsight]:
        if data.get('asiakasTunnus') != person_id:
            raise AdapterError('Perimätieto kuuluu eri henkilölle.')
        study = data.get('tutkimus', {})
        reported_at = parse_date(study.get('pvm'), 'tutkimus.pvm')
        source = study.get('lahde') or 'Perimätieto'
        return [
            GeneticInsight(
                id=_require(item, 'tunnus', 'havainnot'), gene=item.get('geeni'), variant=_require(item, 'variantti', 'havainnot'),
                significance=_require(item, 'luokitus', 'havainnot'), conditions=list(item.get('liittyy', [])),
                confirmation='lab_confirmed' if item.get('vahvistus') == 'vahvistettu' else 'unconfirmed',
                findingId=item.get('evidenssiTunnus'), reportedAt=reported_at, source=source,
            )
            for item in data.get('havainnot', [])
        ]
