"""What Mieliluotsi remembers about the client ("Mieliluotsi muistaa minusta") and who may use it.

Every insight has a status and per-item sharing:
  🔒 Vain minä                          – sharing.professional = sharing.matching = False
  👩‍⚕️ Saa näkyä ammattilaiselle          – sharing.professional = True
  🧩 Saa käyttää terapeutin matchingissa – sharing.matching = True

Only approved insights are used anywhere; proposals (AI interpretations, detected patterns) wait for the client's explicit
decision. Every permission change is stored as an append-only InsightPermission record and in the audit log.
"""
from __future__ import annotations

from typing import Any, Optional

from app.valituki import journey, records
from app.valituki.models import ClientInsight, ClientProfile, Goal, InsightPermission, InsightSharing, ValitukiState
from app.valituki.store import NotFoundError, next_id, now

DEFAULT_SHARING: dict[str, tuple[bool, bool]] = {
    'primary_goal': (True, True),
    'secondary_goal': (True, True),
    'working_style': (True, True),
    'practical': (True, True),
    'difficult_times': (True, False),
    'helped_before': (True, False),
    'pattern': (True, False),
    'activity_helpful': (True, False),
    'activity_not_helpful': (True, False),
    'engagement': (False, False),
}


class InsightError(ValueError):
    """The insight action is not possible (HTTP 409)."""


def scope_label(sharing: InsightSharing) -> str:
    if sharing.professional and sharing.matching:
        return 'professional+matching'
    if sharing.matching:
        return 'matching'
    if sharing.professional:
        return 'professional'
    return 'private'


def default_sharing(kind: str) -> InsightSharing:
    professional, matching = DEFAULT_SHARING.get(kind, (False, False))
    return InsightSharing(professional=professional, matching=matching)


def get(state: ValitukiState, client: ClientProfile, insight_id: str) -> ClientInsight:
    insight = next((i for i in state.insights if i.id == insight_id and i.clientId == client.id), None)
    if insight is None:
        raise NotFoundError('Tietoa ei löytynyt.')
    return insight


def for_client(state: ValitukiState, client_id: str, *, status: Optional[str] = 'approved',
               kind: Optional[str] = None) -> list[ClientInsight]:
    return [i for i in state.insights if i.clientId == client_id and (status is None or i.status == status)
            and (kind is None or i.kind == kind)]


def usable_for_matching(insight: ClientInsight) -> bool:
    return insight.status == 'approved' and insight.sharing.matching


def visible_to_professional(insight: ClientInsight) -> bool:
    return insight.status == 'approved' and insight.sharing.professional


def create(state: ValitukiState, client: ClientProfile, *, category: str, kind: str, title: str, text: str,
           origin: str, source_label: str, actor: str, source: str, status: str = 'proposed',
           structured: Optional[dict[str, Any]] = None, user_words: Optional[list[str]] = None,
           evidence: Optional[dict[str, Any]] = None, sharing: Optional[InsightSharing] = None,
           edited: bool = False, at: Optional[str] = None) -> ClientInsight:
    stamp = now(state, at)
    share = sharing or default_sharing(kind)
    insight = ClientInsight(
        id=next_id(state, 'ins'), clientId=client.id, category=category, kind=kind, title=title, text=text,
        structured=structured or {}, userWords=user_words or [], origin=origin, sourceLabel=source_label, status=status,
        sharing=share, evidence=evidence or {}, editedByClient=edited, consentScope=scope_label(share),
        approvedAt=stamp if status == 'approved' else None, decidedAt=stamp if status == 'approved' else None,
        createdAt=stamp, updatedAt=stamp, createdBy=actor, source=source)
    state.insights.append(insight)
    if status == 'approved':
        _record_permission(state, client, insight, None, actor, 'Oletuslupa hyväksynnän yhteydessä')
        _sync_goal(state, client, insight, actor)
    return insight


def approve(state: ValitukiState, client: ClientProfile, insight: ClientInsight, actor: str) -> ClientInsight:
    if insight.status != 'proposed':
        raise InsightError('Vain ehdotuksen voi hyväksyä.')
    stamp = now(state)
    insight.status = 'approved'
    insight.approvedAt = insight.decidedAt = stamp
    insight.updatedAt = stamp
    _record_permission(state, client, insight, None, actor, 'Oletuslupa hyväksynnän yhteydessä')
    _sync_goal(state, client, insight, actor)
    records.audit(state, actor=actor, action='insight_approved', client_id=client.id,
                  detail=f'Asiakas hyväksyi: {insight.title} – "{insight.text}"')
    return insight


def reject(state: ValitukiState, client: ClientProfile, insight: ClientInsight, actor: str) -> ClientInsight:
    if insight.status != 'proposed':
        raise InsightError('Vain ehdotuksen voi hylätä.')
    insight.status = 'rejected'
    insight.decidedAt = insight.updatedAt = now(state)
    insight.sharing = InsightSharing()
    insight.consentScope = 'private'
    records.audit(state, actor=actor, action='insight_rejected', client_id=client.id,
                  detail=f'Asiakas ei tunnistanut havaintoa omakseen: {insight.title}. Sitä ei käytetä mihinkään.')
    return insight


