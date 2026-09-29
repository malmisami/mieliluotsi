import { CheckIcon, ClockIcon, DnaIcon, LockIcon, MinusIcon } from '../icons';
import { loopApi } from '../loop/api';
import MonitoringCard from '../loop/MonitoringCard';
import type { LoopDashboard } from '../loop/types';
import type { Insight } from './types';
import { useRunner } from './useRunner';

interface Props {
  dashboard: LoopDashboard;
  setDashboard: (dashboard: LoopDashboard) => void;
  onOpenConsent: () => void;
}

/** Gate 1 at a glance: what the professional approved, what waits for review and what was filtered out. */
export default function GeneticSourcePanel({ dashboard, setDashboard, onOpenConsent }: Props) {
  const support = dashboard.support;
  const { busy, error, message, run } = useRunner(setDashboard);
  if (!support.available) return null;
  const allowed = support.consent.dataSources.geneticInsights;
  const showDetails = support.consent.showGeneticDetails;
  const genetic = support.insights.filter((i) => i.kind === 'genetic');
  const approved = genetic.filter((i) => i.reviewStatus === 'approved');
  const pending = genetic.filter((i) => i.reviewStatus === 'pending_professional_review' || i.reviewStatus === 'info_requested');
  const unused = genetic.filter((i) => !i.userVisible || i.reviewStatus === 'rejected');
  const monitorings = dashboard.monitorings.filter((m) => m.active);

  function context(insight: Insight) {
    const plan = support.plans.find((p) => p.id === insight.linkedPlanId);
    if (plan) return `taustatietona: ${plan.name}`;
    return insight.origin === 'dna_analysis' ? 'omasta DNA-analyysistä, ei liitetty seurantaan' : 'ei liitetty seurantaan';
  }

  return (
    <section className="panel genetic-source" aria-labelledby="genetic-source-title">
      <div className="panel-heading">
        <span className="panel-heading-icon" aria-hidden="true"><DnaIcon size={48} /></span>
        <h2 id="genetic-source-title">Perimätieto</h2>
      </div>
      <p className="lead">Vapaaehtoinen lisätieto. Vain ammattilaisen hyväksymä havainto voi olla seurannan taustatietona – muu suodatetaan pois.</p>

      <div className="gate-tiles" role="list">
        <div className="stat gate-tile is-approved" role="listitem">
          <span className="stat-value">{approved.length}</span>
          <span className="stat-label">Hyväksytty taustatiedoksi</span>
        </div>
        <div className="stat gate-tile" role="listitem">
          <span className="stat-value">{pending.length}</span>
          <span className="stat-label">Odottaa ammattilaisen arviota</span>
        </div>
        <div className="stat gate-tile is-filtered" role="listitem">
          <span className="stat-value">{unused.length}</span>
          <span className="stat-label">Suodatettu pois (portti 1)</span>
        </div>
      </div>

      <ul className="gate-list">
        {approved.map((insight) => (
          <li key={insight.id}>
            <CheckIcon size={18} className="icon-yes" />
            <span><strong>{insight.userTitle}</strong> <span className="muted">· {context(insight)}</span></span>
          </li>
        ))}
        {pending.map((insight) => (
          <li key={insight.id}>
            <ClockIcon size={18} />
            <span>
              <strong>{insight.userTitle}</strong>{' '}
              <span className="muted">· {insight.reviewStatusLabel.toLowerCase()}{insight.reviewOwnerLabel ? ` (${insight.reviewOwnerLabel})` : ''}</span>
            </span>
          </li>
        ))}
        {unused.length > 0 && (
          <li>
            <MinusIcon size={18} />
            <span>
              {unused.length === 1 ? 'Yksi havainto' : `${unused.length} havaintoa`} ei käytetä: tulkinta on epävarma tai havainnolla ei ole käytännön merkitystä seurannallesi.
            </span>
          </li>
        )}
        {genetic.length === 0 && (
          <li><MinusIcon size={18} /><span>Perimätietoa ei ole. Palvelu toimii ilman sitä.</span></li>
        )}
      </ul>
      {approved.length > 0 && (
        <p className="muted small">Hyväksytytkin havainnot ovat vahvistamattomia taustatietoja: ne eivät muuta tavoitteitasi eivätkä ohjeitasi.</p>
      )}

      <p className={`consent-state ${allowed ? 'is-on' : 'is-off'}`}>
        <LockIcon size={18} /> Käyttö seurannassa: <strong>{allowed ? 'sallittu' : 'ei sallittu'}</strong>
        {' · '}yksityiskohdat: <strong>{showDetails ? 'näytetään' : 'piilotettu'}</strong>{' '}
        <button type="button" className="link-button" onClick={onOpenConsent}>Muuta suostumusta</button>
      </p>

      {monitorings.length > 0 && showDetails && (
        <details className="genetic-monitoring">
          <summary>Sääntömoottorin seuranta ({monitorings.length})</summary>
          <div className="monitoring-list">
            {monitorings.map((monitoring) => (
              <MonitoringCard key={monitoring.id} monitoring={monitoring} busy={busy} onWhyNow={() => undefined}
                onStop={(id) => run(() => loopApi.stopMonitoring(id), () => 'Geneettinen seuranta lopetettu.')} />
            ))}
          </div>
        </details>
      )}
      <p className="live-message" aria-live="polite">{message}</p>
      {error && <p className="form-error" role="alert">{error}</p>}
    </section>
  );
}
