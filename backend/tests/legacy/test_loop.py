from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.loop.safety import check_text
from app.legacy_api import legacy_app as app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_STATE_PATH', str(tmp_path / 'state.json'))
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'off')
    client.post('/api/loop/demo/reset')


def _run_quick_demo() -> tuple[str, dict]:
    session_id = client.post(
        '/api/analysis/sessions/from-demo',
        json={'kind': 'quick_snippet', 'mode': 'demo', 'resource_profile': 'light'},
    ).json()['session_id']
    for step in ('preflight', 'parse-next', 'match-next', 'classify'):
        assert client.post(f'/api/analysis/sessions/{session_id}/{step}').status_code == 200
    report = client.post(f'/api/analysis/sessions/{session_id}/finalize').json()['report']
    return session_id, report


def _start_ldlr_monitoring() -> dict:
    response = client.post('/api/loop/monitorings', json={'findingId': 'GF-001'})
    assert response.status_code == 200
    return response.json()['dashboard']


def test_dna_report_contains_structured_genomic_findings():
    _, report = _run_quick_demo()
    by_gene = {f['gene']: f['genomic_finding'] for f in report['findings']}
    ldlr = by_gene['LDLR']
    assert ldlr['confirmationStatus'] == 'synthetic_demo_confirmed'
    assert ldlr['monitoringEligible'] is True
    for field in ('id', 'gene', 'variant', 'title', 'description', 'classification', 'confirmationStatus',
                  'evidenceLevel', 'monitoringEligible', 'relevantEventTypes', 'source', 'lastReviewedAt'):
        assert field in ldlr
    assert by_gene['F5']['confirmationStatus'] == 'raw_candidate'
    assert by_gene['F5']['monitoringEligible'] is True


def test_genetic_findings_need_professional_approval_before_monitoring():
    session_id, report = _run_quick_demo()
    ldlr = next(f for f in report['findings'] if f['gene'] == 'LDLR')
    f5 = next(f for f in report['findings'] if f['gene'] == 'F5')

    preview = client.post('/api/loop/monitoring/preview', json={'sessionId': session_id, 'findingId': ldlr['id']}).json()
    assert preview['eligible'] is True
    assert preview['monitoredEvents']
    assert 'diagnoosi' in preview['disclaimer']

    # A raw, unconfirmed candidate finding is now allowed too, but the preview is upfront that no
    # curated rule exists for it, so monitoring it will never produce an observation.
    f5_preview = client.post('/api/loop/monitoring/preview', json={'sessionId': session_id, 'findingId': f5['id']}).json()
    assert f5_preview['eligible'] is True
    assert f5_preview['confirmationStatus'] == 'raw_candidate'
    assert any('vahvistamaton ehdokaslöydös' in note for note in f5_preview['responsibilityNotes'])
    assert any('ei ole tässä demossa määritelty sääntöjä' in note for note in f5_preview['responsibilityNotes'])

    # Gate 2: a raw candidate does not start monitoring - it becomes a professional review item instead
    requested = client.post('/api/loop/monitorings', json={'sessionId': session_id, 'findingId': f5['id']})
    assert requested.status_code == 200
    body = requested.json()
    assert body['status'] == 'pending_professional_review' and body['monitoring'] is None
    assert body['insight']['category'] == 'needs_professional_check'
    assert body['dashboard']['counts']['activeMonitorings'] == 1

    # The LDLR finding was already approved by a physician in Aino's history, so monitoring continues
    created = client.post('/api/loop/monitorings', json={'sessionId': session_id, 'findingId': ldlr['id']})
    assert created.status_code == 200 and created.json()['status'] == 'monitoring'
    assert created.json()['dashboard']['counts']['activeMonitorings'] == 1

    # Only after a professional approves the F5 finding does its monitoring start
    approved = client.post(f"/api/support/insights/{body['insight']['id']}/decision", json={'decision': 'approve', 'role': 'physician'})
    assert approved.status_code == 200
    assert approved.json()['dashboard']['counts']['activeMonitorings'] == 2


