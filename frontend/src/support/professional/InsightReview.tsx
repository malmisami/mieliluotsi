import { useState } from 'react';
import { formatDate } from '../../loop/labels';
import { CategoryBadge } from '../labels';
import type { Insight } from '../types';

interface Props {
  insight: Insight;
  role: string;
  ownerRoles: Record<string, string>;
  busy: boolean;
  onDecide: (body: { decision: 'approve' | 'reject' | 'refer' | 'request_info'; role: string; note?: string; ownerRole?: string }) => void;
}

export default function InsightReview({ insight, role, ownerRoles, busy, onDecide }: Props) {
  const [note, setNote] = useState('');
  const [target, setTarget] = useState('genetics');
  return (
    <article className="insight-review" aria-labelledby={`insight-${insight.id}`}>
      <h3 id={`insight-${insight.id}`}>{insight.title}</h3>
      <p><CategoryBadge category={insight.category} label={insight.categoryLabel} /> {insight.reviewStatusLabel}{insight.reviewOwnerLabel ? ` · ${insight.reviewOwnerLabel}` : ''}</p>
      <p>{insight.reason}</p>
      <p className="muted small">Luokitus lähteessä: {insight.significance ?? '–'} · vahvistus: {insight.confirmation === 'lab_confirmed' ? 'kliinisesti vahvistettu' : 'vahvistamaton'} · {formatDate(insight.createdAt)} · lähde: {insight.origin === 'dna_analysis' ? 'käyttäjän DNA-analyysi' : 'perimätietopalvelu'}</p>
      <label>
        Perustelu (valinnainen)
        <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <div className="row">
        <button type="button" disabled={busy} onClick={() => onDecide({ decision: 'approve', role, note })}>Hyväksy seurannan taustatiedoksi</button>
        <button type="button" className="btn-secondary" disabled={busy} onClick={() => onDecide({ decision: 'reject', role, note })}>Ei käytetä seurannassa</button>
        <label className="inline-select">
          <span className="visually-hidden">Ohjattava ammattilainen</span>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            {Object.entries(ownerRoles).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
        <button type="button" className="btn-secondary" disabled={busy} onClick={() => onDecide({ decision: 'refer', role, note, ownerRole: target })}>Ohjaa arvioon</button>
      </div>
    </article>
  );
}
