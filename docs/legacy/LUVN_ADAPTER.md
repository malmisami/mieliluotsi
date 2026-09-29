# LUVN-tyyppisen datan adapterikerros

Kaikki tietolähteet (CSV-taulut, JSON-poiminnat, vapaaehtoinen perimätieto) muunnetaan **yhteiseen sisäiseen
profiiliin `PersonProfile`** ennen kuin agentti tai käyttöliittymä käyttää niitä. Sovellusta ei ole sidottu
DNA-tiedostomuotoon eikä mihinkään yksittäiseen lähdejärjestelmään. Oikeita LUVN-integraatioita ei ole – rajapinta ja
mäppäykset on mallinnettu synteettisellä datalla.

Koodi: `backend/app/support/adapters/` · Demodata: `data/luvn/aino/` · Testit: `backend/tests/test_support_rules.py`

## Sisäinen malli: PersonProfile

| Kenttä | Sisältö | Esimerkkilähde |
|---|---|---|
| `demographics` | tunniste, nimi, syntymävuosi, sukupuoli, alue | `asiakas.json` → `henkilo` |
| `diagnoses` | koodi, nimi, pvm, tila, lähde | `diagnoosit.csv` |
| `medications` | valmiste, käyttötarkoitus, aloitus, tila | `laakitys.csv` |
| `careEpisodes` | käynnit ja hoitojaksot | `asiakas.json` → `hoitojaksot` |
| `professionalNotes` | ammattilaisten vapaamuotoiset kirjaukset | `asiakas.json` → `kirjaukset` |
| `interactionEvents` | asioinnit eri kanavissa (digi, puhelin, vastaanotto) | `asioinnit.csv` |
| `measurements` | mittaukset (verenpaine ylä/ala erikseen) ja laboratoriotulokset tutkimuspyynnöittäin | `mittaukset.csv`, `laboratoriotulokset.csv` |
| `selfReportedData` | käyttäjän omat ilmoitukset (Ainon demodatassa ei ole omia ilmoituksia) | `asiakas.json` → `omailmoitukset` |
| `geneticInsights` | vapaaehtoinen perimätieto, luokitus säilytetään sellaisenaan | `perimatieto.json` |
| `consents` | lähdejärjestelmän suostumusmerkinnät (informatiivinen) | `asiakas.json` → `suostumukset` |
| `activeSupportPlans` | lähdejärjestelmän tuntemat suunnitelmat | – |
| `sourceSystems` | alkuperätieto: mikä adapteri luki minkä tiedoston ja montako riviä | adapterit täyttävät |

Koko skeema JSON Schemana: `GET /api/support/schema/person-profile`.

Jokaisessa rivissä on `source` (alkuperä) ja päivämäärä, ja `synthetic: true`. Adapteri ei koskaan tulkitse kliinistä
merkitystä: se nimeää kentät, muuntaa muodot ja kirjaa alkuperän. Tulkinta tapahtuu vasta portissa 1
(`app/support/relevance.py`).

## Adapterirajapinta

```python
from app.support.adapters.base import TableMapping
from app.support.adapters.csv_adapter import CsvAdapter

mapping = TableMapping(
    target='measurements',                 # mihin PersonProfile-listaan rivit menevät
    person_column='asiakas_tunnus',        # rivit suodatetaan henkilön mukaan
    columns={'date': 'pvm', 'code': 'mittaus', 'value': 'arvo', 'unit': 'yksikko',
             'systolic': 'systolinen', 'diastolic': 'diastolinen', 'context': 'ymparisto',
             'flag': 'viite_lippu', 'source': 'lahde'},
    value_maps={'code': {'RR': 'BP'}, 'context': {'koti': 'home', 'vastaanotto': 'clinic', 'laboratorio': 'lab'}},
    required=('date', 'code'),
)
target, items, stats = CsvAdapter({'mittaukset.csv': mapping}).load_table(path, 'mittaukset.csv', person_id='SYN-AINO-0046')
```

- **CSV** luetaan virtana `chunk_size` rivin paloissa (`iter_csv_chunks`), ja muiden henkilöiden rivit ohitetaan pala
  kerrallaan. Koko alueen poimintaa ei siis ladata muistiin.
