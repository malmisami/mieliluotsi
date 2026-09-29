import { useEffect, useRef } from 'react';
import { ChatIcon } from '../icons';
import { formatDate } from '../loop/labels';
import { SIGNAL_LABELS, ToneBadge } from './labels';
import type { CheckIn } from './types';

interface Props {
  checkIn: CheckIn;
  planName: string;
  busy: boolean;
  onAnswer: (questionId: string, optionId: string | null, skip: boolean) => void;
}

/** One adaptive check-in. Questions are shown one at a time; answered ones stay visible as a short summary. */
export default function CheckInCard({ checkIn, planName, busy, onAnswer }: Props) {
  const current = checkIn.questions.find((q) => !q.answer && !q.skipped) ?? null;
  const answered = checkIn.questions.filter((q) => q.answer || q.skipped);
  const legendRef = useRef<HTMLLegendElement>(null);
  const index = current ? checkIn.questions.indexOf(current) + 1 : checkIn.questions.length;

  useEffect(() => {
    legendRef.current?.focus();
  }, [current?.id]);

  return (
    <section className="panel checkin-card" aria-labelledby={`checkin-${checkIn.id}`}>
      <div className="checkin-head">
        <span className="checkin-icon" aria-hidden="true"><ChatIcon size={28} /></span>
        <div>
          <h2 id={`checkin-${checkIn.id}`}>Viikkotarkistus: {planName}</h2>
          <p className="muted small">
            Hyvinvointikumppani aloitti tarkistuksen {formatDate(checkIn.createdAt)} (klo {checkIn.deliveredAt.split(' ')[1]}).{' '}
            Kysymys {index}/{checkIn.questions.length}.
          </p>
        </div>
      </div>
      <details className="checkin-why">
        <summary>Miksi tarkistus tehtiin nyt?</summary>
        <p>{checkIn.reason}</p>
        {checkIn.signals.length > 0 && (
          <ul className="chip-list">
            {checkIn.signals.map((s) => <li key={s} className="chip">{SIGNAL_LABELS[s] ?? s}</li>)}
          </ul>
        )}
      </details>

      {answered.length > 0 && (
        <ol className="checkin-answered" aria-label="Vastatut kysymykset">
          {answered.map((q) => (
            <li key={q.id}>
              <span>{q.text}</span>
              <ToneBadge tone="neutral">{q.skipped ? 'Ohitettu' : q.answerLabel}</ToneBadge>
            </li>
          ))}
        </ol>
      )}

      {current && (
        <fieldset className="checkin-question" disabled={busy} aria-describedby={`why-${current.id}`}>
          <legend ref={legendRef} tabIndex={-1}>{current.text}</legend>
          <p id={`why-${current.id}`} className="checkin-reason"><strong>Miksi kysyn:</strong> {current.whyAsked}</p>
          <div className="checkin-options" role="group" aria-label="Vastausvaihtoehdot">
            {current.options.map((option) => (
              <button key={option.id} type="button" className="checkin-option" onClick={() => onAnswer(current.id, option.id, false)}>
                {option.label}
              </button>
            ))}
          </div>
          {current.optional && (
            <button type="button" className="link-button checkin-skip" onClick={() => onAnswer(current.id, null, true)}>
              Ohita tämä kysymys (vapaaehtoinen)
            </button>
          )}
        </fieldset>
      )}
    </section>
  );
}
