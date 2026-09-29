from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.loop import llm
from app.loop.safety import check_text
from app.loop.user_context import USER_CONTEXT_KEYS
from app.legacy_api import legacy_app as app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_STATE_PATH', str(tmp_path / 'state.json'))
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'off')
    client.post('/api/loop/demo/reset')


def say(text: str) -> dict:
    response = client.post('/api/loop/companion/messages', json={'text': text})
    assert response.status_code == 200, response.text
    return response.json()


def act(action_id: str, **args) -> dict:
    response = client.post(f'/api/loop/companion/actions/{action_id}', json={'args': args})
    assert response.status_code == 200, response.text
    return response.json()['dashboard']


def state() -> dict:
    return client.get('/api/loop/state').json()


def agent_messages(dash: dict) -> list[dict]:
    return [m for m in dash['companion']['messages'] if m['role'] == 'agent']


def last_agent(dash: dict) -> dict:
    return agent_messages(dash)[-1]


def action(message: dict, label: str) -> dict:
    return next(a for a in message['actions'] if a['label'] == label)


def add_high_ldl() -> dict:
    return client.post('/api/loop/demo/events', json={'template': 'high_ldl'}).json()['dashboard']


# --- 1. bounded context ----------------------------------------------------------------

def test_llm_only_receives_bounded_user_context(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    prompts: list[str] = []

    def fake_call(prompt, output_schema=None):
        prompts.append(prompt)
        return None  # behave like an unavailable API

    monkeypatch.setattr(llm, '_call', fake_call)
    add_high_ldl()
    say('Miksi tämä huomio nousi esiin?')

    chat_prompts = [p for p in prompts if '"userContext"' in p]
    assert chat_prompts, 'explanation prompt was not sent'
    payload = json.loads(chat_prompts[-1][chat_prompts[-1].index('{'):])
    assert set(payload['userContext']) == set(USER_CONTEXT_KEYS)
    # no names, raw records or DNA; gene names are left out too because Aino has not allowed genetic details
    for forbidden in ('rawText', 'genotype', 'birthYear', 'Aino', 'rs999000001', 'extractedData', 'LDLR'):
        assert forbidden not in chat_prompts[-1]


# --- 2. safety intents -------------------------------------------------------------------

def test_diagnosis_request_does_not_produce_diagnosis():
    add_high_ldl()
    result = say('Onko minulla familiaalinen hyperkolesterolemia?')
    assert result['intent'] == 'DIAGNOSIS_REQUEST'
    reply = last_agent(result['dashboard'])
    assert reply['textSource'] == 'fixed'
    assert 'En voi tehdä diagnoosia' in reply['text']
    assert check_text(reply['text'])['passed']
    assert any(a['type'] == 'request_summary' for a in reply['actions'])


def test_medication_change_request_gives_no_medication_instruction():
    result = say('Pitäisikö minun aloittaa kolesterolilääke tai nostaa annosta?')
    assert result['intent'] == 'MEDICATION_CHANGE_REQUEST'
    reply = last_agent(result['dashboard'])
    assert 'En voi antaa ohjeita' in reply['text']
    assert check_text(reply['text'].replace('Älä muuta lääkitystä', ''))['passed']
    assert 'mg' not in reply['text']


def test_general_health_question_is_answered_by_llm_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    monkeypatch.setattr(llm, 'classify_intent', lambda text, intents: 'GENERAL_HEALTH_QUESTION')
    monkeypatch.setattr(llm, 'answer_general_health_question', lambda text: 'Kuitupitoinen ruokavalio voi tukea sydänterveyttä. Oma tilanteesi kannattaa käydä läpi ammattilaisen kanssa.')
    result = say('Mikä ruokavalio on hyväksi sydämelle?')
    assert result['intent'] == 'GENERAL_HEALTH_QUESTION'
    reply = last_agent(result['dashboard'])
    assert reply['textSource'] == 'llm'
    assert 'Kuitupitoinen ruokavalio' in reply['text']
    assert check_text(reply['text'])['passed']


def test_general_health_question_falls_back_to_scope_message_without_llm():
    result = say('Mikä ruokavalio on hyväksi sydämelle?')
    assert result['intent'] == 'GENERAL_HEALTH_QUESTION'
    reply = last_agent(result['dashboard'])
    assert reply['textSource'] == 'fixed'
    assert 'Autan vain seurantasuunnitelmaasi liittyvissä asioissa' in reply['text']


def test_health_overview_is_answered_by_llm_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    monkeypatch.setattr(llm, 'classify_intent', lambda text, intents: 'HEALTH_OVERVIEW')
    monkeypatch.setattr(llm, 'summarize_health_overview', lambda context: 'Olet 42-vuotias ja seurannassasi on LDLR-löydös. Aiempi LDL-mittaus tukee säännöllistä seurantaa jatkossakin.')
    result = say('Anna kokonaiskuva tilanteestani.')
    assert result['intent'] == 'HEALTH_OVERVIEW'
    reply = last_agent(result['dashboard'])
    assert reply['textSource'] == 'llm'
    assert 'Aiempi LDL-mittaus' in reply['text']
    assert check_text(reply['text'])['passed']


def test_health_overview_combines_monitoring_and_timeline_without_llm():
    result = say('Mihin asioihin minun tulisi kiinnittää huomiota?')
    assert result['intent'] == 'HEALTH_OVERVIEW'
    reply = last_agent(result['dashboard'])
    assert reply['textSource'] == 'template'
    text = reply['text']
    # the monitored genetic finding is combined with the latest LDL result (gene name hidden by Aino's consent)
    assert 'Perimätiedon havainto: viimeisin LDL-kolesteroli 2,9 mmol/l (12.5.2026), viitealueella' in text
    assert 'LDLR' not in text
    # a cardiovascular finding connects the blood pressure trend from the timeline to it
    assert 'Verenpaine on noussut hieman (134/86 → 136/87 mmHg)' in text
    # with an active support plan the agent no longer pushes the monthly survey
    assert 'Elämäntapakysely on tekemättä' not in text
    assert check_text(text)['passed']


def test_get_status_reads_the_timeline_and_reports_nothing_acute():
    result = say('Mikä on tilanteeni?')
    assert result['intent'] == 'GET_STATUS'
    reply = last_agent(result['dashboard'])
    assert reply['textSource'] == 'template'
    text = reply['text']
    assert text.startswith('Tilanteesi 1.9.2026')
    # the support plans come first: situation, next step, themes
    assert 'Seuranta etenee suunnitelman mukaan' in text
    assert 'Verenpaineen omaseuranta (odottaa ammattilaisen hyväksyntää)' in text
    assert 'Ei mitään akuuttia' in text
    assert '30.8.2026 Verenpaine (kotimittaus): 136/87 mmHg' in text
    # older than 3 months: not listed as recent
    assert 'Verensokeri' not in text
    assert '46 vuotta' in text and 'LDLR' not in text
    assert check_text(text)['passed']


def test_get_status_flags_out_of_range_value_as_acute():
    client.post('/api/loop/demo/events', json={'template': 'high_ldl'})
    reply = last_agent(say('Mikä on tilanteeni?')['dashboard'])
    assert 'Huomioitavaa nyt:' in reply['text']
    assert 'Ei mitään akuuttia' not in reply['text']
    assert 'viitealueen yläpuolella' in reply['text']


def test_status_and_focus_answers_differ():
    status = last_agent(say('Mikä on tilanteeni?')['dashboard'])['text']
    focus = last_agent(say('Mihin asioihin minun tulisi kiinnittää huomiota?')['dashboard'])['text']
    assert status != focus


def test_emergency_uses_predefined_message_without_llm(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')

    def must_not_be_called(*args, **kwargs):
        raise AssertionError('LLM must not be used for urgent symptoms')

    monkeypatch.setattr(llm, '_call', must_not_be_called)
    result = say('Minulla on kova rintakipu ja hengitysvaikeuksia.')
    assert result['intent'] == 'EMERGENCY_OR_URGENT'
    reply = last_agent(result['dashboard'])
    assert 'hätänumeroon 112' in reply['text']
    assert 'LDLR' not in reply['text']


def test_llm_cannot_override_safety_intent(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    monkeypatch.setattr(llm, 'classify_intent', lambda text, intents: 'GET_STATUS')
    assert say('Voinko lopettaa lääkkeen?')['intent'] == 'MEDICATION_CHANGE_REQUEST'


# --- 3. confirmation before saving, rule engine decides -----------------------------------

def test_add_context_is_not_saved_without_confirmation():
    events_before = len(state()['events'])
    result = say('Isäni sai sydäninfarktin 49-vuotiaana.')
    assert result['intent'] == 'ADD_CONTEXT'
    dash = result['dashboard']
    confirmation = last_agent(dash)
    assert confirmation['kind'] == 'confirmation'
    assert 'lähisukulainen: isä' in confirmation['text'] and 'ikä tapahtumahetkellä: 49 vuotta' in confirmation['text']
    assert len(dash['events']) == events_before

    cancelled = act(action(confirmation, 'Peruuta')['id'])
    assert len(cancelled['events']) == events_before
    assert cancelled['companion']['knowledge']['missingInformation'][0] == 'Suvun sairaushistoria'


def test_edit_before_saving_uses_validated_values():
    confirmation = last_agent(say('Isäni sai sydäninfarktin 49-vuotiaana.')['dashboard'])
    dash = act(action(confirmation, 'Muokkaa')['id'], data={'relation': 'mother', 'condition': 'stroke', 'ageAtEvent': 52})
    event = next(e for e in dash['events'] if e['type'] == 'family_history')
    assert event['structuredData']['relation'] == 'mother' and event['confirmedByUser'] is True

    bad = last_agent(say('Veljeni sai sydäninfarktin 40-vuotiaana.')['dashboard'])
    response = client.post(f"/api/loop/companion/actions/{action(bad, 'Muokkaa')['id']}",
                           json={'args': {'data': {'relation': 'neighbour', 'condition': 'made_up', 'ageAtEvent': 40}}})
    assert response.status_code == 400


def test_rule_engine_not_llm_changes_monitoring_state(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    monkeypatch.setattr(llm, 'classify_intent', lambda text, intents: 'ADD_CONTEXT')
    monkeypatch.setattr(llm, 'extract_family_history', lambda text, r, c: {'relation': 'father', 'condition': 'myocardial_infarction', 'ageAtEvent': 49})
    monkeypatch.setattr(llm, 'explain_for_chat', lambda ctx, focus: 'Tila on nyt professional_review_recommended.')
    monkeypatch.setattr(llm, '_call', lambda *a, **k: None)

    confirmation = last_agent(say('Isäni sai sydäninfarktin 49-vuotiaana.')['dashboard'])
    dash = act(action(confirmation, 'Tallenna')['id'])
    # Without a high LDL result RULE-002 is not met, whatever the LLM says
    assert dash['monitorings'][0]['status'] == 'monitoring'
    assert dash['counts']['openObservations'] == 0
    assert 'eikä seurannan tila muuttunut' in last_agent(dash)['text']
    log = dash['companion']['chatLog'][0]
    assert log['toolInvoked'] == 'saveHealthEvent + ruleEngine.evaluate'
    assert log['ruleApplied'][0]['id'] == 'RULE-LDLR-FAMHX-002' and log['ruleApplied'][0]['triggered'] is False


# --- 4. summary, follow-up, resolve ------------------------------------------------------------

def test_summary_only_after_user_approval():
    add_high_ldl()
    dash = say('Tee tästä yhteenveto lääkärille.')['dashboard']
    ask = last_agent(dash)
    assert ask['text'] == 'Voin muodostaa nykyiseen seurantaasi perustuvan yhteenvedon. Haluatko jatkaa?'
    assert not any(m['kind'] == 'summary_ready' for m in dash['companion']['messages'])

    dash = act(action(ask, 'Muodosta yhteenveto')['id'])
    ready = last_agent(dash)
    assert ready['kind'] == 'summary_ready'
    assert any(a['type'] == 'open_summary' for a in ready['actions'])

    # an already used choice cannot be replayed
    replay = client.post(f"/api/loop/companion/actions/{action(ask, 'Muodosta yhteenveto')['id']}", json={'args': {}})
    assert replay.status_code == 400


def test_full_summary_spans_all_findings_and_the_timeline():
    add_high_ldl()
    dash = say('Tee tästä yhteenveto lääkärille.')['dashboard']
    ask = last_agent(dash)
    dash = act(action(ask, 'Muodosta yhteenveto')['id'])
    assert dash

    summary = client.get('/api/loop/summary/full').json()
    assert summary['syntheticPersonName'] == 'Aino Demo'
    assert 'syntheticPersonId' not in summary
    finding_ids = {f['finding']['id'] for f in summary['findings']}
    assert finding_ids == {'GF-001'}
    related_ids = {e['id'] for e in summary['findings'][0]['relatedEvents']}
    unrelated_ids = {e['id'] for e in summary['unrelatedEvents']}
    assert related_ids and unrelated_ids
    assert related_ids.isdisjoint(unrelated_ids)
    assert any('verikoe' in step.lower() for step in summary['suggestedNextSteps'])
    ldlr = summary['findings'][0]
    assert ldlr['hasDefinedMetric'] is True
    assert isinstance(ldlr['trackedMetrics'], list)

    html = client.get('/api/loop/summary/full.html')
    assert html.status_code == 200 and 'text/html' in html.headers['content-type']
    # a lab order is one line with its result count; the LDL result of the order is listed under the finding
    assert 'B -Perusverenkuva, minidiff, vieritutkimus: 17 tulosta (2025-01-10)' in html.text
    assert 'Lipidit: 6 tulosta, lisäksi 1 löydöksen kohdalla (2025-03-04)' in html.text
    assert 'Kokonaiskolesteroli' not in html.text  # no single rows of a grouped order


def test_follow_up_task_created_via_chat():
    add_high_ldl()
    # cancel the automatic reminder first so a new task must be created
    task_id = state()['tasks'][0]['id']
    client.post('/api/loop/demo/advance-time', json={'days': 30})
    client.post(f'/api/loop/tasks/{task_id}/respond', json={'response': 'no_reminder'})

    ask = last_agent(say('Muistuta tästä myöhemmin.')['dashboard'])
    assert ask['text'] == 'Milloin haluat muistutuksen?'
    assert {a['label'] for a in ask['actions']} >= {'7 päivän kuluttua', '30 päivän kuluttua', 'Muu päivämäärä'}
    dash = act(action(ask, '7 päivän kuluttua')['id'])
    new_task = dash['tasks'][-1]
    assert new_task['id'] != task_id and new_task['status'] == 'open'
    assert new_task['dueAt'] == '2026-10-08'  # 1.10. + 7 days

    ask = last_agent(say('Muistuta minua myöhemmin.')['dashboard'])
    dash = act(action(ask, 'Muu päivämäärä')['id'], date='2026-12-24')
    assert dash['tasks'][-1]['dueAt'] == '2026-12-24' and len(dash['tasks']) == 2


def test_resolve_requires_confirmation():
    add_high_ldl()
    ask = last_agent(say('Olen jo puhunut tästä lääkärin kanssa.')['dashboard'])
    assert ask['text'] == 'Haluatko merkitä tämän huomion käsitellyksi?'
    assert state()['observations'][0]['status'] == 'professional_review_recommended'
    dash = act(action(ask, 'Kyllä')['id'])
    assert dash['observations'][0]['status'] == 'resolved'
    assert dash['tasks'][0]['status'] == 'completed'


# --- 5. proactive -----------------------------------------------------------------------------

def test_proactive_messages_for_new_observation_and_due_task():
    dash = add_high_ldl()
    proactive = [m for m in dash['companion']['messages'] if m['initiatedByAgent'] and m['kind'] == 'proactive']
    assert proactive[-1]['text'] == 'Seurannassasi on uusi tapahtuma. Haluatko nähdä miksi se voi olla relevantti?'

    dash = client.post('/api/loop/demo/advance-time', json={'days': 30}).json()['dashboard']
    due = last_agent(dash)
    assert due['initiatedByAgent'] is True
    assert 'Onko asia jo käsitelty ammattilaisen kanssa?' in due['text']
    assert [a['label'] for a in due['actions']] == ['Kyllä', 'Ei vielä', 'En halua muistutuksia tästä', 'Löydös todettiin epäolennaiseksi']

    # no duplicate proactive messages on reload
    assert len(state()['companion']['messages']) == len(dash['companion']['messages'])

    dash = act(action(due, 'Ei vielä')['id'])
    assert dash['observations'][0]['status'] == 'professional_review_recommended'
    assert dash['tasks'][0]['status'] == 'open'


def test_irrelevant_event_does_not_start_conversation():
    before = len(state()['companion']['messages'])
    dash = client.post('/api/loop/demo/events', json={'template': 'irrelevant_bp'}).json()['dashboard']
    assert len(dash['companion']['messages']) == before


# --- 6. fallback + full story + reset -------------------------------------------------------------

def test_fallback_without_llm_connection(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    monkeypatch.setattr(llm, '_call', lambda *a, **k: None)
    dash = add_high_ldl()
    explanation = act(action(last_agent(dash), 'Näytä miksi')['id'])
    reply = next(m for m in reversed(agent_messages(explanation)) if m['kind'] == 'explanation')
    assert reply['textSource'] == 'template' and reply['aiUnavailable'] is True
    assert 'sääntömoottori' in reply['text']
    assert say('Mikä on tilanteeni?')['intent'] == 'GET_STATUS'
    ask = last_agent(say('Tee yhteenveto lääkärille')['dashboard'])
    ready = act(action(ask, 'Muodosta yhteenveto')['id'])
    assert last_agent(ready)['kind'] == 'summary_ready'


def test_demo_story_end_to_end():
    initial = state()
    assert initial['counts']['activeMonitorings'] == 1 and initial['counts']['openObservations'] == 0

    dash = add_high_ldl()
    assert dash['monitorings'][0]['status'] == 'professional_review_recommended'
    proactive = last_agent(dash)

    dash = act(action(proactive, 'Näytä miksi')['id'])
    explanation = next(m for m in agent_messages(dash) if m['kind'] == 'explanation')
    assert explanation['whyNowObservationId'] == 'obs-0001'
    assert explanation['basis']['decisionBy'] == 'Sääntömoottori'
    question = last_agent(dash)
    assert question['kind'] == 'question'
    assert 'Onko lähisukulaisillasi ollut nuorella iällä' in question['text']

    result = say('Isäni sai sydäninfarktin 49-vuotiaana.')
    assert result['intent'] == 'ADD_CONTEXT'
    dash = act(action(last_agent(result['dashboard']), 'Tallenna')['id'])
    update = last_agent(dash)
    assert update['text'].startswith('Uusi tieto täydensi seurantaasi. Tämä ei ole diagnoosi, mutta ammattilaisen arvio voi olla perusteltu.')
    assert [r['id'] for r in update['basis']['rules']] == ['RULE-LDLR-LDL-HIGH-001', 'RULE-LDLR-FAMHX-002']
    assert dash['companion']['knowledge']['missingInformation'] == [
        'Aiemmat LDL-tulokset vertailua varten',
        'Ammattilaisen tekemä vahvistus löydökselle (nyt vain synteettinen demovahvistus)',
    ]
    log = dash['companion']['chatLog'][0]
    assert log['userConfirmation'] == 'YES'
    assert any(r['id'] == 'RULE-LDLR-FAMHX-002' and r['triggered'] for r in log['ruleApplied'])
    assert log['finalState'] == 'professional_review_recommended'

    ask = last_agent(say('Tee tästä yhteenveto lääkärille.')['dashboard'])
    dash = act(action(ask, 'Muodosta yhteenveto')['id'])
    ready = last_agent(dash)
    assert ready['kind'] == 'summary_ready'
    summary = client.get('/api/loop/observations/obs-0001/summary').json()
    assert summary['userConfirmedFamilyHistory'][0]['structuredData']['relation'] == 'father'
    assert dash['tasks'][0]['dueAt'] == '2026-10-01'

    dash = client.post('/api/loop/demo/advance-time', json={'days': 30}).json()['dashboard']
    due = last_agent(dash)
    assert due['initiatedByAgent'] and 'Onko asia jo käsitelty ammattilaisen kanssa?' in due['text']
    dash = act(action(due, 'Kyllä')['id'])
    assert dash['observations'][0]['status'] == 'resolved'
    assert dash['counts']['openObservations'] == 0
    assert all(check_text(m['text'])['passed'] for m in agent_messages(dash) if m['textSource'] != 'fixed')


def test_demo_reset_restores_initial_state():
    initial = state()
    add_high_ldl()
    act(action(last_agent(say('Isäni sai sydäninfarktin 49-vuotiaana.')['dashboard']), 'Tallenna')['id'])
    client.post('/api/loop/demo/advance-time', json={'days': 30})

    reset = client.post('/api/loop/demo/reset').json()['dashboard']
    assert reset['currentDate'] == initial['currentDate']
    assert [e['id'] for e in reset['events']] == [e['id'] for e in initial['events']]
    assert reset['observations'] == [] and reset['tasks'] == []
    assert reset['monitorings'][0]['status'] == 'monitoring'
    assert [m['kind'] for m in reset['companion']['messages']] == ['greeting']
    assert reset['companion']['knowledge'] == initial['companion']['knowledge']
    assert reset['companion']['chatLog'] == []


@pytest.mark.parametrize('text, expected', [
    ('Mihin asioihin minun tulisi kiinnittää huomiota?', 'HEALTH_OVERVIEW'),
    ('Mihin minun kannattaa kiinnittää erityistä huomiota?', 'HEALTH_OVERVIEW'),
    ('Miksi tämä huomio syntyi?', 'EXPLAIN_OBSERVATION'),
    ('Kerro avoimesta huomiosta', 'EXPLAIN_OBSERVATION'),
])
def test_everyday_huomio_is_not_an_observation_question(text, expected):
    from app.loop.intent import keyword_intent
    assert keyword_intent(text, False) == expected


# --- 7. automated assessment of the need for care and its urgency (terveydenhuoltolaki 51 § 3 mom., assumed 2027) ---

SYMPTOM_REPORT = 'Minulla on ollut pari päivää päänsärkyä ja huimausta, pitäisikö mennä lääkäriin?'


def approve_bp() -> dict:
    plan_id = next(p['id'] for p in state()['support']['plans'] if p['theme'] == 'blood_pressure')
    response = client.post(f'/api/support/plans/{plan_id}/decision', json={'decision': 'approve', 'role': 'nurse'})
    assert response.status_code == 200, response.text
    return response.json()['dashboard']


def assessments(dash: dict) -> list[dict]:
    return dash['support']['assessments']  # newest first


@pytest.mark.parametrize('text, expected', [
    (SYMPTOM_REPORT, 'CARE_NEED_ASSESSMENT'),
    ('Onko tämä kiireellistä?', 'CARE_NEED_ASSESSMENT'),
    ('Minulla on ollut selkäkipua viikon.', 'CARE_NEED_ASSESSMENT'),
    ('Tarvitsenko lääkäriä?', 'CARE_NEED_ASSESSMENT'),
    ('Haluan ammattilaisen tekemän arvion.', 'HUMAN_ASSESSMENT_REQUEST'),
    ('haluan ammattilaisen arvion', 'HUMAN_ASSESSMENT_REQUEST'),
    ('Haluan puhua hoitajan kanssa.', 'HUMAN_ASSESSMENT_REQUEST'),
    ('Pyydän ammattilaisen arviota.', 'HUMAN_ASSESSMENT_REQUEST'),
    # emergencies and the other safety intents keep precedence
    ('Minulla on kova rintakipu ja päänsärkyä.', 'EMERGENCY_OR_URGENT'),
    ('Minulla on voimakas päänsärky.', 'EMERGENCY_OR_URGENT'),
    ('Tarvitsenko lääkettä?', 'MEDICATION_CHANGE_REQUEST'),
    # a doctor is not a medicine, and a relative's history is context, not the user's symptom
    ('Tee tästä yhteenveto lääkärille.', 'CREATE_SUMMARY'),
    ('Isäni sai sydäninfarktin 49-vuotiaana.', 'ADD_CONTEXT'),
])
def test_care_need_intents_are_deterministic(text, expected):
    from app.loop.intent import classify
    assert classify(text)[0] == expected


def test_symptom_report_in_chat_makes_an_automated_assessment_and_routes_it():
    approve_bp()
    result = say(SYMPTOM_REPORT)
    assert result['intent'] == 'CARE_NEED_ASSESSMENT' and result['intentMethod'] == 'deterministic_care_need_rules'
    dash = result['dashboard']
    messages = dash['companion']['messages']
    assert messages[-2]['role'] == 'user' and messages[-2]['text'] == SYMPTOM_REPORT  # the user's message is recorded first
    reply = last_agent(dash)
    assert reply['kind'] == 'care_assessment' and reply['textSource'] == 'template' and reply['intent'] == 'CARE_NEED_ASSESSMENT'
    assert 'Automaattinen hoidon tarpeen arvio: Kiirevastaanotto 3 arkipäivän kuluessa.' in reply['text']
    assert check_text(reply['text'], allowed_urgency='within_3_days')['passed']
    assert reply['basis']['decisionBy'] == 'Sääntömoottori – automaattinen hoidon tarpeen arvio'
    assert [a['type'] for a in reply['actions']] == ['request_human_assessment', 'dismiss']

    assessment = assessments(dash)[0]
    assert assessment['trigger'] == 'symptom_report' and assessment['urgency'] == 'within_3_days' and assessment['mode'] == 'automated'
    assert assessment['llmUsed'] is False and reply['assessment']['id'] == assessment['id']
    escalation = dash['support']['escalations'][0]
    assert escalation['assessmentId'] == assessment['id'] and escalation['status'] == 'open'
    assert escalation['urgencyLabel'] == 'Kiirevastaanotto 3 arkipäivän kuluessa'
    log = dash['companion']['chatLog'][0]
    assert log['intent'] == 'CARE_NEED_ASSESSMENT' and log['llmRole'] == 'none' and log['finalState'] == 'within_3_days'
    assert log['safetyCheck']['llmUsed'] is False


@pytest.mark.parametrize('text, urgency', [
    ('Minulla on kova päänsärky ja näköhäiriöitä.', 'same_day'),
    ('Minulla on ollut huimausta.', 'within_3_days'),
    ('Minulla on ollut selkäkipua viikon.', 'routine'),
    ('Onko tämä kiireellistä?', 'self_care'),
])
def test_symptom_classes_come_from_the_policy_table(text, urgency):
    # without an active plan nothing is routed: the reply names the service contact instead
    dash = say(text)['dashboard']
    assessment = assessments(dash)[0]
    assert assessment['urgency'] == urgency and assessment['trigger'] == 'symptom_report'
    assert dash['support']['escalations'] == []
    reply = last_agent(dash)
    assert reply['kind'] == 'care_assessment' and reply['assessment']['urgency'] == urgency
    assert check_text(reply['text'], allowed_urgency=urgency)['passed']


def test_human_assessment_request_in_chat_uses_the_latest_open_assessment():
    approve_bp()
    dash = say(SYMPTOM_REPORT)['dashboard']
    assessment_id = assessments(dash)[0]['id']
    result = say('Haluan ammattilaisen arvion.')
    assert result['intent'] == 'HUMAN_ASSESSMENT_REQUEST'
    dash = result['dashboard']
    assessment = next(a for a in assessments(dash) if a['id'] == assessment_id)
    assert assessment['status'] == 'human_review_requested' and assessment['humanReviewRequestedAt'] == dash['currentDate']
    reply = last_agent(dash)
    assert reply['kind'] == 'assessment_notice' and reply['intent'] == 'HUMAN_ASSESSMENT_REQUEST'
    assert reply['text'] == ('Selvä. Pyysit ammattilaisen tekemän arvion: hoitajasi tekee sen 3 arkipäivän kuluessa ja ottaa sinuun '
                             'yhteyttä. Automaattinen arvio (Kiirevastaanotto 3 arkipäivän kuluessa) jää taustatiedoksi.')
    assert dash['support']['escalations'][0]['humanReviewRequested'] is True
    # the button on the assessment message can no longer be used
    care = next(m for m in agent_messages(dash) if m['kind'] == 'care_assessment')
    assert action(care, 'Pyydä ammattilaisen arvio')['used'] is True
    # asking again does not create a second request
    again = last_agent(say('Haluan ammattilaisen tekemän arvion.')['dashboard'])
    assert again['text'].startswith('Olet jo pyytänyt ammattilaisen tekemän arvion')
    assert len(assessments(state())) == 1


def test_human_assessment_button_in_chat():
    approve_bp()
    care = last_agent(say(SYMPTOM_REPORT)['dashboard'])
    button = action(care, 'Pyydä ammattilaisen arvio')
    dash = act(button['id'])
    assert assessments(dash)[0]['status'] == 'human_review_requested'
    assert last_agent(dash)['text'].startswith('Selvä. Pyysit ammattilaisen tekemän arvion')
    assert dash['companion']['messages'][-2]['text'] == 'Pyydä ammattilaisen arvio'
    assert dash['companion']['chatLog'][0]['intent'] == 'HUMAN_ASSESSMENT_REQUEST'
    replay = client.post(f"/api/loop/companion/actions/{button['id']}", json={'args': {}})
    assert replay.status_code == 400


def test_human_assessment_request_without_an_assessment_routes_through_the_plan_rule():
    approve_bp()
    dash = say('Haluan ammattilaisen tekemän arvion.')['dashboard']
    assessment = assessments(dash)[0]
    assert assessment['trigger'] == 'user_request' and assessment['status'] == 'human_review_requested'
    assert assessment['rulesApplied'][0]['id'] == 'ESC-USER-001'
    escalation = dash['support']['escalations'][0]
    assert escalation['assessmentId'] == assessment['id'] and escalation['trigger'] == 'user_request' and escalation['humanReviewRequested']
    assert last_agent(dash)['text'].startswith('Selvä. Pyysit ammattilaisen tekemän arvion: hoitajasi tekee sen')


def test_human_assessment_request_routes_through_another_active_plan():
    # the blood-pressure plan is still waiting for approval; the active lipid plan has a user_request rule
    dash = say('Haluan puhua lääkärin kanssa.')['dashboard']
    assessment = assessments(dash)[0]
    assert assessment['trigger'] == 'user_request' and assessment['rulesApplied'][0]['id'] == 'ESC-GEN-USER'
    assert dash['support']['escalations'][0]['assessmentId'] == assessment['id']
    assert last_agent(dash)['text'].startswith('Selvä. Pyysit ammattilaisen tekemän arvion: lääkärisi tekee sen')


def test_human_assessment_request_without_a_plan_names_the_service_contact():
    from app.loop import store

    with store.transaction() as loop_state:
        for support_plan in loop_state.support.plans:
            support_plan.status = 'paused'
    dash = say('Haluan ammattilaisen tekemän arvion.')['dashboard']
    reply = last_agent(dash)
    assert reply['textSource'] == 'fixed'
    assert reply['text'].startswith('Sinulla on aina oikeus terveydenhuollon ammattihenkilön tekemään arvioon.')
    assert assessments(dash) == [] and dash['support']['escalations'] == []
    assert check_text(reply['text'])['passed']


def test_emergency_is_fixed_and_recorded_as_excluded_from_the_automated_assessment(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')

    def must_not_be_called(*args, **kwargs):
        raise AssertionError('LLM must not be used for urgent symptoms')

    monkeypatch.setattr(llm, '_call', must_not_be_called)
    approve_bp()
    result = say('Minulla on kova rintakipu ja hengitysvaikeuksia.')
    assert result['intent'] == 'EMERGENCY_OR_URGENT'
    dash = result['dashboard']
    reply = last_agent(dash)
    assert reply['kind'] == 'emergency' and reply['textSource'] == 'fixed'
    assert 'hätänumeroon 112' in reply['text']
    assert 'Hätätilanne ei kuulu automaattisen hoidon tarpeen arvion piiriin: soita 112 tai Päivystysapuun 116 117.' in reply['text']
    assessment = assessments(dash)[0]
    assert assessment['mode'] == 'excluded_emergency' and assessment['urgency'] == 'emergency'
    assert assessment['trigger'] == 'symptom_report' and assessment['llmUsed'] is False and assessment['canRequestHuman'] is False
    assert assessment['rulesApplied'][0]['id'] == 'TRI-EMERG-001' and 'rintakipu' in assessment['symptoms']
    assert reply['assessment']['urgency'] == 'emergency'
    assert dash['support']['escalations'] == []  # never routed as an automated assessment: 112
    # the right to a professional's assessment does not pick the excluded emergency
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'off')
    assert say('Haluan ammattilaisen tekemän arvion.')['dashboard']['support']['assessments'][0]['trigger'] == 'user_request'


def test_emergency_class_from_the_symptom_table_uses_the_fixed_path():
    from app.loop import companion, store

    loop_state = store.load_state()
    result = companion._care_need_assessment(loop_state, 'Minulla on rintakipua.')
    assert result['intentOverride'] == 'EMERGENCY_OR_URGENT' and result['textSource'] == 'fixed'
    assert loop_state.chatMessages[-1].kind == 'emergency'
    assert loop_state.support.assessments[-1].mode == 'excluded_emergency'


def test_symptom_report_without_consent_is_a_preliminary_assessment():
    approve_bp()
    response = client.put('/api/support/consent', json={'automatedAssessment': False})
    assert response.status_code == 200, response.text
    dash = say(SYMPTOM_REPORT)['dashboard']
    assessment = assessments(dash)[0]
    assert assessment['mode'] == 'professional_required' and assessment['urgency'] == 'within_3_days'
    reply = last_agent(dash)
    assert reply['kind'] == 'care_assessment' and 'Esiarvio' in reply['text']
    assert check_text(reply['text'], allowed_urgency='within_3_days')['passed']
    assert dash['support']['escalations'][0]['assessmentId'] == assessment['id']


def test_llm_cannot_change_the_urgency_class(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    # the LLM would call it something else and draft an escalation summary that invents another class
    monkeypatch.setattr(llm, 'classify_intent', lambda text, intents: 'GENERAL_HEALTH_QUESTION')
    monkeypatch.setattr(llm, '_call', lambda *a, **k: 'Tilanne on hätätilanne, asiakas on ohjattava heti päivystykseen.')
    approve_bp()
    result = say(SYMPTOM_REPORT)
    assert result['intent'] == 'CARE_NEED_ASSESSMENT' and result['intentMethod'] == 'deterministic_care_need_rules'
    dash = result['dashboard']
    assessment = assessments(dash)[0]
    assert assessment['urgency'] == 'within_3_days' and assessment['llmUsed'] is False
    escalation = dash['support']['escalations'][0]
    assert escalation['urgencyLabel'] == 'Kiirevastaanotto 3 arkipäivän kuluessa'
    assert escalation['summarySource'] == 'template' and 'hätätilanne' not in escalation['summaryText']
    assert last_agent(dash)['textSource'] == 'template'


def test_llm_intent_for_an_assessment_still_gets_the_class_from_the_rules(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    monkeypatch.setattr(llm, 'classify_intent', lambda text, intents: 'CARE_NEED_ASSESSMENT')

    def must_not_be_called(*args, **kwargs):
        raise AssertionError('the chat must not ask the LLM for an urgency class or a reply')

    monkeypatch.setattr(llm, '_call', must_not_be_called)
    result = say('Minulla on ollut outo olo.')
    assert result['intent'] == 'CARE_NEED_ASSESSMENT' and result['intentMethod'] == 'llm'
    assessment = assessments(result['dashboard'])[0]
    assert assessment['urgency'] == 'self_care' and assessment['rulesApplied'][0]['id'] == 'TRI-SELF-005'


def test_get_status_mentions_the_latest_assessment():
    dash = say('Minulla on ollut selkäkipua viikon.')['dashboard']
    assert assessments(dash)[0]['urgency'] == 'routine'
    text = last_agent(say('Mikä on tilanteeni?')['dashboard'])['text']
    assert 'Ei mitään akuuttia' in text
    assert 'Viimeisin automaattinen arvio: Kiireetön (1.9.2026); ammattilaisen arvion voi pyytää.' in text

    say('Minulla on ollut huimausta.')
    text = last_agent(say('Mikä on tilanteeni?')['dashboard'])['text']
    assert 'Huomioitavaa nyt:' in text
    assert '• Viimeisin automaattinen arvio: Kiirevastaanotto 3 arkipäivän kuluessa (1.9.2026); ammattilaisen arvion voi pyytää.' in text


def test_chat_texts_state_the_automated_assessment_and_pass_the_safety_check():
    from app.loop import companion_texts as texts

    assert texts.GREETING.endswith('Voit myös kuvata oireesi, niin teen hoidon tarpeen ja kiireellisyyden arvion automaattisesti – '
                                   'ja voit aina pyytää ammattilaisen tekemän arvion.')
    assert texts.WHY_NOW_DISCLAIMER == ('Tämä ei ole diagnoosi tai hoitosuositus. Hyvinvointikumppani tekee hoidon tarpeen arvion '
                                        'automaattisesti; diagnoosit ja hoitopäätökset tekee ammattilainen.')
    assert texts.DIAGNOSIS_END == ('Diagnoosin tekee terveydenhuollon ammattilainen. Voin kuitenkin tehdä hoidon tarpeen ja '
                                   'kiireellisyyden arvion, jos kuvaat oireesi.')
    assert texts.STATUS_NOTE == ('Tämä on yhteenveto tallennetuista tiedoistasi. Jos haluat hoidon tarpeen arvion, kuvaa oireesi; '
                                 'ammattilaisen arvion voi aina pyytää.')
    assert '112' in texts.EMERGENCY and 'hätänumeroon 112' in texts.EMERGENCY
    assert '112' in texts.EMERGENCY_NOTE and '116 117' in texts.EMERGENCY_NOTE
    assert texts.STATUS_LABELS['professional_review_recommended'] == 'ammattilaisen arvio suositeltu (perimätieto)'
    for text in (texts.GREETING, texts.WHY_NOW_DISCLAIMER, texts.DIAGNOSIS_END, texts.STATUS_NOTE, texts.GENERAL,
                 texts.HUMAN_REVIEW_ALREADY, texts.HUMAN_REVIEW_SERVICE_CONTACT, texts.HUMAN_REVIEW_CHAT_REASON):
        assert check_text(text)['passed'], text
    for urgency, label in (('routine', 'Kiireetön'), ('within_3_days', 'Kiirevastaanotto 3 arkipäivän kuluessa'),
                           ('same_day', 'Kiireellinen – samana päivänä')):
        line = texts.STATUS_LATEST_ASSESSMENT.format(label=label, date='1.9.2026')
        assert check_text(line, allowed_urgency=urgency)['passed'], line
    # with a class, other urgency wording is still blocked
    assert not check_text('Viimeisin automaattinen arvio: Kiireetön. Hakeudu kiireesti päivystykseen.', allowed_urgency='routine')['passed']


def test_llm_prompts_restate_the_rule_based_class():
    assert 'älä arvioi kiireellisyyttä' not in llm._SYSTEM_PROMPT
    assert ('Kiireellisyysluokka tulee aina sääntöpohjaisesta arviosta ja annetaan syötteessä; toista se sellaisenaan, '
            'älä muuta äläkä arvioi sitä itse.') in llm._SYSTEM_PROMPT


def test_escalation_summary_prompt_carries_the_label_verbatim(monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    prompts: list[str] = []
    monkeypatch.setattr(llm, '_call', lambda prompt, output_schema=None: prompts.append(prompt) or None)
    llm.draft_escalation_summary({'plan': 'Verenpaineen omaseuranta', 'urgencyLabel': 'Kiirevastaanotto 3 arkipäivän kuluessa'})
    assert 'kiireellisyysluokka on "Kiirevastaanotto 3 arkipäivän kuluessa"' in prompts[0]
    assert 'sanasta sanaan' in prompts[0]
