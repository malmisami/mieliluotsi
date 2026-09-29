import { useState } from 'react';
import { supportApi } from '../api';

const SAMPLE = 'asiakas_tunnus;pvm;mittaus;arvo;yksikko;systolinen;diastolinen;ymparisto;viite_lippu;lahde\nSYN-TESTI-01;2.9.2026;RR;;mmHg;128;82;koti;;Kotimittaus (synteettinen)\nSYN-TESTI-01;2026-05-12;LDL;3,1;mmol/l;;;laboratorio;H;Laboratorio (synteettinen)';

/** Try the LUVN CSV/JSON mapping without saving anything. */
export default function AdapterPreview() {
  const [content, setContent] = useState(SAMPLE);
  const [table, setTable] = useState('mittaukset.csv');
  const [format, setFormat] = useState<'csv' | 'json'>('csv');
  const [result, setResult] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  async function preview() {
    try {
      const data = await supportApi.previewAdapter({ format, content, table: format === 'csv' ? table : undefined });
      setResult(JSON.stringify(data, null, 2));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
      setResult('');
    }
  }

  return (
    <details className="panel adapter-preview">
      <summary><strong>Tietolähteiden adapterit (kehittäjätyökalu)</strong></summary>
      <p className="muted small">LUVN-tyyppinen CSV- tai JSON-aineisto muunnetaan sisäiseen PersonProfile-malliin. Esikatselu ei tallenna mitään. Oletusskeema: docs/LUVN_ADAPTER.md.</p>
      <div className="filter-row">
        <label>
          Muoto
          <select value={format} onChange={(e) => setFormat(e.target.value as 'csv' | 'json')}>
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
          </select>
        </label>
        {format === 'csv' && (
          <label>
            Taulu
            <select value={table} onChange={(e) => setTable(e.target.value)}>
              {['mittaukset.csv', 'laboratoriotulokset.csv', 'diagnoosit.csv', 'laakitys.csv', 'asioinnit.csv'].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
        )}
      </div>
      <label>
        Sisältö
        <textarea rows={5} value={content} onChange={(e) => setContent(e.target.value)} spellCheck={false} />
      </label>
      <button type="button" onClick={preview}>Esikatsele mäppäys</button>
      {error && <p className="form-error" role="alert">{error}</p>}
      {result && <pre className="json">{result}</pre>}
    </details>
  );
}
