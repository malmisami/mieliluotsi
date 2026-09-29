import { AISwitch } from './DemoDock';

/** The AI switch at the top right of the professional, therapist and Konsepti views – not part of the product. In the client
    view it sits above the panel beside the phone (Backstage); whose view is shown is chosen in the demo dock. */
export default function StageControls() {
  return (
    <div className="stage-controls">
      <div className="stage-ai"><AISwitch /></div>
    </div>
  );
}
