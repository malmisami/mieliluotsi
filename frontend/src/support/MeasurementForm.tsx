import { useId, useState } from 'react';

interface Props {
  busy: boolean;
  onSubmit: (systolic: number, diastolic: number) => void;
  compact?: boolean;
}

/** Record a home blood-pressure measurement. Values are checked for plausibility only - never interpreted here. */
export default function MeasurementForm({ busy, onSubmit, compact = false }: Props) {
  const id = useId();
  const [systolic, setSystolic] = useState('');
  const [diastolic, setDiastolic] = useState('');
  const [error, setError] = useState<string | null>(null);

  function submit() {
    const s = Number(systolic);
    const d = Number(diastolic);
    if (!Number.isInteger(s) || !Number.isInteger(d) || s < 60 || s > 260 || d < 30 || d > 160 || d >= s) {
      setError('Tarkista arvot: yläpaine 60–260 ja alapaine 30–160 mmHg, alapaine yläpainetta pienempi.');
      return;
    }
    setError(null);
    onSubmit(s, d);
    setSystolic('');
    setDiastolic('');
  }

  return (
    <form
      noValidate
      className={`measurement-form ${compact ? 'is-compact' : ''}`}
      aria-labelledby={`${id}-title`}
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <p id={`${id}-title`} className="measurement-title"><strong>Kirjaa kotimittaus</strong></p>
      <div className="measurement-fields">
        <label htmlFor={`${id}-sys`}>
          Yläpaine (mmHg)
          <input id={`${id}-sys`} type="number" inputMode="numeric" min={60} max={260} value={systolic} onChange={(e) => setSystolic(e.target.value)} required />
        </label>
        <label htmlFor={`${id}-dia`}>
          Alapaine (mmHg)
          <input id={`${id}-dia`} type="number" inputMode="numeric" min={30} max={160} value={diastolic} onChange={(e) => setDiastolic(e.target.value)} required />
        </label>
        <button type="submit" disabled={busy}>Tallenna mittaus</button>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </form>
  );
}
