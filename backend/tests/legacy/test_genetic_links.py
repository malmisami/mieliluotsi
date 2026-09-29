"""Linking health records to DNA-analysis findings (Terveystiedot): rules only, gates 2 and 3 apply."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.loop.safety import check_text
from app.legacy_api import legacy_app as app
from app.support import texts

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_STATE_PATH', str(tmp_path / 'state.json'))
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'off')
    client.post('/api/loop/demo/reset')


def _events_by_id() -> dict:
    return {e['id']: e for e in client.get('/api/loop/state').json()['events']}


def _link(session_id=None) -> dict:
    response = client.post('/api/support/genetic-links', json={'sessionId': session_id})
    assert response.status_code == 200, response.text
    return response.json()


def _run_quick_demo() -> str:
    session_id = client.post(
        '/api/analysis/sessions/from-demo',
        json={'kind': 'quick_snippet', 'mode': 'demo', 'resource_profile': 'light'},
    ).json()['session_id']
    for step in ('preflight', 'parse-next', 'match-next', 'classify', 'finalize'):
        assert client.post(f'/api/analysis/sessions/{session_id}/{step}').status_code == 200
    return session_id


def test_elevated_cholesterol_links_every_related_record_to_the_dna_findings():
    body = _link()
    linking = body['result']
    assert linking == body['dashboard']['support']['geneticLinking']
    # every DNA finding gets a theme; themes with health records come first
    assert [t['id'] for t in linking['themes']] == ['cholesterol', 'homocysteine']
    theme = linking['themes'][0]
    assert theme['label'] == 'Kohonnut kolesteroli' and theme['planName'] == 'Kolesteroliarvojen seuranta'

    events = _events_by_id()
    linked = [events[i] for i in theme['eventIds']]
    # the diagnosis, every lipid order since 2014 and the visits whose notes discuss cholesterol
    assert {e['code'] for e in linked if e['type'] == 'diagnosis'} == {'E78.0'}
    lipid_orders = {e['structuredData']['panelId'] for e in linked if e['type'] == 'lab_result'}
    assert lipid_orders == {'LAB-20141118-1', 'LAB-20180412-2', 'LAB-20220510-1', 'LAB-20250304-1', 'LAB-20260512-1'}
    assert sum(1 for e in linked if e['type'] == 'lab_result') == 29
    assert {e['date'] for e in linked if e['type'] == 'professional_note'} == {'2014-11-18', '2018-04-12', '2022-05-10', '2026-05-20'}
    assert theme['recordCount'] == 10
    # nothing unrelated: no blood pressure, glucose, thyroid or liver records, no home readings
    assert not {e['code'] for e in linked} & {'BP', 'I10', 'GLU', 'HBA1C', 'TSH', 'ALAT'}

    # gate 2: only the professional-approved finding is used; the other one is linked as information only
    findings = theme['findings']
    assert [f['used'] for f in findings] == [True, False]
    assert findings[0]['statusLabel'] == 'Käytössä seurannassa: Kolesteroliarvojen seuranta'
    assert findings[1]['statusLabel'] == texts.GENETIC_LINK_STATUS['no_practical_significance']

    assert linking['healthOnlyThemes'] == ['Kohonnut verenpaine', 'Sokeriaineenvaihdunta']
    assert linking['findingCount'] == 3 and linking['unlinkedFindingCount'] == 0
    # the homocysteine finding is linked to the cardiovascular diagnoses, as information only
    vascular = linking['themes'][1]
    assert {events[i]['code'] for i in vascular['eventIds']} == {'I10', 'E78.0'} and not vascular['findings'][0]['used']


def test_gene_names_and_unrelated_conditions_stay_hidden_without_permission():
    linking = _link()['result']
    payload = json.dumps(linking, ensure_ascii=False)
    for secret in ('LDLR', 'APOE', 'MTHFR', 'rs999000001', 'Alzheimer'):
        assert secret not in payload
    # without the gene name the classification tells what the finding is
    assert [f['label'] for f in linking['themes'][0]['findings']] == ['Todennäköisesti haitallinen muutos', 'Riskitekijä']

    client.put('/api/support/consent', json={'showGeneticDetails': True})
    detailed = client.get('/api/loop/state').json()['support']['geneticLinking']['themes'][0]['findings']
    assert [f['label'] for f in detailed] == ['LDLR: todennäköisesti haitallinen muutos', 'APOE: riskitekijä']
    assert detailed[1]['conditions'] == ['rasva-aineenvaihdunnan häiriö ja kohonnut kolesteroli']
    # a condition outside the theme is never shown under it
    assert 'Alzheimer' not in json.dumps(detailed, ensure_ascii=False)


def test_audit_records_the_link_without_gene_names_and_texts_pass_the_safety_check():
    support = _link()['dashboard']['support']
    entries = support['audit']['entries'] if isinstance(support['audit'], dict) else support['audit']
    entry = next(e for e in entries if e.get('action') == 'link_genetics')
    assert entry['stage'] == 'data' and entry['outcome'] == 'linked' and entry['actor'] == 'agent'
    assert 'Kohonnut kolesteroli: 10 terveystietomerkintää ja 2 perimätiedon havaintoa' in entry['detail']
    assert 'LDLR' not in entry['detail'] and 'APOE' not in entry['detail']
    for text in (entry['detail'], texts.GENETIC_LINK_NOTE, *texts.GENETIC_LINK_STATUS.values(),
                 *[t['reason'] for t in support['geneticLinking']['themes']]):
        assert check_text(text)['passed'], text


def test_linking_needs_consent_and_is_suspended_when_consent_is_withdrawn():
    client.put('/api/support/consent', json={'dataSources': {'geneticInsights': False}})
    response = client.post('/api/support/genetic-links', json={})
    assert response.status_code == 400 and 'suostumuksissa' in response.json()['detail']

    client.put('/api/support/consent', json={'dataSources': {'geneticInsights': True}})
    _link()
    client.put('/api/support/consent', json={'dataSources': {'geneticInsights': False}})
    linking = client.get('/api/loop/state').json()['support']['geneticLinking']
    assert linking['suspended'] is True and linking['themes'] == []


def test_unlinking_changes_nothing_in_the_follow_up():
    before = client.get('/api/loop/state').json()['support']
    _link()
    response = client.delete('/api/support/genetic-links')
    assert response.status_code == 200
    after = response.json()['dashboard']['support']
    assert after['geneticLinking'] is None
    assert [(p['id'], p['status'], p['version']) for p in after['plans']] == [(p['id'], p['status'], p['version']) for p in before['plans']]
    assert [(i['id'], i['reviewStatus']) for i in after['insights']] == [(i['id'], i['reviewStatus']) for i in before['insights']]
    assert client.delete('/api/support/genetic-links').status_code == 400


def test_the_users_own_dna_analysis_is_merged_without_duplicates():
    session_id = _run_quick_demo()
    linking = _link(session_id)['result']
    themes = {t['id']: t for t in linking['themes']}
    # LDLR and APOE appear once even though both the source record and the analysis contain them
    assert len(themes['cholesterol']['findings']) == 2 and len({f['key'] for f in themes['cholesterol']['findings']}) == 2
    # every finding of the analysis is shown exactly once, also when no health record relates to it
    assert sum(len(t['findings']) for t in themes.values()) == linking['findingCount'] == 7
    events = _events_by_id()
    assert [events[i]['type'] for i in themes['drug_response']['eventIds']] == ['medication']
    assert themes['coagulation']['eventIds'] == [] and themes['hereditary_cancer']['eventIds'] == []
    assert linking['unlinkedFindingCount'] == 3
    assert list(themes)[-2:] == ['coagulation', 'hereditary_cancer']  # without records last
    assert client.post('/api/support/genetic-links', json={'sessionId': 'missing-session'}).status_code == 400