def test_full_demo_flow():
    initial = client.get('/api/loop/state').json()
    assert initial['synthetic'] is True
    assert initial['profile']['name'] == 'Aino Demo'
    # the timeline is projected from the LUVN-like source files through the adapters
    codes = [e['code'] for e in initial['events']]
    assert codes[0] == 'J02.0' and len(codes) == 130  # history from 2008 onwards
    assert {'I10', 'E78.0', 'MED_RECORD', 'VISIT', 'LDL', 'GLU', 'NOTE', 'CONTACT', 'BP', 'CHOL', 'HB'} <= set(codes)
    # no self-reports: the timeline holds only records from the health care source systems (like Omakanta)
    assert 'SELF_REPORT' not in codes
    # Aino starts with the physician-approved LDLR finding under monitoring and no open observations
    assert initial['counts']['activeMonitorings'] == 1
    assert initial['counts']['openObservations'] == 0

    dashboard = _start_ldlr_monitoring()
    monitoring = dashboard['monitorings'][0]
    assert monitoring['status'] == 'monitoring'
    assert monitoring['currentAssessment'] == 'Seuranta aktiivinen. Ei uusia huomioita.'
    assert dashboard['counts']['openObservations'] == 0
    assert dashboard['counts']['nextReviewDate']

    # Irrelevant event: logged only, no user alert
    bp = client.post('/api/loop/demo/events', json={'template': 'irrelevant_bp'}).json()
    assert bp['userVisibleAlert'] is False
    assert bp['observations'] == []
    assert 'Yhteyttä aktiiviseen seurantaan ei löytynyt' in bp['log'][0]['decisionDetail']
    assert bp['dashboard']['counts']['openObservations'] == 0

    # High LDL: rule fires
    ldl = client.post('/api/loop/demo/events', json={'template': 'high_ldl'}).json()
    assert ldl['userVisibleAlert'] is True
    observation = ldl['observations'][0]
    assert observation['status'] == 'professional_review_recommended'
    assert observation['ruleId'] == 'RULE-LDLR-LDL-HIGH-001'
    assert observation['explanationSource'] == 'template'
    assert check_text(observation['explanation'])['passed']
    log = ldl['log'][0]
    assert log['ruleApplied']['triggered'] is True
    assert log['evidenceCheck']['confirmationOk'] is True
    assert log['safetyCheck']['templateText']['passed'] is True
    dash = ldl['dashboard']
    assert dash['counts']['openObservations'] == 1
    assert dash['monitorings'][0]['status'] == 'professional_review_recommended'

    # "Why now?" data
    enriched = next(o for o in dash['observations'] if o['id'] == observation['id'])
    assert enriched['finding']['gene'] == 'LDLR'
    assert enriched['event']['code'] == 'LDL'
    assert enriched['connection'] and enriched['rule']['id'] and enriched['source']
    assert enriched['evidenceLevelLabel'] and enriched['confirmationLabel']
    assert enriched['missingInformation'] and enriched['systemDid'] and enriched['systemDidNot']

    # Open follow-up task
    task = enriched['task']
    assert task['status'] == 'open' and task['userResponse'] is None
    assert set(task) >= {'id', 'observationId', 'createdAt', 'dueAt', 'status', 'userResponse'}

    # Professional summary
    summary = client.get(f"/api/loop/observations/{observation['id']}/summary").json()
    assert summary['syntheticPersonName'] == 'Aino Demo'
    assert 'syntheticPersonId' not in summary
    assert summary['missingInformation'] and summary['disclaimer'] and summary['reason']
    html = client.get(f"/api/loop/observations/{observation['id']}/summary.html")
    assert html.status_code == 200 and 'SYNTEETTINEN' in html.text and 'LDLR' in html.text
    shared = client.post(f"/api/loop/observations/{observation['id']}/share").json()['dashboard']
    assert shared['observations'][0]['status'] == 'waiting_for_professional_review'

    # Second high LDL does not create a duplicate alert
    again = client.post('/api/loop/demo/events', json={'template': 'high_ldl'}).json()
    assert again['userVisibleAlert'] is False and again['observations'] == []

    # Advance time -> follow-up question
    advanced = client.post('/api/loop/demo/advance-time', json={'days': 30}).json()['dashboard']
    assert len(advanced['pendingQuestions']) == 1
    question = advanced['pendingQuestions'][0]
    assert question['question'] == 'Onko asia käsitelty ammattilaisen kanssa?'
    assert advanced['monitorings'][0]['status'] == 'waiting_for_user'

    answered = client.post(f"/api/loop/tasks/{question['id']}/respond", json={'response': 'yes'}).json()['dashboard']
    assert answered['pendingQuestions'] == []
    assert answered['observations'][0]['status'] == 'resolved'
    assert answered['monitorings'][0]['status'] == 'resolved'
    assert answered['counts']['openObservations'] == 0