- **Päivämäärät**: ISO (`2026-08-30`) ja suomalainen muoto (`30.8.2026`). **Desimaalipilkku**: `3,4` → `3.4`.
- **Koodimäppäys**: tuntemattomat koodit säilytetään sellaisenaan, joten mitään ei pudoteta hiljaa.
- **Laboratoriotulokset**: yksi rivi per tulos, ja `pyynto_tunnus` ryhmittelee saman tutkimuspyynnön tulokset. Terveystiedot-
  näkymä näyttää pyynnön yhtenä merkintänä (esim. *Lipidit*, 7 tulosta) kansallisen terveystietonäkymän tapaan. Tulos
  säilytetään myös alkuperäisessä muodossa (`resultText`, esim. `0,40`), ja sääntömoottorin käyttämät koodit (`LDL`, `GLU`)
  pysyvät ennallaan.
- **Virheet**: puuttuva pakollinen kenttä, virheellinen päivämäärä tai puolikas verenpainemittaus → `AdapterError`
  (API palauttaa 400 ja suomenkielisen viestin).
- `load_person_directory(dir, person_id)` kokoaa henkilön kaikista hakemiston lähteistä. Vain `asiakas.json` on pakollinen;
  **perimätieto on vapaaehtoinen**.
- `projection.profile_events(profile)` vie kaikki lähteet samalle aikajanalle sääntömoottorin tuntemalla sanastolla
  (`lab_result/LDL`, `vital_sign/BP` …). Tuotua historiaa ei arvioida takautuvasti.

## Oletusmäppäys (demo)

| Tiedosto | Sarakkeet → kentät | Koodimäppäykset |
|---|---|---|
| `diagnoosit.csv` | `dg_koodi→code`, `dg_nimi→label`, `dg_pvm→diagnosedAt`, `tila→status` | `aktiivinen→active` |
| `laakitys.csv` | `valmiste→name`, `kayttotarkoitus→purpose`, `aloitus_pvm→startedAt`, `tila→status` | `käytössä→active` |
| `mittaukset.csv` | `pvm, mittaus, arvo, yksikko, systolinen, diastolinen, ymparisto, viite_lippu` | `RR→BP`, `koti→home` |
| `laboratoriotulokset.csv` | `naytteenotto_pvm, pyynto_tunnus→panelId, tutkimus→panelName, lyhenne→abbreviation, analyysi→label, koodi→code, tulos, yksikko, viitearvot→referenceRange, poikkeama→flag` | kaikki rivit `context=lab` (`defaults`); tekstitulos (esim. `Negatiivinen`) sallitaan (`allow_text_values`) |
| `asioinnit.csv` | `pvm→date`, `kanava→channel`, `aihe→topic`, `kuvaus→summary` | `digipalvelu→digital`, `puhelin→phone` |
| `asiakas.json` | `henkilo`, `hoitojaksot`, `kirjaukset`, `omailmoitukset`, `suostumukset` | – |
| `perimatieto.json` | `havainnot[].geeni, variantti, luokitus, liittyy, vahvistus, evidenssiTunnus` | `vahvistettu→lab_confirmed` |

Oikean LUVN-poiminnan käyttöönotto: lisää sille oma `TableMapping` (tai JSON-adapteri) ja anna se `CsvAdapter`ille.
Muuta koodia ei tarvitse muuttaa.

## Esikatselu ilman tallennusta

```bash
curl -s -X POST http://localhost:8002/api/support/adapters/preview -H 'Content-Type: application/json' \
  -d '{"format":"csv","table":"asioinnit.csv","content":"asiakas_tunnus;pvm;kanava;aihe;kuvaus;lahde\nX-1;1.9.2026;puhelin;verenpaine;Kysymys;Testi"}'
```

Sama työkalu on ammattilaisnäkymässä kohdassa *Tietolähteiden adapterit (kehittäjätyökalu)*.

## Laajat aineistot (esim. 50 000 profiilia)

- `GET /api/support/cohort?page=1&pageSize=25&status=active&theme=verenpaine` palauttaa yhden sivun (enintään 100 riviä).
  Palvelin lukee synteettisen kohortin (`runtime/cohort/kohortti.csv`, oletuksena 50 000 henkilöä) paloina.
- `GET /api/support/impact/cohort` laskee vaikuttavuusluvut palvelimella virtana. Tulos välimuistitetaan tiedoston
  muokkausajan mukaan.
- Kohortin voi luoda uudelleen: `backend/.venv/bin/python scripts/generate_synthetic_cohort.py --size 50000`.
