"""Demo scenes: jump to a stage of Aino's journey. Each scene rebuilds the seed and replays the same steps the presenter
would click, through the same engine – so a jump gives exactly the state the live demo would have reached."""
from __future__ import annotations

from app.valituki import client_actions, content, intake, matching_flow, practice, professional, records, simulation, therapy
from app.valituki.models import ValitukiState
from app.valituki.seed import build_seed_state
from app.valituki.store import get_client

ORDER = ['start', 'intake', 'cbt', 'weeks', 'change', 'reviewed', 'matches', 'handover', 'therapy', 'aftercare']


class SceneError(ValueError):
    """Unknown scene (HTTP 400)."""


def build_scene(name: str) -> ValitukiState:
    if name not in ORDER:
        raise SceneError('Tuntematon demovaihe.')
    target = ORDER.index(name)
    state = build_seed_state()
    aino = get_client(state, 'cl-aino')
    who = records.client_actor(aino.id)

    def reached(step: str) -> bool:
        return target < ORDER.index(step)

    if reached('intake'):
        return state
    intake.run_scripted(state, aino, content.client_spec(aino.id)['intake'], who)
    if reached('cbt'):
        return state
    practice.demo_cbt(state, aino, who)
    if reached('weeks'):
        return state
    simulation.advance(state, 14)
    if reached('change'):
        return state
    for item in [i for i in state.insights if i.clientId == aino.id and i.kind == 'pattern' and i.status == 'proposed']:
        client_actions.decide_insight(state, aino, item.id, 'approve')
    simulation.simulate_deterioration(state, aino)
    if reached('reviewed'):
        return state
    for observation in [o for o in state.wellbeingObservations
                        if o.clientId == aino.id and o.status == 'open' and o.kind == 'trend_decline']:
        professional.review_observation(state, observation.id, 'mark_reviewed',
                                        'Soitettu Ainolle – jatketaan jonossa Mieliluotsin tuella.')
    if reached('matches'):
        return state
    simulation.open_next_pending(state)
    if reached('handover'):
        return state
    decision = matching_flow.current_decision(state, aino.id)
    if decision:
        anna = next((c for c in matching_flow.decision_candidates(state, decision) if c.therapistId == 'th-anna'), None)
        if anna:
            client_actions.select_candidate(state, aino, anna.id)
            client_actions.approve_handover(state, aino)
    if reached('therapy'):
        return state
    simulation.hold_first_session(state, aino)
    episode = therapy.episode(state, aino.id)
    if episode and episode.status == 'active':
        therapy.configure(state, aino, episode.therapistId, therapy.suggested_plan(state, aino),
                          records.therapist_actor(episode.therapistId))
    if reached('aftercare'):
        return state
    simulation.end_therapy(state, aino)
    return state