def update_text(state: ValitukiState, client: ClientProfile, insight: ClientInsight, text: str, actor: str,
                structured: Optional[dict[str, Any]] = None) -> ClientInsight:
    if insight.status not in ('approved', 'proposed'):
        raise InsightError('Poistettua tietoa ei voi muokata.')
    text = text.strip()[:400]
    if not text:
        raise InsightError('Kirjoita teksti tai poista tieto.')
    insight.text = text
    if structured is not None:
        insight.structured = {**insight.structured, **structured}
    insight.editedByClient = True
    insight.origin = 'user_said' if insight.origin == 'ai_interpreted' else insight.origin
    insight.version += 1
    insight.updatedAt = now(state)
    _sync_goal(state, client, insight, actor)
    records.audit(state, actor=actor, action='insight_edited', client_id=client.id,
                  detail=f'Asiakas muokkasi tietoa: {insight.title} (versio {insight.version}).')
    return insight


def set_sharing(state: ValitukiState, client: ClientProfile, insight: ClientInsight, *, professional: bool,
                matching: bool, actor: str) -> ClientInsight:
    if insight.status != 'approved':
        raise InsightError('Käyttöoikeuksia voi muuttaa vain hyväksytyille tiedoille.')
    previous = insight.sharing.model_copy()
    if previous.professional == professional and previous.matching == matching:
        return insight
    insight.sharing = InsightSharing(professional=professional, matching=matching)
    insight.consentScope = scope_label(insight.sharing)
    insight.updatedAt = now(state)
    _record_permission(state, client, insight, previous, actor, 'Asiakas muutti käyttöoikeutta')
    journey.apply(state, client, 'INSIGHT_PERMISSION_CHANGED', actor=actor, source='client',
                  payload={'insightId': insight.id, 'professional': professional, 'matching': matching,
                           'previous': previous.model_dump()})
    return insight


def remove(state: ValitukiState, client: ClientProfile, insight: ClientInsight, actor: str) -> ClientInsight:
    if insight.status == 'removed':
        return insight
    previous = insight.sharing.model_copy()
    insight.status = 'removed'
    insight.sharing = InsightSharing()
    insight.consentScope = 'private'
    insight.updatedAt = now(state)
    _record_permission(state, client, insight, previous, actor, 'Tieto poistettiin')
    for goal in state.goals:
        if goal.insightId == insight.id:
            goal.status = 'archived'
            goal.updatedAt = insight.updatedAt
    records.audit(state, actor=actor, action='insight_removed', client_id=client.id,
                  detail=f'Asiakas poisti tiedon: {insight.title}. Sitä ei enää käytetä eikä jaeta.')
    return insight


def _record_permission(state: ValitukiState, client: ClientProfile, insight: ClientInsight,
                       previous: Optional[InsightSharing], actor: str, reason: str) -> None:
    stamp = now(state)
    state.insightPermissions.append(InsightPermission(
        id=next_id(state, 'perm'), clientId=client.id, insightId=insight.id, professional=insight.sharing.professional,
        matching=insight.sharing.matching, previous=previous.model_dump() if previous else None, reason=reason,
        createdAt=stamp, updatedAt=stamp, createdBy=actor, source='client' if actor.startswith('client') else 'system'))
    if previous is not None:
        records.audit(state, actor=actor, action='insight_permission', client_id=client.id,
                      detail=f'{insight.title}: ammattilainen {"kyllä" if insight.sharing.professional else "ei"}, '
                             f'matching {"kyllä" if insight.sharing.matching else "ei"} ({reason.lower()}).')


def _sync_goal(state: ValitukiState, client: ClientProfile, insight: ClientInsight, actor: str) -> None:
    """Approved goal insights are mirrored as Goal records (used by the plan, the handover and the therapist)."""
    if insight.kind not in ('primary_goal', 'secondary_goal') or insight.status != 'approved':
        return
    goal = next((g for g in state.goals if g.insightId == insight.id), None)
    stamp = now(state)
    if goal is None:
        state.goals.append(Goal(id=next_id(state, 'goal'), clientId=client.id, insightId=insight.id,
                                priority='primary' if insight.kind == 'primary_goal' else 'secondary', text=insight.text,
                                topics=list(insight.structured.get('topics', [])), createdAt=stamp, updatedAt=stamp,
                                createdBy=actor, source='client_approved'))
    else:
        goal.text = insight.text
        goal.topics = list(insight.structured.get('topics', goal.topics))
        goal.status = 'active'
        goal.updatedAt = stamp


def active_goals(state: ValitukiState, client_id: str) -> list[Goal]:
    goals = [g for g in state.goals if g.clientId == client_id and g.status == 'active']
    return sorted(goals, key=lambda g: (g.priority != 'primary', g.createdAt, g.id))
