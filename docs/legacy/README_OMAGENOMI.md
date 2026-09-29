# Agenttinen hyvinvointikumppani – omahoidon jatkuvuuden moottori (pohjana OmaGenomi Lite / Loop)

SOTE AI Hackathon 2026, LUVN-haaste 3. **AI pitää omahoidon käynnissä arjessa myös vastaanottojen välissä.**
Hyvinvointikumppani toimii asiakkaan rinnalla **ammattilaisen hyväksymän seurantasuunnitelman** mukaan, ja sillä on
neljä ydintehtävää:

1. **Muistaa puolestasi:** tavoitteet, ammattilaisen kanssa sovitut asiat, mitä seurataan, mitä on jo kokeiltu, mikä
   toimii ja milloin asia tarkistetaan uudelleen.
2. **Ottaa itse yhteyttä:** esimerkiksi "Verenpaineesi on ollut viime viikkoina hieman aiempaa korkeampi. Haluaisitko
   tehdä tällä viikolla kolmen päivän kotiseurannan?"
3. **Auttaa tekemään pieniä asioita:** yksi realistinen askel kerrallaan ("Kokeillaan seuraavat 7 päivää yhtä asiaa:
   30 minuutin kävely kolme kertaa"). Tästä syntyy jatkuva kierros: tavoite, teko, palaute, mukautus ja uusi teko.
4. **Huomaa, milloin omahoito ei enää riitä:** agentti seuraa samalla, jatketaanko omahoitoa, muutetaanko suunnitelmaa
   vai tarvitaanko ammattilaista. Kun ammattilaista tarvitaan, agentti tekee **hoidon tarpeen ja kiireellisyyden arvion
   automaattisesti sääntöjen perusteella** ja ohjaa tilanteen vastuuammattilaiselle.

Ammattilainen päättää hoidosta, vahvistaa tai muuttaa automaattiset arviot ja valvoo niitä. Asiakkaalla on aina oikeus
ammattilaisen tekemään arvioon. Kaikki päätökset tulevat säännöistä; kielimalli ei tee päätöksiä. Perimätieto on
vapaaehtoinen lisätietolähde, ei käytön edellytys.

> Hyvinvointikumppani tekee hoidon tarpeen ja kiireellisyyden arvion automaattisesti sääntöjen perusteella; ammattilainen päättää hoidosta ja valvoo arvioita, ja asiakkaalla on aina oikeus ammattilaisen tekemään arvioon.

Kaikki henkilöt ja tiedot ovat **synteettisiä** (demohenkilö **Aino Demo, 46 v**).

Sovellus tekee hoidon tarpeen ja kiireellisyyden arvion automaattisesti sääntöjen perusteella (ennakoi terveydenhuoltolain 51 §:n muutosta, oletettu voimaantulo 2027). Se ei tee diagnooseja, ei muuta hoitoa tai lääkitystä eikä esitä riskiprosentteja; hoitopäätökset tekee ammattilainen, ja ammattilaisen arvion voi aina pyytää.

Automaattinen arvio ennakoi lakimuutosta, jota ei ole vielä säädetty: *terveydenhuoltolaki 51 § 3 mom. (digitaalinen hoidon tarpeen arvio) – prototyyppi olettaa lakimuutoksen voimaan 2027*. Oikeusperuste on siis
**oletus** – ks. [Lakimuutos: automaattinen hoidon tarpeen arvio (oletus)](#lakimuutos-automaattinen-hoidon-tarpeen-arvio-oletus).

👉 Täydellinen kuvaus, arkkitehtuuri, turvallisuusmalli, rajaukset ja demopolku: **[HACKATHON_DEMO.md](HACKATHON_DEMO.md)**
👉 LUVN-tyyppisen CSV/JSON-datan adapterit ja oletusskeema: **[docs/LUVN_ADAPTER.md](docs/LUVN_ADAPTER.md)**

## Omahoidon jatkuvuuden moottori

| Ydintehtävä | Miten se toimii (säännöt ja tekstipohjat, ei kielimallin päätöksiä) |
|---|---|
| 1 Muistaa puolestasi | *Muistan puolestasi* kokoaa kuusi asiaa: **tavoitteet** (suunnitelman tavoitetaso ja askel), **sovitut asiat** (hyväksyntä, ammattilaisen ohjeet ja ammattilaisten kirjauksista sääntöjen perusteella poimitut sovitut asiat, esim. "Omahoidon tavoitteeksi sovittiin kaksi 30 minuutin kävelyä viikossa", hoitaja 20.8.2026), **mitä seuraat** (kotimittaukset, LDL-kontrolli, käynnissä oleva kotiseuranta), **mitä olet jo kokeillut** (viikkokierrosten askeleet ja palaute, kotiseurannat, aiemmat ohjaukset kirjauksista), **mikä toimii** (onnistuneet askeleet, esim. "LDL-arvo laskenut ruokavaliomuutosten jälkeen", ja haasteet, kuten työn kiire) sekä **milloin tarkistetaan uudelleen**. Kirjausten poimintasäännöt ovat policyssa (`continuity.noteRules`). Perimätietoa, lääkitystä ja diagnooseja ei poimita, ja kirjauksia luetaan vain suostumuksella. |
| 2 Ottaa itse yhteyttä | Viikkotarkistukset, muistutukset ja yhteydenottosääntö **OUT-BP-001**: kun kotimittausten keskiarvo nousee (signaali SIG-BP-TREND), agentti ehdottaa itse kolmen päivän kotiseurantaa aamulla ja illalla. Käyttäjä päättää (*Kyllä, aloitetaan* / *Ei tällä viikolla*). Ehdotus vanhenee viikossa, eikä sitä toisteta 14 päivään. Portti 3 pätee: yhteydenottokielto, viikkoraja ja hiljaiset ajat. |
| 3 Yksi askel kerrallaan | Suunnitelman tavoite on seitsemän päivän askel ("30 minuutin kävely kaksi kertaa"). Viikkotarkistus kysyy, miten askel sujui: onnistunut askel kasvaa hieman (enintään ammattilaisen asettamaan ylärajaan), osittain onnistunut jatkuu samana ja toteutumaton pienenee esteen mukaan. Kierros *tavoite → teko → palaute → mukautus → uusi teko* ja aiemmat kierrokset näkyvät. |
| 4 Huomaa, milloin omahoito ei riitä | Suunta jokaiselle seurannalle: **Jatketaan omahoitoa**, **Muutetaan suunnitelmaa** (askel ei toteutunut, mittausten taso nousi, kotiseurannan keskiarvo tavoitetason yläpuolella) tai **Tarvitaan ammattilaista** (ohjaussääntö täyttyi, esim. ESC-BP-001 tai ESC-BP-004, jolloin kotiseurannan keskiarvo on vähintään 145/90 mmHg). Lisäksi näkyy *Seuraan samalla* -lista ja se, milloin agentti ottaa ammattilaisen mukaan. |

Koodi: `backend/app/support/continuity.py` (muisti, yhteydenotot, askel ja suunta), `interventions.py` (askeleen
mukautus), `cycle.py` (yhteydenottosääntö agenttisyklissä ja uuden mittauksen havainnoinnissa). Käyttöliittymä:
`frontend/src/support/ContinuityPanel.tsx`. Chatissa kysymykset *Mitä olemme sopineet?*, *Mikä on seuraava askel?*,
*Mitä olen jo kokeillut?* ja *Riittääkö omahoito?* tunnistetaan säännöillä ja vastataan samoista tiedoista.

**API:** `POST /api/support/home-monitoring/{id}/respond` `{accept}` (asiakas) ja `POST /api/support/simulate/home-monitoring`
(demo). Lukumalli on `/api/loop/state` → `support.continuity`.

## Hyvinvointidata (Apple Health)

Apple Health on yksi lisätietolähde samalle hyvinvointikumppanille, ei erillinen tuote:
*perimätieto + terveystiedot + Apple Healthin pitkittäisdata + keskustelu → henkilökohtainen konteksti → agentti*.

- **Välilehti Hyvinvointidata** (Terveystiedot-välilehden jälkeen) koostuu seuraavista osista:
  - yhteyden tila ja viimeisin synkronointi
  - *Havainnot seurannastasi*: muutos, *Miksi näen tämän?* ja *Selvitetään yhdessä*
  - *Seurannassa*: seuranta-alueet
  - *Tänään*
  - *Trendit*: 7 pv, 30 pv, 3 kk ja 12 kk, oma taso katkoviivana
  - *Merkittävät muutokset*
  - *Mitä hyvinvointikumppani saa tietää*: tiivis konteksti
- **Arkkitehtuuri:** selain ei pääse HealthKitiin. Pieni iOS-silta (`ios/HyvinvointiBridge`, SwiftUI ja HealthKit, vain
  lukuoikeus) yhdistetään web-sovelluksen kertakäyttöisellä koodilla. Silta lähettää päivittäiset yhteenvedot osoitteeseen
  `POST /api/health/sync` omalla laitetunnisteellaan. Henkilö päätellään tunnisteesta, ei pyynnön sisällöstä.
- **Tietomalli:** tallennetaan yksi päivittäinen yhteenveto lähdettä ja päivää kohden, ei raakanäytteitä. Mittarit ovat
  askeleet, uni, leposyke, HRV, aktiivinen energia, liikuntasuoritukset, paino ja VO2 max. Tallennus on idempotentti ja
  säilyttää alkuperätiedon (lähde, laite, synkronointiaika, yksiköt katalogissa). Myöhemmät mittarit (verenpaine,
  hengitystiheys, happisaturaatio, kävelysyke, verensokeri, lämpötila, kuukautiskierto) kulkevat kentässä `extra`.
- **Henkilökohtainen perustaso:** nykytasoa (7 päivää) verrataan omaan 90 päivän tasoon ennen viimeisintä kuukautta.
  Funktiot ovat `calculate_personal_baseline`, `calculate_rolling_average`, `calculate_trend` ja
  `detect_meaningful_change`. Kynnykset ovat demo-policyja (`wellbeingData.metrics[].change`), eivät johtopäätöksiä.
- **Seurantalista:** agentti ottaa itse yhteyttä vain aktiivisen seuranta-alueen muutoksista. Alueet ovat käyttäjän
  valitsemia (esim. *Palautuminen*: leposyke, HRV ja uni) tai ammattilaisen hyväksymien suunnitelmien alueita
  (*Verenpaine*, *Kolesteroli*). Havainto nostetaan esiin harvoin (viilentymisaika), perustellusti ja rauhallisesti.
  Portti 3 pätee: suostumus, viikkoraja ja hiljaiset ajat.
- **Agentin konteksti:** `build_user_context()` saa lohkon `wellbeingData`. Siinä on nykytaso, oma perustaso ja muutokset
  absoluuttisina yksikköinä, seuranta-alueet ja käsiteltävä havainto, ei historiaa. Lohko jää pois, jos yhteyttä ei ole
  tai käyttäjä on estänyt tietolähteen Suostumuksissa.
- **Keskustelu:** *Selvitetään yhdessä* avaa chatin. Viestissä data (luvut), tulkinta ("syitä voi olla monta, data ei kerro
  syytä") ja seuraava askel ovat erillään: mahdolliset syyt → hyväksytty ohje ja viikon seuranta, tai *Haluan
  ammattilaisen arvion*. Oireet ohjautuvat edelleen olemassa olevaan hoidon tarpeen arvioon.
- **Tietosuoja:** vain luku ja mittarikohtaiset valinnat. Pois valittu mittari poistetaan myös tallennetuista tiedoista.
  Yhteyden voi katkaista ja tuodut tiedot poistaa. Terveysarvoja ei kirjata lokeihin eikä audit-lokiin, ja
  laitetunnisteesta ja yhdistämiskoodista tallennetaan vain tiiviste.
- **Demo:** *Käytä synteettistä testidataa* lataa 12 kuukautta selvästi merkittyä synteettistä dataa (lähde
  `synthetic_demo`, ei koskaan "oikeaa Apple Health -dataa"). Yhdeksän kuukautta on vakaata, ja kahden viimeisen kuukauden
  aikana aktiivisuus ja uni vähenevät, leposyke nousee ja HRV laskee. Painike näkyy vain demo- ja kehitystilassa
  (`HEALTH_DEMO_MODE=1`).

**API:** `GET /api/health/summary?period=7|30|90|365`, `POST /api/health/pairing-code`, `POST /api/health/devices/pair`,
`POST /api/health/sync` (Bearer-laitetunniste), `POST /api/health/sync-now`, `POST /api/health/demo/synthetic`,
`PUT /api/health/permissions`, `PUT /api/health/monitoring`, `POST /api/health/disconnect`, `DELETE /api/health/data`,
`POST /api/health/observations/{id}/discuss` ja `…/dismiss`. Koodi: `backend/app/wellbeing/`,
`frontend/src/wellbeing/`, `ios/HyvinvointiBridge/`.

## Käynnistys

Vaatimukset: Python 3.12+ (demo toimii myös 3.9:llä ilman valinnaista LLM-integraatiota), Node.js 20+ ja npm.

```bash
# kerran: riippuvuudet
python3 -m venv backend/.venv && backend/.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend install

# macOS / Linux
./start-macos.sh            # frontend http://localhost:5180, backend http://localhost:8002
```

Windows (PowerShell): `start.ps1` (backend 8000, frontend 5173). Porttien vaihto macOS:llä:
`BACKEND_PORT=8010 FRONTEND_PORT=5190 ./start-macos.sh`. Skripti ohittaa `frontend/.env.local`-tiedoston
`VITE_API_BASE`-arvon ja sallii frontendin osoitteen backendin CORS-asetuksissa.

Käsin:

```bash
ALLOWED_ORIGINS=http://localhost:5180 backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8002
VITE_API_BASE=http://localhost:8002 npm --prefix frontend run dev -- --port 5180
```

Valinnainen Claude-integraatio (tekstien muotoilu, tiivistelmäluonnokset, vapaan tekstin jäsennys – ei päätöksiä):
`LOOP_LLM_PROVIDER=anthropic` ja `ANTHROPIC_API_KEY` ympäristössä tai `.env`-tiedostossa. Jos kutsu epäonnistuu tai
teksti ei läpäise turvatarkistusta, käytetään valmiita tekstipohjia. **Kielimalli ei koskaan aseta
kiireellisyysluokkaa:** hoidon tarpeen arvion tekee sääntömoottori, ja kielimalli saa korkeintaan muotoilla tekstin,
jossa luokka toistetaan sellaisenaan. **Demo toimii kokonaan ilman kielimallia.**

## Demo 3–5 minuutissa

Asiakkaan välilehdet ovat järjestyksessä **Perimätieto → Terveystiedot → Hyvinvointidata → Hyvinvointikumppani →
Suostumukset → Tilanne nyt → Agentin toiminta**, ja jokaisen näkymän lopussa on linkki seuraavaan. Rooli vaihdetaan yläkulman valinnalla
**Asiakas / Ammattilainen**. Demo-ohjaus-paneeli (Tilanne nyt) näyttää demon kulun vaihe vaiheelta ja merkitsee tehdyt
vaiheet; **Palauta demo alkutilaan** aloittaa alusta.

1. **Perimätieto:** portti 1 yhdellä silmäyksellä – yksi ammattilaisen hyväksymä taustatieto, kaksi suodatettua
   havaintoa, ei geenien nimiä. Oma DNA-analyysi on valinnainen.
2. **Terveystiedot:** LUVN-tyyppisistä lähteistä adaptereilla luetut terveydenhuollon kirjaukset kansallisen
   terveystietonäkymän tapaan, uusin ensin: tekstimerkinnät (käynti ja sen kirjaukset yhtenä merkintänä),
   laboratoriotutkimukset (esim. *B -Perusverenkuva, minidiff, vieritutkimus*, 17 tulosta, ja *Lipidit*, 7 tulosta, avautuvat
   taulukoksi viitearvoineen), mittaukset, diagnoosit ja lääkitys. Omia ilmoituksia ja kotimittauksia ei listata. Mitään ei
   kirjata uudelleen. **Linkitä DNA-analyysiin** yhdistää terveystiedot ja DNA-analyysin havainnot aiheittain
   sääntöjen perusteella: esimerkiksi *Kohonnut kolesteroli* kokoaa diagnoosin E78.0, kaikki lipiditutkimukset vuodesta 2014 ja
   käynnit kirjauksineen sekä niihin liittyvät perimätiedon havainnot. Terveyshistoria ulottuu vuoteen 2008. Vain ammattilaisen hyväksymä havainto on
   käytössä seurannan taustatietona, geenien nimet näkyvät vain suostumuksella, eikä linkitys muuta seurantaa.
3. **Suostumukset:** portti 3 – tietolähteet, oma-aloitteiset yhteydenotot, hiljaiset ajat, kanava, perimätiedon
   yksityiskohdat, tauko sekä nimenomainen suostumus automaattiseen hoidon tarpeen arvioon ja kuvaus *Näin
   automaattinen hoidon tarpeen arvio toimii*.
4. **Tilanne nyt:** tilanne ja seuraava askel ensin. Avaa kolesteroliteemasta *Miksi tätä seurataan?*: lähteet,
   hyväksyjä ja mitä agentti saa tai ei saa tehdä.
5. **Ammattilainen → Työjono:** *Verenpaineen omaseuranta* odottaa hyväksyntää. Suunnitelma lyhyesti, sitten
   **Hyväksy suunnitelma → Vahvista**.
6. **Asiakas → Hyvinvointikumppani:** hyväksyntäviesti antaa ensimmäisen askeleen ("Kokeillaan seuraavat 7 päivää yhtä
   asiaa: 30 minuutin kävely kaksi kertaa"). *Omahoidon jatkuvuus* -paneelin kortti **1 Muistan puolestasi** näyttää
   tavoitteet, sovitut asiat, seurattavat asiat, kokeillut asiat, toimivat asiat ja tarkistuspäivät. Kortti **3 Yksi askel
   kerrallaan** näyttää kierroksen *tavoite → teko → palaute → mukautus → uusi teko*.
7. **Tilanne nyt → Simuloi seuraava viikko:** agentti aloittaa itse viikkotarkistuksen: "Kokeilimme seitsemän päivää
   yhtä asiaa… Miten se sujui?" Vastaa *Ei tällä kertaa → Aika tai kiire → Sopii* (myös chatissa): askel pienenee
   hoitajan rajoissa, ja suunta on **Muutetaan suunnitelmaa**.
8. **Lisää uusi mittaus** kahdesti: agentti huomaa nousun ja **ottaa itse yhteyttä** (OUT-BP-001): "Verenpaineesi on
   ollut viime viikkoina hieman aiempaa korkeampi… Haluaisitko tehdä tällä viikolla kolmen päivän kotiseurannan?"
   Valitse **Kyllä, aloitetaan** chatissa, paneelissa tai Tilanne nyt -näkymässä ja sitten **Simuloi kotiseuranta
   (3 pv)**. Yhteenveto: keskiarvo 140/89 mmHg on hieman tavoitetason yläpuolella, joten suunnitelmaa mukautetaan.
9. **Simuloi seuraava viikko** → vastaa taas *Ei tällä kertaa*. Omahoito ei enää riitä: sääntö ESC-BP-001 täyttyy, ja
   agentti tekee automaattisen hoidon tarpeen arvion **Kiireetön** (hoitajan yhteydenotto 5 arkipäivän kuluessa) ja
   ohjaa tilanteen hoitajalle. Suunta on **Tarvitaan ammattilaista**. Aino saa rauhallisen viestin ja painikkeen
   **Pyydä ammattilaisen arvio**; *Tilanne nyt* näyttää arviokortin, jonka perustelut ovat kohdassa *Näin arvio tehtiin*.
10. **Ammattilainen → Työjono:** ryhmissä *Automaattiset arviot (valvonta)* ja *Eskaloidut* näkyy automaattinen arvio
    ja ohjaus – syy, muutos, aikajana, sääntö ja vastaukset. Valitse **Vahvista arvio** (tai *Muuta
    kiireellisyysluokkaa* / *Tee arvio itse (ammattihenkilön arvio)*). **Muokkaa suunnitelmaa** (kysymys *Oliko
    automaattinen kiireellisyysarvio oikea?*) tai *Simuloi ammattilaisen päätös* nostaa suunnitelman versioon 2.
11. **Asiakas:** uusi ohje näkyy seuraavana askeleena, ja suunta on taas **Jatketaan omahoitoa**. **Simuloi seuraava
    viikko:** agentti kysyy version 2 askeleesta.
12. **Agentin toiminta** (toimintaketjut, mukana agentin oma yhteydenotto ja vaihe *Automaattinen arvio*, sekä
    audit-loki) ja **Ammattilainen → Vaikuttavuus** (simuloitu demo- ja kohorttidata).

Valinnaiset lisänäytöt:

- **Hyvinvointidata:** *Yhdistä Apple Health* näyttää iPhone-sillan yhdistämiskoodin. Demossa valitse *Käytä synteettistä
  testidataa*. Havainto *Huomasin muutoksen* (palautuminen: leposyke 47 → 53 bpm, HRV −9 ms, uni −36 min/yö) on *Miksi näen
  tämän?* -perusteluineen välilehdellä ja agentin omana viestinä chatissa. *Selvitetään yhdessä* → *Käydään läpi mahdollisia
  syitä* → *Olen nukkunut huonommin* → hyväksytty ohje ja viikon seuranta. Trendit näkyvät 7 päivältä, 30 päivältä,
  3 kuukaudelta ja 12 kuukaudelta. *Mitä hyvinvointikumppani saa tietää* näyttää kontekstin.
- **Kuvaa oireesi chatissa → automaattinen arvio → Pyydä ammattilaisen arvio** (tai Demo-ohjaus → *Simuloi
  oirekuvaus chatissa*): "Minulla on ollut pari päivää päänsärkyä ja huimausta, pitäisikö mennä lääkäriin?" → sääntö
  TRI-BP-003, automaattinen arvio *Kiirevastaanotto 3 arkipäivän kuluessa*, tieto välittyy hoitajalle →
  **Pyydä ammattilaisen arvio**.
- **Hätäoire** (esim. "minulla on rintakipua"): kiinteä ohje soittaa hätänumeroon 112 ilman kielimallia. Hätätilanne ei
  kuulu automaattisen arvion piiriin; tapaus kirjataan, mutta *Pyydä ammattilaisen arvio* -painiketta ei tarjota.
- **Kirjaa mittaus 186/112:** automaattinen arvio *Kiireellinen – samana päivänä* ja ennalta määritelty turvaviesti
  (hätänumero 112 mainitaan aina).
- **Suostumus pois:** kytke automaattinen arvio pois Suostumuksissa ja kuvaa oire uudelleen → *Esiarvio – ammattilainen
  tekee arvion*, joka ohjautuu aina ammattilaiselle.
- **Pyydä ammattilaisen arvio → Ammattilainen → Työjono:** pyyntö näkyy ryhmässä *Automaattiset arviot (valvonta)*
  merkinnällä *Asiakas pyysi ammattilaisen tekemän arvion*.

Tarkempi käsikirjoitus lisänäyttöineen: [HACKATHON_DEMO.md](HACKATHON_DEMO.md#7-demotapaus-vaihe-vaiheelta-35-minuuttia).

## Näkymät

| Rooli | Näkymä | Sisältö |
|---|---|---|
| Asiakas | Perimätieto | Portti 1 yhdellä silmäyksellä: hyväksytty, arviota odottava ja suodatettu. Vapaaehtoinen oma DNA-analyysi, jonka raportissa on *Pyydä ammattilaisen arvio* |
| Asiakas | Terveystiedot | Kaikki lähteet yhdellä aikajanalla lähteen ja suostumustilan kanssa. Vapaaehtoinen laaja elämäntapakysely |
| Asiakas | Suostumukset | Tietolähteet, yhteydenotot, raja, hiljaiset ajat, kanava, perimätiedon yksityiskohdat, tauko. Nimenomainen suostumus automaattiseen hoidon tarpeen arvioon ja kuvaus *Näin automaattinen hoidon tarpeen arvio toimii* (oikeusperuste, periaatteet, kiireellisyysluokat, vastuuhenkilö) |
| Asiakas | Tilanne nyt | Tilanne, seuraava askel (mukana agentin ehdotus ja käynnissä oleva kotiseuranta), *Omahoidon jatkuvuus* lyhyesti (suunta ja tämän viikon askel), automaattisen arvion kortti (*Näin arvio tehtiin*, *Pyydä ammattilaisen arvio*), check-in, seurantateemat (2-tasoinen), edistyminen, kotimittauksen kirjaus, demo-ohjaus |
| Asiakas | Hyvinvointidata | Apple Health -yhteys, havainnot seuranta-alueilta (*Miksi näen tämän?*, *Selvitetään yhdessä*), seurantalista, tänään, trendit (7 pv – 12 kk) oman tason kanssa, merkittävät muutokset, tiedon hallinta (mittarit, katkaisu, poisto) ja agentille annettava tiivis konteksti |
| Asiakas | Hyvinvointikumppani | Chat ja *Omahoidon jatkuvuus* -paneelin neljä ydintehtävää: *Muistan puolestasi*, *Otan itse yhteyttä* (ehdotukset ja tulevat yhteydenotot), *Yksi askel kerrallaan* (kierros ja aiemmat kierrokset) ja *Huomaan, milloin omahoito ei riitä* (suunta, *Seuraan samalla*, milloin ammattilainen otetaan mukaan). Agentin omat viestit, check-in-kysymykset ja automaattiset arviot tulevat myös tänne; oireen voi kuvata ja ammattilaisen arvion pyytää |
| Molemmat | Agentin toiminta | Toimintaketjut (7 vaihetta, mukana *Automaattinen arvio*) ja audit-loki |
| Ammattilainen | Työjono | Hyväksynnät, eskalaatiot (automaattinen arvio ja ohjaus), *Automaattiset arviot (valvonta)* pyydettyine ammattilaisarvioineen, arvioinnit, perimätiedon arviopyynnöt, suodatetut havainnot, synteettinen asiakaslista |
| Ammattilainen | Vaikuttavuus | Demotapauksen mittarit (automaattiset arviot, vahvistetut ja muutetut, pyydetyt ammattilaisen arviot) ja 50 000 hengen synteettinen pilottikohortti |

## Rakenne

- `backend/app/support/` – seurantasuunnitelmat, portit 1–3, agenttisykli, mikrointerventiot, omahoidon jatkuvuuden
  moottori (`continuity.py`: muisti, oma-aloitteinen kotiseurantaehdotus, askel ja suunta), automaattinen hoidon
  tarpeen arvio (`assessment.py`: kiireellisyysluokat, oireluokittelu, ammattilaisen arvion pyyntö ja valvonta),
  eskalaatio, ammattilaisen päätökset, audit, vaikuttavuus, adapterit (`adapters/`), API `/api/support/*`
- `backend/app/loop/` – perimätiedon sääntömoottori, huomiot, Hyvinvointikumppani-chat, valinnainen LLM, API `/api/loop/*`
- `backend/app/services/` – DNA-analyysin putki
- `frontend/src/support/` – asiakkaan ja ammattilaisen näkymät (mm. `ContinuityPanel`, `AssessmentCard`,
  `AutomationNotice`, `professional/AssessmentReview`) · `frontend/src/loop/` – chat, aikajana, huomiot, kysely
- `data/luvn/aino/` – synteettiset LUVN-tyyppiset lähdetiedostot · `data/support/` – demo-policyt (mukana
  `automation`-lohko: kiireellisyysluokat, oiresäännöt, valvontaotanta; `continuity`-lohko: ydintehtävät, suunnat ja
  kirjausten poimintasäännöt; teemojen `outreachRules`) ja demotapaus ·
  `data/loop/` – perimätiedon synteettinen evidenssi · `data/demo/` – synteettinen DNA-aineisto
- `runtime/` – paikallinen tila (demotila, DNA-istunnot, synteettinen kohortti; luodaan automaattisesti)
- `scripts/` – synteettisen DNA-aineiston ja kohortin generointi

## Testit ja build

```bash
cd backend && .venv/bin/python -m pytest -q
cd frontend && npx tsc --noEmit -p . && npm run build
```

Backend-testit kattavat tilakoneen, portit, adapterit, agenttisyklin, eskalaation, ammattilaisen päätökset,
suostumukset, auditin ja LLM-rajauksen sekä automaattisen hoidon tarpeen arvion: kiireellisyysluokat, oirekuvauksen
luokittelu, ammattilaisen arvion pyyntö ja valvonta, suostumuksen puuttuminen (esiarvio), hätätilanteen rajaus ja se,
ettei kielimalli voi muuttaa luokkaa. `test_continuity.py` kattaa omahoidon jatkuvuuden moottorin: muistin kirjauksista
ja suunnitelmista (myös suostumuksen rajaus), askeleen kasvattamisen ja pienentämisen ammattilaisen rajoissa,
oma-aloitteisen kotiseurantaehdotuksen (portti 3, vanheneminen, kieltäytyminen), kotiseurannan yhteenvedon ja
ESC-BP-004-ohjauksen, suunnan koko demopolulla sekä chatin vastaukset. Projektissa ei ole lint-konfiguraatiota. Laadunvarmistus tehdään
tyyppitarkistuksella, testeillä ja buildilla.

## Lakimuutos: automaattinen hoidon tarpeen arvio (oletus)

> **Oikeusperuste on oletus, ei voimassa olevaa lakia.** Proto rakentuu sosiaali- ja terveysministeriön luonnokseen
> "Hallituksen esitys eduskunnalle laiksi terveydenhuoltolain 51 §:n muuttamisesta (digitaalinen hoidon tarpeen arvio)", STM011:00/2026, lausuntokierros 4.5.–15.6.2026. Esityksellä ei ole vielä HE-numeroa eikä vahvistettua voimaantulopäivää.
> Sovelluksessa ja dokumentaatiossa lakiin viitataan aina muodossa:
> *terveydenhuoltolaki 51 § 3 mom. (digitaalinen hoidon tarpeen arvio) – prototyyppi olettaa lakimuutoksen voimaan 2027*.

Ehdotetun 51 §:n 3 momentin mukaan hyvinvointialue voisi käyttää automaatiota hoidon tarpeen ja kiireellisyyden
arvioinnissa tietyin edellytyksin. Hoitopäätökset tekee edelleen ammattilainen, ja diagnoosit, lääkitys ja hoito
kuuluvat laillistetuille ammattihenkilöille (ammattihenkilölaki 22 §, 23 a §). Näin proto toteuttaa edellytykset:

| Edellytys (luonnos STM011:00/2026, ehdotettu 51 § 3 mom.) | Toteutus tässä protossa |
|---|---|
| **Nimenomainen suostumus** selkeän ja ymmärrettävän tiedon perusteella | *Suostumukset*-näkymässä oma valinta "Hyväksyn, että hoidon tarpeen ja kiireellisyyden arvio tehdään automaattisesti" ja kuvaus *Näin automaattinen hoidon tarpeen arvio toimii*. Tila `ConsentSettings.automatedAssessment`, tiedonantopäivä `automatedAssessmentInformedAt`; demossa suostumus on annettu hoitajan vastaanotolla 20.8.2026 (synteettinen kirjaus SUO-03). Ilman suostumusta arvio on vain **esiarvio** (`mode: professional_required`), ja ammattilainen tekee arvion. Suostumuksen antaminen ja peruminen kirjataan audit-lokiin. |
| **Oikeus terveydenhuollon ammattihenkilön arvioon** aina | Jokaisen arvion yhteydessä lause "Sinulla on aina oikeus terveydenhuollon ammattihenkilön tekemään arvioon." ja painike **Pyydä ammattilaisen arvio** (*Tilanne nyt* ja chat; chatissa myös omin sanoin). `POST /api/support/assessments/{id}/request-human-review` → tila `human_review_requested`: avoimeen ohjaukseen merkitään pyyntö, tai suunnitelman `user_request`-sääntö luo ohjauksen (ei toista arviota). Pyyntö näkyy ammattilaisen työjonossa omana merkintänään. |
| **Lääketieteellisesti hyväksyttävät kriteerit** | Arvion tekee sääntömoottori dokumentoiduista säännöistä: oiretaulukko `TRI-*`, kontekstisäännöt `TRI-CTX-*` (voivat vain nostaa luokkaa), suunnitelman ohjaussäännöt `ESC-*` ja ammattilaisen asettama turvaraja (`data/support/policies.json`, lohko `automation`). Viisi kiireellisyysluokkaa lakisääteisellä sanastolla (hätätilanne, kiireellinen, kiireetön), THL:n PTHAVO-tulosluokkia mukaillen. **Demossa kriteerit ovat synteettisiä demo-policyja, eivät kliinisesti validoituja.** |
| **Laadunvarmistus ennen käyttöönottoa ja seuranta** | Ennen: automaattiset testit (deterministinen luokittelu, jokainen arvion tekstipohja läpäisee turvatarkistuksen omalla luokallaan, kielimalli ei voi muuttaa luokkaa). Käytössä: ammattilaisen työjonon ryhmä *Automaattiset arviot (valvonta)* – jokainen ohjaukseen johtanut arvio vahvistetaan tai muutetaan (**Vahvista arvio**, **Muuta kiireellisyysluokkaa**, **Tee arvio itse (ammattihenkilön arvio)**), ja ilman ohjausta jääneistä arvioista 20 % nostetaan valvontaan deterministisellä otannalla. Ohjauksen ratkaisussa kysytään "Oliko automaattinen kiireellisyysarvio oikea?". *Vaikuttavuus* näyttää vahvistetut ja muutetut arviot. |
| **Riskienhallinta** (turvallisuus, oikeusturva, yhdenvertaisuus) | Säännöt ratkaisevat; kielimalli ei koskaan aseta kiireellisyysluokkaa. Sen tekstit tarkistetaan (`check_text(..., allowed_urgency=…)`), ja niiden on toistettava luokka sellaisenaan – muuten käytetään tekstipohjaa. Turvaraja- ja hätäviestit ovat kiinteitä. Jokainen arvio perusteluineen, sääntöineen ja ammattilaisen päätöksineen kirjataan audit-lokiin (vaihe *Hoidon tarpeen arvio (automaattinen)*). Yhdenvertaisuuden arviointi (kieliversiot, saavutettavuus, digituki) on tekemättä. |
| **Vastuuhenkilö** nimetty | `automation.responsiblePerson`: "Vastuuhenkilö: vastaava ylilääkäri (synteettinen demohenkilö)". Näkyy arviokortissa ja toimintaperiaatteiden kuvauksessa. |
| **Julkaistu kuvaus automaation toimintaperiaatteista** | *Näin automaattinen hoidon tarpeen arvio toimii* (Suostumukset, linkki arviokortista): oikeusperuste oletukseksi merkittynä, periaatteet, kiireellisyysluokat, mikä jää ammattilaiselle, vastuuhenkilö ja sääntöversio (`demo-1`). Jokaisen arvion kohdalla *Näin arvio tehtiin* (peruste, käytetyt tiedot, säännöt, lakiviite). |
| **Hätätilanteiden rajaus** | Hätätilanteeseen viittaavat oireet (`TRI-EMERG-001`) eivät kuulu automaattisen arvion piiriin: kiinteä ohje soittaa hätänumeroon 112 (tai Päivystysapuun 116 117), ei kielimallia eikä *Pyydä ammattilaisen arvio* -painiketta. Tapaus kirjataan (`mode: excluded_emergency`). |
| **Hoitopäätökset ammattilaisella** | Arvio ratkaisee vain yhteydenoton ja sen kiireellisyyden. Diagnoosit, hoitopäätökset (`treatment_decision`), lääkitys ja kliiniset raja-arvot ovat kiellettyjä agentin toimia, joita ammattilainenkaan ei voi sallia. Suunnitelmaa muuttavat vain ammattilaisen päätökset. |

**Kiireellisyysluokat** (`automation.urgencyClasses`; THL:n PTHAVO-tulosluokkia mukaillen, käsittelyajat ovat demo-policyja):

| Luokka | Hoidon tarve | Käsittely |
|---|---|---|
| Hätätilanne | Soita hätänumeroon 112 (ei automaattisen arvion piirissä) | heti |
| Kiireellinen – samana päivänä | Yhteys terveysasemalle tänään, virka-ajan ulkopuolella Päivystysapu 116 117 | samana päivänä |
| Kiirevastaanotto 3 arkipäivän kuluessa | Aika akuutti- tai kiirevastaanotolle 3 arkipäivän kuluessa | 3 arkipäivän kuluessa |
| Kiireetön | Hoitajan yhteydenotto 5 arkipäivän kuluessa | 5 arkipäivän kuluessa |
| Omahoito riittää | Jatka omahoitoa suunnitelman mukaan; uusi arvio, jos tilanne muuttuu | ei yhteydenottoa |

**Mistä arvio syntyy:** suunnitelman ohjaussääntö (esim. ESC-BP-001 → *Kiireetön*), turvarajan ylitys (ESC-BP-002 →
*Kiireellinen – samana päivänä*, kiinteä viesti), asiakkaan pyyntö (ESC-USER-001 / ESC-GEN-USER → *Kiirevastaanotto 3
arkipäivän kuluessa*) tai oirekuvaus chatissa (oiretaulukko TRI-EMERG-001, TRI-BP-002, TRI-BP-003, TRI-GEN-004 ja
oletuksena TRI-SELF-005; kontekstisäännöt TRI-CTX-BP-SAFETY ja TRI-CTX-BP-ABOVE voivat vain nostaa luokkaa).
Koodi: `backend/app/support/assessment.py`.

**API:** `POST /api/support/assessments/{id}/request-human-review` (asiakas),
`POST /api/support/assessments/{id}/review` `{decision: confirm | change_urgency | take_over, role, note?, newUrgency?}`
(ammattilainen), `POST /api/support/simulate/symptom-report` (demo) ja `PUT /api/support/consent`
`{automatedAssessment}`.

Avoimet kysymykset (ei HE-numeroa, ei vahvistettua voimaantulopäivää, luonnos voi muuttua, soveltamisala
perusterveydenhuolto, alaikäiset): [HACKATHON_DEMO.md, luku 12](HACKATHON_DEMO.md#12-lakimuutoksen-huomiointi).

## DNA-analyysi (vapaaehtoinen lisätietolähde)

Käyttöliittymä tukee DNA-tekstin liittämistä, tiedoston lähetystä, pikademoa ja synteettistä 100k-aineistoa. Analyysi
tehdään paikallisesti, eikä raakaa DNA:ta lähetetä pilveen tai kielimallille.

Paikallisen ClinVar VCF:n käyttö ensisijaisena vertailulähteenä (tavallinen `.vcf` tai `.vcf.gz`):

```bash
CLINVAR_VCF_PATH=/polku/clinvar.vcf.gz OMAGENOMI_MODE=clinvar backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8002
```

Synteettisen 100k-aineiston uudelleenluonti: `python scripts/generate_full_demo.py`.
Synteettisen kohortin uudelleenluonti: `backend/.venv/bin/python scripts/generate_synthetic_cohort.py --size 50000`.

## Huomiot

- Tutkimus- ja demokäyttöön. Ei diagnoosi eikä lääkinnällinen laite.
- Automaattinen hoidon tarpeen arvio perustuu oletukseen lakimuutoksesta: *terveydenhuoltolaki 51 § 3 mom. (digitaalinen hoidon tarpeen arvio) – prototyyppi olettaa lakimuutoksen voimaan 2027*. Laki ei ole voimassa, ja luonnos
  (STM011:00/2026) voi muuttua; demo-policyn säännöt eivät ole hoitosuosituksia eivätkä kliinisesti validoitu hoidon
  tarpeen arviointi.
- Oikeita LUVN- tai potilastietojärjestelmäintegraatioita ei ole – ne on mallinnettu adaptereilla ja synteettisellä datalla.