@pytest.mark.parametrize(
    ('response', 'observation_status', 'task_status'),
    [
        ('not_yet', 'professional_review_recommended', 'open'),
        ('no_reminder', 'professional_review_recommended', 'cancelled'),
        ('not_relevant', 'dismissed', 'completed'),
    ],
)
def test_follow_up_responses(response, observation_status, task_status):
    _start_ldlr_monitoring()
    client.post('/api/loop/demo/events', json={'template': 'high_ldl'})
    task_id = client.post('/api/loop/demo/advance-time', json={'days': 30}).json()['dashboard']['pendingQuestions'][0]['id']
    dash = client.post(f'/api/loop/tasks/{task_id}/respond', json={'response': response}).json()['dashboard']
    assert dash['observations'][0]['status'] == observation_status
    assert dash['tasks'][0]['status'] == task_status
    assert dash['tasks'][0]['userResponse'] == response


def test_context_events_do_not_alert_and_research_updates_review_date():
    _start_ldlr_monitoring()
    med = client.post('/api/loop/demo/events', json={'template': 'new_medication'}).json()
    assert med['userVisibleAlert'] is False and med['log'][0]['decision'] == 'no_action'
    research = client.post('/api/loop/demo/events', json={'template': 'research_update'}).json()
    assert research['userVisibleAlert'] is False
    finding = research['dashboard']['monitorings'][0]['finding']
    assert finding['lastReviewedAt'] == research['event']['date']


def test_events_without_monitoring_never_alert():
    monitoring_id = client.get('/api/loop/state').json()['monitorings'][0]['id']
    client.post(f'/api/loop/monitorings/{monitoring_id}/stop')
    ldl = client.post('/api/loop/demo/events', json={'template': 'high_ldl'}).json()
    assert ldl['userVisibleAlert'] is False
    assert ldl['dashboard']['counts']['openObservations'] == 0


def test_free_text_uses_parser_and_deterministic_flag():
    _start_ldlr_monitoring()
    result = client.post('/api/loop/events/free-text', json={'text': 'Labra: LDL 4,6 mmol/l'}).json()
    assert result['event']['code'] == 'LDL'
    assert result['event']['abnormalFlag'] == 'high'
    assert result['log'][0]['extractionMethod'] == 'deterministic_parser'
    assert result['observations'][0]['status'] == 'professional_review_recommended'


def test_lifestyle_quiz_result_is_saved_and_visible_in_user_context():
    payload = {
        'structuredData': {'liikunta': {'answer': 'Hyvin harvoin', 'tier': 'watch'}},
        'rawText': 'Elämäntapatesti: liikunta hyvin harvoin.',
    }
    result = client.post('/api/loop/lifestyle-quiz', json=payload).json()
    events = result['dashboard']['events']
    quiz_event = next(e for e in events if e['type'] == 'lifestyle_survey')
    assert quiz_event['code'] == 'LIFESTYLE_QUIZ'
    assert quiz_event['structuredData'] == payload['structuredData']
    assert quiz_event['confirmedByUser'] is True

    state_dash = client.get('/api/loop/state').json()
    assert any(e['type'] == 'lifestyle_survey' for e in state_dash['events'])
    assert state_dash['eventTypeLabels']['lifestyle_survey'] == 'Elämäntapatesti'


