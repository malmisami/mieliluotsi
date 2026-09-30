"""Which therapy approach fits the client – a transparent, rule-based suggestion next to therapist matching.

The approaches and their profiles live in data/valituki/modalities.json (a demo table a clinical owner would approve).
Three components, each 0–1, weighted to 0–100 like therapist matching:

- goals: how well the approach suits the client's approved goal topics (the referral's topics until the client has
  approved goals of their own);
- workingStyle: the client's approved working-style wishes against the approach's typical way of working, on the same
  1–5 levels as the therapists' in matching;
- experience: how the approach's own exercises went during the wait – the 0–10 changes of guided exercises (with the
  practice-sharing consent; journal entries are never read) and the client's ratings of self-care activities they allow
  to be used in matching. Unknown until there is some, and counted as neutral until then.

Only data the client allows to be used in matching is used, as in therapist matching. No language model takes part and
the same input always gives the same order. It is a suggestion for the professional's decision, not a treatment
recommendation.
"""
from __future__ import annotations

from statistics import mean
from typing import Any

from app.valituki import adapters, content, insights
from app.valituki.labels import join_fi, topic
from app.valituki.matching import STYLE_TARGETS
from app.valituki.models import ClientProfile, ValitukiState

COMPONENTS = (('goals', 'Tavoitteet'), ('workingStyle', 'Työtapa'), ('experience', 'Kokemus'))
TOOL_NAMES = {'thought_record': 'Ajatusten tutkiminen', 'exposure': 'Altistusaskeleet', 'experiment': 'Käyttäytymiskokeet'}


def config() -> dict[str, Any]:
    return content.load('modalities.json')


def _topics(state: ValitukiState, client: ClientProfile) -> tuple[dict[str, float], str]:
    """The goal topics with their weights (primary goals weigh more, as in matching) – or the referral's."""
    weights = content.matching_config()['goalWeights']
    topics: dict[str, float] = {}
    for insight in insights.for_client(state, client.id):
        if insight.kind in ('primary_goal', 'secondary_goal') and insight.sharing.matching:
            weight = float(weights['primary' if insight.kind == 'primary_goal' else 'secondary'])
            for key in insight.structured.get('topics', []):
                topics[key] = max(topics.get(key, 0.0), weight)
    if topics:
        return topics, 'tavoitteet'
    referral = adapters.waiting_list.referral_for(state, client.id)
    return {key: 1.0 for key in (referral.requiredCompetencies if referral else [])}, 'lähete'


def _style(state: ValitukiState, client: ClientProfile) -> dict[str, str]:
    insight = next((i for i in insights.for_client(state, client.id, kind='working_style') if i.sharing.matching), None)
    return {key: value for key in STYLE_TARGETS if insight and (value := insight.structured.get(key))}


def _helped(change: int) -> float:
    """A 0–10 change as how much an exercise helped: 0.5 = no change, 1 = three points or more."""
    return max(0.0, min(1.0, 0.5 + change / 6))


def _practice(state: ValitukiState, client: ClientProfile) -> dict[str, list[float]]:
    """Per guided tool, how each of the client's exercises went – only with the practice-sharing consent."""
    if not client.consent.sharePractice:
        return {}
    done: dict[str, list[float]] = {}
    for record in state.thoughtRecords:
        if record.clientId == client.id and record.intensityBefore is not None and record.intensityAfter is not None:
            done.setdefault('thought_record', []).append(_helped(record.intensityBefore - record.intensityAfter))
    for ladder in (lad for lad in state.ladders if lad.clientId == client.id):
        for attempt in (a for step in ladder.steps for a in step.attempts):
            if attempt.peak is not None and attempt.after is not None:
                done.setdefault('exposure', []).append(_helped(attempt.peak - attempt.after))
    for experiment in state.experiments:
        if experiment.clientId == client.id and experiment.status == 'done' and None not in (experiment.beliefBefore,
                                                                                               experiment.beliefAfter):
            done.setdefault('experiment', []).append(_helped(experiment.beliefBefore - experiment.beliefAfter))
    return done


def _ratings(state: ValitukiState, client: ClientProfile) -> dict[str, list[float]]:
    """The client's own 1–5 ratings of self-care activities – those whose insight they allow to be used in matching."""
    allowed = {i.structured.get('activityId') for i in insights.for_client(state, client.id)
               if i.kind in ('activity_helpful', 'activity_not_helpful') and i.sharing.matching}
    ratings: dict[str, list[float]] = {}
    for completion in state.activityCompletions:
        if completion.clientId == client.id and completion.rating and completion.activityId in allowed:
            ratings.setdefault(completion.activityId, []).append((completion.rating - 1) / 4)
    return ratings


def rank(state: ValitukiState, client: ClientProfile) -> dict[str, Any]:
    cfg = config()
    weights, neutral, full = cfg['weights'], float(cfg['neutralScore']), float(cfg['experienceFullAfter'])
    topics, topic_source = _topics(state, client)
    style = _style(state, client)
    practice, ratings = _practice(state, client), _ratings(state, client)
    pool = [t for t in adapters.therapist_directory.therapists(state) if t.active]
    rows = []
    for modality in cfg['modalities']:
        # Goals: the weighted share of the client's topics the approach suits.
        goal = (sum(w * float(modality['topics'].get(key, 0.0)) for key, w in topics.items()) / sum(topics.values())
                if topics else neutral)
        # Working style: 1 − distance / 4 on each wish the client has approved, as for the therapists.
        fits = [1 - abs(STYLE_TARGETS[key][1][wish] - int(modality['style'][key])) / 4 for key, wish in style.items()]
        working = mean(fits) if fits else neutral
        # Experience: what the client's own exercises and ratings say – more of it counts more, up to `full` items.
        tried = {name: practice[tool] for tool, name in TOOL_NAMES.items() if tool in modality['tools'] and practice.get(tool)}
        evidence = [h for values in tried.values() for h in values] + [
            h for activity in modality['activities'] for h in ratings.get(activity, [])]
        experience = neutral + (mean(evidence) - neutral) * min(1.0, len(evidence) / full) if evidence else neutral
        scores = {'goals': goal, 'workingStyle': working, 'experience': experience}
        known = {'goals': bool(topics), 'workingStyle': bool(style), 'experience': bool(evidence)}
        own = len(evidence) - sum(len(values) for values in tried.values())
        details = {
            'goals': (f'{"Tavoitteet" if topic_source == "tavoitteet" else "Lähete"}: '
                      + join_fi([topic(key).lower() for key in topics])) if topics else 'Ei vielä tavoitteita',
            'workingStyle': 'Hyväksytyt työskentelytapatoiveet' if style else 'Ei vielä työskentelytapatoiveita',
            'experience': join_fi([f'{name} {len(values)}×' for name, values in tried.items()]
                                  + ([f'omat arviot {own}×'] if own else [])) or 'Ei vielä kokemusta odotusajalta',
        }
        total = round(sum(float(weights[key]) * scores[key] for key, _ in COMPONENTS), 1)
        offered = [t.name for t in pool if set(t.therapeuticApproaches) & set(modality['approaches'])]
        rows.append({'id': modality['id'], 'label': modality['label'], 'total': total,
                     'therapists': len(offered),
                     'components': [{'key': key, 'label': label, 'score': round(scores[key], 3), 'known': known[key],
                                     'detail': details[key]} for key, label in COMPONENTS]})
    rows.sort(key=lambda r: (-r['total'], r['label']))
    return {'rows': rows, 'version': cfg['version']}
