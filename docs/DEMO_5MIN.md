# Mieliluotsi – 5 minuutin demo

Koko demo etenee yhdellä näppäimellä. Paina **→** tai yläpalkin **Seuraava**. Jokainen painallus tekee seuraavan
vaiheen oikeassa näkymässä: se syöttää demotekstin, painaa oikeaa painiketta, avaa oikean välilehden ja korostaa
kohdan, josta puhutaan.

Yläpalkin vaihenumero (esim. 5/24) kertoo, missä kohtaa demoa ollaan. Kun viet hiiren numeron päälle, näet, mitä
ruudulla nyt on. Seuraava-painikkeen päällä näet, mitä seuraava painallus tekee. Vaiherivi noudattaa konseptin
runkoa:
avun haku → AI-alkukeskustelu → Mieliluotsi (KKT, seuranta ja muutosten tunnistus, Therapy Fit Profile) → sopivin
terapeutti ja handover → terapia ja välitehtävät → seuranta terapian jälkeen.

## Ennen demoa

1. **Käynnistä v4 ja tarkista, että selaimessa on v4.** Koneella voi pyöriä myös vanha Terapiabotti (portit 5195/8020)
   ja v3 (5198/8032).
   `BACKEND_PORT=8034 FRONTEND_PORT=5200 ./start-macos.sh` → http://127.0.0.1:5200
2. **Tee selainikkunasta leveä (vähintään 1200 px),** jotta puhelimen vieressä näkyvät profiili- ja matching-paneelit.
3. **Tekoäly on oletuksena Demo-tilassa.** Pidä se niin: Claude-tilassa jokainen vastaus odottaa mallia, ja demo venyy.
   Palvelimen uudelleenkäynnistys palauttaa aina Demon.
4. **Aloita alusta:** paina **Aloita demo** tai avaa demopalkin oikean reunan nuolipainike ja valitse **Aloita demo alusta**.
   Demo alkaa suoraan Samin kotinäkymästä.
5. **Näppäimet:** → tai PageDown vie eteenpäin, ← tai PageUp palaa ja Shift+→ vie vaiheen loppuun. Myös esitysklikkeri
   toimii.
6. **Ohjaus paneelin viereen (valinnainen):** nuolipainikkeen takaa löytyvä **Ohjaus paneelin viereen** siirtää
   demo-ohjauksen omaksi sarakkeekseen oikealle, asiakasnäkymässä Taustalla-paneelin viereen. Sarakkeessa on vaiheen
   kerronta (ks. alla), ja puhelin ja paneeli saavat ruudun koko korkeuden. Sarake pysyy samassa paikassa myös
   ammattilaisen ja terapeutin näkymissä. **Ohjaus yläpalkkiin** palauttaa sen. Valinta muistetaan selaimessa. Alle
   900 px leveässä ikkunassa ohjaus on aina yläpalkissa.

## Pitch-video: noin 3 minuuttia, kerronta ruudulla

Kun ohjaus on paneelin vieressä, sarakkeessa näkyy vaihe (esim. *Vaihe 3/8*), vaiheen nimi ja luettava kerronta.
Kerronta on esittäjän pitch minämuodossa, asiakkaan roolissa. Vaiheen teksti on jaettu osiin, jotka vaihtuvat painallusten
mukaan niin, että sarakkeessa on aina ruudulla näkyvään kuuluva osa – esimerkiksi *Vointikysely*, *Hoitokoordinaattorin
näkymä* ja *Yhteenveto ensikäynnille*. Pisteet kertovat, montako painallusta vaiheessa on ja montako on tehty; alimpana
näkyy seuraava vaihe. Tekstit ovat tiedostossa `frontend/src/valituki/components/demoPilot.ts` (`STAGES[].tell` ja
`DEMO_INTRO`); kerronta on yhteensä noin 520 sanaa. Demo-ohjaus tekee pitchin teot itse: askeleella 13 ammattilainen
merkitsee tilanteen tarkistetuksi ja muuttaa kiireellisyyden kiireelliseksi, askeleella 19 asiakas poistaa yhteenvedosta
yhden kohdan (*Mitä olen kokeillut*) ja hyväksyy loput. Aiempi, lyhyempi videon käsikirjoitus painallusvihjeineen on
tiedostossa [DEMO_VIDEO.md](DEMO_VIDEO.md).

- **Ennen ensimmäistä painallusta** luetaan johdanto ("Kun ihminen saa lähetteen terapiaan, hoito ei ala…"). Aloita
  tallennus *Alkutilaan*-painikkeen jälkeen, jolloin sarakkeessa näkyy johdanto; *Aloita demo alusta* tekee heti askeleen 1.
- **Paina seuraavaa vasta, kun painikkeessa lukee taas Seuraava.** Jos siinä lukee *Kelaa*, painallus vain vie käynnissä
  olevan keskustelun loppuun.
- **Tallenna Demo-tilassa,** jolloin keskustelut etenevät tasaisesti eivätkä odota kielimallia.

