import type { MessageBasis } from '../types';

function List({ items, empty }: { items: string[]; empty: string }) {
  return items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">{empty}</p>;
}

export default function BasisPanel({ basis, id }: { basis: MessageBasis; id: string }) {
  return (
    <div className="basis-panel" id={id}>
      <p className="basis-statement"><strong>{basis.statement}</strong></p>
      <dl className="fact-list">
        <div>
          <dt>Käytetty seuranta</dt>
          <dd><List items={basis.monitorings.map((m) => `${m.finding} (tila: ${m.status})`)} empty="Ei käytetty" /></dd>
        </div>
        <div>
          <dt>Käytetty terveystapahtuma</dt>
          <dd><List items={basis.events} empty="Ei käytetty" /></dd>
        </div>
        <div>
          <dt>Käyttäjän antama tieto</dt>
          <dd><List items={basis.userProvided} empty="Ei käyttäjän vahvistamia tietoja" /></dd>
        </div>
        <div>
          <dt>Käytetty evidenssilähde</dt>
          <dd>{basis.evidenceSource ?? <span className="muted">Ei käytetty</span>}</dd>
        </div>
        <div>
          <dt>Käytetty sääntö</dt>
          <dd>
            {basis.rules.length ? (
              <ul>
                {basis.rules.map((rule) => (
                  <li key={rule.id}>
                    <code>{rule.id}</code> – {rule.name}
                    {rule.demoNotice && <><br /><small className="muted">{rule.demoNotice}</small></>}
                  </li>
                ))}
              </ul>
            ) : (
              <span className="muted">Ei sääntöä</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Kuka teki päätöksen</dt>
          <dd>{basis.decisionBy}</dd>
        </div>
        <div>
          <dt>Kuka muotoili tekstin</dt>
          <dd>{basis.textBy}</dd>
        </div>
      </dl>
    </div>
  );
}
