# Mieliluotsi – 5 minuutin demo

Koko demo etenee yhdellä näppäimellä. Paina **→** tai yläpalkin **Seuraava**. Jokainen painallus tekee seuraavan
vaiheen oikeassa näkymässä: se syöttää demotekstin, painaa oikeaa painiketta, avaa oikean välilehden ja korostaa
kohdan, josta puhutaan.

Yläpalkin vaihenumero (esim. 5/25) kertoo, missä kohtaa demoa ollaan. Kun viet hiiren numeron päälle, näet, mitä
ruudulla nyt on. Seuraava-painikkeen päällä näet, mitä seuraava painallus tekee. Vaiherivi noudattaa Konsepti-sivun
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
4. **Aloita alusta:** avaa demopalkin oikean reunan nuolipainike ja valitse **Konsepti – aloita alusta**.
5. **Näppäimet:** → tai PageDown vie eteenpäin, ← tai PageUp palaa. Myös esitysklikkeri toimii.

## Runko: 25 painallusta, noin 5 minuuttia

| Konseptin vaihe | Painallus | Mitä ruudulla tapahtuu | Aika |
|---|---|---|---|
| Konsepti | 1 | Konsepti-sivu: ennen ja Mieliluotsilla | 0:00–0:20 |
| 1 · Avun haku | 2 | Aino on terapiajonossa, jonotiedot korostettuna | 0:20–0:35 |
| 2 · AI-alkukeskustelu | 3–6 | Keskustelu alkaa → vastaukset toistuvat (noin 6 s) → ”Ymmärsinkö tilanteesi oikein?” → Aino hyväksyy, ja profiili täyttyy → check-in-rytmi → kotinäkymässä ”Miten voit tänään?” (oma lähtötaso) | 0:35–1:35 |
| 3 · Mieliluotsi: KKT | 7–9 | Demoviesti → ”Kyllä, tutkitaan” → harjoitus toistuu (noin 20 s) → altistusporras | 1:35–2:20 |
| 4 · Mieliluotsi: seuranta ja muutosten tunnistus | 10–14 | Kaksi viikkoa myöhemmin: mieliala ja ahdistus käyrällä, ja vointi heikkenee → ”Huomasimme jotain” (havainto on vain ehdotus) → Ammattilainen: jono → ”Miksi Aino nousi tarkistettavaksi?” → merkitään tarkistetuksi | 2:20–3:10 |
| 5 · Mieliluotsi: havainto tarkentaa terapeuttiprofiilia | 15 | Aino hyväksyy havainnon, ja profiili päivittyy | 3:10–3:30 |
| 6 · Sopivin terapeutti ja handover | 16–20 | Vapaa paikka → matching → ”Miksi Anna?” → valinta ja ensimmäinen aika → yhteenveto → hyväksytään jaettavaksi | 3:30–4:15 |
| 7 · Terapia + välitehtävät | 21–24 | Terapia alkaa: Anna näkee hyväksytyn yhteenvedon → välituen määritys → tallennus → Aino näkee suunnitelman | 4:15–4:50 |
| 8 · Seuranta terapian jälkeen | 25 | Terapia päättyy – seuranta jatkuu | 4:50–5:00 |

Kun toisto on käynnissä, painike näyttää tekstiä **Odota…**. Tänä aikana ylimääräiset painallukset eivät tee mitään.

## Jos jokin menee pieleen

- **←** palaa edelliseen vaiheeseen ja palauttaa demon tilan. Seuraava → tekee vaiheen uudelleen.
- **Vaiherivin numeron klikkaus** siirtää demon suoraan kyseiseen vaiheeseen, yleensä alle sekunnissa. Jatka siitä →-näppäimellä.
- Jos vaihe ei onnistu, palkki kertoo sen. Paina silloin → uudelleen.
- Jos etenet sovelluksessa itse klikkaamalla, vaiherivi ja numero siirtyvät mukana. Seuraava → jatkaa siitä, mihin pääsit, ja puuttuva tila rakennetaan tarvittaessa.

## Kysymyksiin (ei kuulu viiteen minuuttiin)

- **Turvallisuus:** demopalkin **Lisää → Kriisipolku** avaa kiinteän näkymän *Tarvitsetko apua juuri nyt?* (112,
  Päivystysapu 116117, MIELI Kriisipuhelin 09 2525 0111). Näkymässä ei käytetä tekoälyä. Seuraava → palaa Ainon demoon.
- **Mitä agentit tekivät:** Ammattilainen → **Mitä Mieliluotsi teki?** näyttää jokaisen toimenpiteen ja sen säännön.
- **Tietojen hallinta:** asiakkaan avatar → **Tietoni** näyttää käyttöoikeudet tietokohtaisesti.
- **Vaikuttavuus:** Ammattilainen → **Vaikuttavuus** (synteettiset luvut).

Kaikki demon henkilöt ja terveystiedot ovat täysin kuvitteellisia.
