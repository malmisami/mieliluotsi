import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { ViewScope } from '../api';
import { useValituki } from '../context';
import type { ClientTab } from '../context';
import type { GuidedView, IntakeView, Mutation, ValitukiView } from '../types';
import { chatRevealing, hurryChat } from '../client/chatPace';

/* DEMO-OHJAIN – the presenter presses "Seuraava" (or →) and the demo takes the next step of the concept's story: it
   types the demo text, presses the right button and opens the right view. Every step goes through the same API as a
   click in the app. The stages follow the Konsepti page: avun haku → AI-alkukeskustelu → Mieliluotsi (KKT, seuranta
   ja muutosten tunnistus, Therapy Fit Profile) → terapeutti ja handover → terapia → seuranta terapian jälkeen. */

const AINO = 'cl-aino';
const ANNA = 'th-anna';
const SCOPE: ViewScope = { clientId: AINO, therapistId: ANNA };
const STORAGE_KEY = 'vt-demo-pilot';
const FALLBACK_MESSAGE = 'Tiistaina minun pitää esitellä projektin tilanne koko tiimille, ja jännittää jo nyt ihan hirveästi.';

export type StageKey = 'intro' | 'haku' | 'alku' | 'seuranta' | 'kkt' | 'tfp' | 'terapeutti' | 'terapia' | 'jalkeen';

/** The concept's stages in the order of the Konsepti page; `group` marks the four inside the "Mieliluotsi" box. `tell` is
    the stage's narration beside the panel: what the stage shows of the solution, read aloud in the pitch video – one text
    per stage, not per press. */
export const STAGES: { key: StageKey; label: string; group?: 'valituki'; tell: string }[] = [
  { key: 'haku', label: 'Avun haku',
    tell: 'Mieliluotsi-sovelluksessa tuki alkaa heti. Se ei korvaa terapeuttia eikä päivystystä. Aina esillä '
      + 'oleva ”Apua nyt” -painike näyttää kriisinumerot. Puhelimen vieressä on taustanäkymä, jota asiakas ei '
      + 'näe.' },
  { key: 'alku', label: 'AI-alkukeskustelu',
    tell: 'Lomakkeen sijaan asiakas kertoo tilanteestaan omin sanoin. Tekoäly eli kielimalli saa esittää '
      + 'jatkokysymyksiä ja tiivistää vastaukset ehdotuksiksi, mutta demossa tekstit on kirjoitettu valmiiksi. '
      + 'Vain asiakkaan hyväksymät tiedot siirtyvät taustanäkymään: terapeutille koottavaan profiiliin ja osin '
      + 'terapeutin valintaan.' },
  { key: 'kkt', label: 'Ohjattu KKT-harjoittelu chatissa', group: 'valituki',
    tell: 'Asiakas kertoo jännittävänsä esitystä töissä. Jokainen viesti tarkistetaan ensin säännöillä kriisin '
      + 'merkkien varalta. Mieliluotsi ehdottaa ajatusten tutkimista kognitiivisen käyttäytymisterapian '
      + 'keinoin. Säännöt päättävät harjoituksen vaiheet, kielimalli saa vain muotoilla ja ehdottaa. Lopuksi '
      + 'hän rakentaa altistusportaat: tilannetta lähestytään pienin askelin.' },
  { key: 'seuranta', label: 'Mielialan ja ahdistuksen seuranta', group: 'valituki',
    tell: 'Viikot kuluvat, ja asiakas vastaa lyhyisiin vointikyselyihin. Mielialaa verrataan hänen omaan '
      + 'lähtötasoonsa, ei muihin. Jos mieliala on kolmesti peräkkäin vähintään pisteen alempana, '
      + 'hoitokoordinaattori saa tarkistuspyynnön, ja asiakkaalle kerrotaan siitä. Koordinaattori näkee, mihin '
      + 'sääntöön pyyntö perustuu. Vain ammattilainen voi muuttaa hoidon kiireellisyyttä.' },
  { key: 'tfp', label: 'Havainto tarkentaa terapeuttiprofiilia', group: 'valituki',
    tell: 'Toinen sääntö on poiminut asiakkaan vastauksista havainnon: työpäiviä edeltävinä iltoina ahdistusta on '
      + 'enemmän. Asiakas hyväksyy sen. Jokaisella tiedolla on oma käyttölupa: tämä havainto näkyy terapeutille, '
      + 'mutta ei vaikuta terapeutin valintaan.' },
  { key: 'terapeutti', label: 'Sopivin saatavilla oleva terapeutti',
    tell: 'Kun terapeutilta vapautuu paikka, sopivuus lasketaan säännöillä, ei tekoälyllä. Ensin pakolliset '
      + 'ehdot, sitten avoimesti painotetut kriteerit. Asiakas näkee perustelut sekä toteutumatta jäävät toiveet '
      + 'ja valitsee itse Annan. Annalle kootaan yhteenveto ilman keskusteluhistoriaa, ja asiakas voi muokata '
      + 'sitä, hyväksyä sen tai perua jakamisen.' },
  { key: 'terapia', label: 'Terapia + välitehtävät Mieliluotsissa',
    tell: 'Ensimmäinen tapaaminen ei ala tyhjästä: Annan näkymässä on asiakkaan hyväksymä yhteenveto. Anna '
      + 'päättää, mitä Mieliluotsi saa tarjota tapaamisten välillä. Asiakas näkee puhelimessaan, mitä Anna on '
      + 'sallinut.' },
  { key: 'jalkeen', label: 'Seuranta terapian jälkeen',
    tell: 'Annan ylläpitosuunnitelmassa ovat opitut keinot ja merkit, joihin reagoida. Vointia kysytään kerran '
      + 'viikossa, ja jos mieliala laskee, asia palaa ammattilaisen arvioitavaksi.' },
];

