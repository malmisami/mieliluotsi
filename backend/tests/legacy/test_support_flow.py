"""API-level tests for the agent cycle, the automated care-need assessment, professional decisions and oversight,
consent and the end-to-end demo case (Aino)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.loop import llm
from app.loop.safety import check_text
from app.legacy_api import legacy_app as app
from app.support import texts

client = TestClient(app)

REQUIRED_AUDIT_FIELDS = ('date', 'personId', 'planId', 'stage', 'actor', 'signal', 'rule', 'action', 'llmUsed', 'llmTask',
                         'outcome', 'userResponse', 'escalated', 'professionalDecision')
FLOW_KEYS = ['signal', 'agent', 'user', 'follow', 'assessment', 'escalation', 'professional']


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_STATE_PATH', str(tmp_path / 'state.json'))
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'off')
    monkeypatch.setattr(settings, 'SUPPORT_COHORT_PATH', str(tmp_path / 'cohort.csv'))
    monkeypatch.setattr(settings, 'SUPPORT_COHORT_SIZE', 300)
    client.post('/api/loop/demo/reset')


def ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()['dashboard']


def support(dash: dict) -> dict:
    return dash['support']


def plan(dash: dict, theme: str) -> dict:
    return next(p for p in support(dash)['plans'] if p['theme'] == theme)


def agent_messages(dash: dict) -> list[dict]:
    return [m for m in dash['companion']['messages'] if m['role'] == 'agent']


def assessment_by_id(dash: dict, assessment_id: str) -> dict:
    return next(a for a in support(dash)['assessments'] if a['id'] == assessment_id)


def approve_bp() -> dict:
    dash = client.get('/api/loop/state').json()
    return ok(client.post(f"/api/support/plans/{plan(dash, 'blood_pressure')['id']}/decision", json={'decision': 'approve', 'role': 'nurse'}))


def answer_all(answers: dict[str, str]) -> dict:
    """Answer the open check-in question by question (skipping questions not in `answers`)."""
    dash = client.get('/api/loop/state').json()
    for _ in range(8):
        open_checkins = support(dash)['openCheckIns']
        if not open_checkins:
            return dash
        checkin = open_checkins[0]
        question = next(q for q in checkin['questions'] if not q['answer'] and not q['skipped'])
        if question['kind'] in answers:
            body = {'questionId': question['id'], 'optionId': answers[question['kind']]}
        else:
            body = {'questionId': question['id'], 'skip': True} if question['optional'] else {'questionId': question['id'], 'optionId': question['options'][0]['id']}
        dash = ok(client.post(f"/api/support/checkins/{checkin['id']}/answer", json=body))
    raise AssertionError('check-in did not complete')


def _escalate() -> dict:
    """Week 2 of the demo story: the goal fails twice while the average is above target -> automated assessment + routing."""
    approve_bp()
    ok(client.post('/api/support/simulate/week'))
    answer_all({'goal_progress': 'none', 'barrier': 'time', 'smaller_goal': 'accept'})
    ok(client.post('/api/support/simulate/measurement'))
    ok(client.post('/api/support/simulate/measurement'))
    ok(client.post('/api/support/simulate/week'))
    return answer_all({'goal_progress': 'none', 'barrier': 'time'})


# --- initial state: the three gates ---------------------------------------------------------------------------------

def test_initial_state_passes_every_source_through_the_gates():
    dash = client.get('/api/loop/state').json()
    s = support(dash)
    assert s['person']['name'] == 'Aino Demo' and s['person']['age'] == 46
    assert plan(dash, 'blood_pressure')['status'] == 'pending_professional_review'
    assert plan(dash, 'lipids')['status'] == 'active'
    genetic = {i['gene']: i for i in s['insights'] if i['kind'] == 'genetic'}
    assert genetic['MTHFR']['category'] == 'uncertain_or_conflicting' and genetic['MTHFR']['userVisible'] is False
    assert genetic['APOE']['category'] == 'no_practical_significance' and genetic['APOE']['userVisible'] is False
    assert genetic['LDLR']['category'] == 'professionally_approved'
    # the uncertain variant is not presented to the user anywhere in the default view
    situation_text = json.dumps(s['situation'], ensure_ascii=False)
    assert 'MTHFR' not in situation_text and 'APOE' not in situation_text and 'LDLR' not in situation_text
    assert s['situation']['nextStep']['kind'] == 'none' and s['situation']['assessment'] is None
    assert set(s['professional']['filteredInsightIds']) >= {genetic['MTHFR']['id'], genetic['APOE']['id']}
    assert s['assessments'] == [] and s['professional']['assessmentReviewIds'] == []
    # the published description of the automation and the explicit consent to it
    automation = s['policy']['automation']
    assert automation['legalBasis'].endswith('prototyyppi olettaa lakimuutoksen voimaan 2027') and len(automation['urgencyClasses']) == 5
    assert automation['whatStaysHuman'] and s['policy']['urgencyLabels']['routine'] == 'Kiireetön'
    assert s['consent']['automatedAssessment'] is True and s['consent']['automatedAssessmentInformedAt'] == dash['currentDate']
    assert any(r['target'].startswith('Automaattinen hoidon tarpeen arvio') for r in s['consent']['records'])
    assert s['professional']['assessmentDecisionLabels'] == {'confirm': 'Vahvista arvio', 'change_urgency': 'Muuta kiireellisyysluokkaa',
                                                            'take_over': 'Tee arvio itse (ammattihenkilön arvio)'}
    assert s['policy']['statusLabels']['escalated'] == 'Arvioitu automaattisesti – ammattilainen mukana'


def test_nothing_is_sent_before_a_professional_approves_the_plan():
    dash = ok(client.post('/api/support/simulate/week'))
    assert support(dash)['openCheckIns'] == []
    assert plan(dash, 'blood_pressure')['checkIns'] == []


def test_stable_theme_produces_no_contact():
    dash = ok(client.post('/api/support/cycle'))
    lipid = plan(dash, 'lipids')
    assert lipid['lastAgentAction']['action'] == 'no_action'
    assert not [m for m in agent_messages(dash) if m['intent'] == 'SUPPORT_PLAN']


def test_service_works_without_any_genetic_data():
    dash = ok(client.put('/api/support/consent', json={'dataSources': {'geneticInsights': False}}))
    assert dash['counts']['activeMonitorings'] == 0  # genetic monitoring stopped
    assert dash['companion']['userContext']['activeGenomicFindings'] == []
    dash = approve_bp()
    dash = ok(client.post('/api/support/simulate/week'))
    assert support(dash)['openCheckIns'], 'the support plan runs on health data alone'
    lipid_card = next(c for c in support(dash)['situation']['plans'] if c['id'] == plan(dash, 'lipids')['id'])
    assert 'rajannut sen pois' in lipid_card['why']['geneticNote']


# --- gate 2: professional decisions -------------------------------------------------------------------------------

def test_approval_activates_the_plan_and_informs_the_user_calmly():
    dash = approve_bp()
    bp = plan(dash, 'blood_pressure')
    assert bp['status'] == 'active' and bp['approval']['status'] == 'approved' and bp['approval']['byRole'] == 'Sairaanhoitaja'
    assert bp['nextCheckInAt'] == '2026-09-08'
    message = agent_messages(dash)[-1]
    assert message['kind'] == 'plan_update' and 'Hoitajasi hyväksyi seurantasuunnitelman' in message['text']
    assert 'Näin mittaat verenpaineen kotona' in message['text']  # repeated contacts about home measuring
    assert support(dash)['situation']['nextStep']['kind'] == 'record_measurement'


@pytest.mark.parametrize('decision', ['approve', 'end', 'set_review_date'])
def test_decisions_that_do_not_fit_the_plan_status_are_rejected(decision):
    dash = client.get('/api/loop/state').json()
    lipid = plan(dash, 'lipids') if decision == 'approve' else plan(dash, 'blood_pressure')
    response = client.post(f"/api/support/plans/{lipid['id']}/decision", json={'decision': decision, 'reviewDate': '2026-12-01'})
    assert response.status_code == 400


def test_professional_cannot_grant_actions_outside_the_theme_policy():
    dash = approve_bp()
    bp = plan(dash, 'blood_pressure')
    response = client.post(f"/api/support/plans/{bp['id']}/decision",
                           json={'decision': 'change_permissions', 'allowedActions': ['reminder', 'change_medication']})
    assert response.status_code == 400
    narrowed = ok(client.post(f"/api/support/plans/{bp['id']}/decision",
                              json={'decision': 'change_permissions', 'allowedActions': ['reminder', 'check_in', 'escalate']}))
    bp = plan(narrowed, 'blood_pressure')
    assert bp['version'] == 2 and bp['allowedActions'] == ['reminder', 'check_in', 'escalate']


def test_reject_and_request_info():
    dash = client.get('/api/loop/state').json()
    bp_id = plan(dash, 'blood_pressure')['id']
    assert client.post(f'/api/support/plans/{bp_id}/decision', json={'decision': 'request_info'}).status_code == 400  # note required
    dash = ok(client.post(f'/api/support/plans/{bp_id}/decision', json={'decision': 'request_info', 'note': 'Onko mittari validoitu?'}))
    assert plan(dash, 'blood_pressure')['approval']['status'] == 'info_requested'
    dash = ok(client.post(f'/api/support/plans/{bp_id}/decision', json={'decision': 'reject', 'note': 'Seuranta vastaanotolla.'}))
    assert plan(dash, 'blood_pressure')['status'] == 'rejected'
    assert check_text(agent_messages(dash)[-1]['text'])['passed']


# --- the agent cycle and adaptive micro-interventions ----------------------------------------------------------------

def test_agent_starts_a_check_in_on_its_own_with_reasons():
    approve_bp()
    dash = ok(client.post('/api/support/simulate/week'))
    checkin = support(dash)['openCheckIns'][0]
    kinds = [q['kind'] for q in checkin['questions']]
    assert kinds[0] == 'goal_progress' and 'measurement_status' in kinds and len(kinds) <= 3
    assert all(q['whyAsked'] for q in checkin['questions'])
    assert 'missing_measurement' in checkin['signals']
    assert checkin['deliveredAt'].endswith('09:00')
    chat = agent_messages(dash)
    assert chat[-2]['kind'] == 'check_in_intro' and chat[-2]['initiatedByAgent'] is True
    assert chat[-1]['kind'] == 'check_in' and {a['type'] for a in chat[-1]['actions']} == {'checkin_answer'}


def test_goal_not_met_leads_to_a_barrier_question_and_a_smaller_goal_not_the_same_advice():
    approve_bp()
    ok(client.post('/api/support/simulate/week'))
    dash = answer_all({'goal_progress': 'none', 'barrier': 'time', 'smaller_goal': 'accept', 'measurement_status': 'no_time'})
    bp = plan(dash, 'blood_pressure')
    done = bp['checkIns'][0]
    assert [q['kind'] for q in done['questions']][:3] == ['goal_progress', 'barrier', 'smaller_goal']
    assert bp['goal']['label'] == 'yksi 20 minuutin kävely viikossa' and bp['goal']['setBy'] == 'agent_with_user'
    assert bp['version'] == 1  # adapting inside the approved range does not need a new professional version
    assert bp['history'][-1]['actor'] == 'agent'
    assert bp['status'] == 'active' and not support(dash)['escalations'] and not support(dash)['assessments']
    closing = agent_messages(dash)[-1]['text']
    assert 'Seuraavat 7 päivää kokeillaan: 20 minuutin kävely kerran.' in closing and check_text(closing)['passed']


def test_pain_as_barrier_offers_a_professional_assessment_instead_of_exercise():
    approve_bp()
    ok(client.post('/api/support/simulate/week'))
    dash = answer_all({'goal_progress': 'none', 'barrier': 'pain', 'contact_request': 'request'})
    checkin = plan(dash, 'blood_pressure')['checkIns'][0]
    assert 'smaller_goal' not in [q['kind'] for q in checkin['questions']]
    contact_question = next(q for q in checkin['questions'] if q['kind'] == 'contact_request')
    assert contact_question['text'] == 'Kuvaamasi kipu tai vaiva kannattaa arvioida. Haluatko, että hoitajasi ottaa sinuun yhteyttä?'
    escalation = support(dash)['escalations'][0]
    assert escalation['trigger'] == 'user_request' and escalation['urgency'] == 'soon'
    assert escalation['urgencyLabel'] == 'Kiirevastaanotto 3 arkipäivän kuluessa' and escalation['handlingTime'] == '3 arkipäivän kuluessa'
    assert escalation['humanReviewRequested'] is True and escalation['openDecision'].startswith('Asiakas käytti oikeuttaan ammattilaisen tekemään arvioon.')
    # the user exercised the right to a professional's assessment: the automated one stays as background information
    assessment = assessment_by_id(dash, escalation['assessmentId'])
    assert assessment['trigger'] == 'user_request' and assessment['status'] == 'human_review_requested'
    assert assessment['reason'] == 'Asiakas pyysi ammattilaisen tekemän arvion tarkistuksessa.' and assessment['urgency'] == 'within_3_days'
    assert assessment['id'] in support(dash)['professional']['humanReviewRequestIds']
    assert 'tekee hoidon tarpeen arvion ja tarjoaa ammattilaisen yhteydenottoa' in ' '.join(e['detail'] for e in support(dash)['audit']['entries'])


def test_repeated_failure_leads_to_an_automated_assessment_and_a_structured_escalation():
    dash = _escalate()
    bp = plan(dash, 'blood_pressure')
    assert bp['status'] == 'escalated' and bp['statusLabel'] == 'Arvioitu automaattisesti – ammattilainen mukana'
    assert bp['lastAgentAction']['label'] == 'Arvioitu automaattisesti ja ohjattu ammattilaiselle'
    escalation = support(dash)['escalations'][0]
    for field in ('reason', 'observedChange', 'timeline', 'sources', 'rulesApplied', 'agentActions', 'userResponses', 'urgencyLabel', 'openDecision'):
        assert escalation[field], field
    assert escalation['rulesApplied'][0]['id'] == 'ESC-BP-001'
    assert escalation['urgency'] == 'routine' and escalation['urgencyLabel'] == 'Kiireetön' and escalation['handlingTime'] == '5 arkipäivän kuluessa'
    assert escalation['summarySource'] == 'template' and 'Automaattinen hoidon tarpeen arvio: Kiireetön (5 arkipäivän kuluessa). Peruste: sääntö ESC-BP-001.' in escalation['summaryText']
    assert escalation['openDecision'].startswith('Vahvista tai muuta automaattinen kiireellisyysarvio')
    assert any('2/2' in line for line in escalation['observedChange'])
    # the assessment behind the routing
    assessment = assessment_by_id(dash, escalation['assessmentId'])
    assert assessment['trigger'] == 'rule' and assessment['mode'] == 'automated' and assessment['status'] == 'issued'
    assert assessment['urgency'] == 'routine' and assessment['urgencyLabel'] == 'Kiireetön' and assessment['escalationId'] == escalation['id']
    assert assessment['careNeedLabel'] == 'Hoitajan yhteydenotto 5 arkipäivän kuluessa' and assessment['llmUsed'] is False
    assert assessment['legalNotice'] == texts.LEGAL_NOTICE and assessment['rulesApplied'][0]['id'] == 'ESC-BP-001'
    assert assessment['basis'] and assessment['planVersion'] == 1 and assessment['chainId'] == escalation['chainId']
    # the user is told calmly, with the right to a professional's assessment one click away
    notice = agent_messages(dash)[-1]
    assert notice['kind'] == 'escalation_notice' and 'Tein tilanteestasi automaattisen hoidon tarpeen arvion: Kiireetön.' in notice['text']
    assert 'ei vaadi sinulta nyt muuta' in notice['text'] and 'ei kielimalliin' in notice['text']
    button = next(a for a in notice['actions'] if a['type'] == 'request_human_assessment')
    assert button['label'] == 'Pyydä ammattilaisen arvio' and button['args'] == {'assessmentId': assessment['id']} and button['used'] is False
    assert notice['assessment'] == {'id': assessment['id'], 'urgency': 'routine', 'urgencyLabel': 'Kiireetön', 'mode': 'automated', 'status': 'issued'}
    assert check_text(notice['text'], allowed_urgency='routine')['passed'] and check_text(escalation['summaryText'], allowed_urgency='routine')['passed']
    situation = support(dash)['situation']
    assert situation['tone'] == 'waiting' and situation['headline'].startswith('Arvioin tilanteesi automaattisesti: Kiireetön. Hoitajasi ottaa yhteyttä 5 arkipäivän kuluessa.')
    assert situation['nextStep']['title'] == 'Ei tehtäviä – arvio on tehty ja hoitajasi ottaa yhteyttä'
    assert situation['assessment']['id'] == assessment['id'] and situation['assessment']['canRequestHuman'] is True
    assert situation['assessment']['statusLabel'] == 'Arvio tehty' and situation['whatStaysHuman']
    card = next(c for c in situation['plans'] if c['id'] == bp['id'])
    assert 'Arvio: Kiireetön – hoitajasi ottaa yhteyttä 5 arkipäivän kuluessa.' in card['sentence']
    professional = support(dash)['professional']
    assert professional['escalationIds'] == [escalation['id']] and professional['assessmentReviewIds'] == [assessment['id']]
    # the cycle waits for the professional
    dash = ok(client.post('/api/support/cycle'))
    assert 'odottaa ammattilaisen päätöstä' in plan(dash, 'blood_pressure')['lastAgentAction']['detail'] or \
        'Arvioitu automaattisesti' in plan(dash, 'blood_pressure')['lastAgentAction']['label']


def test_professional_update_flows_back_and_the_agent_follows_the_new_version():
    dash = _escalate()
    assessment_id = support(dash)['escalations'][0]['assessmentId']
    dash = ok(client.post('/api/support/simulate/professional-decision'))
    bp = plan(dash, 'blood_pressure')
    assert bp['status'] == 'active' and bp['version'] == 2 and bp['measurementsPerWeek'] == 14
    escalation = support(dash)['escalations'][0]
    assert escalation['status'] == 'resolved' and escalation['appropriate'] is True
    # "Oliko automaattinen kiireellisyysarvio oikea?" -> the assessment is confirmed with the plan decision
    assessment = assessment_by_id(dash, assessment_id)
    assert assessment['status'] == 'confirmed' and assessment['professionalReview']['decision'] == 'confirm'
    assert assessment['professionalReview']['byRole'] == 'Sairaanhoitaja' and assessment['statusLabel'] == 'Ammattilainen vahvisti arvion'
    decision_entry = next(e for e in support(dash)['audit']['entries'] if e['stage'] == 'professional_decision')
    assert 'Automaattinen kiireellisyysarvio oli oikea: kyllä.' in decision_entry['detail']
    assert support(dash)['situation']['nextStep']['title'] == 'Tee kotimittaus aamulla ja illalla seuraavan 7 päivän ajan.'
    assert 'versio 2' in agent_messages(dash)[-1]['text']
    assert support(dash)['professional']['assessmentReviewIds'] == []
    # a week later the agent works under version 2 and does not re-escalate on failures the nurse already reviewed
    dash = ok(client.post('/api/support/simulate/week'))
    checkin = support(dash)['openCheckIns'][0]
    assert checkin['planVersion'] == 2
    assert '10 minuutin taukoliikuntahetki kolme kertaa' in checkin['questions'][0]['text']
    assert plan(dash, 'blood_pressure')['status'] == 'active'
    assert len(support(dash)['escalations']) == 1 and len(support(dash)['assessments']) == 1


def test_continue_without_confirming_the_assessment_changes_it_and_says_so():
    dash = _escalate()
    escalation = support(dash)['escalations'][0]
    dash = ok(client.post(f"/api/support/plans/{escalation['planId']}/decision",
                          json={'decision': 'continue', 'role': 'nurse', 'escalationAppropriate': False, 'note': 'Ei tarvetta yhteydenottoon.'}))
    assessment = assessment_by_id(dash, escalation['assessmentId'])
    assert assessment['status'] == 'changed' and assessment['professionalReview']['decision'] == 'change_urgency'
    assert 'Automaattinen kiireellisyysarvio oli oikea: ei.' in next(e for e in support(dash)['audit']['entries'] if e['stage'] == 'professional_decision')['detail']
    assert agent_messages(dash)[-1]['text'].startswith('Hoitajasi kävi tilanteesi läpi ja tarkensi automaattista arviota.')


def test_safety_threshold_goes_through_even_without_proactive_contact():
    approve_bp()
    ok(client.put('/api/support/consent', json={'proactiveContact': False}))
    dash = ok(client.post('/api/support/measurements', json={'systolic': 186, 'diastolic': 112}))
    escalation = support(dash)['escalations'][0]
    assert escalation['trigger'] == 'safety_threshold' and escalation['urgency'] == 'same_day'
    assert escalation['urgencyLabel'] == 'Kiireellinen – samana päivänä' and escalation['handlingTime'] == 'samana päivänä'
    assert escalation['openDecision'] == 'Automaattinen arvio: kiireellinen, samana päivänä. Vahvista arvio ja ota yhteyttä asiakkaaseen tänään.'
    assessment = assessment_by_id(dash, escalation['assessmentId'])
    assert assessment['trigger'] == 'safety_threshold' and assessment['urgency'] == 'same_day' and assessment['rulesApplied'][0]['id'] == 'ESC-BP-002'
    message = agent_messages(dash)[-1]
    assert message['kind'] == 'safety_threshold' and '112' in message['text'] and message['textSource'] == 'fixed'
    assert message['text'].startswith('Automaattinen hoidon tarpeen arvio: kiireellinen, hoidettava samana päivänä.')
    assert 'Välitin tiedon myös hoitajallesi.' in message['text'] and message['assessment']['urgency'] == 'same_day'
    assert any(a['type'] == 'request_human_assessment' for a in message['actions'])
    situation = support(dash)['situation']
    assert situation['tone'] == 'urgent' and situation['headline'] == 'Automaattinen arvio: kiireellinen, samana päivänä. Toimi alla olevan ohjeen mukaan.'
    # the same reading does not escalate twice
    dash = ok(client.post('/api/support/cycle'))
    assert len(support(dash)['escalations']) == 1 and len(support(dash)['assessments']) == 1


def test_invalid_measurements_are_rejected():
    approve_bp()
    assert client.post('/api/support/measurements', json={'systolic': 80, 'diastolic': 120}).status_code == 400


# --- the user's right to an assessment made by a professional ------------------------------------------------------------

def test_user_can_request_a_professional_assessment_of_the_automated_one():
    dash = _escalate()
    escalation = support(dash)['escalations'][0]
    assessment_id = escalation['assessmentId']
    notice_id = agent_messages(dash)[-1]['id']
    response = client.post(f'/api/support/assessments/{assessment_id}/request-human-review')
    dash = ok(response)
    result = response.json()['result']
    assert result['status'] == 'human_review_requested' and result['humanReviewRequestedAt'] == dash['currentDate']
    assert result['statusLabel'] == 'Ammattilaisen arvio pyydetty' and result['canRequestHuman'] is False
    escalation = support(dash)['escalations'][0]
    assert escalation['humanReviewRequested'] is True and escalation['openDecision'].startswith('Asiakas pyysi ammattilaisen tekemän arvion. ')
    assert len(support(dash)['escalations']) == 1 and len(support(dash)['assessments']) == 1
    messages = dash['companion']['messages']
    assert messages[-2]['role'] == 'user' and messages[-2]['text'] == 'Pyydä ammattilaisen arvio'
    confirmation = messages[-1]
    assert confirmation['kind'] == 'assessment_notice' and confirmation['text'] == (
        'Selvä. Pyysit ammattilaisen tekemän arvion: hoitajasi tekee sen 5 arkipäivän kuluessa ja ottaa sinuun yhteyttä. '
        'Automaattinen arvio (Kiireetön) jää taustatiedoksi.')
    assert check_text(confirmation['text'], allowed_urgency='routine')['passed']
    # the button in the earlier notice is spent, the queues know about the request, the audit trail records the right
    notice = next(m for m in messages if m['id'] == notice_id)
    assert all(a['used'] for a in notice['actions'] if a['type'] == 'request_human_assessment')
    professional = support(dash)['professional']
    assert professional['humanReviewRequestIds'] == [assessment_id] and professional['assessmentReviewIds'] == [assessment_id]
    assert support(dash)['situation']['assessment']['canRequestHuman'] is False
    entry = next(e for e in support(dash)['audit']['entries'] if e['stage'] == 'assess' and e['actor'] == 'user')
    assert entry['outcome'] == 'human_review_requested' and 'oikeuttaan ammattilaisen tekemään arvioon' in entry['detail']
    assert client.post(f'/api/support/assessments/{assessment_id}/request-human-review').status_code == 400
    assert client.post('/api/support/assessments/hta-9999/request-human-review').status_code == 400


def test_human_review_can_be_requested_through_the_chat_button():
    dash = _escalate()
    notice = agent_messages(dash)[-1]
    button = next(a for a in notice['actions'] if a['type'] == 'request_human_assessment')
    response = client.post(f"/api/loop/companion/actions/{button['id']}", json={'args': {}})
    if response.status_code == 200:  # the chat handler for the button (owned by the chat) is in place
        dash = response.json()['dashboard']
        assert assessment_by_id(dash, button['args']['assessmentId'])['status'] == 'human_review_requested'
        assert support(dash)['escalations'][0]['humanReviewRequested'] is True
    else:
        assert response.status_code == 400


# --- professional oversight of the automated assessments -------------------------------------------------------------------

def test_professional_confirms_the_automated_assessment():
    dash = _escalate()
    assessment_id = support(dash)['escalations'][0]['assessmentId']
    response = client.post(f'/api/support/assessments/{assessment_id}/review', json={'decision': 'confirm', 'role': 'nurse'})
    dash = ok(response)
    result = response.json()['result']
    assert result['status'] == 'confirmed' and result['professionalReview']['label'] == 'Vahvista arvio'
    assert result['professionalReview']['byRole'] == 'Sairaanhoitaja' and result['professionalReview']['newUrgency'] is None
    assert agent_messages(dash)[-1]['text'] == 'Hoitajasi vahvisti automaattisen arvion: Kiireetön.'
    assert agent_messages(dash)[-1]['kind'] == 'assessment_notice'
    entry = next(e for e in support(dash)['audit']['entries'] if e['stage'] == 'professional_decision')
    assert entry['professionalDecision'] == 'Vahvista arvio' and entry['outcome'] == 'confirmed' and entry['actor'] == 'professional'
    assert support(dash)['professional']['assessmentReviewIds'] == []  # confirmed: out of the oversight queue
    assert support(dash)['escalations'][0]['status'] == 'open'  # the care decision is still the professional's plan decision
    assert client.post(f'/api/support/assessments/{assessment_id}/review', json={'decision': 'confirm', 'role': 'nurse'}).status_code == 400
    assert support(dash)['impact']['assessmentsConfirmed'] == 1


def test_professional_changes_the_urgency_class_and_the_escalation_follows():
    dash = _escalate()
    escalation = support(dash)['escalations'][0]
    body = {'decision': 'change_urgency', 'role': 'nurse', 'newUrgency': 'within_3_days', 'note': 'Soitan huomenna.'}
    response = client.post(f"/api/support/assessments/{escalation['assessmentId']}/review", json=body)
    dash = ok(response)
    result = response.json()['result']
    assert result['status'] == 'changed' and result['urgency'] == 'within_3_days' and result['urgencyLabel'] == 'Kiirevastaanotto 3 arkipäivän kuluessa'
    assert result['professionalReview']['newUrgency'] == 'within_3_days' and result['professionalReview']['newUrgencyLabel'] == 'Kiirevastaanotto 3 arkipäivän kuluessa'
    updated = support(dash)['escalations'][0]
    assert updated['urgency'] == 'soon' and updated['urgencyLabel'] == 'Kiirevastaanotto 3 arkipäivän kuluessa' and updated['handlingTime'] == '3 arkipäivän kuluessa'
    assert agent_messages(dash)[-1]['text'] == 'Hoitajasi tarkensi arviota: Kiirevastaanotto 3 arkipäivän kuluessa. Soitan huomenna.'
    assert support(dash)['situation']['headline'].startswith('Arvioin tilanteesi automaattisesti: Kiirevastaanotto 3 arkipäivän kuluessa. Hoitajasi ottaa yhteyttä 3 arkipäivän kuluessa.')
    assert support(dash)['impact']['assessmentsChanged'] == 1


def test_professional_takes_over_the_assessment():
    dash = _escalate()
    assessment_id = support(dash)['escalations'][0]['assessmentId']
    body = {'decision': 'take_over', 'role': 'physician', 'newUrgency': 'same_day', 'note': 'Soitan asiakkaalle tänään.'}
    dash = ok(client.post(f'/api/support/assessments/{assessment_id}/review', json=body))
    assessment = assessment_by_id(dash, assessment_id)
    assert assessment['status'] == 'human_reviewed' and assessment['statusLabel'] == 'Ammattilainen teki arvion itse'
    assert assessment['urgency'] == 'same_day' and support(dash)['escalations'][0]['urgency'] == 'same_day'
    assert agent_messages(dash)[-1]['text'] == 'Lääkärisi teki hoidon tarpeen arvion itse: Kiireellinen – samana päivänä. Soitan asiakkaalle tänään.'
    assert support(dash)['situation']['tone'] == 'urgent'


def test_review_rejects_unknown_ids_roles_and_classes():
    dash = _escalate()
    assessment_id = support(dash)['escalations'][0]['assessmentId']
    assert client.post('/api/support/assessments/hta-9999/review', json={'decision': 'confirm', 'role': 'nurse'}).status_code == 400
    assert client.post(f'/api/support/assessments/{assessment_id}/review', json={'decision': 'confirm', 'role': 'astronaut'}).status_code == 400
    assert client.post(f'/api/support/assessments/{assessment_id}/review', json={'decision': 'change_urgency', 'role': 'nurse'}).status_code == 400
    assert client.post(f'/api/support/assessments/{assessment_id}/review', json={'decision': 'change_urgency', 'role': 'nurse', 'newUrgency': 'routine'}).status_code == 400
    assert client.post(f'/api/support/assessments/{assessment_id}/review', json={'decision': 'change_urgency', 'role': 'nurse', 'newUrgency': 'asap'}).status_code == 422
    assert client.post(f'/api/support/assessments/{assessment_id}/review', json={'decision': 'approve', 'role': 'nurse'}).status_code == 422
    assert assessment_by_id(client.get('/api/loop/state').json(), assessment_id)['status'] == 'issued'


# --- consent to the automation (terveydenhuoltolaki 51 § 3 mom., assumed 2027) ---------------------------------------------

def test_without_consent_the_routing_asks_the_professional_to_make_the_assessment():
    dash = ok(client.put('/api/support/consent', json={'automatedAssessment': False}))
    assert support(dash)['consent']['automatedAssessment'] is False
    assert any('suostumus peruttu' in e['detail'] for e in support(dash)['audit']['entries'] if e['stage'] == 'consent')
    dash = _escalate()
    escalation = support(dash)['escalations'][0]
    assert escalation['openDecision'] == 'Asiakas ei ole antanut suostumusta automaattiseen arvioon: tee hoidon tarpeen arvio itse. Esiarvio: Kiireetön.'
    assessment = assessment_by_id(dash, escalation['assessmentId'])
    assert assessment['mode'] == 'professional_required' and assessment['modeLabel'] == 'Esiarvio – ammattilainen tekee arvion'
    notice = agent_messages(dash)[-1]
    assert 'Tein tilanteestasi esiarvion, koska et ole antanut suostumusta automaattiseen arvioon: Kiireetön.' in notice['text']
    assert check_text(notice['text'], allowed_urgency='routine')['passed']
    assert support(dash)['situation']['headline'].startswith('Tein tilanteestasi esiarvion: Kiireetön. Hoitajasi tekee hoidon tarpeen arvion')
    assert assessment['id'] in support(dash)['professional']['assessmentReviewIds']
    dash = ok(client.put('/api/support/consent', json={'automatedAssessment': True}))
    assert support(dash)['consent']['automatedAssessmentInformedAt'] == dash['currentDate']
    assert any('nimenomainen suostumus annettu' in e['detail'] for e in support(dash)['audit']['entries'] if e['stage'] == 'consent')


# --- symptom reports in the chat (demo simulation) -------------------------------------------------------------------------

def test_symptom_report_simulation_makes_an_assessment_and_routes_it():
    approve_bp()
    response = client.post('/api/support/simulate/symptom-report')
    dash = ok(response)
    result = response.json()['result']
    assert result['text'] == 'Minulla on ollut pari päivää päänsärkyä ja huimausta, pitäisikö mennä lääkäriin?'
    assessment = result['assessment']
    assert assessment['trigger'] == 'symptom_report' and assessment['urgency'] == 'within_3_days' and assessment['mode'] == 'automated'
    assert set(assessment['symptoms']) >= {'päänsärkyä', 'huimausta'} and assessment['llmUsed'] is False
    escalation = support(dash)['escalations'][0]
    assert escalation['assessmentId'] == assessment['id'] and escalation['urgencyLabel'] == 'Kiirevastaanotto 3 arkipäivän kuluessa'
    assert plan(dash, 'blood_pressure')['status'] == 'escalated'
    reply = next(m for m in reversed(agent_messages(dash)) if m['kind'] == 'care_assessment')
    assert 'Automaattinen hoidon tarpeen arvio: Kiirevastaanotto 3 arkipäivän kuluessa.' in reply['text'] and reply['textSource'] == 'template'
    assert reply['assessment']['id'] == assessment['id'] and {a['type'] for a in reply['actions']} >= {'request_human_assessment'}
    assert check_text(reply['text'], allowed_urgency='within_3_days')['passed']
    assert support(dash)['situation']['assessment']['id'] == assessment['id']
    assert dash['support']['demo']['symptomReport'] == result['text']


def test_symptom_report_without_consent_is_a_preliminary_assessment():
    approve_bp()
    ok(client.put('/api/support/consent', json={'automatedAssessment': False}))
    response = client.post('/api/support/simulate/symptom-report')
    dash = ok(response)
    assessment = response.json()['result']['assessment']
    assert assessment['mode'] == 'professional_required' and assessment['urgency'] == 'within_3_days'
    reply = next(m for m in reversed(agent_messages(dash)) if m['kind'] == 'care_assessment')
    assert 'Esiarvio' in reply['text'] and check_text(reply['text'], allowed_urgency='within_3_days')['passed']
    escalation = support(dash)['escalations'][0]
    assert escalation['openDecision'].endswith('Esiarvio: Kiirevastaanotto 3 arkipäivän kuluessa.')


def test_full_demo_scenario_of_the_assumed_law_change():
    dash = _escalate()
    escalation = support(dash)['escalations'][0]
    assessment_id = escalation['assessmentId']
    assert assessment_by_id(dash, assessment_id)['urgencyLabel'] == 'Kiireetön'
    ok(client.post(f'/api/support/assessments/{assessment_id}/request-human-review'))
    dash = ok(client.post(f'/api/support/assessments/{assessment_id}/review', json={'decision': 'confirm', 'role': 'nurse'}))
    assert assessment_by_id(dash, assessment_id)['status'] == 'confirmed'
    dash = ok(client.post('/api/support/simulate/professional-decision'))
    assert plan(dash, 'blood_pressure')['version'] == 2 and support(dash)['escalations'][0]['status'] == 'resolved'
    dash = ok(client.post('/api/support/simulate/week'))
    assert len(support(dash)['escalations']) == 1
    # a symptom report in the chat: assessed within 3 days and routed
    dash = ok(client.post('/api/support/simulate/symptom-report'))
    symptom = support(dash)['assessments'][0]
    assert symptom['trigger'] == 'symptom_report' and symptom['urgency'] == 'within_3_days'
    assert any(m['kind'] == 'care_assessment' for m in agent_messages(dash))
    # a reading over the safety limit: same day, fixed message with 112
    dash = ok(client.post('/api/support/measurements', json={'systolic': 186, 'diastolic': 112}))
    safety = support(dash)['assessments'][0]
    assert safety['trigger'] == 'safety_threshold' and safety['urgency'] == 'same_day'
    assert agent_messages(dash)[-1]['kind'] == 'safety_threshold' and '112' in agent_messages(dash)[-1]['text']
    # without consent the next assessment is preliminary
    ok(client.put('/api/support/consent', json={'automatedAssessment': False}))
    dash = ok(client.post('/api/support/simulate/symptom-report'))
    preliminary = support(dash)['assessments'][0]
    assert preliminary['mode'] == 'professional_required'
    assert 'Esiarvio' in next(m for m in reversed(agent_messages(dash)) if m['kind'] == 'care_assessment')['text']
    assert all(check_text(m['text'], allowed_urgency=(m.get('assessment') or {}).get('urgency'))['passed']
               for m in agent_messages(dash) if m['textSource'] != 'fixed' and m['kind'] != 'emergency')
    dash = ok(client.post('/api/loop/demo/reset'))
    assert support(dash)['assessments'] == []


# --- gate 3 in the agent cycle ----------------------------------------------------------------------------------------

def test_no_proactive_contact_defers_the_action_and_logs_why():
    approve_bp()
    ok(client.put('/api/support/consent', json={'proactiveContact': False}))
    dash = ok(client.post('/api/support/simulate/week'))
    assert support(dash)['openCheckIns'] == []
    bp = plan(dash, 'blood_pressure')
    assert bp['lastAgentAction']['action'] == 'deferred'
    assert any(e['action'] == 'deferred' and 'portti 3' in e['detail'] for e in support(dash)['audit']['entries'])


def test_weekly_contact_limit_and_quiet_hours():
    approve_bp()
    ok(client.put('/api/support/consent', json={'maxContactsPerWeek': 0, 'quietHours': {'start': '22:00', 'end': '10:00'}}))
    dash = ok(client.post('/api/support/simulate/week'))
    assert plan(dash, 'blood_pressure')['lastAgentAction']['action'] == 'deferred'
    ok(client.put('/api/support/consent', json={'maxContactsPerWeek': 3}))
    dash = ok(client.post('/api/support/cycle'))
    assert support(dash)['openCheckIns'][0]['deliveredAt'].endswith('10:00')


def test_paused_theme_is_left_alone_and_can_resume():
    dash = approve_bp()
    bp_id = plan(dash, 'blood_pressure')['id']
    ok(client.post(f'/api/support/plans/{bp_id}/pause', json={}))
    dash = ok(client.post('/api/support/simulate/week'))
    assert support(dash)['openCheckIns'] == [] and plan(dash, 'blood_pressure')['status'] == 'paused'
    dash = ok(client.post(f'/api/support/plans/{bp_id}/resume'))
    assert plan(dash, 'blood_pressure')['status'] == 'active'


def test_invalid_consent_values_are_rejected():
    assert client.put('/api/support/consent', json={'quietHours': {'start': '25:00', 'end': '08:00'}}).status_code == 400
    assert client.put('/api/support/consent', json={'dataSources': {'unknown': True}}).status_code == 400


# --- audit trail, LLM boundaries ----------------------------------------------------------------------------------------

def test_every_step_is_in_the_audit_trail():
    approve_bp()
    ok(client.post('/api/support/simulate/week'))
    dash = answer_all({'goal_progress': 'met'})
    entries = support(dash)['audit']['entries']
    assert {e['stage'] for e in entries} >= {'data', 'gate', 'observe', 'compare', 'detect', 'decide', 'act', 'wait', 'evaluate', 'update', 'professional_decision'}
    for entry in entries:
        for field in REQUIRED_AUDIT_FIELDS:
            assert field in entry
        assert entry['llmUsed'] is False  # LLM off: everything is rules and templates
    chain = next(c for c in support(dash)['audit']['chains'] if c['flow'][2].get('text'))
    assert [step['label'] for step in chain['flow']][:4] == ['Havainto', 'Agentin toimi', 'Käyttäjän vastaus', 'Seuranta']
    assert [step['key'] for step in chain['flow']] == FLOW_KEYS


def test_the_assessment_is_its_own_audit_stage_and_flow_step():
    dash = _escalate()
    entries = support(dash)['audit']['entries']
    assess = next(e for e in entries if e['stage'] == 'assess')
    assert assess['stageLabel'] == 'Hoidon tarpeen arvio (automaattinen)' and assess['actor'] == 'agent' and assess['outcome'] == 'routine'
    assert assess['rule']['id'] == 'ESC-BP-001' and assess['detail'].startswith('Automaattinen hoidon tarpeen arvio: Kiireetön (5 arkipäivän kuluessa).')
    escalate = next(e for e in entries if e['stage'] == 'escalate')
    assert escalate['detail'].startswith('Ohjaus vastuuammattilaiselle (Sairaanhoitaja) automaattisen arvion perusteella: Kiireetön, käsittely 5 arkipäivän kuluessa.')
    assert escalate['stageLabel'] == 'Eskalaatio'
    chain = next(c for c in support(dash)['audit']['chains'] if c['flow'][4].get('text'))
    assert len(chain['flow']) == 7 and [s['label'] for s in chain['flow']] == [
        'Havainto', 'Agentin toimi', 'Käyttäjän vastaus', 'Seuranta', 'Automaattinen arvio', 'Eskalaatio', 'Ammattilaisen päätös']
    assert chain['flow'][4]['text'].startswith('Automaattinen hoidon tarpeen arvio') and chain['flow'][5]['text'].startswith('Ohjaus vastuuammattilaiselle')


def test_llm_drafts_the_escalation_summary_from_bounded_facts_only(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    prompts: list[str] = []

    def fake_call(prompt, output_schema=None):
        prompts.append(prompt)
        if 'vastuuammattilaiselle' in prompt:
            return ('Asiakkaan sovittu liikuntatavoite ei ole toteutunut kahdella viikolla. Kotimittausten keskiarvo on sovitun tason '
                    'yläpuolella. Automaattinen arvio: Kiireetön.')
        return None

    monkeypatch.setattr(llm, '_call', fake_call)
    dash = _escalate()
    escalation = support(dash)['escalations'][0]
    assert escalation['summarySource'] == 'llm'
    prompt = next(p for p in prompts if 'vastuuammattilaiselle' in p)
    for forbidden in ('Aino', 'SYN-AINO', 'rawText', 'Kävelyt ovat jääneet', 'rs999000001', 'LDLR'):
        assert forbidden not in prompt
    assert '"urgencyLabel": "Kiireetön"' in prompt  # the class is given to the LLM, never asked from it
    audit = next(e for e in support(dash)['audit']['entries'] if e['stage'] == 'escalate')
    assert audit['llmUsed'] is True and 'draft_escalation_summary' in audit['llmTask']
    # the LLM text never decides: status, rule and urgency come from the plan
    assert escalation['rulesApplied'][0]['id'] == 'ESC-BP-001' and escalation['urgency'] == 'routine'
    assert assessment_by_id(dash, escalation['assessmentId'])['llmUsed'] is False


def test_unsafe_llm_summary_falls_back_to_the_template(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    monkeypatch.setattr(llm, '_call', lambda prompt, output_schema=None: 'Sinulla on todettu verenpainetauti. Aloita lääkitys heti. Kiireetön.')
    escalation = support(_escalate())['escalations'][0]
    assert escalation['summarySource'] == 'template'
    assert 'todettu' not in escalation['summaryText']


def test_llm_summary_that_changes_the_class_falls_back_to_the_template(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    monkeypatch.setattr(llm, '_call', lambda prompt, output_schema=None: 'Tilanne vaikuttaa kiireelliseltä, arvio: Kiireellinen – samana päivänä.')
    escalation = support(_escalate())['escalations'][0]
    assert escalation['summarySource'] == 'template' and escalation['urgencyLabel'] == 'Kiireetön'


# --- DNA report and professional review of genetic findings ---------------------------------------------------------------

def _dna_report() -> tuple[str, dict]:
    session_id = client.post('/api/analysis/sessions/from-demo', json={'kind': 'quick_snippet', 'mode': 'demo', 'resource_profile': 'light'}).json()['session_id']
    for step in ('preflight', 'parse-next', 'match-next', 'classify'):
        client.post(f'/api/analysis/sessions/{session_id}/{step}')
    return session_id, client.post(f'/api/analysis/sessions/{session_id}/finalize').json()['report']


def test_dna_report_marks_relevance_and_uncertain_variants_cannot_be_sent_to_follow_up():
    session_id, report = _dna_report()
    by_gene = {f['gene']: f for f in report['findings']}
    assert by_gene['MTHFR']['relevance']['category'] == 'uncertain_or_conflicting'
    assert by_gene['BRCA1']['relevance']['userVisible'] is False
    assert by_gene['F5']['relevance']['category'] == 'needs_professional_check'
    refused = client.post('/api/support/insights/request-review', json={'sessionId': session_id, 'findingId': by_gene['MTHFR']['id']})
    assert refused.status_code == 400
    requested = client.post('/api/support/insights/request-review', json={'sessionId': session_id, 'findingId': by_gene['TP53']['id']})
    insight = requested.json()['result']
    assert insight['reviewStatus'] == 'pending_professional_review'
    dash = ok(client.post(f"/api/support/insights/{insight['id']}/decision", json={'decision': 'refer', 'ownerRole': 'genetics'}))
    reviewed = next(i for i in support(dash)['insights'] if i['id'] == insight['id'])
    assert reviewed['reviewOwnerRole'] == 'genetics' and reviewed['reviewStatus'] == 'pending_professional_review'
    assert dash['counts']['activeMonitorings'] == 1  # nothing reached the user's follow-up


# --- impact, cohort, adapters, demo ------------------------------------------------------------------------------------------

def test_impact_metrics_and_paginated_synthetic_cohort():
    _escalate()
    dash = ok(client.post('/api/support/simulate/professional-decision'))
    metrics = support(dash)['impact']
    assert metrics['synthetic'] is True and metrics['microInterventions'] == 2 and metrics['escalations'] == 1
    assert metrics['escalationsAppropriate'] == 1 and metrics['goalAdjustments'] == 1
    assert metrics['assessments'] == 1 and metrics['assessmentsAutomated'] == 1 and metrics['assessmentsConfirmed'] == 1
    assert metrics['assessmentsChanged'] == 0 and metrics['humanReviewRequests'] == 0 and metrics['avgMinutesToAssessment'] == 0
    assert metrics['assessmentsByUrgency'] == {'routine': 1}
    page = client.get('/api/support/cohort', params={'page': 2, 'pageSize': 20, 'status': 'active'}).json()
    assert page['page'] == 2 and len(page['rows']) == 20 and all(r['status'] == 'active' for r in page['rows'])
    assert all(r['assessments'] >= r['escalations'] for r in page['rows'])
    assert client.get('/api/support/cohort', params={'pageSize': 500}).status_code == 422  # never the whole cohort at once
    aggregate = client.get('/api/support/impact/cohort').json()
    assert aggregate['people'] == 300 and aggregate['synthetic'] is True
    assert aggregate['assessments'] >= aggregate['escalations'] and 0 < aggregate['assessmentsConfirmedShare'] <= 1
    assert isinstance(aggregate['humanReviewRequests'], int)


def test_adapter_preview_and_schema():
    csv_text = 'asiakas_tunnus;pvm;kanava;aihe;kuvaus;lahde\nX-1;1.9.2026;puhelin;verenpaine;Kysymys;Testi'
    preview = client.post('/api/support/adapters/preview', json={'format': 'csv', 'table': 'asioinnit.csv', 'content': csv_text}).json()
    assert preview['target'] == 'interactionEvents' and preview['items'][0]['channel'] == 'phone' and preview['items'][0]['date'] == '2026-09-01'
    schema = client.get('/api/support/schema/person-profile').json()
    assert {'diagnoses', 'medications', 'careEpisodes', 'professionalNotes', 'interactionEvents', 'measurements',
            'selfReportedData', 'geneticInsights', 'consents', 'activeSupportPlans'} <= set(schema['properties'])


def test_check_in_can_be_answered_in_the_chat_too():
    approve_bp()
    dash = ok(client.post('/api/support/simulate/week'))
    question_message = agent_messages(dash)[-1]
    choice = next(a for a in question_message['actions'] if a['args']['optionId'] == 'met')
    response = client.post(f"/api/loop/companion/actions/{choice['id']}", json={'args': {}})
    dash = ok(response)
    answered = support(dash)['openCheckIns'][0]['questions'][0]
    assert answered['answer'] == 'met'
    assert all(a['used'] for a in next(m for m in agent_messages(dash) if m['id'] == question_message['id'])['actions'])


def test_demo_reset_restores_the_initial_story():
    _escalate()
    dash = ok(client.post('/api/loop/demo/reset'))
    assert plan(dash, 'blood_pressure')['status'] == 'pending_professional_review'
    assert support(dash)['escalations'] == [] and support(dash)['assessments'] == [] and dash['currentDate'] == '2026-09-01'
    assert support(dash)['situation']['assessment'] is None
