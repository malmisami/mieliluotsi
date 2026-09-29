"""Conversational intake: interpretations stay proposals until the client approves them."""
from __future__ import annotations

import pytest

from app.valituki import content, fit_profile, insights, intake, matching_flow, records
from app.valituki.ai import DemoAIProvider
from app.valituki.matching_flow import MatchingError

from .conftest import client_of

CONSENT = {'proactiveCheckins': True, 'storeHistory': True, 'professionalMonitoring': True}


def _converse(state, client):
    answers = content.client_spec(client.id)['intake']['answers']
    who = records.client_actor(client.id)
    session = intake.start(state, client, CONSENT, who)
    while session.status == 'conversation':
        intake.answer(state, client, answers[session.pendingQuestionKey], DemoAIProvider(), who)
    return session


def test_intake_asks_focused_questions_one_at_a_time(state):
    client = client_of(state)
    session = intake.start(state, client, CONSENT, records.client_actor(client.id))
    assert session.messages[-1].text == 'Kerro omin sanoin, miksi hait apua.'
    intake.answer(state, client, 'Työhön liittyvä ahdistus on kasvanut, jännitän palavereja.', DemoAIProvider(), 'client:cl-aino')
    questions = [m for m in session.messages if m.role == 'assistant' and m.questionKey]
    assert questions[-1].text.count('?') == 1
    assert session.pendingQuestionKey == 'change'


def test_conversational_intake_does_not_automatically_approve_inferred_information(state):
    """Test 1: AI inferences are proposals – nothing is stored, profiled or matchable before explicit approval."""
    client = client_of(state)
    session = _converse(state, client)
    assert session.status == 'review'
    assert {p.category for p in session.proposals} >= {'goal', 'working_style', 'practical'}
    goal = next(p for p in session.proposals if p.category == 'goal')
    assert goal.text == 'Haluan pystyä hallitsemaan työtilanteisiin liittyvää ahdistusta.'
    assert insights.for_client(state, client.id) == []
    assert insights.for_client(state, client.id, status=None) == []
    assert fit_profile.get(state, client.id) is None
    with pytest.raises(MatchingError):
        matching_flow.build_input(state, client)

    intake.confirm(state, client, records.client_actor(client.id))
    approved = insights.for_client(state, client.id)
    assert {i.kind for i in approved} >= {'primary_goal', 'working_style', 'practical'}
    assert all(i.status == 'approved' and i.approvedAt for i in approved)
    assert fit_profile.get(state, client.id) is not None


def test_excluded_or_edited_proposals_are_respected(state):
    client = client_of(state)
    session = _converse(state, client)
    style = next(p for p in session.proposals if p.category == 'working_style')
    goal = next(p for p in session.proposals if p.category == 'goal')
    intake.update_proposal(state, client, style.id, {'included': False})
    intake.update_proposal(state, client, goal.id, {'text': 'Haluan pärjätä palavereissa ilman unettomia öitä.'})
    intake.confirm(state, client, records.client_actor(client.id))
    kinds = {i.kind for i in insights.for_client(state, client.id)}
    assert 'working_style' not in kinds
    primary = insights.for_client(state, client.id, kind='primary_goal')[0]
    assert primary.text == 'Haluan pärjätä palavereissa ilman unettomia öitä.'
    assert primary.origin == 'user_said' and primary.editedByClient


def test_intake_completion_starts_support_immediately(state):
    client = client_of(state)
    _converse(state, client)
    intake.confirm(state, client, 'client:cl-aino')
    intake.complete(state, client, {'checkInDays': [0, 2, 5], 'communicationStyle': 'brief'}, 3, 'client:cl-aino')
    assert client.journeyState == 'WAITING_ACTIVE'
    assert client.baseline == 3
    assert client.nextCheckInDate
    assert any(a.clientId == client.id and a.type == 'create_plan' for a in state.actions)
    assert client.todayActivity is not None


def test_todays_wellbeing_can_be_answered_on_the_home_screen_after_the_intake(state):
    client = client_of(state)
    _converse(state, client)
    intake.confirm(state, client, 'client:cl-aino')
    intake.complete(state, client, {'checkInDays': [0, 2, 5], 'communicationStyle': 'brief'}, None, 'client:cl-aino')
    assert client.journeyState == 'WAITING_ACTIVE'
    assert client.baseline is None
    assert intake.needs_baseline(state, client)
    intake.record_baseline(state, client, 3, 'client:cl-aino', anxiety=3)
    assert client.baseline == 3
    assert not intake.needs_baseline(state, client)
    with pytest.raises(intake.IntakeError):
        intake.record_baseline(state, client, 4, 'client:cl-aino')


def test_safety_phrase_in_intake_interrupts_the_conversation(state):
    client = client_of(state)
    session = intake.start(state, client, CONSENT, 'client:cl-aino')
    result = intake.answer(state, client, 'En jaksa enää, haluaisin kuolla.', DemoAIProvider(), 'client:cl-aino')
    assert result['safety']['level'] == 3
    assert client.safetyLock and not client.safetyLock.dismissedAt
    assert session.messages[-1].source == 'fixed' and '112' in session.messages[-1].text
