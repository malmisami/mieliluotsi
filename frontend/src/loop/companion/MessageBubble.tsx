import { useId, useState } from 'react';
import { ChatIcon, ClipboardIcon, InfoIcon, SirenIcon } from '../../icons';
import { UrgencyBadge } from '../../support/labels';
import { formatDate } from '../labels';
import type { ChatAction, ChatMessage, LoopDashboard } from '../types';
import BasisPanel from './BasisPanel';
import WhyNowCard from './WhyNowCard';

interface Props {
  message: ChatMessage;
  dashboard: LoopDashboard;
  busy: boolean;
  onAction: (action: ChatAction, args?: Record<string, unknown>) => void;
  onOpenSummary: (observationId: string | null) => void;
}

function FamilyHistoryEditForm({ dashboard, message, onSubmit, onCancel }: {
  dashboard: LoopDashboard;
  message: ChatMessage;
  onSubmit: (data: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const options = dashboard.companion.familyHistoryOptions;
  const extracted = dashboard.companion.pendingActions.find((p) => p.id === message.pendingActionId)?.payload.data ?? {};
  const [relation, setRelation] = useState(String(extracted.relation ?? 'father'));
  const [condition, setCondition] = useState(String(extracted.condition ?? 'myocardial_infarction'));
  const [age, setAge] = useState(extracted.ageAtEvent ? String(extracted.ageAtEvent) : '');
  const baseId = `edit-${message.id}`;
  return (
    <form
      className="inline-form"
      onKeyDown={(e) => e.key === 'Escape' && onCancel()}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ relation: condition === 'none_reported' ? null : relation, condition, ageAtEvent: age ? Number(age) : null });
      }}
      aria-label="Muokkaa tulkintaa"
    >
      <label htmlFor={`${baseId}-condition`}>Tapahtuma</label>
      <select id={`${baseId}-condition`} value={condition} onChange={(e) => setCondition(e.target.value)} autoFocus>
        {Object.entries(options.conditions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select>
      {condition !== 'none_reported' && (
        <>
          <label htmlFor={`${baseId}-relation`}>Lähisukulainen</label>
          <select id={`${baseId}-relation`} value={relation} onChange={(e) => setRelation(e.target.value)}>
            {Object.entries(options.relations).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
          <label htmlFor={`${baseId}-age`}>Ikä tapahtumahetkellä (vuotta, valinnainen)</label>
          <input id={`${baseId}-age`} type="number" min={1} max={119} value={age} onChange={(e) => setAge(e.target.value)} />
        </>
      )}
      <div className="row">
        <button type="submit">Tallenna muokattu tieto</button>
        <button type="button" className="btn-secondary" onClick={onCancel}>Peruuta muokkaus</button>
      </div>
    </form>
  );
}

function DateForm({ min, onSubmit, onCancel, id }: { min: string; onSubmit: (date: string) => void; onCancel: () => void; id: string }) {
  const [value, setValue] = useState('');
  return (
    <form
      className="inline-form"
      onKeyDown={(e) => e.key === 'Escape' && onCancel()}
      onSubmit={(e) => {
        e.preventDefault();
        if (value) onSubmit(value);
      }}
    >
      <label htmlFor={id}>Muistutuksen päivämäärä</label>
      <input id={id} type="date" min={min} value={value} onChange={(e) => setValue(e.target.value)} autoFocus required />
      <div className="row">
        <button type="submit">Luo muistutus</button>
        <button type="button" className="btn-secondary" onClick={onCancel}>Peruuta</button>
      </div>
    </form>
  );
}

export default function MessageBubble({ message, dashboard, busy, onAction, onOpenSummary }: Props) {
  const [showBasis, setShowBasis] = useState(false);
  const [form, setForm] = useState<ChatAction | null>(null);
  const basisId = useId();
  const isAgent = message.role === 'agent';
  const observation = message.whyNowObservationId ? dashboard.observations.find((o) => o.id === message.whyNowObservationId) : null;
  const minDate = new Date(new Date(dashboard.currentDate).getTime() + 86400000).toISOString().slice(0, 10);
  // messages that carry an automated care-need assessment (class set by the rule engine, never by the LLM)
  const assessment = isAgent && message.kind !== 'emergency' ? message.assessment ?? null : null;
  const isAssessmentMessage = Boolean(assessment) || message.kind === 'care_assessment' || message.kind === 'assessment_notice';
  const modeLabel = assessment?.mode && assessment.mode !== 'automated'
    ? dashboard.support.policy?.assessmentModeLabels?.[assessment.mode]
    : undefined;

  function click(action: ChatAction) {
    if (action.type === 'open_summary') {
      onOpenSummary(action.args.observationId != null ? String(action.args.observationId) : null);
    } else if (action.type === 'edit_pending' || action.type === 'choose_date') {
      setForm(action);
    } else {
      onAction(action);
    }
  }

  return (
    <li className={`chat-message ${isAgent ? 'from-agent' : 'from-user'} kind-${message.kind}`}>
      {isAgent && <span className="chat-avatar" aria-hidden="true"><ChatIcon size={24} /></span>}
      <div className="chat-body">
      <div className="chat-meta">
        <span className="chat-author">{isAgent ? 'Hyvinvointikumppani' : message.kind === 'action_choice' ? 'Sinä (valinta)' : 'Sinä'}</span>
        {message.initiatedByAgent && <span className="chip chip-attention"><InfoIcon size={14} /> Viesti seurannasta</span>}
        <span className="muted small">{formatDate(message.date)}</span>
      </div>
      <div className="chat-bubble">
        {message.kind === 'emergency' && <p className="emergency-title"><SirenIcon size={22} /> Turvallisuusviesti</p>}
        {isAssessmentMessage && isAgent && message.kind !== 'emergency' && (
          <div className="chat-assessment-head">
            <span className="chat-assessment-title"><ClipboardIcon size={18} /> Automaattinen hoidon tarpeen arvio</span>
            {assessment && <UrgencyBadge urgency={assessment.urgency} label={assessment.urgencyLabel} />}
            {modeLabel && <span className="chip">{modeLabel}</span>}
          </div>
        )}
        <p className="chat-text">{message.text}</p>
        {message.aiUnavailable && (
          <p className="ai-unavailable" role="note">{dashboard.companion.disclaimers.aiUnavailable}</p>
        )}

        {observation && <WhyNowCard observation={observation} disclaimer={dashboard.companion.disclaimers.whyNow} />}

        {message.actions.length > 0 && !form && (
          <div className="chat-actions" role="group" aria-label="Vastausvaihtoehdot">
            {message.actions.map((action) => (
              <button
                key={action.id}
                type="button"
                className={action.style === 'secondary' ? 'btn-secondary' : ''}
                disabled={busy || (action.used && action.type !== 'open_summary')}
                onClick={() => click(action)}
              >
                {action.label}
              </button>
            ))}
          </div>
        )}
        {form?.type === 'edit_pending' && (
          <FamilyHistoryEditForm
            dashboard={dashboard}
            message={message}
            onCancel={() => setForm(null)}
            onSubmit={(data) => {
              onAction(form, { data });
              setForm(null);
            }}
          />
        )}
        {form?.type === 'choose_date' && (
          <DateForm
            id={`date-${message.id}`}
            min={minDate}
            onCancel={() => setForm(null)}
            onSubmit={(date) => {
              onAction(form, { date });
              setForm(null);
            }}
          />
        )}

        {isAgent && message.basis && (
          <>
            <button
              type="button"
              className="link-button basis-toggle"
              aria-expanded={showBasis}
              aria-controls={basisId}
              onClick={() => setShowBasis(!showBasis)}
            >
              {isAssessmentMessage ? 'Näin arvio tehtiin' : 'Mihin tämä perustuu?'}
            </button>
            {showBasis && <BasisPanel basis={message.basis} id={basisId} />}
          </>
        )}
        {isAgent && isAssessmentMessage && message.basis?.legalNotice && (
          <p className="chat-legal-notice muted small">{message.basis.legalNotice}</p>
        )}
      </div>
      </div>
    </li>
  );
}