/** The narration before the first press – the presenter's opening line, shown in the demo control beside the panel. */
export const DEMO_INTRO = 'Kuvitteellinen asiakas on saanut lähetteen lyhytterapiaan. Tavallisesti edessä olisi '
  + 'kuukausien passiivinen odotus.';

type Where = { role: 'pitch' } | { role: 'client'; tab: ClientTab } | { role: 'professional'; client: string | null } | { role: 'therapist' };

interface PilotCtx {
  /** The newest view: the last mutation's result, or the rendered one. */
  view: () => ValitukiView;
  /** Run one API call for Sami/Anna; resolves to the new view, or null when it failed. */
  mutate: <T>(call: (s: ViewScope) => Promise<Mutation<T>>) => Promise<ValitukiView | null>;
  go: (where: Where) => void;
  /** Scroll the first matching element into view and pulse it; resolves to the element. */
  spot: (selectors: string | string[], block?: 'start' | 'center') => Promise<HTMLElement | null>;
  /** Pauses between replayed answers – skipped when a jump rebuilds a step in the background. */
  pause: (ms: number) => Promise<void>;
  /** Wait until the chat has shown Mieliluotsi's whole reply, bubble by bubble (at once when hurried or rebuilt). */
  settle: () => Promise<void>;
}

export interface Beat {
  stage: StageKey;
  /** What is on the screen after this step – the presenter's cue and the audience's subtitle. */
  title: string;
  say: string;
  /** The state change (same API as the app's buttons). Returns false when it did not succeed. */
  act?: (p: PilotCtx) => Promise<boolean>;
  /** Where to look: role, tab, scroll position and the highlighted element. */
  show: (p: PilotCtx) => Promise<void>;
}

const ok = (view: ValitukiView | null) => view !== null;

/** The intake conversation: the rest of the scripted answers, one at a time. */
async function playIntake(p: PilotCtx): Promise<boolean> {
  let view: ValitukiView | null = p.view();
  for (let i = 0; i < 12; i += 1) {
    const intake: IntakeView | undefined = view?.client?.intake;
    if (!intake || intake.status !== 'conversation') break;
    const question: IntakeView['pendingQuestion'] = intake.pendingQuestion;
    const answer: string | null = question ? intake.demoAnswers?.[question.key] ?? question.demoAnswer : null;
    if (!answer) break;
    await p.pause(i === 0 ? 250 : 900);
    view = await p.mutate((s): Promise<Mutation> => api.intakeAnswer(s, AINO, answer));
  }
  if (view?.client?.intake.status === 'conversation' && view.client.intake.canFinish) {
    view = await p.mutate((s) => api.intakeFinish(s, AINO));
  }
  return ok(view);
}

/** A guided CBT exercise in the chat: the rest of the scripted answers, one at a time – each once Mieliluotsi's reply and
    question are on the screen and there has been a moment to read them. */
async function playGuided(p: PilotCtx): Promise<boolean> {
  let view: ValitukiView | null = p.view();
  for (let i = 0; i < 30; i += 1) {
    const guided: GuidedView | null | undefined = view?.client?.guided;
    if (!guided || guided.demoAnswer === null || guided.demoAnswer === undefined) break;
    await p.settle();
    await p.pause(i === 0 ? 400 : 900);
    view = await p.mutate((s): Promise<Mutation> => api.answerPractice(s, AINO,
      { sessionId: guided.id, stepKey: guided.stepKey, value: guided.demoAnswer }));
  }
  await p.settle();
  return ok(view);
}

