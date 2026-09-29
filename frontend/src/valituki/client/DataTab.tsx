import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { fmtDateTime, fmtShort } from '../format';
import { CheckIcon, CrossIcon, EditIcon, LayersIcon, SparkleIcon, TrashIcon } from '../icons';
import { Empty, Pill, SharingControl } from '../components/ui';
import type { ConsentScope, InsightRow } from '../types';
import { useClientUI } from './ClientApp';

export default function DataTab() {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const memory = client.memory;
  const consents = view.meta.labels.consents;
  return (
    <div className="screen data">
      <h1 className="display-sm">Mieliluotsi muistaa minusta</h1>
      <p className="lead-sm">Sinä päätät, mitä tietoja jaetaan. Jokaisesta tiedosta näet, mistä se tuli ja kuka saa käyttää sitä.</p>

      {memory.pending.length > 0 && (
        <section className="card pending-card">
          <h3 className="card-title"><SparkleIcon size={17} /> Odottaa päätöstäsi</h3>
          {memory.pending.map((item) => (
            <div key={item.id} className="pending-item">
              <p>{item.text}</p>
              <div className="row-gap">
                <button type="button" className="btn btn-violet btn-sm" disabled={busy} onClick={() => run((s) => api.decideInsight(s, client.id, item.id, 'approve'))}>
                  <CheckIcon size={15} /> Tämä tuntuu oikealta</button>
                <button type="button" className="btn btn-quiet btn-sm" disabled={busy} onClick={() => run((s) => api.decideInsight(s, client.id, item.id, 'reject'))}>
                  <CrossIcon size={15} /> Ei kuvaa tilannettani</button>
              </div>
            </div>
          ))}
        </section>
      )}

      {memory.groups.map((group) => (
        <section key={group.key} className="mem-group">
          <h2 className="mem-title">{group.label}</h2>
          {group.items.length === 0 ? <p className="muted small">Ei tallennettuja tietoja.</p>
            : group.items.map((item) => <MemoryItem key={item.id} item={item} />)}
        </section>
      ))}

      <section className="card">
        <h3 className="card-title">Palvelun suostumukset</h3>
        {(Object.keys(consents) as (keyof ConsentScope)[]).map((key) => (
          <label key={key} className="switch-row">
            <span><span className="switch-title">{consents[key].title}</span><span className="switch-desc">{consents[key].description}</span></span>
            <input type="checkbox" className="switch" checked={memory.consent[key]} disabled={busy}
              onChange={(e) => run((s) => api.setConsent(s, client.id, { [key]: e.target.checked }), () => 'Suostumus päivitettiin ja kirjattiin.')} />
          </label>
        ))}
      </section>

      {memory.fitProfile && (
        <section className="card">
          <div className="card-row"><h3 className="card-title"><LayersIcon size={17} /> Therapy Fit Profile</h3><Pill tone="brand">versio {memory.fitProfile.version}</Pill></div>
          <ol className="changelog">
            {[...memory.fitProfile.changelog].reverse().map((c) => (
              <li key={c.version}><span className="muted small">v{c.version} · {fmtShort(c.at)}</span> {c.change}</li>
            ))}
          </ol>
        </section>
      )}

      {memory.permissionHistory.length > 0 && (
        <section className="card">
          <h3 className="card-title">Käyttöoikeuksien muutokset</h3>
          <ul className="perm-log">
            {memory.permissionHistory.map((p, i) => (
              <li key={i}><span className="muted small">{fmtDateTime(p.at)}</span> {p.title}: ammattilainen {p.professional ? 'kyllä' : 'ei'},
                matching {p.matching ? 'kyllä' : 'ei'}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="card">
        <h3 className="card-title">Mitä on tallennettu</h3>
        <p className="small">{memory.stored.checkIns} check-iniä · {memory.stored.journal} päiväkirjamerkintää (näkyvät vain sinulle) ·
          {' '}{memory.stored.messages} viestiä · keskusteluhistoriaa ei jaeta kenellekään</p>
        {memory.handover && <p className="small">Yhteenveto terapeutille: {memory.handover.statusLabel}</p>}
      </section>
      {memory.pending.length === 0 && memory.groups.every((g) => g.items.length === 0) && (
        <Empty title="Mieliluotsi ei muista sinusta vielä mitään">Tiedot tallennetaan vasta, kun hyväksyt ne.</Empty>
      )}
    </div>
  );
}

function MemoryItem({ item }: { item: InsightRow }) {
  const { run, busy } = useValituki();
  const { client } = useClientUI();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.text);
  return (
    <article className="mem-item">
      <div className="mem-head">
        <p className="mem-kind">{item.title}</p>
        {item.editedByClient && <Pill tone="brand" icon={<EditIcon size={11} />}>Muokattu</Pill>}
      </div>
      {editing ? (
        <div className="stack-sm">
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} aria-label={`Muokkaa: ${item.title}`} />
          <div className="row-gap">
            <button type="button" className="btn btn-primary btn-sm" disabled={busy || !text.trim()}
              onClick={async () => { await run((s) => api.editInsight(s, client.id, item.id, text), () => 'Tieto päivitettiin.'); setEditing(false); }}>Tallenna</button>
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => { setText(item.text); setEditing(false); }}>Peruuta</button>
          </div>
        </div>
      ) : <p className="mem-text">{item.text}</p>}
      <p className="mem-meta">{item.sourceLabel} · {fmtShort(item.date)} · {item.originLabel}</p>
      <p className="mem-q">Kuka saa käyttää tätä tietoa?</p>
      <SharingControl sharing={item.sharing} busy={busy}
        onChange={(next) => run((s) => api.setSharing(s, client.id, item.id, next), () =>
          `Käyttöoikeus päivitettiin: ${!next.professional && !next.matching ? 'vain sinä' : [next.professional && 'ammattilainen', next.matching && 'matching'].filter(Boolean).join(' + ')}.`)} />
      <div className="mem-actions">
        {item.editable && !editing && <button type="button" className="btn btn-quiet btn-sm" disabled={busy} onClick={() => setEditing(true)}><EditIcon size={14} /> Muokkaa</button>}
        <button type="button" className="btn btn-quiet btn-sm" disabled={busy}
          onClick={() => run((s) => api.removeInsight(s, client.id, item.id), () => 'Tieto poistettiin – sitä ei enää käytetä eikä jaeta.')}>
          <TrashIcon size={14} /> Poista
        </button>
      </div>
    </article>
  );
}
