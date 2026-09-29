import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api';
import type { ViewScope } from './api';
import ClientApp from './client/ClientApp';
import DemoDock, { AISwitch } from './components/DemoDock';
import { ValitukiContext } from './context';
import type { ClientTab, ProTab, ValitukiContextValue } from './context';
import { PersonIcon, StethoscopeIcon, UsersIcon } from './icons';
import PitchScreen from './pitch/PitchScreen';
import ProfessionalApp from './pro/ProfessionalApp';
import TherapistApp from './therapist/TherapistApp';
import type { Mutation, Role, ValitukiView } from './types';

const ROLE_SLUGS: Record<Role, string> = { client: 'asiakas', professional: 'ammattilainen', therapist: 'terapeutti', pitch: 'konsepti' };
const SLUG_ROLES: Record<string, Role> = { asiakas: 'client', ammattilainen: 'professional', terapeutti: 'therapist', konsepti: 'pitch' };
const CLIENT_TABS: ClientTab[] = ['koti', 'keskustelu', 'harjoitukset', 'edistyminen', 'polku'];
// Deep links of the earlier client app keep working.
const OLD_TABS: Record<string, ClientTab> = { tanaan: 'koti', viestit: 'keskustelu', suunnitelma: 'harjoitukset', matkani: 'polku',
  terapeutti: 'polku', tietoni: 'koti' };
const DEFAULT_CLIENT = 'cl-aino';
const DEFAULT_THERAPIST = 'th-anna';

// Bumped by every mutation so that a view load started earlier never overwrites a newer mutation result.
let viewVersion = 0;

interface Route { role: Role; clientId: string; therapistId: string; tab: ClientTab; proClientId: string | null }

