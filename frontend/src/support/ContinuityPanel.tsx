import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { AlertIcon, CheckIcon, ClockIcon, DotIcon, InfoIcon, StethoscopeIcon } from '../icons';
import { formatDate } from '../loop/labels';
import type { LoopDashboard } from '../loop/types';
import { supportApi } from './api';
import type {
  ContinuityDirection,
  ContinuityItem,
  ContinuityStep,
  ContinuityView,
  DirectionKey,
  HomeMonitoringPeriod,
  MemorySection,
  MemorySectionKey,
} from './types';
import { useRunner } from './useRunner';

const DIRECTION_ICONS: Record<DirectionKey, ReactNode> = {
  continue: <CheckIcon size={16} />,
  adjust: <InfoIcon size={16} />,
  professional: <StethoscopeIcon size={16} />,
  pending: <ClockIcon size={16} />,
  paused: <DotIcon size={16} />,
};

/** "Jatketaan omahoitoa" / "Muutetaan suunnitelmaa" / "Tarvitaan ammattilaista" – the label always comes from the rules. */
export function DirectionBadge({ direction }: { direction: Pick<ContinuityDirection, 'key' | 'label'> }) {
  return <span className={`support-badge direction-badge direction-${direction.key}`}>{DIRECTION_ICONS[direction.key]} {direction.label}</span>;
}