def test_llm_failure_falls_back_to_templates(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    from app.loop import llm

    monkeypatch.setattr(llm, '_call', lambda *args, **kwargs: None)
    _start_ldlr_monitoring()
    ldl = client.post('/api/loop/demo/events', json={'template': 'high_ldl'}).json()
    assert ldl['observations'][0]['explanationSource'] == 'template'
    assert 'epäonnistui' in ldl['log'][0]['safetyCheck']['used']


def test_unsafe_llm_text_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    from app.loop import llm

    monkeypatch.setattr(llm, 'explain_decision', lambda decision: 'Sinulla on todettu sairaus, riski on 40 %. Aloita statiinilääkitys.')
    monkeypatch.setattr(llm, 'extract_event', lambda text: None)
    _start_ldlr_monitoring()
    ldl = client.post('/api/loop/demo/events', json={'template': 'high_ldl'}).json()
    observation = ldl['observations'][0]
    assert observation['explanationSource'] == 'template'
    assert observation['status'] == 'professional_review_recommended'
    assert ldl['log'][0]['safetyCheck']['llmText']['passed'] is False


def test_safety_check_blocks_forbidden_content():
    assert not check_text('Riski on 35 %')['passed']
    assert not check_text('Sinulla on todettu perinnöllinen sairaus')['passed']
    assert not check_text('Lopeta lääkkeen käyttö')['passed']
    assert check_text('Tiedot kannattaa käydä läpi terveydenhuollon ammattilaisen kanssa.')['passed']


def test_urgency_wording_needs_the_rule_based_class():
    # without an allowed class urgency wording is blocked (unchanged); with the class the rule engine set, only that
    # class's own phrases (and the fixed 112 / 116 117 phrases) are allowed
    assert not check_text('Hätätilanne: soita hätänumeroon 112.')['passed']
    assert check_text('Hätätilanne: soita hätänumeroon 112.', allowed_urgency='emergency')['passed']
    assert not check_text('Tämä on hätätilanne.', allowed_urgency='same_day')['passed']
    assert check_text('Automaattinen arvio: Kiireellinen – samana päivänä.', allowed_urgency='same_day')['passed']
    assert not check_text('Automaattinen arvio: Kiireetön. Hakeudu kiireesti päivystykseen.', allowed_urgency='routine')['passed']


def test_why_now_disclaimer_states_the_automated_assessment():
    disclaimers = client.get('/api/loop/state').json()['companion']['disclaimers']
    assert disclaimers['whyNow'] == ('Tämä ei ole diagnoosi tai hoitosuositus. Hyvinvointikumppani tekee hoidon tarpeen arvion '
                                     'automaattisesti; diagnoosit ja hoitopäätökset tekee ammattilainen.')


def _confirmed_family_history(age: int = 49, relation: str = 'father'):
    from app.loop import agent, family_history
    from app.loop.store import transaction

    data = family_history.validate({'relation': relation, 'condition': 'myocardial_infarction', 'ageAtEvent': age})
    with transaction() as state:
        return agent.add_confirmed_family_history(state, data, 'test', 'test')


def test_family_history_alone_does_not_change_state():
    result = _confirmed_family_history()
    assert result['created'] == [] and result['updated'] == []
    dash = client.get('/api/loop/state').json()
    assert dash['monitorings'][0]['status'] == 'monitoring'
    assert dash['counts']['openObservations'] == 0
    family_event = next(e for e in dash['events'] if e['type'] == 'family_history')
    assert family_event['confirmedByUser'] is True
    assert family_event['structuredData'] == {'relation': 'father', 'condition': 'myocardial_infarction',
                                              'conditionCategory': 'cardiovascular_disease', 'ageAtEvent': 49}


def test_rule_002_updates_open_observation_after_confirmed_family_history():
    client.post('/api/loop/demo/events', json={'template': 'high_ldl'})
    result = _confirmed_family_history()
    assert [o.id for o in result['updated']] == ['obs-0001']
    dash = client.get('/api/loop/state').json()
    observation = dash['observations'][0]
    assert observation['status'] == 'professional_review_recommended'
    assert [r['id'] for r in observation['rules']] == ['RULE-LDLR-LDL-HIGH-001', 'RULE-LDLR-FAMHX-002']
    assert 'Suvun sairaushistoria' not in observation['missingInformation']
    assert len(observation['supportingEvents']) == 2
    summary = client.get('/api/loop/observations/obs-0001/summary').json()
    assert summary['userConfirmedFamilyHistory'][0]['structuredData']['ageAtEvent'] == 49


def test_rule_002_ignores_older_relatives_and_late_onset():
    client.post('/api/loop/demo/events', json={'template': 'high_ldl'})
    assert _confirmed_family_history(age=72)['updated'] == []
    assert _confirmed_family_history(age=45, relation='grandparent')['updated'] == []


def test_clear_removes_the_users_own_data_but_keeps_the_health_records():
    baseline = client.get('/api/loop/state').json()
    client.post('/api/loop/demo/events', json={'template': 'high_ldl'})
    client.post('/api/loop/companion/messages', json={'text': 'Mikä on tilanteeni?'})
    assert client.post('/api/support/genetic-links', json={}).status_code == 200
    changed = client.get('/api/loop/state').json()
    assert len(changed['events']) == len(baseline['events']) + 1 and changed['observations']

    dashboard = client.post('/api/loop/data/clear').json()['dashboard']
    # the app's own data is gone: the added result, its observation, the chat and the links
    assert [e['id'] for e in dashboard['events']] == [e['id'] for e in baseline['events']]
    assert dashboard['observations'] == []
    assert all(m['kind'] == 'greeting' for m in dashboard['companion']['messages'])
    assert dashboard['support']['geneticLinking'] is None
    # the health care records are read again from the source systems: Terveystiedot is never empty
    assert len(dashboard['events']) == 130 and dashboard['support']['available'] is True
    assert all(e['extractedData'].get('sourceKind') for e in dashboard['events'])