export const BEATS: Beat[] = [
  // 1 · Avun haku – the demo starts here, from the prepared start state
  { stage: 'haku', title: 'Sami on hakenut apua ja on terapiajonossa',
    say: 'Työhön liittyvä ahdistus, lyhytterapia, arvioitu odotus 20–25 viikkoa. Normaalisti tästä alkaisi pelkkä odotus – Mieliluotsilla tuki alkaa heti.',
    act: async (p) => ok(await p.mutate((s) => api.scene(s, 'start'))),
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); await p.spot('.wait-card'); } },

  // 2 · AI-alkukeskustelu
  { stage: 'alku', title: 'Alkukeskustelu alkaa – lomakkeen sijaan',
    say: 'Sami päätti ensin itse, mitä Mieliluotsi saa tehdä. Mieliluotsi kysyy yhden asian kerrallaan: ”Kerro omin sanoin, miksi hait apua.”',
    act: async (p) => ok(await p.mutate((s) => api.intakeStart(s, AINO, p.view().client?.intake.consentDefaults ?? {
      proactiveCheckins: true, storeHistory: true, professionalMonitoring: true, sharePractice: true }))),
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); } },
  { stage: 'alku', title: 'Sami kertoo omin sanoin → ”Ymmärsinkö tilanteesi oikein?”',
    say: 'Kuusi tarkentavaa kysymystä: tavoite, vaikeat hetket, mikä on auttanut ja toiveet terapialta. Tulkinnat ovat vasta ehdotuksia.',
    act: playIntake,
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); } },
  { stage: 'alku', title: 'Sami hyväksyy tulkinnat → Therapy Fit Profile syntyy',
    say: 'Vasta hyväksytyt tiedot siirtyvät terapeutin profiiliin ja matchingiin (oikealla). Viimeisenä rytmi ja tämän päivän vointi.',
    act: async (p) => ok(await p.mutate((s) => api.intakeConfirm(s, AINO))),
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); await p.spot('.bp-doc'); } },

  { stage: 'alku', title: 'Check-in-rytmi ja oma lähtötaso – Mieliluotsi käynnistyy',
    say: 'Mieliala ja ahdistus 1–5 kolmesti viikossa. Vointia verrataan Samin omaan lähtötasoon, ei muihin ihmisiin.',
    act: async (p) => {
      const intake = p.view().client?.intake;
      const rhythm = intake?.demoRhythm;
      if (intake?.status === 'rhythm' && !ok(await p.mutate((s) => api.intakeComplete(s, AINO, {
        checkInDays: rhythm?.checkInDays ?? [0, 2, 5], communicationStyle: rhythm?.communicationStyle ?? 'brief' })))) return false;
      if (!p.view().client?.checkIn.needsBaseline) return true;
      // "Miten voit tänään?" on the home screen: the card is on screen for a moment, then Sami answers.
      p.go({ role: 'client', tab: 'koti' });
      await p.spot('.cx-baseline', 'center');
      await p.pause(1600);
      return ok(await p.mutate((s) => api.recordBaseline(s, AINO, { mood: intake?.demoMood ?? 3, anxiety: 3 })));
    },
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); await p.spot('.cx-teaser', 'center'); } },

  // 3 · Mieliluotsi: ohjattu KKT-harjoittelu chatissa
  { stage: 'kkt', title: 'Sami kertoo jännittävästä tilanteesta',
    say: '”Tiistaina pitää esitellä projekti koko tiimille…” Mieliluotsi tunnistaa tilanteen ja ehdottaa, että sitä tutkitaan yhdessä.',
    act: async (p) => {
      const text = p.view().client?.demoMessage ?? FALLBACK_MESSAGE;
      p.go({ role: 'client', tab: 'keskustelu' });
      await p.pause(500);
      const sent = ok(await p.mutate((s) => api.sendMessage(s, AINO, text)));
      await p.settle();
      return sent;
    },
    show: async (p) => { p.go({ role: 'client', tab: 'keskustelu' }); } },
  { stage: 'kkt', title: '”Kyllä, tutkitaan” – ohjattu harjoitus alkaa',
    say: 'Ajatusten tutkiminen kysymys kerrallaan. Jokaisen kysymyksen voi ohittaa, ja harjoituksen voi lopettaa milloin tahansa.',
    act: async (p) => {
      const offer = [...(p.view().client?.chat ?? [])].reverse()
        .find((m) => m.kind === 'offer' && m.actionable && m.widget?.options.some((o) => o.value.startsWith('start:')));
      const option = offer?.widget?.options.find((o) => o.value.startsWith('start:'))?.value;
      const started = offer && option
        ? ok(await p.mutate((s) => api.chooseOffer(s, AINO, offer.id, option)))
        : ok(await p.mutate((s) => api.startPractice(s, AINO, 'thought_record', {}, 'chat')));
      await p.settle();
      return started;
    },
    show: async (p) => { p.go({ role: 'client', tab: 'keskustelu' }); } },
  { stage: 'kkt', title: 'Tilanne → ajatus → tunne → ajatusloukku → tasapainoisempi ajatus → askel',
    say: 'Säännöt päättävät vaiheet, kielimalli vain muotoilee. Lopuksi sovitaan konkreettinen askel: altistusportaan ensimmäinen askel huomenna.',
    act: playGuided,
    show: async (p) => { p.go({ role: 'client', tab: 'keskustelu' }); } },

  // 4 · Mieliluotsi: mielialan ja ahdistuksen seuranta – kun dataa on kertynyt
  { stage: 'seuranta', title: 'Kaksi viikkoa myöhemmin: mieliala ja ahdistus käyrällä – vointi laskee alle oman lähtötason',
    say: 'Check-init kolmesti viikossa ja harjoittelu kertyvät, ja jokaista check-iniä verrataan Samin omaan lähtötasoon. Sitten '
      + 'check-in jää väliin ja uni heikkenee: havaintoagentti tunnistaa muutoksen ja pyytää ammattilaista katsomaan.',
    act: async (p) => {
      const view = p.view();
      if (daysBetween(view.meta.demoStartDate, view.meta.currentDate) < 14) {
        if (!ok(await p.mutate((s) => api.advance(s, 14)))) return false;
        // The two weeks on the chart first, then the decline.
        p.go({ role: 'client', tab: 'edistyminen' });
        await p.spot('.ma-chart');
        await p.pause(1800);
      }
      return ok(await p.mutate((s) => api.deteriorate(s, AINO)));
    },
    show: async (p) => { p.go({ role: 'client', tab: 'edistyminen' }); await p.spot('.ma-chart'); } },
  { stage: 'seuranta', title: '”Huomasimme jotain” – havainto on vain ehdotus',
    say: 'Työpäiviä edeltävinä iltoina ahdistusta on ollut enemmän. Sami päättää itse, tallennetaanko havainto.',
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); await p.spot(['.cx-insight', '.bp-doc']); } },
  { stage: 'seuranta', title: 'Hoitotiimin terapiajono: Sami nousee tarkistettavaksi',
    say: 'Avoimet tarkistuspyynnöt ensin. Mieliluotsi ei priorisoi asiakkaita eikä muuta hoidon kiireellisyyttä.',
    show: async (p) => { p.go({ role: 'professional', client: null }); await p.spot('.queue-table tr.row-primary', 'center'); } },
  { stage: 'seuranta', title: '”Miksi Sami nousi tarkistettavaksi?”',
    say: 'Perustelut, sääntö ja itse raportoidut tiedot näkyvät – ei diagnoosia eikä mustaa laatikkoa.',
    show: async (p) => { p.go({ role: 'professional', client: AINO }); await p.spot('.why-card'); } },
  { stage: 'seuranta', title: 'Ammattilainen merkitsee tarkistetuksi – ihminen päättää',
    say: 'Sami jatkaa jonossa Mieliluotsin tuella. Hoidon kiireellisyydestä päättää aina ammattilainen.',
    act: async (p) => {
      const review = p.view().professional.details[AINO]?.openReview;
      return review ? ok(await p.mutate((s) => api.reviewObservation(s, review.id, 'mark_reviewed'))) : true;
    },
    show: async (p) => { p.go({ role: 'professional', client: AINO }); await p.spot(['.reviewed-card', '.review-main']); } },

  // 6 · Mieliluotsi: Therapy Fit Profile
  { stage: 'tfp', title: 'Sami hyväksyy – Therapy Fit Profile päivittyy',
    say: 'Profiili terapeutille rakentuu vain hyväksytyistä tiedoista, ja jokaisella tiedolla on oma käyttöoikeus.',
    act: async (p) => {
      const pattern = p.view().client?.memory.pending.find((i) => i.kind === 'pattern');
      return pattern ? ok(await p.mutate((s) => api.decideInsight(s, AINO, pattern.id, 'approve'))) : true;
    },
    show: async (p) => { p.go({ role: 'client', tab: 'koti' }); await p.spot('.bp-doc'); } },

  // 7 · Sopivin saatavilla oleva terapeutti
  { stage: 'terapeutti', title: 'Terapeutilta vapautuu paikka – matching ajetaan heti',
    say: 'Ensin kovat ehdot, sitten läpinäkyvä pisteytys. Sami näkee kolme tilanteeseensa sopivinta terapeuttia.',
    act: async (p) => ok(await p.mutate((s) => api.openSlot(s))),
    show: async (p) => { p.go({ role: 'client', tab: 'polku' }); await p.spot('.matching'); } },
  { stage: 'terapeutti', title: '”Miksi Anna?” – perustelut, vapaa aika ja täyttymättömät toiveet',
    say: 'Ei todennäköisyyksiä: Sami näkee, mihin suositus perustuu ja mitä toiveita ei voitu täyttää.',
    show: async (p) => {
      p.go({ role: 'client', tab: 'polku' });
      const card = await p.spot('.cand');
      card?.querySelector('details.unmet')?.setAttribute('open', '');
    } },
  { stage: 'terapeutti', title: 'Sami valitsee Annan – ensimmäinen aika varataan',
    say: 'Etävastaanotto tiistai-iltana, kuten Sami toivoi. Samalla syntyy luonnos yhteenvedosta ensimmäistä tapaamista varten.',
    act: async (p) => {
      const candidates = p.view().client?.matching.candidates ?? [];
      const anna = candidates.find((c) => c.therapist.id === ANNA) ?? candidates[0];
      return anna ? ok(await p.mutate((s) => api.selectCandidate(s, AINO, anna.id))) : false;
    },
    show: async (p) => { p.go({ role: 'client', tab: 'polku' }); await p.spot('.booking-card'); } },

  // (terapeutti jatkuu: asiakkaan hyväksymä yhteenveto ensimmäistä tapaamista varten)
  { stage: 'terapeutti', title: 'Yhteenveto ensimmäistä tapaamista varten',
    say: 'Jokainen kohta on merkitty: omin sanoin, mitattu tai tekoälyn tiivistelmä. Sami voi muokata ja poistaa kohtia.',
    show: async (p) => { p.go({ role: 'client', tab: 'polku' }); await p.spot('.handover-card'); } },
  { stage: 'terapeutti', title: 'Sami hyväksyy yhteenvedon jaettavaksi',
    say: 'Mitään ei jaeta ennen hyväksyntää, eikä keskusteluhistoriaa jaeta koskaan.',
    act: async (p) => ok(await p.mutate((s) => api.approveHandover(s, AINO))),
    show: async (p) => { p.go({ role: 'client', tab: 'polku' }); await p.spot(['.handover-card .banner-ok', '.handover-card']); } },

  // 9 · Terapia + välitehtävät Mieliluotsissa
  { stage: 'terapia', title: 'Terapia alkaa – Anna näkee vain hyväksytyn yhteenvedon',
    say: 'Ensimmäinen tapaaminen ei ala tyhjästä: tavoitteet, voinnin suunta ja harjoittelu ovat valmiina. Harjoittelu näkyy '
      + 'Annalle Samin luvalla, ajatuspäiväkirjan merkinnät vain, jos Sami jakaa ne.',
    act: async (p) => ok(await p.mutate((s) => api.firstSession(s, AINO))),
    show: async (p) => { p.go({ role: 'therapist' }); await p.spot('.doc-card'); } },
  { stage: 'terapia', title: 'Terapeutti määrittää välituen ja välitehtävän',
    say: 'Päätavoite, sallitut KKT-harjoitukset, viikoittainen välitehtävä ja check-in-tiheys – tekoäly toimii vain näissä rajoissa.',
    show: async (p) => { p.go({ role: 'therapist' }); await p.spot('.plan-card'); } },
  { stage: 'terapia', title: 'Tallenna ja ota käyttöön',
    say: 'Mieliluotsi siirtyy odotusajan protokollasta terapeutin ohjaamaksi välitueksi, ja Sami saa siitä ilmoituksen.',
    act: async (p) => {
      const row = p.view().therapist.selected?.clients.find((c) => c.clientId === AINO);
      const plan = row?.therapy.suggestedPlan;
      return plan ? ok(await p.mutate((s) => api.savePlan(s, ANNA, AINO, plan))) : false;
    },
    show: async (p) => { p.go({ role: 'therapist' }); await p.spot('.plan-card'); } },
  { stage: 'terapia', title: 'Sami näkee terapeutin määrittämän välituen',
    say: 'Välitehtävä ja harjoitukset tapaamisten välillä – terapeutin rajaamina.',
    show: async (p) => { p.go({ role: 'client', tab: 'polku' }); await p.spot('.cx-modecard'); } },

  // 10 · Seuranta terapian jälkeen
  { stage: 'jalkeen', title: 'Terapia päättyy – seuranta jatkuu',
    say: 'Ylläpitosuunnitelma ja merkit, joihin reagoida. Mieliala ja ahdistus kerran viikossa, ja muutos palaa hoitotiimille.',
    act: async (p) => ok(await p.mutate((s) => api.demoEndTherapy(s, AINO))),
    show: async (p) => { p.go({ role: 'client', tab: 'polku' }); await p.spot('.cx-modecard'); } },
];