function parseHash(): Route {
  const [, roleSlug, id, tab] = window.location.hash.replace(/^#/, '').split('/');
  const role = SLUG_ROLES[roleSlug] ?? 'client';
  return {
    role,
    clientId: role === 'client' && id ? id : DEFAULT_CLIENT,
    therapistId: role === 'therapist' && id ? id : DEFAULT_THERAPIST,
    tab: CLIENT_TABS.includes(tab as ClientTab) ? (tab as ClientTab) : OLD_TABS[tab] ?? 'koti',
    proClientId: role === 'professional' && id ? id : null,
  };
}

export default function ValitukiApp() {
  const [initial] = useState(parseHash);
  const [role, setRoleState] = useState<Role>(initial.role);
  const [clientId, setClientIdState] = useState(initial.clientId);
  const [therapistId, setTherapistIdState] = useState(initial.therapistId);
  const [clientTab, setClientTab] = useState<ClientTab>(initial.tab);
  const [proTab, setProTab] = useState<ProTab>('jono');
  const [proClientId, setProClientId] = useState<string | null>(initial.proClientId);
  const [view, setView] = useState<ValitukiView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');

  const scope: ViewScope = useMemo(() => ({ clientId, therapistId }), [clientId, therapistId]);

  useEffect(() => {
    let ignore = false;
    const version = viewVersion;
    api.view(scope)
      .then((data) => {
        if (ignore || version !== viewVersion) return;
        setView(data);
        setError(null);
      })
      .catch((e: Error) => { if (!ignore) setError(e.message); });
    return () => { ignore = true; };
  }, [scope]);

  useEffect(() => {
    function onHashChange() {
      const route = parseHash();
      setRoleState(route.role);
      if (route.role === 'client') { setClientIdState(route.clientId); setClientTab(route.tab); }
      if (route.role === 'therapist') setTherapistIdState(route.therapistId);
      if (route.role === 'professional') setProClientId(route.proClientId);
    }
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  useEffect(() => {
    const id = role === 'client' ? `/${clientId}/${clientTab}` : role === 'therapist' ? `/${therapistId}`
      : role === 'professional' && proClientId ? `/${proClientId}` : '';
    const hash = `#/${ROLE_SLUGS[role]}${id}`;
    if (window.location.hash !== hash) window.history.replaceState(null, '', hash);
  }, [role, clientId, therapistId, clientTab, proClientId]);

  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(''), 5200);
    return () => window.clearTimeout(timer);
  }, [message]);

  // The phone and the backstage fill the screen below the top bar and the demo dock (--stage-top), whatever their height.
  // Measured again once the view has loaded: the demo dock only appears then.
  const stageRef = useRef<HTMLElement>(null);
  const loaded = view !== null;
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const update = () => {
      const top = Math.round(stage.getBoundingClientRect().top + window.scrollY);
      stage.parentElement?.style.setProperty('--stage-top', `${top}px`);
      // The phone keeps an iPhone's proportions (836 px tall at full size) and is scaled down to the room below the dock.
      const room = Math.min(860, Math.max(540, window.innerHeight - top - 28));
      stage.parentElement?.style.setProperty('--phone-zoom', String(Math.min(1, room / 836)));
      // The demo dock sticks right under the (sticky) top bar.
      const header = stage.parentElement?.querySelector<HTMLElement>('.topbar');
      if (header) stage.parentElement?.style.setProperty('--topbar-h', `${header.offsetHeight}px`);
    };
    update();
    const observer = new ResizeObserver(update);
    Array.from(stage.parentElement?.children ?? []).forEach((el) => { if (el !== stage) observer.observe(el); });
    window.addEventListener('resize', update);
    return () => { observer.disconnect(); window.removeEventListener('resize', update); };
  }, [role, loaded]);

  const run = useCallback(async <T,>(action: (s: ViewScope) => Promise<Mutation<T>>, describe?: (result: T) => string) => {
    setBusy(true);
    setError(null);
    viewVersion += 1;
    try {
      const response = await action(scope);
      setView(response.view);
      if (describe) setMessage(describe(response.result));
      return response.result;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }, [scope]);

  const setRole = useCallback((next: Role) => { setRoleState(next); window.scrollTo({ top: 0 }); }, []);

  const ctx: ValitukiContextValue | null = view && {
    view, scope, role, busy, run, announce: setMessage, setRole,
    setClientId: (id: string) => setClientIdState(id),
    setTherapistId: (id: string) => setTherapistIdState(id),
    clientTab, setClientTab, proTab, setProTab, proClientId, setProClientId,
  };

  const clientName = view?.demo.clients.find((c) => c.id === clientId)?.firstName;
  const therapistName = view?.demo.therapists.find((t) => t.id === therapistId)?.name.split(' ')[0];

  return (
    <div className={`vt role-${role}`}>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/konsepti" onClick={(e) => { e.preventDefault(); setRole('pitch'); }}>
            <BrandMark />
            <span className="brand-text">
              <span className="brand-name">Mieliluotsi</span>
              <span className="brand-tag">Tuki alkaa heti, vaikka terapia ei vielä ala.</span>
            </span>
          </a>
          {ctx && <ValitukiContext.Provider value={ctx}><div className="topbar-ai"><AISwitch /></div></ValitukiContext.Provider>}
          <nav className="roles" aria-label="Demo: näkymä">
            <span className="roles-label">Demo:</span>
            <div className="roles-group" role="group">
              <button type="button" aria-pressed={role === 'client'} onClick={() => setRole('client')}>
                <PersonIcon size={17} /> Asiakas{clientName ? <span className="role-who">{clientName}</span> : null}
              </button>
              <button type="button" aria-pressed={role === 'professional'} onClick={() => setRole('professional')}>
                <StethoscopeIcon size={17} /> Ammattilainen
              </button>
              <button type="button" aria-pressed={role === 'therapist'} onClick={() => setRole('therapist')}>
                <UsersIcon size={17} /> Terapeutti{therapistName ? <span className="role-who">{therapistName}</span> : null}
              </button>
            </div>
          </nav>
        </div>
      </header>

      {/* On every view, the Konsepti page included: the demo is driven from here (Seuraava / →). */}
      {ctx && <ValitukiContext.Provider value={ctx}><DemoDock /></ValitukiContext.Provider>}

      <main className="stage" id="main" ref={stageRef}>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        {!view && !error && <p className="loading" role="status">Ladataan Mieliluotsia…</p>}
        {ctx && (
          <ValitukiContext.Provider value={ctx}>
            {role === 'client' && <ClientApp />}
            {role === 'professional' && <ProfessionalApp />}
            {role === 'therapist' && <TherapistApp />}
            {role === 'pitch' && <PitchScreen />}
          </ValitukiContext.Provider>
        )}
      </main>

      <div className={`toast ${message ? 'toast-on' : ''}`} role="status" aria-live="polite">{message}</div>

    </div>
  );
}

/** A pilot's compass: a ring and a needle that shows the way – white towards the goal, mint behind – on a teal-to-green tile. */
function BrandMark() {
  return (
    <svg className="brand-mark" width="34" height="34" viewBox="0 0 34 34" aria-hidden="true">
      <defs>
        <linearGradient id="brand-tile" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#0d5f6f" />
          <stop offset="1" stopColor="#2a9d82" />
        </linearGradient>
      </defs>
      <rect width="34" height="34" rx="10" fill="url(#brand-tile)" />
      <circle cx="17" cy="17" r="10" fill="none" stroke="#fff" strokeOpacity="0.55" strokeWidth="1.6" />
      <g transform="rotate(40 17 17)">
        <path d="M17 8.2 20.2 17h-6.4Z" fill="#fff" />
        <path d="M13.8 17h6.4L17 25.8Z" fill="#bff0de" />
      </g>
      <circle cx="17" cy="17" r="1.5" fill="#0d5f6f" />
    </svg>
  );
}
