import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtDateTime, illative, partitive } from '../format';
import { CalendarIcon, CheckIcon, ChevronDownIcon, CrossIcon, EyeIcon, InfoIcon, PuzzleIcon, SparkleIcon, UsersIcon, VideoIcon } from '../icons';
import { HandoverDoc } from '../components/HandoverDoc';
import { Pill, Scale5, Segmented, SharingSummary, TypeTag } from '../components/ui';
import type { Candidate, FitProfile } from '../types';
import { useClientUI } from './ClientApp';

/** Finding the right therapist – from the Therapy Fit Profile to the choice, the first session and the handover. Shown in
    "Hoitopolku"; `embedded` drops the screen padding. */
export default function MatchingTab({ embedded = false }: { embedded?: boolean }) {
  const { client } = useClientUI();
  const matching = client.matching;
  return (
    <div className={embedded ? 'matching matching-embedded' : 'screen matching'}>
      {matching.stage === 'choose' && <Choose />}
      {['booked', 'therapy', 'aftercare'].includes(matching.stage) && <Booked />}
      {['no_profile', 'building', 'searching', 'on_hold'].includes(matching.stage) && <Searching />}
    </div>
  );
}

function Searching() {
  const { client } = useClientUI();
  const matching = client.matching;
  return (
    <>
      <h1 className="display-sm">Etsimme tilanteeseesi sopivaa terapeuttia</h1>
      <p className="muted">{matching.stage === 'on_hold'
        ? 'Terapeutin etsintä jatkuu, kun ammattilainen on tarkistanut tilanteesi.'
        : 'Kun sopivalta terapeutilta vapautuu aika, Mieliluotsi etsii vaihtoehdot heti ja kertoo, miksi kutakin ehdotetaan.'}</p>
      {client.fitProfile && <FitProfileCard profile={client.fitProfile} />}
      {matching.readiness && (
        <section className="card">
          <h3 className="card-title">Etsinnän edellytykset</h3>
          <ul className="criteria">
            {matching.readiness.map((c) => (
              <li key={c.key} className={c.passed ? 'ok' : 'todo'}>{c.passed ? <CheckIcon size={15} /> : <span className="dot-todo" />} {c.label}
                {c.detail && <span className="muted small"> · {c.detail}</span>}</li>
            ))}
          </ul>
        </section>
      )}
      <p className="notice"><InfoIcon size={16} /> Matching on deterministinen: ensin kovat ehdot (kieli, etävastaanotto, kapasiteetti, osaaminen), sitten
        läpinäkyvä painotettu sopivuus. Tekoäly ei valitse terapeuttia.</p>
    </>
  );
}