/** The first step of each stage – where a click on the stage takes the demo. */
export function stageStart(stage: StageKey): number {
  return Math.max(0, BEATS.findIndex((b) => b.stage === stage));
}

/** The index of a stage's last step. */
export function stageEnd(stage: StageKey): number {
  return BEATS.reduce((last, beat, i) => (beat.stage === stage ? i : last), -1);
}

/* How far Sami's story has come, as the index of the last step whose change is in the state. It lets a step notice that
   it was already done by hand (skip it) and that the state is behind (rebuild it first). */
function progress(view: ValitukiView): number {
  const client = view.client;
  if (!client || client.id !== AINO) return -1;
  const intake = client.intake.status;
  if (intake === 'not_started' || intake === 'consent') return 0;
  if (intake === 'conversation') return 1;
  if (intake === 'review') return 2;
  if (intake === 'rhythm' || client.checkIn.needsBaseline) return 3;
  const row = view.therapist.selected?.clients.find((c) => c.clientId === AINO);
  const stage = client.matching.stage;
  if (stage === 'aftercare' || client.modeKey === 'aftercare_support') return 23;
  if (row?.therapy.config) return 21;
  if (row?.therapy.episodeStatus === 'active') return 19;
  if (client.matching.handover?.status === 'approved') return 18;
  if (stage === 'booked' || stage === 'therapy') return 16;
  if (stage === 'choose') return 14;
  const pro = view.professional.details[AINO];
  if (pro?.observations.some((o) => o.kind === 'trend_decline')) {
    if (pro.openReview) return 8;
    return client.memory.pending.some((i) => i.kind === 'pattern') ? 12 : 13;
  }
  if (daysBetween(view.meta.demoStartDate, view.meta.currentDate) >= 14) return 7;  // the decline is still to come
  if (client.practice.thoughtRecords.length > 0) return 7;
  if (client.guided?.tool === 'thought_record') return 6;
  if (client.chat.some((m) => m.role === 'client')) return 5;
  return 4;
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(to.slice(0, 10)) - Date.parse(from.slice(0, 10))) / 86_400_000);
}

