import { AISwitch } from './DemoDock';

/** The AI switch on the screen, not part of the product: demo texts or Claude. Beside the phone in the client view (`side`),
    at the top right of the other views. Whose view is shown is chosen in the demo dock. */
export default function StageControls({ side = false }: { side?: boolean }) {
  return (
    <div className={`stage-controls ${side ? 'is-side' : ''}`}>
      <div className="stage-ai"><AISwitch /></div>
    </div>
  );
}