| Vaihe | Painallukset | Aika | Vinkki |
|---|---|---|---|
| 1 · Avun haku | 1 | ~15 s | Lue johdanto ennen painallusta, vaiheen teksti sen jälkeen. |
| 2 · AI-alkukeskustelu | 4 | ~22 s | Paina askeleet 2 ja 3 heti; keskustelu pyörii noin 10 s. Askel 4, kun *Ymmärsinkö tilanteesi oikein?* näkyy, ja 5 heti perään. Älä kelaa vaihetta: keskustelu ja tietojen siirtyminen paneeliin ovat sen ydin. |
| 3 · Ohjattu harjoittelu | 3 | ~23 s | Askel 8 toistaa koko harjoituksen (noin 45 s). Anna sen edetä noin 10 s ja paina → (*Kelaa*), niin harjoitus ja altistusportaat valmistuvat kerralla. |
| 4 · Seuranta | 5 | ~23 s | Askel 9 kelaa kaksi viikkoa. Askeleet 11–13 ovat hoitokoordinaattorin näkymässä; kerronta pysyy oikealla. |
| 5 · Havainto | 1 | ~17 s | Paina ennen kuin alat puhua – tieto lentää profiiliin parissa sekunnissa. |
| 6 · Sopivin terapeutti | 5 | ~23 s | Kiireessä paina askeleen 16 jälkeen *Vaihe 6 loppuun* (Shift+→): aika varataan ja yhteenveto hyväksytään kerralla. |
| 7 · Terapia | 4 | ~16 s | Askeleet 20–22 ovat terapeutin näkymässä, askel 23 palaa puhelimeen. |
| 8 · Seuranta terapian jälkeen | 1 | ~15 s | Viimeinen askel: lopeta tallennus, kun ylläpitosuunnitelma näkyy ja teksti on luettu. |

## Runko: 24 painallusta, noin 5 minuuttia

| Konseptin vaihe | Painallus | Mitä ruudulla tapahtuu | Aika |
|---|---|---|---|
| 1 · Avun haku | 1 | Sami on terapiajonossa, jonotiedot korostettuna | 0:00–0:35 |
| 2 · AI-alkukeskustelu | 2–5 | Keskustelu alkaa → vastaukset toistuvat (noin 6 s) → ”Ymmärsinkö tilanteesi oikein?” → Sami hyväksyy, ja profiili täyttyy → check-in-rytmi → kotinäkymässä ”Miten voit tänään?” (oma lähtötaso) | 0:35–1:35 |
| 3 · Mieliluotsi: KKT | 6–8 | Demoviesti → ”Kyllä, tutkitaan” → keskustelu etenee kuin terapeutin kanssa: Mieliluotsi vastaa lyhyin kuplin yksi kerrallaan ja kysyy yhden asian kerrallaan (noin 45 s, → kelaa loppuun) → altistusporras | 1:35–2:30 |
| 4 · Mieliluotsi: seuranta ja muutosten tunnistus | 9–13 | Kaksi viikkoa myöhemmin: mieliala ja ahdistus käyrällä, ja vointi heikkenee → ”Huomasimme jotain” (havainto on vain ehdotus) → Ammattilainen: jono → ”Miksi Sami nousi tarkistettavaksi?” → merkitään tarkistetuksi ja kiireellisyydeksi kiireellinen | 2:20–3:10 |
| 5 · Mieliluotsi: havainto tarkentaa terapeuttiprofiilia | 14 | Sami hyväksyy havainnon, ja profiili päivittyy | 3:10–3:30 |
| 6 · Sopivin terapeutti ja handover | 15–19 | Vapaa paikka → matching → ”Miksi Anna?” → valinta ja ensimmäinen aika → yhteenveto → yksi kohta poistetaan ja loput hyväksytään jaettavaksi | 3:30–4:15 |
| 7 · Terapia + välitehtävät | 20–23 | Terapia alkaa: Anna näkee hyväksytyn yhteenvedon → välituen määritys → tallennus → Sami näkee suunnitelman | 4:15–4:50 |
| 8 · Seuranta terapian jälkeen | 24 | Terapia päättyy – seuranta jatkuu | 4:50–5:00 |

Kun vaihe on käynnissä, painikkeessa lukee **Kelaa**. Painallus (tai →) vie käynnissä olevan keskustelun heti loppuun,
kuten animaation ohitus diaesityksessä. Seuraava painallus jatkaa taas seuraavaan vaiheeseen.

**Vaihe loppuun** (Seuraava-painikkeen vieressä, tai Shift+→) simuloi koko vaiheen kerralla: kaikki vaiheen
painallukset tehdään peräkkäin ilman taukoja, keskustelut näkyvät heti kokonaan, ja ruudulle jää vaiheen viimeinen
näkymä. Painike kertoo, minkä vaiheen se vie loppuun (esim. *Vaihe 3 loppuun*). Kun vaihe on jo valmis, se vie seuraavan
vaiheen loppuun.

## Jos jokin menee pieleen

- **←** palaa edelliseen vaiheeseen ja palauttaa demon tilan. Seuraava → tekee vaiheen uudelleen.
- **Vaiherivin numeron klikkaus** siirtää demon suoraan kyseiseen vaiheeseen, yleensä alle sekunnissa. Jatka siitä →-näppäimellä.
- Jos vaihe ei onnistu, palkki kertoo sen. Paina silloin → uudelleen.
- Jos etenet sovelluksessa itse klikkaamalla, vaiherivi ja numero siirtyvät mukana. Seuraava → jatkaa siitä, mihin pääsit, ja puuttuva tila rakennetaan tarvittaessa.

## Kysymyksiin (ei kuulu viiteen minuuttiin)

- **Turvallisuus:** demopalkin **Lisää → Kriisipolku** avaa kiinteän näkymän *Tarvitsetko apua juuri nyt?* (112,
  Päivystysapu 116117, MIELI Kriisipuhelin 09 2525 0111). Näkymässä ei käytetä tekoälyä. Seuraava → palaa Samin demoon.
- **Mitä agentit tekivät:** Ammattilainen → **Mitä Mieliluotsi teki?** näyttää jokaisen toimenpiteen ja sen säännön.
- **Tietojen hallinta:** asiakkaan avatar → **Tietoni** näyttää käyttöoikeudet tietokohtaisesti.
- **Vaikuttavuus:** Ammattilainen → **Vaikuttavuus** (synteettiset luvut).

Kaikki demon henkilöt ja terveystiedot ovat täysin kuvitteellisia.
