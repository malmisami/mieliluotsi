import { Fragment } from 'react';
import { useValituki } from '../context';
import { ArrowDownIcon, ArrowRightIcon, CheckIcon, ClockIcon, EyeIcon, HandHeartIcon, NodesIcon, PuzzleIcon, ShieldIcon, SparkleIcon, StethoscopeIcon, ThoughtIcon } from '../icons';

const BEFORE = ['Avun haku', 'Jono', 'Odotus', 'Odotus', 'Terapia'];
const AFTER_TOP = ['Avun haku', 'AI-alkukeskustelu'];
const AFTER_BOX = ['Mielialan ja ahdistuksen seuranta', 'Ohjattu KKT-harjoittelu chatissa', 'Muutosten tunnistus', 'Therapy Fit Profile'];
const AFTER_BOTTOM = ['Sopivin saatavilla oleva terapeutti', 'Valmis, asiakkaan hyväksymä handover', 'Terapia + välitehtävät Mieliluotsissa',
  'Seuranta terapian jälkeen'];
const CHAIN = ['Avun haku', 'Odotus', 'Proaktiivinen tuki', 'KKT-harjoittelu', 'Ihmisen valvonta', 'Terapeutin matching', 'Handover', 'Terapia',
  'Tuki tapaamisten välillä', 'Seuranta'];

const PRINCIPLES = [
  { icon: <ClockIcon size={20} />, title: 'Tuki alkaa heti', text: 'Hyödyllistä tukea siitä hetkestä, kun asiakas liitetään jonoon.' },
  { icon: <ThoughtIcon size={20} />, title: 'KKT kysymys kerrallaan', text: 'Tilanne → ajatus → tunne 0–10 → ajatusloukku → vaihtoehto → harjoitus.' },
  { icon: <ArrowRightIcon size={20} />, title: 'Jatkuvuus', text: 'Odotusaikana opittu jatkuu terapiassa – ja seurannassa sen jälkeen.' },
  { icon: <PuzzleIcon size={20} />, title: 'Läpinäkyvä matching', text: 'Selitettävät, eksplisiittiset kriteerit – ei mustaa laatikkoa.' },
  { icon: <EyeIcon size={20} />, title: 'Käyttäjä päättää', text: 'Mitä tallennetaan, jaetaan ja käytetään matchingissa.' },
  { icon: <StethoscopeIcon size={20} />, title: 'Ihminen päättää', text: 'AI ehdottaa ja tiivistää – hoito ja priorisointi ovat ammattilaisen.' },
];

const AGENTS = [
  { name: 'Tukiagentti', text: 'Chat ja ohjatut KKT-harjoitukset' },
  { name: 'Check-in-agentti', text: 'Mieliala, ahdistus, muistutukset' },
  { name: 'Havaintoagentti', text: 'Muutos omaan lähtötasoon' },
  { name: 'Matching-agentti', text: 'Deterministinen matching' },
  { name: 'Palveluohjausagentti', text: 'Seuraava askel ja siirtymät' },
  { name: 'Turvallisuusagentti', text: 'Voi keskeyttää kaiken' },
];

export default function PitchScreen() {
  const { setRole, setClientId, setClientTab } = useValituki();
  return (
    <div className="pitch">
      <section className="pitch-hero">
        <p className="pitch-kicker">Mieliluotsi</p>
        <h1 className="pitch-title">Passiivisesta jonosta aktiiviseksi hoitopoluksi</h1>
        <p className="pitch-lead">Tuki alkaa heti, vaikka terapia ei vielä ala. Jonosta ei tule passiivista odottamista, vaan aktiivinen osa hoitopolkua.</p>
      </section>

      <section className="pitch-compare" aria-label="Ennen ja Mieliluotsilla">
        <div className="flow flow-before">
          <p className="flow-label">Ennen</p>
          {BEFORE.map((step, i) => (
            <Fragment key={`${step}-${i}`}>
              <div className={`flow-step ${step === 'Odotus' ? 'flow-wait' : ''}`}>{step}</div>
              {i < BEFORE.length - 1 && <span className="flow-arrow" aria-hidden="true"><ArrowDownIcon size={18} /></span>}
            </Fragment>
          ))}
        </div>
        <div className="flow flow-after">
          <p className="flow-label">Mieliluotsilla</p>
          {AFTER_TOP.map((step) => (
            <Fragment key={step}>
              <div className="flow-step">{step}</div>
              <span className="flow-arrow" aria-hidden="true"><ArrowDownIcon size={18} /></span>
            </Fragment>
          ))}
          <div className="flow-box">
            <p className="flow-box-title"><SparkleIcon size={18} /> Mieliluotsi</p>
            <ul>{AFTER_BOX.map((item) => <li key={item}><CheckIcon size={15} /> {item}</li>)}</ul>
          </div>
          {AFTER_BOTTOM.map((step) => (
            <Fragment key={step}>
              <span className="flow-arrow" aria-hidden="true"><ArrowDownIcon size={18} /></span>
              <div className={`flow-step ${step.startsWith('Seuranta') ? 'flow-final' : ''}`}>{step}</div>
            </Fragment>
          ))}
        </div>
      </section>

      <section className="pitch-orchestration">
        <h2>Keskustelu edessä – säännöt, agentit ja ammattilaiset takana</h2>
        <ol className="chain">
          {CHAIN.map((step, i) => <li key={step}><span className="chain-n">{i + 1}</span>{step}</li>)}
        </ol>
      </section>

      <section className="pitch-agents">
        <div className="agents-diagram">
          <div className="orchestrator"><NodesIcon size={22} /><strong>Orkestroija</strong><span>päättää, mikä agentti toimii</span></div>
          <ul className="agent-ring">{AGENTS.map((a) => <li key={a.name}><strong>{a.name}</strong><span>{a.text}</span></li>)}</ul>
        </div>
        <div className="pitch-rules">
          <p><ShieldIcon size={18} /><span><strong>Säännöt päättävät, kielimalli vain muotoilee.</strong> Harjoitusten vaiheet, turvallisuustaso,
            matching ja tilat ovat deterministisiä; jokainen vastaus kulkee turvallisuustarkistuksen läpi.</span></p>
          <p><StethoscopeIcon size={18} /><span><strong>Ihminen päättää hoidosta.</strong> Mieliluotsi nostaa muutokset tarkistettaviksi – se ei muuta
            kiireellisyyttä.</span></p>
          <p><EyeIcon size={18} /><span><strong>Asiakas päättää tiedoistaan.</strong> Tulkinnat tallennetaan vasta hyväksyttyinä, ja jokaisella tiedolla on
            oma käyttöoikeus.</span></p>
        </div>
      </section>

      <section className="pitch-principles">
        {PRINCIPLES.map((p) => (
          <div key={p.title} className="principle"><span className="principle-icon">{p.icon}</span><strong>{p.title}</strong><p>{p.text}</p></div>
        ))}
      </section>

      <section className="pitch-close">
        <HandHeartIcon size={30} />
        <p className="pitch-quote">Mieliluotsi ei korvaa terapeuttia.</p>
        <p className="pitch-quote-2">Se tekee ajasta ennen terapiaa, tapaamisten välillä ja niiden jälkeen jatkuvan osan hoitopolkua.</p>
        <button type="button" className="btn btn-primary btn-lg" onClick={() => { setClientId('cl-aino'); setClientTab('koti'); setRole('client'); }}>
          Aloita demo: Sami on jonossa terapiaan <ArrowRightIcon size={18} />
        </button>
        <p className="muted small">Kaikki demon henkilöt ja terveystiedot ovat täysin kuvitteellisia.</p>
      </section>
    </div>
  );
}