export function FitProfileCard({ profile }: { profile: FitProfile }) {
  return (
    <section className="card fit-card">
      <div className="card-row">
        <h3 className="card-title">Therapy Fit Profile</h3>
        <Pill tone="brand">versio {profile.version}</Pill>
      </div>
      <p className="muted small">Rakentuu odotuksen aikana vain hyväksymistäsi tiedoista.</p>
      <dl className="fit-dl">
        {profile.goals.primary.map((g) => (
          <div key={g.insightId}><dt>Tavoite</dt><dd>{g.text} <SharingSummary sharing={g} /></dd></div>
        ))}
        {profile.goals.secondary.map((g) => (
          <div key={g.insightId}><dt>Myös</dt><dd>{g.text}</dd></div>
        ))}
        {profile.preferredWorkingStyle.text && (
          <div><dt>Työskentelytapa</dt><dd>{String(profile.preferredWorkingStyle.text)} <SharingSummary sharing={{
            professional: Boolean(profile.preferredWorkingStyle.professional), matching: Boolean(profile.preferredWorkingStyle.matching) }} /></dd></div>
        )}
        {profile.practicalRows.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
        {profile.selfCareResponses.filter((r) => r.helpful).map((r) => (
          <div key={r.activityId}><dt>Toimiva keino</dt><dd>{r.title} ({r.latestRating}/5)</dd></div>
        ))}
      </dl>
    </section>
  );
}

function CandidateCard({ candidate, onSelect, busy }: { candidate: Candidate; onSelect: () => void; busy: boolean }) {
  const [open, setOpen] = useState(false);
  const [allReasons, setAllReasons] = useState(false);
  const t = candidate.therapist;
  const reasons = allReasons ? candidate.reasons : candidate.reasons.slice(0, 5);
  return (
    <article className={`cand cand-${candidate.label}`}>
      <header className="cand-head">
        <span className="avatar" aria-hidden="true">{t.name.split(' ').map((p) => p[0]).join('')}</span>
        <div>
          <h3 className="cand-name">{t.name}</h3>
          <p className="cand-role">{t.role}</p>
        </div>
      </header>
      <p className={`fit-label fit-${candidate.label}`}>{candidate.labelText.toUpperCase()}</p>
      <p className="cand-why-title">Miksi {t.firstName}?</p>
      <ul className="reasons">{reasons.map((r) => <li key={r}><CheckIcon size={15} /> {r}</li>)}</ul>
      {candidate.reasons.length > 5 && (
        <button type="button" className="link-btn" onClick={() => setAllReasons(!allReasons)}>
          {allReasons ? 'Näytä vähemmän' : `+ ${candidate.reasons.length - 5} muuta perustetta`}
        </button>
      )}
      <div className="slot-box">
        <span className="eyebrow">Ensimmäinen vapaa aika</span>
        <strong><CalendarIcon size={16} /> {candidate.firstSlotText}</strong>
      </div>
      <details className="unmet">
        <summary>Mitä toiveita ei pystytty täyttämään? <span className="unmet-count">{candidate.unmet.length || 'ei yhtään'}</span></summary>
        {candidate.unmet.length ? <ul>{candidate.unmet.map((u) => <li key={u}><CrossIcon size={13} /> {u}</li>)}</ul>
          : <p className="muted small">Kaikki kertomasi toiveet täyttyvät.</p>}
      </details>
      {open && (
        <div className="cand-more">
          <p>{t.bio}</p>
          <dl className="mini-dl">
            <div><dt>Menetelmä</dt><dd>{t.approaches.join(', ')}</dd></div>
            <div><dt>Työote</dt><dd>{t.workingStyle}</dd></div>
            <div><dt>Kielet</dt><dd>{t.languages.join(', ')}</dd></div>
            <div><dt>Vastaanotto</dt><dd>{t.formats.join(' · ')}</dd></div>
            <div><dt>Ajat</dt><dd>{t.availableTimes.join(', ')}</dd></div>
          </dl>
          <p className="muted small">{candidate.explanation}</p>
          <p className="synthetic-tag">{t.syntheticLabel}</p>
        </div>
      )}
      <div className="cand-actions">
        <button type="button" className="btn btn-secondary" onClick={() => setOpen(!open)}>
          {open ? 'Sulje' : `Tutustu ${illative(t.firstName)}`} <ChevronDownIcon size={15} />
        </button>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={onSelect}>Valitse</button>
      </div>
    </article>
  );
}

function Choose() {
  const { run, busy } = useValituki();
  const { client } = useClientUI();
  const matching = client.matching;
  const count = matching.candidates.length;
  const words: Record<number, string> = { 1: 'yhden', 2: 'kaksi', 3: 'kolme', 4: 'neljä', 5: 'viisi', 6: 'kuusi' };
  const first = matching.candidates[0];
  return (
    <>
      <p className="eyebrow eyebrow-ok"><SparkleIcon size={14} /> Terapeutin löytäminen</p>
      <h1 className="display-sm">{count === 1 ? 'Löysimme yhden tilanteeseesi sopivan terapeutin.' : `Löysimme ${words[count] ?? count} tilanteeseesi sopivaa terapeuttia.`}</h1>
      <p className="muted">Järjestys perustuu hyväksymiisi tietoihin ja läpinäkyviin kriteereihin – ei todennäköisyyteen. {first ? `Miksi suosittelemme ${partitive(first.therapist.firstName)}? Katso perustelut.` : ''}</p>
      <div className="cands">
        {matching.candidates.map((candidate) => (
          <CandidateCard key={candidate.id} candidate={candidate} busy={busy}
            onSelect={() => run((s) => api.selectCandidate(s, client.id, candidate.id),
              () => `Valitsit: ${candidate.therapist.name}. Ensimmäinen aika varattiin – tarkista yhteenveto.`)} />
        ))}
      </div>
      <div className="stack-sm">
        {matching.decision?.canShowMore && (
          <button type="button" className="btn btn-secondary btn-block" disabled={busy}
            onClick={() => run((s) => api.moreCandidates(s, client.id), (r) => (r.added ? `${r.added} lisävaihtoehtoa.` : 'Muita vaihtoehtoja ei juuri nyt ole.'))}>
            Näytä muut vaihtoehdot
          </button>
        )}
        <button type="button" className="btn btn-quiet btn-block" disabled={busy || matching.decision?.helpRequested}
          onClick={() => run((s) => api.matchingHelp(s, client.id, ''), () => 'Pyyntö välitettiin hoitotiimille.')}>
          <UsersIcon size={17} /> {matching.decision?.helpRequested ? 'Ammattilainen auttaa valinnassa – pyyntö välitetty' : 'Haluan ammattilaisen auttavan valinnassa'}
        </button>
      </div>
      {first && (
        <details className="data-used card">
          <summary>Mitä tietoja matchingissa käytettiin?</summary>
          <p className="section-label"><PuzzleIcon size={14} /> Käytettiin</p>
          <ul>{first.dataUsed.map((d) => <li key={d}>{d}</li>)}</ul>
          <p className="section-label"><EyeIcon size={14} /> Ei käytetty</p>
          <ul>{first.dataNotUsed.map((d) => <li key={d}>{d}</li>)}</ul>
        </details>
      )}
    </>
  );
}

// Summary items shown only in the therapist's view.
const CLIENT_HIDDEN = new Set(['sources', 'ai_summary']);

function Booked() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const matching = client.matching;
  const booking = matching.booking;
  const handover = matching.handover;
  if (!booking) return null;
  const therapy = matching.stage === 'therapy' || matching.stage === 'aftercare';
  return (
    <>
      <section className="booking-card">
        <p className="eyebrow">{matching.stage === 'aftercare' ? 'Terapia päättynyt – seuranta jatkuu' : therapy ? 'Terapeuttisi' : 'Ensimmäinen tapaaminen'}</p>
        {matching.stage === 'aftercare' ? (
          <p className="booking-when"><UsersIcon size={20} /> {booking.therapist.name}</p>
        ) : (
          <p className="booking-when"><CalendarIcon size={20} /> {booking.startText}</p>
        )}
        <p className="booking-who">{matching.stage === 'aftercare' ? `Terapia alkoi ${booking.startText.toLowerCase()}` : booking.therapist.name} · <VideoIcon size={15} /> {booking.format}</p>
        <p className="synthetic-tag">{booking.therapist.syntheticLabel}</p>
      </section>

      {matching.stage === 'therapy' && <MatchFeedback />}

      {handover && (
        <section className="card handover-card">
          <div className="card-row">
            <h2 className="card-title-lg">Yhteenveto ensimmäistä tapaamista varten</h2>
          </div>
          {handover.status === 'approved' ? (
            <p className="banner banner-ok"><CheckIcon size={17} /> Hyväksyit yhteenvedon {fmtDateTime(handover.approvedAt)}. {handover.therapistName} näkee vain alla olevat kohdat.</p>
          ) : (
            <p className="muted">Tämä on luonnos. Mitään ei jaeta ennen kuin hyväksyt sen. Voit muokata tai poistaa kohtia – keskusteluhistoriaa ei jaeta.</p>
          )}
          <div className="type-legend" aria-label="Tietotyypit">
            {(['user_said', 'measured', 'ai_summary', 'professional_note'] as const).map((t) => <TypeTag key={t} type={t} />)}
          </div>
          {/* The sources list and the AI summary are for the therapist's view – the client sees the items themselves. */}
          <HandoverDoc sections={handover.sections.filter((x) => !CLIENT_HIDDEN.has(x.key))} editable busy={busy}
            onRemove={(section) => run((s) => api.updateHandover(s, client.id, { action: 'remove', section }), () => 'Kohta poistettiin yhteenvedosta.')}
            onRestore={(section) => run((s) => api.updateHandover(s, client.id, { action: 'restore', section }))}
            onEditText={(section, text) => run((s) => api.updateHandover(s, client.id, { action: 'edit', section, text }), () => 'Muokkaus tallennettiin.')}
            onEditQuestions={(questions) => run((s) => api.updateHandover(s, client.id, { action: 'edit', section: 'questions', questions }))} />
          <div className="stack-sm">
            {handover.status !== 'approved' ? (
              <button type="button" className="btn btn-primary btn-lg btn-block" disabled={busy}
                onClick={() => run((s) => api.approveHandover(s, client.id), () => `Yhteenveto jaettiin: ${handover.therapistName} näkee vain hyväksymäsi kohdat.`)}>
                <CheckIcon size={18} /> Hyväksy jaettavaksi
              </button>
            ) : (
              <button type="button" className="btn btn-quiet btn-block" disabled={busy}
                onClick={() => run((s) => api.withdrawHandover(s, client.id), () => 'Jakaminen peruttiin.')}>Peru jakaminen</button>
            )}
            <p className="muted small">{view.meta.syntheticNotice}</p>
          </div>
        </section>
      )}

    </>
  );
}

