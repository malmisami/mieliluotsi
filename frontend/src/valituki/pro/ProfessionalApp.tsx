import type { ReactNode } from 'react';
import { useValituki } from '../context';
import type { ProTab } from '../context';
import { Logo } from '../components/Logo';
import { BarsIcon, ClockIcon, ListIcon, UsersIcon } from '../icons';
import AgentLog from './AgentLog';
import ClientReview from './ClientReview';
import Directory from './Directory';
import Impact from './Impact';
import Queue from './Queue';

const TABS: { key: ProTab; label: string; icon: ReactNode }[] = [
  { key: 'jono', label: 'Terapiajono', icon: <ListIcon size={17} /> },
  { key: 'loki', label: 'Mitä Mieliluotsi teki?', icon: <ClockIcon size={17} /> },
  { key: 'terapeutit', label: 'Terapeutit', icon: <UsersIcon size={17} /> },
  { key: 'vaikuttavuus', label: 'Vaikuttavuus', icon: <BarsIcon size={17} /> },
];

export default function ProfessionalApp() {
  const { view, proTab, setProTab, proClientId, setProClientId } = useValituki();
  const pro = view.professional;
  return (
    <div className="pro">
      <header className="pro-head">
        <div className="pro-brand"><Logo size={32} /></div>
        <p className="pro-kicker"><span className="pro-kicker-dot" aria-hidden="true" />Hoitotiimin näkymä · {pro.coordinatorName}</p>
        <h1 className="pro-title">Älykäs terapiajono</h1>
        <p className="pro-lede">Jonosta ei tule passiivista odottamista. Mieliluotsi nostaa muutokset tarkistettaviksi – ammattilainen päättää.</p>
      </header>
      <nav className="pro-tabs" aria-label="Ammattilaisen näkymät">
        {TABS.map((tab) => (
          <button key={tab.key} type="button" aria-current={proTab === tab.key && !proClientId ? 'page' : undefined}
            onClick={() => { setProTab(tab.key); setProClientId(null); }}>
            {tab.icon} {tab.label}{tab.key === 'jono' && pro.openTasks > 0 && <span className="count">{pro.openTasks}</span>}
          </button>
        ))}
      </nav>
      {proClientId && pro.details[proClientId] ? <ClientReview client={pro.details[proClientId]} /> : (
        <>
          {proTab === 'jono' && <Queue />}
          {proTab === 'loki' && <AgentLog />}
          {proTab === 'terapeutit' && <Directory />}
          {proTab === 'vaikuttavuus' && <Impact />}
        </>
      )}
    </div>
  );
}