/** The prepared scenes and the step whose state each one equals – a jump rebuilds the nearest one and replays the rest. */
const SCENE_AFTER: [scene: string, beat: number][] = [
  ['start', 0], ['intake', 4], ['cbt', 7], ['reviewed', 13], ['matches', 14], ['handover', 18], ['therapy', 21],
  ['aftercare', 23],
];

const lastActBefore = (index: number) => {
  for (let i = index - 1; i >= 0; i -= 1) if (BEATS[i].act) return i;
  return -1;
};

const frame = () => new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));

function scrollParent(el: HTMLElement): HTMLElement | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const overflow = getComputedStyle(node).overflowY;
    if ((overflow === 'auto' || overflow === 'scroll') && node.scrollHeight > node.clientHeight + 2) return node;
  }
  return null;
}

async function findVisible(selectors: string[], timeout = 2500): Promise<HTMLElement | null> {
  const until = Date.now() + timeout;
  while (Date.now() < until) {
    for (const selector of selectors) {
      const el = Array.from(document.querySelectorAll<HTMLElement>(selector)).find((e) => e.getClientRects().length > 0);
      if (el) return el;
    }
    await frame();
  }
  return null;
}

function scrollToElement(el: HTMLElement, block: 'start' | 'center') {
  const container = scrollParent(el);
  const rect = el.getBoundingClientRect();
  if (container) {
    const box = container.getBoundingClientRect();
    // The phone is scaled with CSS zoom: screen pixels → the container's own pixels.
    const scale = box.height / (container.offsetHeight || box.height) || 1;
    const height = rect.height / scale;
    const offset = (rect.top - box.top) / scale + container.scrollTop;
    const top = block === 'center' ? offset - (container.clientHeight - height) / 2 : offset - 12;
    container.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    return;
  }
  // The page itself scrolls: keep the element below the sticky top bar and demo dock (beside the panel it covers nothing).
  const covered = document.querySelector('.dock:not(.is-side)')?.getBoundingClientRect().bottom ?? 0;
  const offset = rect.top + window.scrollY;
  const top = block === 'center' ? offset - (window.innerHeight - covered - rect.height) / 2 - covered : offset - covered - 16;
  window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
}

