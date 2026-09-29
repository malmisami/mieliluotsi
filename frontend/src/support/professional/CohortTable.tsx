import { useEffect, useState } from 'react';
import { supportApi } from '../api';
import type { CohortPage } from '../types';

/** The synthetic cohort, one server-side page at a time (never all profiles in the browser). */
export default function CohortTable() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [theme, setTheme] = useState('');
  const [data, setData] = useState<CohortPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    supportApi.cohort({ page, pageSize: 20, status, theme })
      .then((result) => { setData(result); setError(null); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [page, status, theme]);

  return (
    <section className="panel cohort-panel" aria-labelledby="cohort-list-title">
      <h2 id="cohort-list-title">Asiakaslista (synteettinen pilottikohortti)</h2>
      <p className="muted small">Yksi sivu kerrallaan palvelimelta. Henkilöt ovat keksittyjä.</p>
      <div className="filter-row">
        <label>
          Tila
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">Kaikki</option>
            {data && Object.entries(data.filters.statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
        <label>
          Teema
          <select value={theme} onChange={(e) => { setTheme(e.target.value); setPage(1); }}>
            <option value="">Kaikki</option>
            {data?.filters.themes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <span className="muted small" aria-live="polite">{loading ? 'Haetaan…' : data ? `${data.total.toLocaleString('fi-FI')} henkilöä` : ''}</span>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {data && (
        <>
          <div className="table-wrap">
            <table className="audit-table">
              <caption className="visually-hidden">Synteettinen asiakaslista, sivu {data.page}/{data.pages}</caption>
              <thead>
                <tr><th scope="col">Tunnus</th><th scope="col">Ikäryhmä</th><th scope="col">Teemat</th><th scope="col">Tila</th><th scope="col">Omahoitotehtävät</th><th scope="col">Eskalaatiot</th></tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.id}>
                    <td><code>{row.id}</code></td>
                    <td>{row.ageBand}</td>
                    <td>{row.themes.join(', ')}</td>
                    <td>{row.statusLabel}{row.waitingForProfessional ? ' · odottaa' : ''}</td>
                    <td>{row.tasksDone}/{row.tasksAgreed}</td>
                    <td>{row.escalations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="pager" aria-label="Sivutus">
            <button type="button" className="btn-secondary" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}>Edellinen</button>
            <span>Sivu {data.page}/{data.pages}</span>
            <button type="button" className="btn-secondary" disabled={page >= data.pages || loading} onClick={() => setPage(page + 1)}>Seuraava</button>
          </nav>
        </>
      )}
    </section>
  );
}
