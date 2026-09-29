import { createContext, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import type { ClientTab } from '../context';
import { ArrowLeftIcon, BellIcon, ChatIcon, GridIcon, HomeIcon, LifebuoyIcon, RouteIcon, TrendIcon } from '../icons';
import { HelpSheet, SafetyScreen } from '../components/Safety';
import StageControls from '../components/StageControls';
import type { ClientView } from '../types';
import ActivitySheet from './ActivitySheet';
import Backstage from './Backstage';
import ChatTab from './ChatTab';
import ContactSheet from './ContactSheet';
import DataTab from './DataTab';
import HomeTab from './HomeTab';
import Intake from './Intake';
import NoticesPage from './NoticesPage';
import PathTab from './PathTab';
import ProgressTab from './ProgressTab';
import ToolsTab from './ToolsTab';

export type SheetState = { type: 'activity'; activityId: string } | { type: 'help' } | { type: 'contact'; reason?: string } | null;
export type PageState = 'profile' | 'notices' | null;

interface ClientUI {
  client: ClientView;
  openSheet: (sheet: SheetState) => void;
  openPage: (page: PageState) => void;
  openTab: (tab: ClientTab) => void;
  /** Start a guided tool (check-in or a CBT exercise) and continue in the chat. */
  startTool: (tool: string, prefill?: Record<string, unknown>, from?: string) => Promise<void>;
  /** Send a free-text message and continue in the chat. Resolves to false when it could not be sent. */
  send: (text: string) => Promise<boolean>;
  /** The client's own message while the reply is on its way (a live model can take a few seconds). */
  pending: string | null;
  /** Show `label` as the client's pending message while `action` runs. */
  withPending: <T>(label: string, action: () => Promise<T>) => Promise<T>;
  /** Answer "Miten voit tänään?" – the open check-in question, or a new check-in that starts with this answer. */
  answerMood: (mood: number) => Promise<void>;
  /** "Kerro, miten meni" / "Tein tämän" / "Aloita" on an agreed task. */
  doTask: (taskId: string) => Promise<void>;
}

const ClientUIContext = createContext<ClientUI | null>(null);

export function useClientUI(): ClientUI {
  const ctx = useContext(ClientUIContext);
  if (!ctx) throw new Error('useClientUI outside ClientApp');
  return ctx;
}

const TABS: { key: ClientTab; label: string; icon: ReactNode }[] = [
  { key: 'koti', label: 'Koti', icon: <HomeIcon size={21} /> },
  { key: 'keskustelu', label: 'Keskustelu', icon: <ChatIcon size={21} /> },
  { key: 'harjoitukset', label: 'Harjoitukset', icon: <GridIcon size={21} /> },
  { key: 'edistyminen', label: 'Edistyminen', icon: <TrendIcon size={21} /> },
  { key: 'polku', label: 'Hoitopolku', icon: <RouteIcon size={21} /> },
];

export default function ClientApp() {
  const { view, clientTab, setClientTab, run, busy } = useValituki();
  const [sheet, setSheet] = useState<SheetState>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [opened, setOpened] = useState<{ page: PageState; clientId: string | null }>({ page: null, clientId: null });
  const scrollRef = useRef<HTMLDivElement>(null);
  const client = view.client;
  // A page (Tietoni, Viestit) belongs to the client it was opened for; switching the demo client closes it.
  const page = opened.clientId === client?.id ? opened.page : null;
  const setPage = (next: PageState) => setOpened({ page: next, clientId: client?.id ?? null });

  // A new tab, client, intake step or matching stage starts from the top of the screen.
  useEffect(() => { scrollRef.current?.scrollTo({ top: 0 }); }, [clientTab, client?.id, client?.intake.status, client?.matching.stage]);

  if (!client) return <p className="muted">Valitse demoasiakas demo-ohjauksesta.</p>;
  const current = client;
  const inIntake = current.intake.status !== 'completed' && ['INVITED', 'INTAKE'].includes(current.journeyState);
  const locked = current.safety.lockActive;

  function openTab(tab: ClientTab) {
    setPage(null);
    setClientTab(tab);
  }

  function openPage(next: PageState) {
    setPage(next);
    if (next === 'notices' && current.unreadCount > 0) void run((s) => api.markNotificationsRead(s, current.id));
  }

  async function startTool(tool: string, prefill: Record<string, unknown> = {}, from = 'chat') {
    const result = await run((s) => api.startPractice(s, current.id, tool, prefill, from));
    if (result) openTab('keskustelu');
  }

  async function withPending<T>(label: string, action: () => Promise<T>): Promise<T> {
    setPending(label.trim() || null);
    try {
      return await action();
    } finally {
      setPending(null);
    }
  }

  async function send(text: string) {
    const value = text.trim();
    if (!value) return false;
    openTab('keskustelu');
    return (await withPending(value, () => run((s) => api.sendMessage(s, current.id, value)))) !== null;
  }

  async function answerMood(mood: number) {
    const guided = current.guided;
    openTab('keskustelu');
    if (guided?.tool === 'checkin' && guided.stepKey === 'mood') {
      await run((s) => api.answerPractice(s, current.id, { sessionId: guided.id, stepKey: 'mood', value: mood }));
    } else {
      await run((s) => api.startPractice(s, current.id, 'checkin', { mood }, 'home'));
    }
  }

  async function doTask(taskId: string) {
    const task = current.practice.tasks.find((t) => t.id === taskId);
    const result = await run((s) => api.clientTaskAction(s, current.id, taskId, 'done'),
      (r) => (r.started ? '' : `Kirjattu: ${task?.title ?? 'harjoitus'}.`));
    if (result && result.started) openTab('keskustelu');
  }

  const ui: ClientUI = { client: current, openSheet: setSheet, openPage, openTab, startTool, send, pending, withPending, answerMood, doTask };
  const initial = current.firstName.slice(0, 1);

  return (
    <ClientUIContext.Provider value={ui}>
      <div className="client-stage">
        <StageControls side />
        <div className="phone cx" aria-label={`Asiakkaan sovellus: ${current.displayName}`}>
          <div className="phone-inner">
            {inIntake ? (
              <header className="app-bar">
                <span className="app-title">Mieliluotsi</span>
                <button type="button" className="help-btn" onClick={() => setSheet({ type: 'help' })}>
                  <LifebuoyIcon size={17} /> Apua nyt
                </button>
              </header>
            ) : (
              <header className="cx-bar">
                <button type="button" className="cx-sos" onClick={() => setSheet({ type: 'help' })}>
                  <LifebuoyIcon size={16} /> Apua nyt
                </button>
                <div className="cx-bar-actions">
                  <button type="button" className="cx-icon-btn" aria-label={`Viestit Mieliluotsilta${current.unreadCount ? ` – ${current.unreadCount} uutta` : ''}`}
                    onClick={() => openPage('notices')}>
                    <BellIcon size={20} />
                    {current.unreadCount > 0 && <span className="cx-badge" aria-hidden="true" />}
                  </button>
                  <button type="button" className="cx-avatar" aria-label="Tietoni ja suostumukset" onClick={() => openPage('profile')}>{initial}</button>
                </div>
              </header>
            )}
            {inIntake ? (
              <div className="phone-scroll" ref={scrollRef}><Intake /></div>
            ) : clientTab === 'keskustelu' ? (
              <ChatTab />
            ) : (
              <div className="phone-scroll" ref={scrollRef}>
                {clientTab === 'koti' && <HomeTab />}
                {clientTab === 'harjoitukset' && <ToolsTab />}
                {clientTab === 'edistyminen' && <ProgressTab />}
                {clientTab === 'polku' && <PathTab />}
              </div>
            )}
            {!inIntake && (
              <nav className="cx-nav" aria-label="Asiakkaan navigaatio">
                {TABS.map((tab) => (
                  <button key={tab.key} type="button" aria-current={clientTab === tab.key && !page ? 'page' : undefined} onClick={() => openTab(tab.key)}>
                    <span className="cx-nav-icon">
                      {tab.icon}
                      {tab.key === 'keskustelu' && current.guided && <span className="cx-badge cx-badge-live" aria-label="Harjoitus kesken" />}
                    </span>
                    <span className="cx-nav-label">{tab.label}</span>
                  </button>
                ))}
              </nav>
            )}
            {page === 'profile' && <Page title="Tietoni" onBack={() => setPage(null)}><DataTab /></Page>}
            {page === 'notices' && <Page title="Viestit Mieliluotsilta" onBack={() => setPage(null)}><NoticesPage /></Page>}
            {sheet?.type === 'activity' && <ActivitySheet activityId={sheet.activityId} onClose={() => setSheet(null)} />}
            {sheet?.type === 'contact' && <ContactSheet initialReason={sheet.reason} onClose={() => setSheet(null)} />}
            {sheet?.type === 'help' && (
              <HelpSheet safety={view.meta.safety} busy={busy} onClose={() => setSheet(null)}
                onContact={() => setSheet({ type: 'contact' })}
                onHelpNow={() => { setSheet(null); void run((s) => api.helpNow(s, current.id), () => 'Turvallisuusohjeet näytettiin. Hoitotiimin työjonoon syntyi hälytys.'); }} />
            )}
            {locked && (
              <SafetyScreen safety={view.meta.safety} busy={busy}
                onDismiss={() => run((s) => api.dismissSafety(s, current.id), () => 'Ohjeet kuitattu. Ne löytyvät aina "Apua nyt" -painikkeesta.')} />
            )}
          </div>
        </div>
        <Backstage client={current} />
      </div>
    </ClientUIContext.Provider>
  );
}

function Page({ title, onBack, children }: { title: string; onBack: () => void; children: ReactNode }) {
  const backRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { backRef.current?.focus(); }, []);
  return (
    <section className="cx-page" aria-label={title}>
      <header className="cx-page-bar">
        <button type="button" ref={backRef} className="cx-icon-btn" aria-label="Takaisin" onClick={onBack}><ArrowLeftIcon size={20} /></button>
        <span className="cx-page-title">{title}</span>
      </header>
      <div className="cx-page-scroll">{children}</div>
    </section>
  );
}