function readPointer(): number {
  try {
    const value = Number(window.sessionStorage.getItem(STORAGE_KEY));
    return Number.isInteger(value) && value >= 0 && value <= BEATS.length ? value : 0;
  } catch {
    return 0;
  }
}

export interface DemoPilot {
  /** How many steps are done – BEATS[pointer] is the next one. */
  pointer: number;
  running: boolean;
  failed: boolean;
  next: () => Promise<void>;
  prev: () => Promise<void>;
  /** Go to step `index`: rebuild the demo to just before it and take it. */
  enter: (index: number) => Promise<void>;
  /** The rest of the stage the next step belongs to, at once: no presses or pauses in between (Shift+→). */
  finishStage: () => Promise<void>;
  restart: () => void;
  replay: () => Promise<void>;
}

export function useDemoPilot(): DemoPilot {
  const ctx = useValituki();
  const [stored, setPointerState] = useState(readPointer);
  // Clicking ahead in the app by hand moves the demo along too: once the demo has started, the pointer never trails the state.
  // It only follows steps that change the state, so a step that just shows something is never skipped or pulled back.
  const pointer = stored > 0 ? Math.max(stored, lastActBefore(progress(ctx.view) + 1) + 1) : 0;
  const [running, setRunning] = useState(false);
  const [failed, setFailed] = useState(false);
  const latest = useRef(ctx.view);
  const ctxRef = useRef(ctx);
  const runningRef = useRef(false);
  // → while a step plays (a conversation) finishes it at once, like skipping an animation in a slide show.
  const hurryRef = useRef(false);
  // The steps run in event handlers: they read the newest view and context through refs, synced after every render.
  useEffect(() => {
    latest.current = ctx.view;
    ctxRef.current = ctx;
  });

  const setPointer = useCallback((value: number) => {
    setPointerState(value);
    try { window.sessionStorage.setItem(STORAGE_KEY, String(value)); } catch { /* the pointer just is not remembered */ }
  }, []);

  const pilot = useCallback((fast: boolean): PilotCtx => ({
    view: () => latest.current,
    mutate: async (call) => {
      let fresh: ValitukiView | null = null;
      await ctxRef.current.run(async () => {
        const response = await call(SCOPE);
        fresh = response.view;
        return response;
      });
      if (!fresh) return null;  // the app already shows the error
      latest.current = fresh;
      return fresh;
    },
    go: (where) => {
      if (fast) return;
      const c = ctxRef.current;
      c.setClientId(AINO);
      c.setTherapistId(ANNA);
      if (where.role === 'client') c.setClientTab(where.tab);
      if (where.role === 'professional') { c.setProTab('jono'); c.setProClientId(where.client); }
      if (c.role !== where.role) c.setRole(where.role);
    },
    spot: async (selectors, block = 'start') => {
      if (fast) return null;
      await frame();
      await frame();
      const el = await findVisible(Array.isArray(selectors) ? selectors : [selectors]);
      if (!el) return null;
      scrollToElement(el, block);
      el.classList.remove('pilot-spot');
      void el.offsetWidth;  // restart the pulse
      el.classList.add('pilot-spot');
      window.setTimeout(() => el.classList.remove('pilot-spot'), 2600);
      return el;
    },
    pause: (ms) => (fast || hurryRef.current ? Promise.resolve() : sleep(ms)),
    settle: async () => {
      if (fast) return;
      await sleep(60);  // the new view renders and the chat starts showing the reply
      await frame();
      const until = Date.now() + 20000;
      while (chatRevealing() && Date.now() < until) await sleep(100);
    },
  }), []);

  /** Bring the state to "after step index − 1": the nearest prepared scene, then the remaining steps without pauses. */
  const rebuild = useCallback(async (index: number): Promise<boolean> => {
    const target = index - 1;
    const [scene, after] = [...SCENE_AFTER].reverse().find(([, beat]) => beat <= target) ?? SCENE_AFTER[0];
    const quiet = pilot(true);
    hurryChat(true);  // a rebuilt conversation appears at once
    try {
      if (!(await quiet.mutate((s) => api.scene(s, scene)))) return false;
      for (let i = after + 1; i <= target; i += 1) {
        const act = BEATS[i].act;
        if (act && !(await act(quiet))) return false;
      }
      return true;
    } finally {
      await sleep(60);  // the last rebuilt view renders while the chat is still hurried
      hurryChat(hurryRef.current);
    }
  }, [pilot]);

  const guard = useCallback(async (task: () => Promise<boolean>) => {
    if (runningRef.current) return;
    runningRef.current = true;
    setRunning(true);
    setFailed(false);
    try {
      if (!(await task())) setFailed(true);
    } finally {
      if (hurryRef.current) await sleep(60);  // a hurried step's last reply renders at once too
      runningRef.current = false;
      hurryRef.current = false;
      hurryChat(false);
      setRunning(false);
    }
  }, []);

  /** The steps judge progress from Sami's and Anna's view – another demo client or therapist may be on screen. */
  const ensureScope = useCallback(async () => {
    const view = latest.current;
    if (view.client?.id === AINO && view.therapist.selected?.id === ANNA) return;
    try { latest.current = await api.view(SCOPE); } catch { /* judged from the view on screen */ }
  }, []);

  /** Take step `index` from the state it needs: the change (unless already made) and then the view. */
  const perform = useCallback(async (index: number) => {
    const beat = BEATS[index];
    if (!beat) return true;
    const live = pilot(false);
    await ensureScope();
    // The cue changes at once: the presenter talks while the step plays (a replayed conversation takes a few seconds).
    setPointer(index + 1);
    const done = (index === 0 || !(progress(latest.current) < lastActBefore(index)) || await rebuild(index))
      && (!beat.act || (index > 0 && progress(latest.current) >= index) || await beat.act(live));
    if (!done) {
      setPointer(index);
      return false;
    }
    await beat.show(live);
    return true;
  }, [ensureScope, pilot, rebuild, setPointer]);

  const next = useCallback(async () => {
    if (runningRef.current) {
      hurryRef.current = true;
      hurryChat(true);
      return;
    }
    await guard(() => perform(pointer));
  }, [guard, perform, pointer]);

  // A stage on the rail: rebuild the demo to just before the stage's first step and take that step, so the stage is on
  // the screen at once.
  const enter = useCallback((index: number) => guard(async () => {
    const target = Math.max(0, Math.min(BEATS.length - 1, index));
    if (target > 0 && !(await rebuild(target))) return false;
    return perform(target);
  }), [guard, perform, rebuild]);

  // "Vaihe loppuun": every remaining step of the stage in a row without pauses – the chat shows each reply whole – and then
  // the view of the stage's last step. While a step plays, it finishes that step at once like Seuraava.
  const finishStage = useCallback(async () => {
    if (runningRef.current) {
      hurryRef.current = true;
      hurryChat(true);
      return;
    }
    await guard(async () => {
      const start = pointer;
      if (!BEATS[start]) return true;
      const end = stageEnd(BEATS[start].stage);
      await ensureScope();
      hurryRef.current = true;
      hurryChat(true);
      setPointer(end + 1);
      if (start > 0 && progress(latest.current) < lastActBefore(start) && !(await rebuild(start))) {
        setPointer(start);
        return false;
      }
      const quiet = pilot(true);
      for (let i = start; i <= end; i += 1) {
        const act = BEATS[i].act;
        if (act && !(i > 0 && progress(latest.current) >= i) && !(await act(quiet))) {
          setPointer(i);
          return false;
        }
      }
      await BEATS[end].show(pilot(false));
      return true;
    });
  }, [ensureScope, guard, pilot, pointer, rebuild, setPointer]);

  const back = useCallback((index: number) => guard(async () => {
    const target = Math.max(1, Math.min(BEATS.length, index));
    if (!(await rebuild(target))) return false;
    setPointer(target);
    await BEATS[target - 1].show(pilot(false));
    return true;
  }), [guard, pilot, rebuild, setPointer]);

  const prev = useCallback(async () => {
    if (pointer <= 1 || runningRef.current) return;
    // A step that only showed something is undone by showing the one before it; a step that changed the state is rebuilt.
    if (!BEATS[pointer - 1].act) {
      await guard(async () => {
        setPointer(pointer - 1);
        await BEATS[pointer - 2].show(pilot(false));
        return true;
      });
      return;
    }
    await back(pointer - 1);
  }, [back, guard, pilot, pointer, setPointer]);

  const restart = useCallback(() => setPointer(0), [setPointer]);

  /** "Toista demokeskustelu": plays the rest of the intake or of the guided exercise that is open now. */
  const replay = useCallback(() => guard(async () => {
    await ensureScope();
    const client = latest.current.client;
    if (client?.intake.status === 'conversation') return playIntake(pilot(false));
    if (client?.guided) return playGuided(pilot(false));
    return true;
  }), [ensureScope, guard, pilot]);

  // Keyboard and presentation clickers: → / PageDown = next, ← / PageUp = back, Shift+→ = the rest of the stage. Typing
  // in a field is never hijacked.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest('input, textarea, select, [contenteditable="true"], [role="radiogroup"], [role="tablist"]')) return;
      if (event.shiftKey) {
        if (event.key === 'ArrowRight') {
          event.preventDefault();
          void finishStage();
        }
        return;
      }
      if (event.key === 'ArrowRight' || event.key === 'PageDown') {
        event.preventDefault();
        void next();
      } else if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
        event.preventDefault();
        void prev();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [finishStage, next, prev]);

  return { pointer, running, failed, next, prev, enter, finishStage, restart, replay };
}
