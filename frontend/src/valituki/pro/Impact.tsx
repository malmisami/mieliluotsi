import { useValituki } from '../context';
import { ArrowRightIcon } from '../icons';

/** "Vaikuttavuus" – every value is a synthetic example, never a real outcome. */
export default function Impact() {
  const { view } = useValituki();
  const impact = view.professional.impact;
  const [hero, second, ...rest] = impact.metrics;
  return (
    <div className="impact-page">
      <p className="impact-label" role="note">{impact.label}</p>
      <section className="impact-hero">
        {[hero, second].map((m) => (
          <div key={m.key} className="impact-compare">
            <p className="kpi-label">{m.label}</p>
            <div className="compare-row">
              <div className="compare-before"><span className="compare-tag">Ennen</span><span className="compare-value">{m.before}</span></div>
              <ArrowRightIcon size={22} />
              <div className="compare-after"><span className="compare-tag">Mieliluotsilla</span><span className="compare-value">{m.after}</span></div>
            </div>
            <p className="muted small">{m.detail}</p>
            <p className="synthetic-tag">{impact.label}</p>
          </div>
        ))}
      </section>
      <section className="impact-grid">
        {rest.map((m) => (
          <div key={m.key} className="impact-tile">
            <p className="kpi-label">{m.label}</p>
            <p className="impact-value">{m.value}</p>
            <p className="muted small">{m.detail}</p>
            {m.demoValue && <p className="impact-demo">Tässä demossa: {m.demoValue}</p>}
            <p className="synthetic-tag">Synteettinen esimerkkiluku</p>
          </div>
        ))}
      </section>
      <p className="muted small">{impact.liveNote} Prototyyppi ei ole kliinisesti validoitu, eikä luvut kuvaa todellisia terveysvaikutuksia.</p>
    </div>
  );
}
