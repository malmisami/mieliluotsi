import { useValituki } from '../context';
import { Pill, Synthetic } from '../components/ui';

export default function Directory() {
  const { view } = useValituki();
  const rows = view.professional.directory;
  const weights = view.meta.matching.weights;
  return (
    <div className="directory-page">
      <section className="card">
        <h2 className="card-title-lg">Terapeuttihakemisto ja kapasiteetti</h2>
        <Synthetic>Demon kuvitteelliset terapeutit. Vapaat ajat tulevat TherapistDirectoryAdapterin kalenterisynkronoinnista (mock).</Synthetic>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th scope="col">Terapeutti</th><th scope="col">Erityisosaaminen</th><th scope="col">Työote</th><th scope="col">Kielet</th>
                <th scope="col">Vastaanotto</th><th scope="col">Kapasiteetti</th><th scope="col">Seuraava vapaa aika</th></tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id} className={t.active ? '' : 'row-muted'}>
                  <td><strong>{t.name}</strong><span className="row-sub">{t.role}</span></td>
                  <td className="small">{t.specialties.join(', ')}</td>
                  <td className="small">{t.workingStyle}<span className="row-sub">{t.approaches.join(', ')}</span></td>
                  <td className="small">{t.languages.join(', ')}</td>
                  <td className="small">{t.formats.join(' · ')}<span className="row-sub">{t.availableTimes.join(', ')}</span></td>
                  <td>{t.active ? (
                    <Pill tone={t.currentCapacity >= t.maxCapacity ? 'warn' : 'ok'}>{t.currentCapacity}/{t.maxCapacity}</Pill>
                  ) : <Pill tone="neutral">{t.inactiveReason}</Pill>}</td>
                  <td className="small">{t.nextAvailableSlot ?? (t.currentCapacity >= t.maxCapacity ? 'Ei paikkoja' : '–')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card">
        <h2 className="card-title">Matchingin painot (muokattavissa: data/valituki/matching_config.json)</h2>
        <div className="weights">
          {Object.entries(weights).map(([key, value]) => (
            <div key={key} className="weight"><span>{WEIGHT_LABELS[key] ?? key}</span><strong>{value} %</strong></div>
          ))}
        </div>
        <p className="muted small">{view.meta.matching.note}</p>
        <h3 className="card-title">Integraatiopisteet (demossa mock-toteutukset)</h3>
        <ul className="adapters">
          {view.meta.adapters.map((a) => <li key={a.name}><code>{a.name}</code> – {a.production}</li>)}
        </ul>
      </section>
    </div>
  );
}

const WEIGHT_LABELS: Record<string, string> = {
  goalCompetence: 'Tavoitteet ja osaaminen', workingStyle: 'Työskentelytapa', userPreferences: 'Omat toiveet',
  languageAccessibility: 'Kieli ja saavutettavuus', availabilityContinuity: 'Saatavuus ja jatkuvuus', logistics: 'Logistiikka',
};
