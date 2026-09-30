"""The therapy approach suggestion: rules only, approved data allowed in matching only, practice only with the consent."""
from __future__ import annotations

from app.valituki import content, insights, modality, practice, view
from app.valituki.ai import DemoAIProvider

from .conftest import client_of, run_intake

DEMO = content.client_spec('cl-aino')['practiceDemo']


def _row(result, modality_id):
    return next(r for r in result['rows'] if r['id'] == modality_id)


def _component(row, key):
    return next(c for c in row['components'] if c['key'] == key)


def _thought_record(state, client):
    practice.start(state, client, 'thought_record', DemoAIProvider(), 'client:cl-aino',
                   prefill={'situation': 'Tiistaina pitää esitellä.'})
    practice.run_script(state, client, {'thought_record': {**DEMO['thought_record'], 'nextStep': 'none'}}, actor='client:cl-aino')


def test_the_approach_follows_the_goals_and_the_working_style(state):
    client = run_intake(state)
    result = modality.rank(state, client)
    # Anxiety in work situations, a structured and concrete way of working with homework → CBT first.
    assert result['rows'][0]['id'] == 'cbt' and result['rows'][-1]['id'] == 'psychodynamic'
    cbt = _row(result, 'cbt')
    assert _component(cbt, 'goals')['known'] and _component(cbt, 'workingStyle')['known']
    assert not _component(cbt, 'experience')['known']  # nothing tried yet: neutral, shown as unknown
    assert modality.rank(state, client) == result  # the same input always gives the same order
    assert view.client_view(state, client)['backstage']['modality']['rows'][0]['id'] == 'cbt'


def test_before_the_intake_the_referral_decides_the_goals(state):
    cbt = _row(modality.rank(state, client_of(state)), 'cbt')
    assert _component(cbt, 'goals')['detail'].startswith('Lähete')
    assert not _component(cbt, 'workingStyle')['known']


def test_practice_during_the_wait_counts_only_with_the_consent(state):
    client = run_intake(state)
    before = _row(modality.rank(state, client), 'cbt')['total']
    client.consent.sharePractice = False
    _thought_record(state, client)
    assert _row(modality.rank(state, client), 'cbt')['total'] == before
    client.consent.sharePractice = True
    cbt = _row(modality.rank(state, client), 'cbt')
    assert _component(cbt, 'experience')['known'] and cbt['total'] > before  # the feeling went 8/10 → 5/10
    assert _component(cbt, 'experience')['detail'] == 'Ajatusten tutkiminen 1×'
    assert not _component(_row(modality.rank(state, client), 'act'), 'experience')['known']


def test_only_data_the_client_allows_in_matching_is_used(state):
    client = run_intake(state)
    insights.for_client(state, client.id, kind='working_style')[0].sharing.matching = False
    assert not _component(_row(modality.rank(state, client), 'cbt'), 'workingStyle')['known']
