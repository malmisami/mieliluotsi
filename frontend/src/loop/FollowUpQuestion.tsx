import { ClockIcon } from '../icons';
import { formatDate } from './labels';
import type { LoopDashboard, UserResponse } from './types';

const OPTIONS: { value: UserResponse; label: string }[] = [
  { value: 'yes', label: 'Kyllä' },
  { value: 'not_yet', label: 'Ei vielä' },
  { value: 'no_reminder', label: 'En halua muistutusta' },
  { value: 'not_relevant', label: 'Löydös todettiin epäolennaiseksi' },
];

interface Props {
  question: LoopDashboard['pendingQuestions'][number];
  busy: boolean;
  onRespond: (taskId: string, response: UserResponse) => void;
}

export default function FollowUpQuestion({ question, busy, onRespond }: Props) {
  const headingId = `question-${question.id}`;
  return (
    <section className="panel follow-up" role="region" aria-labelledby={headingId}>
      <p className="status-badge tone-waiting"><ClockIcon size={16} /> Odottaa toimintaasi</p>
      <h2 id={headingId}>{question.question}</h2>
      <p>
        Huomio {formatDate(question.observation.createdAt)}: {question.observation.title}. Seurantatehtävän määräpäivä oli {formatDate(question.dueAt)}.
      </p>
      <div className="row" role="group" aria-labelledby={headingId}>
        {OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={option.value === 'yes' ? '' : 'btn-secondary'}
            disabled={busy}
            onClick={() => onRespond(question.id, option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </section>
  );
}