function capitalize(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function MemoryRow({ item, dateFirst }: { item: ContinuityItem; dateFirst: boolean }) {
  return (
    <li className={`memory-item${item.tone ? ` tone-${item.tone}` : ''}${item.pending ? ' is-pending' : ''}`}>
      <span className="memory-mark" aria-hidden="true">
        {item.tone === 'positive' ? <CheckIcon size={14} /> : item.tone === 'barrier' ? <AlertIcon size={14} /> : <DotIcon size={14} />}
      </span>
      <span className="memory-body">
        {dateFirst && item.date && <span className="memory-date">{formatDate(item.date)}</span>}
        {item.tone === 'barrier' && <span className="memory-tag">Haaste</span>}
        <span className="memory-text">{item.text}</span>
        {item.detail && <span className="memory-detail">{item.detail}</span>}
        {item.source && <span className="memory-source">{item.source}</span>}
      </span>
    </li>
  );
}

function MemoryAccordion({ sections }: { sections: MemorySection[] }) {
  const [openKey, setOpenKey] = useState<MemorySectionKey | null>('goals');
  return (
    <div className="memory-accordion">
      {sections.map((section) => {
        const open = openKey === section.key;
        const panelId = `memory-${section.key}`;
        return (
          <div key={section.key} className={`memory-section${open ? ' is-open' : ''}`}>
            <button type="button" className="memory-toggle" aria-expanded={open} aria-controls={panelId}
              onClick={() => setOpenKey(open ? null : section.key)}>
              <span className="memory-toggle-title">{section.title}</span>
              <span className="memory-count" aria-label={`${section.items.length} kohtaa`}>{section.items.length}</span>
              {!open && section.items[0] && <span className="memory-preview">{section.items[0].text}</span>}
            </button>
            {open && (
              <div id={panelId} className="memory-panel">
                {section.items.length ? (
                  <ul className="memory-list">
                    {section.items.map((item, index) => (
                      <MemoryRow key={`${section.key}-${index}-${item.text}`} item={item} dateFirst={section.key === 'recheck'} />
                    ))}
                  </ul>
                ) : (
                  <p className="muted small">{section.empty}</p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PeriodProgress({ period }: { period: HomeMonitoringPeriod }) {
  const share = Math.min(100, Math.round((period.readings / Math.max(1, period.total)) * 100));
  return (
    <div className="continuity-offer is-active">
      <p className="continuity-offer-title">{period.title} {formatDate(period.startsAt)}–{formatDate(period.endsAt)}</p>
      <div className="continuity-progress" role="progressbar" aria-label="Kotiseurannan mittaukset" aria-valuemin={0} aria-valuemax={period.total} aria-valuenow={period.readings}>
        <span style={{ width: `${share}%` }} />
      </div>
      <p className="small">{period.readings}/{period.total} mittausta. Mittaa aamulla ja illalla ja kirjaa mittaukset Tilanne nyt -näkymässä.</p>
    </div>
  );
}

function StepLoop({ step }: { step: ContinuityStep }) {
  const index = step.loop.findIndex((stage) => stage.state === 'current');
  const current = index >= 0 ? step.loop[index] : null;
  const next = index >= 0 ? step.loop[index + 1] ?? null : null;
  return (
    <>
      <p className="step-now">{capitalize(step.text)}</p>
      <ol className="loop-chips" aria-label="Omahoidon kierros">
        {step.loop.map((stage, index) => (
          <li key={stage.id} className={`loop-chip is-${stage.state}`} aria-current={stage.state === 'current' ? 'step' : undefined}>
            <span className="loop-mark" aria-hidden="true">{stage.state === 'done' ? <CheckIcon size={12} /> : index + 1}</span>
            {stage.label}
            <span className="visually-hidden">{stage.state === 'done' ? ' (tehty)' : stage.state === 'current' ? ' (nyt)' : ''}</span>
          </li>
        ))}
      </ol>
      {current && (
        <p className="loop-now small">
          <strong>{current.label}:</strong> {current.id === 'action' ? (step.day ? `päivä ${step.day}/${step.days}` : `${step.days} päivän kokeilu`) : current.text}
          {next && <><br /><span className="muted">Seuraavaksi {next.label.toLowerCase()}: {next.text.charAt(0).toLowerCase() + next.text.slice(1)}</span></>}
        </p>
      )}
      <p className="muted small">{step.setByLabel}. Vaihteluväli {step.range}.</p>
      {step.rounds.length > 0 && (
        <details className="continuity-more">
          <summary>Aiemmat kierrokset ({step.rounds.length})</summary>
          <ul className="round-list">
            {step.rounds.map((round) => (
              <li key={round.checkInId} className={`round-item feedback-${round.feedback}`}>
                <span className="memory-date">{formatDate(round.date)}</span>
                <span>
                  {capitalize(round.step)}: <strong>{round.feedbackLabel.toLowerCase()}</strong>
                  {round.barrier ? ` (${round.barrier.toLowerCase()})` : ''} → {round.adaptationLabel}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

function DirectionBlock({ directions }: { directions: ContinuityDirection[] }) {
  const followed = directions.filter((d) => d.key !== 'pending');
  const main = [...(followed.length ? followed : directions)].sort((a, b) => b.watch.length - a.watch.length)[0];
  return (
    <>
      <ul className="direction-list">
        {directions.map((direction) => (
          <li key={direction.planId} className="direction-row">
            <span className="direction-head">
              <span className="direction-plan">{direction.planName}</span>
              <DirectionBadge direction={direction} />
            </span>
            <span className="small">{direction.reasons.join(' ')}</span>
          </li>
        ))}
      </ul>
      {main && main.watch.length > 0 && (
        <>
          <h4>Seuraan samalla</h4>
          <ul className="watch-list">
            {main.watch.map((item) => (
              <li key={item.label} className={item.ok ? 'is-ok' : 'is-attention'}>
                <span className="watch-mark" aria-hidden="true">{item.ok ? <CheckIcon size={14} /> : <InfoIcon size={14} />}</span>
                <span><strong>{item.label}</strong> <span className="muted">{item.detail}</span></span>
                <span className="visually-hidden">{item.ok ? '(kunnossa)' : '(huomioitavaa)'}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {main && main.professionalWhen.length > 0 && (
        <details className="continuity-more">
          <summary>Milloin otan ammattilaisen mukaan?</summary>
          <ul className="plain-list small">
            {main.professionalWhen.map((rule) => <li key={rule.id}>{capitalize(rule.text)} <span className="muted">({rule.id})</span></li>)}
          </ul>
        </details>
      )}
      <p className="muted small">Suunta tulee ammattilaisen hyväksymistä säännöistä, ei kielimallilta. Voit aina pyytää ammattilaisen arvion.</p>
    </>
  );
}

interface CardProps {
  id: string;
  number: number;
  title: string;
  status: ReactNode;
  open: boolean;
  onToggle: (open: boolean) => void;
  children: ReactNode;
}

function TaskCard({ id, number, title, status, open, onToggle, children }: CardProps) {
  return (
    <details className="continuity-card" open={open} onToggle={(e) => onToggle((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>
        <span className="continuity-num" aria-hidden="true">{number}</span>
        <span className="continuity-summary">
          <span className="continuity-title" id={`${id}-title`}>{title}</span>
          <span className="continuity-status">{status}</span>
        </span>
      </summary>
      <div className="continuity-body">{children}</div>
    </details>
  );
}

interface Props {
  dashboard: LoopDashboard;
  setDashboard: (dashboard: LoopDashboard) => void;
}

/** The self-care continuity engine's four core tasks: remember, reach out, one step at a time, notice when self-care
 * is not enough. Everything shown comes from the plans' rules; the LLM makes no decisions. */
export default function ContinuityPanel({ dashboard, setDashboard }: Props) {
  const { busy, error, message, run } = useRunner(setDashboard);
  const continuity: ContinuityView | undefined = dashboard.support.available ? dashboard.support.continuity : undefined;
  const offer = continuity?.outreach?.offer ?? null;
  const active = continuity?.outreach?.active ?? null;
  const [open, setOpen] = useState<Record<string, boolean>>({ remember: true, reach_out: Boolean(offer || active), one_step: true, notice: true });

  // a new offer or a running home monitoring opens "Otan itse yhteyttä" so the user sees it
  useEffect(() => {
    if (offer || active) setOpen((current) => ({ ...current, reach_out: true }));
  }, [offer?.id, active?.id]);

  if (!continuity?.available || !continuity.memory || !continuity.outreach) {
    return (
      <section className="panel continuity-panel" aria-labelledby="continuity-title">
        <h2 id="continuity-title">Omahoidon jatkuvuus</h2>
        <p className="muted small">Seurannan tietoja ei ole ladattu.</p>
      </section>
    );
  }
  const tasks = Object.fromEntries((continuity.coreTasks ?? []).map((task) => [task.id, task]));
  const memory = continuity.memory;
  const outreach = continuity.outreach;
  const step = continuity.step ?? null;
  const directions = continuity.directions ?? [];
  const overall = continuity.direction ?? null;
  const goals = memory.sections.find((s) => s.key === 'goals')?.items.length ?? 0;
  const nextCheck = memory.sections.find((s) => s.key === 'recheck')?.items.find((i) => i.date);
  const toggle = (key: string) => (value: boolean) => setOpen((current) => ({ ...current, [key]: value }));

  return (
    <section className="panel continuity-panel" aria-labelledby="continuity-title">
      <h2 id="continuity-title">Omahoidon jatkuvuus</h2>
      <p className="muted small continuity-tagline">{continuity.tagline}</p>

      <TaskCard id="ct-remember" number={1} title={tasks.remember?.title ?? 'Muistan puolestasi'} open={open.remember} onToggle={toggle('remember')}
        status={`${goals} ${goals === 1 ? 'tavoite' : 'tavoitetta'}${nextCheck?.date ? ` · seuraava tarkistus ${formatDate(nextCheck.date)}` : ''}`}>
        <p className="continuity-intro small">{tasks.remember?.text}</p>
        <MemoryAccordion sections={memory.sections} />
        {memory.notesNotice && <p className="muted small">{memory.notesNotice}</p>}
        {memory.notice && <p className="muted small continuity-footnote">{memory.notice}</p>}
      </TaskCard>

      <TaskCard id="ct-reach" number={2} title={tasks.reach_out?.title ?? 'Otan itse yhteyttä'} open={open.reach_out} onToggle={toggle('reach_out')}
        status={offer ? 'Ehdotus odottaa vastaustasi' : active ? `Kotiseuranta ${active.readings}/${active.total}`
          : outreach.upcoming[0] ? `Seuraavaksi ${formatDate(outreach.upcoming[0].date)}` : 'Ei suunniteltuja yhteydenottoja'}>
        <p className="continuity-intro small">{tasks.reach_out?.text}</p>
        {offer && (
          <div className="continuity-offer" role="group" aria-label="Hyvinvointikumppanin ehdotus">
            <p className="continuity-offer-title">Ehdotan: {offer.title.toLowerCase()} aamulla ja illalla</p>
            <p className="small">{offer.reason}</p>
            <div className="row">
              <button type="button" disabled={busy} onClick={() => run(() => supportApi.respondHomeMonitoring(offer.id, true), () => 'Kotiseuranta aloitettiin.')}>
                Kyllä, aloitetaan
              </button>
              <button type="button" className="btn-secondary" disabled={busy}
                onClick={() => run(() => supportApi.respondHomeMonitoring(offer.id, false), () => 'Selvä, ei tällä viikolla.')}>
                Ei tällä viikolla
              </button>
            </div>
          </div>
        )}
        {active && <PeriodProgress period={active} />}
        {!outreach.settings.proactive && <p className="small">Oma-aloitteiset yhteydenotot ovat pois päältä suostumuksissasi.</p>}
        <h4>Seuraavaksi</h4>
        {outreach.upcoming.length ? (
          <ul className="memory-list">
            {outreach.upcoming.map((item) => (
              <li key={`${item.date}-${item.label}`} className="memory-item">
                <span className="memory-mark" aria-hidden="true"><ClockIcon size={14} /></span>
                <span className="memory-body"><span className="memory-date">{formatDate(item.date)}</span><span className="memory-text">{item.label}</span></span>
              </li>
            ))}
          </ul>
        ) : <p className="muted small">Ei suunniteltuja yhteydenottoja.</p>}
        {outreach.recent.length > 0 && (
          <>
            <h4>Viimeksi</h4>
            <ul className="memory-list">
              {outreach.recent.slice(0, 3).map((item, index) => (
                <li key={`${item.date}-${item.kind}-${index}`} className="memory-item">
                  <span className="memory-mark" aria-hidden="true"><DotIcon size={14} /></span>
                  <span className="memory-body"><span className="memory-date">{formatDate(item.date)}</span><span className="memory-text">{item.label}</span></span>
                </li>
              ))}
            </ul>
          </>
        )}
        <details className="continuity-more">
          <summary>Milloin otan itse yhteyttä?</summary>
          <ul className="plain-list small">
            {outreach.rules.map((rule) => <li key={rule.id}>{rule.text}</li>)}
          </ul>
          <p className="muted small">
            {outreach.settings.channel} · enintään {outreach.settings.maxPerWeek} viikossa (tällä viikolla {outreach.settings.usedThisWeek}) ·
            ei klo {outreach.settings.quietHours}. Voit muuttaa näitä Suostumukset-välilehdellä.
          </p>
        </details>
      </TaskCard>

      <TaskCard id="ct-step" number={3} title={tasks.one_step?.title ?? 'Yksi askel kerrallaan'} open={open.one_step} onToggle={toggle('one_step')}
        status={step ? `${capitalize(step.text)}${step.day ? ` · päivä ${step.day}/${step.days}` : ''}` : 'Ei käynnissä olevaa askelta'}>
        <p className="continuity-intro small">{tasks.one_step?.text}</p>
        {step ? <StepLoop step={step} /> : <p className="muted small">Askel sovitaan, kun ammattilainen on hyväksynyt seurantasuunnitelman.</p>}
      </TaskCard>

      <TaskCard id="ct-notice" number={4} title={tasks.notice?.title ?? 'Huomaan, milloin omahoito ei riitä'} open={open.notice} onToggle={toggle('notice')}
        status={overall ? <DirectionBadge direction={overall} /> : 'Ei seurantoja'}>
        <p className="continuity-intro small">{tasks.notice?.text}</p>
        <DirectionBlock directions={directions} />
      </TaskCard>

      <p className="live-message" aria-live="polite">{message}</p>
      {error && <p className="form-error" role="alert">{error}</p>}
    </section>
  );
}
