import { useState } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { Sheet } from '../components/ui';
import { useClientUI } from './ClientApp';

export default function ContactSheet({ initialReason, onClose }: { initialReason?: string; onClose: () => void }) {
  const { view, run, busy } = useValituki();
  const { client } = useClientUI();
  const [reason, setReason] = useState(initialReason ?? 'wellbeing');
  const [message, setMessage] = useState('');
  const reasons = view.meta.labels.contactReasons;

  async function send() {
    const result = await run((s) => api.requestHuman(s, client.id, reason, message),
      () => 'Pyyntö välitettiin hoitotiimille heti. Demo: yhteydenotto kahden arkipäivän kuluessa.');
    if (result) onClose();
  }

  return (
    <Sheet title="Haluan keskustella ammattilaisen kanssa" onClose={onClose}
      footer={<button type="button" className="btn btn-primary btn-block" disabled={busy} onClick={send}>Lähetä pyyntö</button>}>
      <p className="muted">Pyyntö menee hoitotiimille heti. Se ei ole päivystyspalvelu – jos tarvitset apua juuri nyt, käytä ”Apua nyt”.</p>
      <div className="radio-list" role="radiogroup" aria-label="Aihe">
        {Object.entries(reasons).map(([key, label]) => (
          <label key={key} className="radio-row">
            <input type="radio" name="contact-reason" checked={reason === key} onChange={() => setReason(key)} /> {label}
          </label>
        ))}
      </div>
      <label className="q" htmlFor="contact-msg">Viesti (vapaaehtoinen)</label>
      <textarea id="contact-msg" rows={3} value={message} onChange={(e) => setMessage(e.target.value)} />
    </Sheet>
  );
}
