import { useValituki } from '../context';
import { PersonIcon, StethoscopeIcon, UsersIcon } from '../icons';
import { AISwitch } from './DemoDock';

/** Demo controls on the screen, not part of the product: whose view is shown, and demo texts or Claude. A column beside the
    phone in the client view (`side`), a row above the other views. */
export default function StageControls({ side = false }: { side?: boolean }) {
  const { view, role, setRole, scope } = useValituki();
  const clientName = view.demo.clients.find((c) => c.id === scope.clientId)?.firstName;
  const therapistName = view.demo.therapists.find((t) => t.id === scope.therapistId)?.name.split(' ')[0];
  return (
    <div className={`stage-controls ${side ? 'is-side' : ''}`}>
      <nav className="roles" aria-label="Demo: näkymä">
        <span className="roles-label">Näkymä</span>
        <div className="roles-group" role="group">
          <button type="button" aria-pressed={role === 'client'} onClick={() => setRole('client')}>
            <PersonIcon size={17} /> Asiakas{clientName ? <span className="role-who">{clientName}</span> : null}
          </button>
          <button type="button" aria-pressed={role === 'professional'} onClick={() => setRole('professional')}>
            <StethoscopeIcon size={17} /> Ammattilainen
          </button>
          <button type="button" aria-pressed={role === 'therapist'} onClick={() => setRole('therapist')}>
            <UsersIcon size={17} /> Terapeutti{therapistName ? <span className="role-who">{therapistName}</span> : null}
          </button>
        </div>
      </nav>
      <div className="stage-ai"><AISwitch /></div>
    </div>
  );
}