function MatchFeedback() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const given = client.matching.feedback.given;
  const [heard, setHeard] = useState<number | null>(null);
  const [goals, setGoals] = useState<number | null>(null);
  const [style, setStyle] = useState<number | null>(null);
  const [cont, setCont] = useState<'yes' | 'unsure' | 'no'>('yes');
  const [discuss, setDiscuss] = useState(false);
  const labels = { '1': 'Ei lainkaan', '2': 'Vähän', '3': 'Jonkin verran', '4': 'Paljon', '5': 'Täysin' };
  if (given.length) {
    const last = given[given.length - 1];
    return (
      <section className={`banner ${last.negative ? 'banner-warn' : 'banner-ok'}`}>
        <CheckIcon size={17} />
        <p>{last.negative ? 'Kiitos palautteesta. Terapeuttia ei vaihdeta automaattisesti – hoitotiimi ottaa yhteyttä ja käy tilanteen kanssasi läpi.'
          : 'Kiitos palautteesta! Se auttaa arvioimaan, miten hyvin matching toimii.'}</p>
      </section>
    );
  }
  return (
    <section className="card feedback-card">
      <h3 className="card-title">Miltä yhteistyö terapeutin kanssa tuntuu?</h3>
      <p className="muted small">Vastaukset eivät vaihda terapeuttia automaattisesti. Kielteinen palaute avaa keskustelun ammattilaisen kanssa.</p>
      <p className="q">Tunsinko tulleeni kuulluksi?</p>
      <Scale5 name="Tunsinko tulleeni kuulluksi?" value={heard} onChange={setHeard} labels={labels} />
      <p className="q">Ymmärsikö terapeutti tavoitteeni?</p>
      <Scale5 name="Ymmärsikö terapeutti tavoitteeni?" value={goals} onChange={setGoals} labels={labels} />
      <p className="q">Tuntuiko työskentelytapa sopivalta?</p>
      <Scale5 name="Tuntuiko työskentelytapa sopivalta?" value={style} onChange={setStyle} labels={labels} />
      <p className="q">Haluanko jatkaa tämän terapeutin kanssa?</p>
      <Segmented label="Haluanko jatkaa?" value={cont} onChange={setCont}
        options={[{ value: 'yes', label: 'Kyllä' }, { value: 'unsure', label: 'En ole varma' }, { value: 'no', label: 'En' }]} />
      <label className="check-row"><input type="checkbox" checked={discuss} onChange={(e) => setDiscuss(e.target.checked)} /> Haluan keskustella toisesta vaihtoehdosta</label>
      <button type="button" className="btn btn-primary btn-block" disabled={busy || !heard || !goals || !style}
        onClick={() => run((s) => api.matchFeedback(s, client.id, { heard: heard ?? 3, goalsUnderstood: goals ?? 3, styleFit: style ?? 3,
          wantContinue: cont, wantDiscussAlternative: discuss, note: '' }), (negative) => (negative
          ? 'Palaute välitettiin: hoitotiimi saa tarkistuspyynnön (Matching review requested).' : 'Kiitos palautteesta!'))}>
        Lähetä palaute
      </button>
      <p className="muted small">{view.meta.syntheticNotice}</p>
    </section>
  );
}

