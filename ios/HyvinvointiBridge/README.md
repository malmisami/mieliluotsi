# HyvinvointiBridge – HealthKit-silta (iOS)

Pieni iOS-kumppanisovellus, joka tuo Apple Healthin päivittäiset yhteenvedot hyvinvointikumppanin backendiin.
Selain ei pääse HealthKitiin, joten web-sovellus ei yritä lukea terveystietoja itse. Arkkitehtuuri:

```
iPhone / Apple Watch ── HealthKit (vain luku) ── HyvinvointiBridge ──HTTPS──▶ backend /api/health/sync
                                                                                 │
web-sovellus (Hyvinvointidata-välilehti) ◀──────────── /api/health/summary ──────┘
                                                        └─ tiivis yhteenveto agentin kontekstiin
```

## Kulku

1. Web-sovelluksen **Hyvinvointidata → Yhdistä Apple Health** näyttää kertakäyttöisen 6-numeroisen koodin, joka on voimassa 10 minuuttia.
   Backend tallentaa koodista vain tiivisteen.
2. Sovellus lähettää koodin osoitteeseen `POST /api/health/devices/pair` ja saa laitekohtaisen tunnisteen.
   Tunniste tallennetaan Keychainiin ja backend tallentaa siitä vain tiivisteen.
3. **Salli terveystiedot**: Apple näyttää oman lupaikkunansa, jossa jokainen tieto sallitaan erikseen. Sovellus pyytää
   vain lukuoikeutta (`toShare: []`) seuraaviin: askeleet, uni, leposyke, HRV (SDNN), aktiivinen energia, liikuntasuoritukset,
   paino ja VO2 max.
4. **Synkronoi nyt** koostaa päivittäiset yhteenvedot (summat, päiväkeskiarvot tai päivän viimeisin arvo) ja lähettää ne
   osoitteeseen `POST /api/health/sync` otsakkeella `Authorization: Bearer <laitetunniste>`. Henkilö päätellään
   tunnisteesta, eikä sovellus lähetä käyttäjätunnistetta.
   - Ensimmäinen synkronointi lähettää vuoden historian, myöhemmät vain uudet päivät sekä kaksi edellistä päivää
     myöhässä saapuvien tietojen vuoksi. Lähetykset tehdään 120 päivän erissä, ja backend hyväksyy enintään 400 päivää kerralla.
   - Backend päivittää saman lähteen ja päivän rivin, joten sama päivä ei synny kahdesti.
   - Unen päällekkäiset näytteet (kello ja puhelin) yhdistetään ennen summaa.
   - Yksittäisiä mittauksia ei lähetetä.

Esimerkki payloadista:

```json
{
  "source": "apple_health",
  "deviceId": "device-0001",
  "dailyMetrics": [
    {"date": "2026-09-25", "steps": 8450, "sleepMinutes": 431, "restingHeartRate": 48, "hrvMs": 52,
     "activeEnergyKcal": 480, "workoutMinutes": 35, "workoutCount": 1, "vo2Max": 46.1, "weightKg": 62.1}
  ]
}
```

## Rakentaminen

Vaatii Xcoden (iOS 17 SDK) ja Apple Developer -tilin HealthKit-capabilityllä.

```bash
brew install xcodegen
cd ios/HyvinvointiBridge && xcodegen generate && open HyvinvointiBridge.xcodeproj
```

Valitse tiimi (Signing & Capabilities). HealthKit on mukana entitlementissä `HyvinvointiBridge.entitlements`, ja lupateksti
on kohdassa `NSHealthShareUsageDescription` (`Info.plist`). HealthKit toimii myös iOS-simulaattorissa, kun Terveys-apissa on dataa.
Oikealla laitteella palvelimen osoitteeksi annetaan Macin osoite lähiverkossa, esimerkiksi `http://192.168.1.20:8002`.
Tuotannossa käytetään vain HTTPS:ää.

Tässä kehitysympäristössä (Command Line Tools, ei Xcodea) lähdekoodi on tyyppitarkistettu macOS-SDK:ta vasten:

```bash
swiftc -typecheck -parse-as-library -sdk "$(xcrun --show-sdk-path)" -target arm64-apple-macos14.0 HyvinvointiBridge/Sources/*.swift
```

Sovellusta ei ole ajettu iPhonessa. Demo toimii ilman sitä synteettisellä testidatalla (Hyvinvointidata → *Käytä
synteettistä testidataa*).

## Seuraavat askeleet

- Taustasynkronointi: `HKObserverQuery` ja `enableBackgroundDelivery` vaativat entitlementin
  `com.apple.developer.healthkit.background-delivery`.
- Anchored-kyselyt (`HKAnchoredObjectQuery`) päivämäärähaun tilalle.
- Myöhemmät mittarit backendin `futureMetrics`-listan mukaan: verenpaine, hengitystiheys, happisaturaatio, kävelysyke,
  verensokeri, kehon lämpötila ja kuukautiskierto. Ne lähetetään kentässä `extra`.
