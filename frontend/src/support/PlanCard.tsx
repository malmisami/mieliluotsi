import { useId, useState } from 'react';
import { CheckIcon, CrossIcon, LockIcon } from '../icons';
import { formatDate } from '../loop/labels';
import { ToneBadge } from './labels';
import type { PlanCard as PlanCardData } from './types';

interface Props {
  card: PlanCardData;
  busy: boolean;
  onPause: (planId: string) => void;
  onResume: (planId: string) => void;
}

export default function PlanCard({ card, busy, onPause, onResume }: Props) {
  const [open, setOpen] = useState(false);
  const whyId = useId();
  const why = card.why;
  return (
    <article className={`plan-card plan-tone-${card.tone}`} aria-labelledby={`${whyId}-title`}>
      <header className="plan-card-head">
        <h3 id={`${whyId}-title`}>{card.name}</h3>
        <ToneBadge tone={card.tone}>{card.statusLabel}</ToneBadge>
      </header>
      <p className="plan-sentence">{card.sentence}</p>

      {card.progress.map((item) => (
        <div key={item.label} className="plan-progress">
          <span className="plan-progress-label">{item.label}: <strong>{item.value}/{item.target}</strong></span>
          <span className="plan-progress-track" aria-hidden="true">
            <span className="plan-progress-fill" style={{ width: `${Math.min(100, (item.value / Math.max(1, item.target)) * 100)}%` }} />
          </span>
        </div>
      ))}

      {card.instructions.length > 0 && (
        <div className="plan-instructions">
          <p><strong>Ammattilaisen ohjeet sinulle:</strong></p>
          <ul>{card.instructions.map((text, i) => <li key={`${i}-${text}`}>{text}</li>)}</ul>
        </div>
      )}

      <dl className="plan-facts">
        {card.nextCheckInAt && <div><dt>Seuraava tarkistus</dt><dd>{formatDate(card.nextCheckInAt)}</dd></div>}
        {card.nextReviewAt && card.status !== 'pending_professional_review' && <div><dt>Suunnitelman arviointi</dt><dd>{formatDate(card.nextReviewAt)}</dd></div>}
        <div>
          <dt>Hyväksyntä</dt>
          <dd>{card.approvedBy ? `${card.approvedBy} hyväksyi ${formatDate(card.approvedAt)} (versio ${card.version})` : 'Odottaa ammattilaisen hyväksyntää'}</dd>
        </div>
      </dl>

      <div className="row">
        <button type="button" className="btn-secondary" aria-expanded={open} aria-controls={whyId} onClick={() => setOpen(!open)}>
          {open ? 'Piilota perustelut' : 'Miksi tätä seurataan?'}
        </button>
        {card.canPause && (
          <button type="button" className="btn-secondary" disabled={busy} onClick={() => onPause(card.id)}>Tauota seuranta</button>
        )}
        {card.canResume && (
          <button type="button" disabled={busy} onClick={() => onResume(card.id)}>Jatka seurantaa</button>
        )}
      </div>

      {open && (
        <div id={whyId} className="plan-why">
          <h4>Miksi tätä seurataan?</h4>
          <p>{why.rationale}</p>
          <p><strong>Seurannan tavoite:</strong> {why.objective}</p>
          {card.goal && <p><strong>Omahoidon tavoite nyt:</strong> {card.goal}{card.goalSetBy === 'agent_with_user' ? ' (sovittu kanssasi)' : ''}</p>}
          {why.target && <p><strong>Sovittu tavoitetaso:</strong> {why.target.label}. <span className="muted">{why.target.setBy}.</span></p>}

          <h4>Mihin tieto perustuu</h4>
          <ul className="source-list">
            {why.sources.map((source, i) => (
              <li key={`${i}-${source.kind}`}>
                <span>{source.label}</span>
                <span className="muted small">{source.kindLabel}{source.date ? ` · ${formatDate(source.date)}` : ''}</span>
                {!source.inUse && <span className="chip"><LockIcon size={14} /> Ei käytössä (suostumus)</span>}
              </li>
            ))}
          </ul>
          {why.geneticNote && <p className="muted">{why.geneticNote}</p>}
          {why.filteredNote && <p className="muted">{why.filteredNote}</p>}

          <h4>Kuka on hyväksynyt ja kuka valvoo</h4>
          <p>{why.approval}. Vastuuammattilainen: {why.owner}. {why.userConsent}.</p>
          <p><strong>{why.rightsSentence ?? 'Sinulla on aina oikeus terveydenhuollon ammattihenkilön tekemään arvioon.'}</strong></p>

          <div className="agent-limits">
            <div>
              <h4>Hyvinvointikumppani saa</h4>
              <ul className="check-list">{why.agentMay.map((item) => <li key={item}><CheckIcon size={16} /> {item}</li>)}</ul>
            </div>
            <div>
              <h4>Hyvinvointikumppani ei koskaan</h4>
              <ul className="check-list is-negative">{why.agentMayNot.map((item) => <li key={item}><CrossIcon size={16} /> {item}</li>)}</ul>
            </div>
          </div>
          {why.escalationRules.length > 0 && (
            <>
              <h4>Miten kiireellisyys arvioidaan ja milloin ammattilainen tulee mukaan</h4>
              <ul>{why.escalationRules.map((rule) => <li key={rule.name}>{rule.name} – arvio: {rule.urgency.toLowerCase()}, käsittely {rule.handlingTime}.</li>)}</ul>
            </>
          )}
          <h4>Muutoshistoria</h4>
          <ol className="history-list">
            {why.history.map((change, i) => (
              <li key={`${change.version}-${i}`}>
                {formatDate(change.date)} · v{change.version} · {change.actorRole ?? { system: 'Järjestelmä', agent: 'Hyvinvointikumppani', user: 'Sinä', professional: 'Ammattilainen' }[change.actor]}: {change.summary}
                {change.changes.length > 0 && <ul>{change.changes.map((line) => <li key={line}>{line}</li>)}</ul>}
              </li>
            ))}
          </ol>
          <p className="muted small">{why.demoNotice}</p>
        </div>
      )}
    </article>
  );
}
