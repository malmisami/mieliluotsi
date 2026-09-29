import { useEffect, useState } from 'react';
import type { DecisionKind, DecisionRequest, Escalation, SupportPlan } from '../types';

const AVAILABLE: Record<string, DecisionKind[]> = {
  pending_professional_review: ['approve', 'edit', 'reject', 'request_info', 'change_permissions', 'contact_user'],
  active: ['edit', 'continue', 'change_permissions', 'contact_user', 'set_review_date', 'end'],
  escalated: ['edit', 'continue', 'contact_user', 'set_review_date', 'end'],
  paused: ['edit', 'change_permissions', 'contact_user', 'set_review_date', 'end'],
};
const ACTIVITIES = ['kävely', 'taukoliikunta', 'sisäliikunta'];

interface Props {
  plan: SupportPlan;
  escalation: Escalation | null;
  role: string;
  labels: Record<string, string>;
  busy: boolean;
  currentDate: string;
  /** "Oliko automaattinen kiireellisyysarvio oikea?" (backend professional.assessmentQuestion). */
  appropriateQuestion?: string;
  onDecide: (body: DecisionRequest) => void;
}

export default function DecisionPanel({ plan, escalation, role, labels, busy, currentDate, appropriateQuestion = 'Oliko automaattinen kiireellisyysarvio oikea?', onDecide }: Props) {
  const options = AVAILABLE[plan.status] ?? [];
  const [decision, setDecision] = useState<DecisionKind | null>(null);
  const [note, setNote] = useState('');
  const [appropriate, setAppropriate] = useState<'' | 'yes' | 'no'>('');
  const [contactUser, setContactUser] = useState(false);
  const [reviewDate, setReviewDate] = useState('');
  const [allowed, setAllowed] = useState<string[]>(plan.allowedActions);
  const [form, setForm] = useState(() => ({
    measurementsPerWeek: String(plan.measurementsPerWeek),
    checkInEveryDays: String(plan.checkInEveryDays),
    systolic: String(plan.demoTarget?.systolic ?? ''),
    diastolic: String(plan.demoTarget?.diastolic ?? ''),
    activity: plan.goal?.activity ?? 'kävely',
    timesPerWeek: String(plan.goal?.timesPerWeek ?? 2),
    minutes: String(plan.goal?.minutes ?? 30),
    minTimes: String(plan.goal?.minTimesPerWeek ?? 1),
    maxTimes: String(plan.goal?.maxTimesPerWeek ?? 3),
    goalFailuresInRow: String(plan.escalationRules.find((r) => r.kind === 'goal_failures_and_above_target')?.params.goalFailuresInRow ?? 2),
    reviewInDays: '',
    instructions: plan.professionalInstructions.join('\n'),
  }));

  useEffect(() => {
    setDecision(null);
    setNote('');
    setAppropriate('');
    setAllowed(plan.allowedActions);
  }, [plan.id, plan.version, plan.status, plan.allowedActions]);

  const needsAppropriate = Boolean(escalation) && decision !== null && ['edit', 'continue', 'end'].includes(decision);

  function submit() {
    if (!decision) return;
    const body: DecisionRequest = { decision, role, note: note || undefined, contactUser };
    if (decision === 'edit') {
      body.changes = {
        measurementsPerWeek: Number(form.measurementsPerWeek),
        checkInEveryDays: Number(form.checkInEveryDays),
        ...(plan.demoTarget ? { demoTarget: { systolic: Number(form.systolic), diastolic: Number(form.diastolic) } } : {}),
        ...(plan.goal ? { goal: { activity: form.activity, timesPerWeek: Number(form.timesPerWeek), minutes: Number(form.minutes) || null,
          minTimesPerWeek: Number(form.minTimes), maxTimesPerWeek: Number(form.maxTimes) } } : {}),
        ...(plan.escalationRules.some((r) => r.kind === 'goal_failures_and_above_target') ? { goalFailuresInRow: Number(form.goalFailuresInRow) } : {}),
        ...(form.reviewInDays ? { reviewInDays: Number(form.reviewInDays) } : {}),
        instructions: form.instructions.split('\n').map((line) => line.trim()).filter(Boolean),
      };
    }
    if (decision === 'change_permissions') body.allowedActions = allowed;
    if (decision === 'set_review_date') body.reviewDate = reviewDate;
    if (needsAppropriate && appropriate) body.escalationAppropriate = appropriate === 'yes';
    onDecide(body);
  }

  const input = (key: keyof typeof form, label: string, type = 'number', extra: Record<string, unknown> = {}) => (
    <label>
      {label}
      <input type={type} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} {...extra} />
    </label>
  );

  return (
    <section className="decision-panel" aria-labelledby={`decision-${plan.id}`}>
      <h3 id={`decision-${plan.id}`}>Päätös</h3>
      <div className="decision-buttons" role="group" aria-label="Valitse päätös">
        {options.map((option) => (
          <button key={option} type="button" className={decision === option ? '' : 'btn-secondary'} aria-pressed={decision === option}
            onClick={() => setDecision(option)} disabled={busy}>
            {labels[option]}
          </button>
        ))}
      </div>

      {decision && (
        <form noValidate className="decision-form" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          {decision === 'edit' && (
            <fieldset>
              <legend>Suunnitelman asetukset (versio {plan.version} → {plan.version + 1})</legend>
              <div className="form-grid">
                {plan.measurementCode === 'BP' && input('measurementsPerWeek', 'Kotimittauksia tarkistusvälillä', 'number', { min: 0, max: 28 })}
                {input('checkInEveryDays', 'Tarkistusväli (pv)', 'number', { min: 3, max: 90 })}
                {plan.demoTarget && input('systolic', 'Tavoitetaso, yläpaine (demo)', 'number', { min: 100, max: 180 })}
                {plan.demoTarget && input('diastolic', 'Tavoitetaso, alapaine (demo)', 'number', { min: 60, max: 110 })}
                {plan.goal && (
                  <label>
                    Omahoidon tavoite
                    <select value={form.activity} onChange={(e) => setForm({ ...form, activity: e.target.value })}>
                      {ACTIVITIES.map((a) => <option key={a} value={a}>{a}</option>)}
                    </select>
                  </label>
                )}
                {plan.goal && input('timesPerWeek', 'Kertaa viikossa', 'number', { min: 1, max: 14 })}
                {plan.goal && input('minutes', 'Minuuttia kerralla', 'number', { min: 5, max: 120 })}
                {plan.goal && input('minTimes', 'Agentti saa pienentää vähintään (krt/vko)', 'number', { min: 1 })}
                {plan.goal && input('maxTimes', 'Tavoitteen yläraja (krt/vko)', 'number', { min: 1 })}
                {plan.escalationRules.some((r) => r.kind === 'goal_failures_and_above_target') && input('goalFailuresInRow', 'Kiireellisyysarvio: toteutumattomia tarkistuksia peräkkäin', 'number', { min: 1, max: 6 })}
                {input('reviewInDays', 'Uusi arviointi (päivän päästä, valinnainen)', 'number', { min: 1, max: 365 })}
              </div>
              <label>
                Ohjeet asiakkaalle (yksi per rivi)
                <textarea rows={3} value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} />
              </label>
              <p className="muted small">Tavoitetasot ovat demo-arvoja, jotka ammattilainen asettaa – eivät hoitosuosituksia.</p>
            </fieldset>
          )}

          {decision === 'change_permissions' && (
            <fieldset>
              <legend>Agentin sallitut toimet</legend>
              {Object.entries(plan.allowedActionLabels).map(([key, label]) => (
                <label key={key} className="toggle-row">
                  <input type="checkbox" checked={allowed.includes(key)}
                    onChange={(e) => setAllowed(e.target.checked ? [...allowed, key] : allowed.filter((a) => a !== key))} />
                  <span>{label}</span>
                </label>
              ))}
              <p className="muted small">Kiellettyjä toimia (diagnoosit, hoitopäätökset, lääkitys, kliiniset raja-arvot) ei voi sallia.</p>
            </fieldset>
          )}

          {decision === 'set_review_date' && (
            <label>
              Uusi tarkistuspäivä
              <input type="date" min={currentDate} value={reviewDate} onChange={(e) => setReviewDate(e.target.value)} required />
            </label>
          )}

          {needsAppropriate && (
            <fieldset>
              <legend>{appropriateQuestion}</legend>
              <div className="radio-row">
                <label><input type="radio" name="appropriate" checked={appropriate === 'yes'} onChange={() => setAppropriate('yes')} /> Kyllä</label>
                <label><input type="radio" name="appropriate" checked={appropriate === 'no'} onChange={() => setAppropriate('no')} /> Ei</label>
              </div>
            </fieldset>
          )}

          <label>
            Perustelu tai viesti {decision === 'request_info' ? '(pakollinen – näytetään asiakkaalle)' : '(valinnainen)'}
            <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} required={decision === 'request_info'} />
          </label>
          {decision !== 'contact_user' && (
            <label className="toggle-row">
              <input type="checkbox" checked={contactUser} onChange={(e) => setContactUser(e.target.checked)} />
              <span>Ilmoita asiakkaalle, että otan yhteyttä</span>
            </label>
          )}
          <div className="row">
            <button type="submit" disabled={busy}>Vahvista: {labels[decision]}</button>
            <button type="button" className="btn-secondary" onClick={() => setDecision(null)}>Peruuta</button>
          </div>
        </form>
      )}
    </section>
  );
}
