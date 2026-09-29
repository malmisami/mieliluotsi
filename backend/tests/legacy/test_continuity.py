"""The self-care continuity engine: 1 remember, 2 reach out on its own, 3 one step at a time, 4 notice when self-care is
not enough. Rules and templates only; the LLM makes no decisions."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.loop import companion_texts, llm
from app.loop.safety import check_text
from app.legacy_api import legacy_app as app
from app.support import continuity, texts

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_STATE_PATH', str(tmp_path / 'state.json'))
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'off')
    client.post('/api/loop/demo/reset')


def ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()['dashboard']


def state() -> dict:
    return client.get('/api/loop/state').json()


def plan(dash: dict, theme: str = 'blood_pressure') -> dict:
    return next(p for p in dash['support']['plans'] if p['theme'] == theme)


def engine(dash: dict) -> dict:
    return dash['support']['continuity']


def section(dash: dict, key: str) -> list[dict]:
    return next(s for s in engine(dash)['memory']['sections'] if s['key'] == key)['items']


def direction(dash: dict, theme: str = 'blood_pressure') -> dict:
    return next(d for d in engine(dash)['directions'] if d['planId'] == plan(dash, theme)['id'])


def agent_messages(dash: dict) -> list[dict]:
    return [m for m in dash['companion']['messages'] if m['role'] == 'agent']


def approve_bp() -> dict:
    return ok(client.post(f"/api/support/plans/{plan(state())['id']}/decision", json={'decision': 'approve', 'role': 'nurse'}))


def answer_all(answers: dict[str, str]) -> dict:
    dash = state()
    for _ in range(10):
        if not dash['support']['openCheckIns']:
            return dash
        checkin = dash['support']['openCheckIns'][0]
        question = next(q for q in checkin['questions'] if not q['answer'] and not q['skipped'])
        if question['kind'] in answers:
            body = {'questionId': question['id'], 'optionId': answers[question['kind']]}
        else:
            body = {'questionId': question['id'], 'skip': True} if question['optional'] else {'questionId': question['id'], 'optionId': question['options'][0]['id']}
        dash = ok(client.post(f"/api/support/checkins/{checkin['id']}/answer", json=body))
    raise AssertionError('check-in did not complete')


def week_one_and_rising_readings() -> dict:
    """Demo story up to the agent's own contact: week 1 (step not met, smaller step) and two higher home readings."""
    approve_bp()
    ok(client.post('/api/support/simulate/week'))
    answer_all({'goal_progress': 'none', 'barrier': 'time', 'smaller_goal': 'accept', 'measurement_status': 'no_time'})
    ok(client.post('/api/support/simulate/measurement'))
    return ok(client.post('/api/support/simulate/measurement'))


def say(text: str) -> dict:
    response = client.post('/api/loop/companion/messages', json={'text': text})
    assert response.status_code == 200, response.text
    return response.json()


# --- 1 remember --------------------------------------------------------------------------------------------------------

def test_memory_collects_goals_agreements_follow_up_history_and_rechecks():
    dash = state()
    goals = section(dash, 'goals')
    assert [g['text'] for g in goals][:2] == ['Kotimittausten keskiarvo alle 135/85 mmHg', 'Liikunta: kaksi 30 minuutin kävelyä viikossa']
    assert all(g['pending'] and g['source'] == 'Ehdotus – odottaa hoitajasi hyväksyntää' for g in goals[:2])
    agreed = {i['text']: i for i in section(dash, 'agreed')}
    # what was agreed at the nurse's visit is read from the record, not typed in again
    assert agreed['Omahoidon tavoitteeksi sovittiin kaksi 30 minuutin kävelyä viikossa']['source'] == 'Sairaanhoitaja, kirjaus 20.8.2026'
    assert 'Kotimittaukset sovittu tehtäväksi kahdesti viikossa' in agreed and 'Asiakas toivoo muistutuksia sovelluksen kautta' in agreed
    assert 'Kolesteroliarvojen seuranta, versio 1' in agreed
    works = section(dash, 'works')
    assert works[0]['text'] == 'LDL-arvo laskenut ruokavaliomuutosten jälkeen' and works[0]['tone'] == 'positive'
    assert any(w['tone'] == 'barrier' and 'kiireistä' in w['text'] for w in works)
    tried = [t['text'] for t in section(dash, 'tried')]
    assert tried == ['Elintapaohjaus', 'Suositeltu kotimittauksia ja laboratoriokontrollia terveysasemalla',
                     'Ruokavalio-ohjaus, kontrolli seuraavassa tarkastuksessa', 'Keskusteltu ruokavaliosta ja liikunnasta']
    recheck = section(dash, 'recheck')
    assert [(r['text'], r['date']) for r in recheck] == [('LDL-kolesterolin laboratoriokontrolli', '2026-11-12'),
                                                          ('Kontrolli noin kolmen kuukauden kuluttua', None)]
    monitor = [m['text'] for m in section(dash, 'monitor')]
    assert monitor == ['Verenpaine kotona kaksi kertaa viikossa', 'LDL-kolesteroli laboratoriossa']
    # genetic, medication and diagnosis wording never enters the memory, and gene names stay hidden
    payload = json.dumps(engine(dash)['memory'], ensure_ascii=False)
    for secret in ('LDLR', 'Perimätiedon', 'lääkity', 'Todettu'):
        assert secret not in payload


def test_memory_reads_the_notes_only_with_consent():
    dash = ok(client.put('/api/support/consent', json={'dataSources': {'professionalNotes': False}}))
    memory = engine(dash)['memory']
    assert memory['notesAllowed'] is False and memory['notesNotice'] == texts.MEMORY_NOTES_OFF
    assert not [i for s in memory['sections'] for i in s['items'] if i['origin'] == 'record']
    assert section(dash, 'goals')  # the plans themselves are still remembered


@pytest.mark.parametrize('clause, kind', [
    ('Omahoidon tavoitteeksi sovittiin kaksi 30 minuutin kävelyä viikossa', 'agreed'),
    ('LDL-arvo laskenut ruokavaliomuutosten jälkeen', 'works'),
    ('Asiakas kertoo työn olleen kiireistä', 'barrier'),
    ('Ruokavalio-ohjaus, kontrolli seuraavassa tarkastuksessa', 'tried'),
    ('Kontrolli noin kolmen kuukauden kuluttua', 'recheck'),
    ('Perimätiedon havainto kirjataan taustatiedoksi', None),
    ('Laboratoriotutkimukset ja lääkityksen tarpeen arvio seuraavalla käynnillä', None),
    ('Verenpaine 128/82 mmHg', None),
])
def test_note_clauses_are_read_with_documented_rules(clause, kind):
    assert continuity.classify_clause(clause) == kind


# --- 3 one step at a time ------------------------------------------------------------------------------------------------

def test_the_first_step_is_one_realistic_thing_for_seven_days():
    dash = approve_bp()
    message = agent_messages(dash)[-1]['text']
    assert 'Kokeillaan seuraavat 7 päivää yhtä asiaa: 30 minuutin kävely kaksi kertaa.' in message
    assert 'Kysyn 8.9.2026, miten meni.' in message
    step = engine(dash)['step']
    assert step['text'] == '30 minuutin kävely kaksi kertaa' and step['stage'] == 'action' and step['day'] == 1 and step['days'] == 7
    assert step['feedbackAt'] == '2026-09-08' and step['range'].startswith('1–3 kertaa viikossa')
    assert [s['label'] for s in step['loop']] == ['Tavoite', 'Teko', 'Palaute', 'Mukautus', 'Uusi teko']
    assert [s['state'] for s in step['loop']] == ['done', 'current', 'upcoming', 'upcoming', 'upcoming']


def test_a_step_that_worked_grows_a_little_but_never_past_the_professional_range():
    approve_bp()
    dash = ok(client.post('/api/support/simulate/week'))
    assert engine(dash)['step']['stage'] == 'feedback'
    dash = answer_all({'goal_progress': 'met', 'step_up': 'accept'})
    bp = plan(dash)
    checkin = bp['checkIns'][0]
    step_up = next(q for q in checkin['questions'] if q['kind'] == 'step_up')
    assert step_up['text'] == 'Hienoa! Kokeillaanko seuraavat 7 päivää hieman enemmän: 30 minuutin kävely kolme kertaa?'
    assert 'enintään kolme kertaa viikossa' in step_up['whyAsked']
    assert bp['goal']['label'] == 'kolme 30 minuutin kävelyä viikossa' and bp['goal']['setBy'] == 'agent_with_user' and bp['version'] == 1
    closing = agent_messages(dash)[-1]['text']
    assert 'Hienoa, että askel toteutui. Seuraavat 7 päivää kokeillaan: 30 minuutin kävely kolme kertaa.' in closing
    rounds = engine(dash)['step']['rounds']
    assert rounds[0]['feedback'] == 'met' and rounds[0]['adaptation'] == 'bigger'
    assert any(w['text'] == '30 minuutin kävely kaksi kertaa onnistui' for w in section(dash, 'works'))
    assert direction(dash)['key'] == 'continue' and 'Viime kierroksen askel toteutui.' in direction(dash)['reasons']
    # at the professional's maximum the step stays the same
    ok(client.post('/api/support/simulate/week'))
    dash = answer_all({'goal_progress': 'met'})
    checkin = plan(dash)['checkIns'][0]
    assert 'step_up' not in [q['kind'] for q in checkin['questions']] and checkin['outcome']['goalProposalSkipped'] == 'at_maximum'
    assert 'Pidetään nykyinen askel: 30 minuutin kävely kolme kertaa.' in agent_messages(dash)[-1]['text']


def test_a_step_that_did_not_work_becomes_smaller_and_the_direction_turns_to_adjust():
    approve_bp()
    ok(client.post('/api/support/simulate/week'))
    dash = answer_all({'goal_progress': 'none', 'barrier': 'time', 'smaller_goal': 'accept'})
    step = engine(dash)['step']
    assert step['text'] == '20 minuutin kävely kerran' and step['setBy'] == 'agent_with_user'
    assert step['rounds'][0]['adaptation'] == 'smaller' and step['rounds'][0]['barrier'] == 'Aika tai kiire'
    info = direction(dash)
    assert info['key'] == 'adjust' and info['label'] == 'Muutetaan suunnitelmaa'
    assert info['reasons'] == ['Viime kierroksen askel ei toteutunut (este: aika tai kiire), joten askelta mukautettiin.']
    tried = section(dash, 'tried')[0]
    assert tried['text'] == '30 minuutin kävely kaksi kertaa' and tried['detail'] == 'Ei tällä kertaa, este: aika tai kiire'


# --- 2 reach out on its own ------------------------------------------------------------------------------------------------

def test_the_agent_offers_three_day_home_monitoring_when_the_readings_rise():
    dash = week_one_and_rising_readings()
    offer = agent_messages(dash)[-1]
    assert offer['kind'] == 'outreach_offer' and offer['initiatedByAgent'] is True
    assert offer['text'] == ('Verenpaineesi on ollut viime viikkoina hieman aiempaa korkeampi: kotimittausten keskiarvo 137/88 mmHg, '
                             'aiemmin 132/84 mmHg. Haluaisitko tehdä tällä viikolla kolmen päivän kotiseurannan? Mittaisit aamulla ja '
                             'illalla, ja kokoan tuloksista yhteenvedon.')
    assert [(a['label'], a['type']) for a in offer['actions']] == [('Kyllä, aloitetaan', 'home_monitoring_accept'),
                                                                     ('Ei tällä viikolla', 'home_monitoring_decline')]
    assert offer['basis']['rules'][0]['id'] == 'OUT-BP-001' and check_text(offer['text'])['passed']
    support = dash['support']
    assert support['contacts'] if 'contacts' in support else True
    assert support['situation']['nextStep']['kind'] == 'answer_offer'
    assert support['situation']['nextStep']['title'] == 'Vastaa ehdotukseen: kolmen päivän kotiseuranta'
    assert engine(dash)['outreach']['offer']['reason'].startswith('Kotimittausten keskiarvo on noussut: 132/84 → 137/88 mmHg')
    assert engine(dash)['outreach']['recent'][0]['kind'] == 'home_monitoring_offer'
    assert 'Ehdotin kolmen päivän kotiseurantaa.' in direction(dash)['reasons'] and direction(dash)['key'] == 'adjust'
    # the outreach is its own chain in Agentin toiminta: signal -> the agent's own contact
    entries = support['audit']['entries']
    act = next(e for e in entries if e['action'] == 'offer_home_monitoring' and e['stage'] == 'act')
    chain = next(c for c in support['audit']['chains'] if c['id'] == act['chainId'])
    assert chain['flow'][0]['text'].startswith('Havaitut signaalit: Mittausten trendi nousussa.')
    assert chain['flow'][1]['text'].startswith('Agentti otti itse yhteyttä ja ehdotti kolmen päivän kotiseurantaa (sääntö OUT-BP-001).')
    # no second offer while the first one is open
    dash = ok(client.post('/api/support/simulate/measurement'))
    assert sum(1 for m in agent_messages(dash) if m['kind'] == 'outreach_offer') == 1


def test_accepted_home_monitoring_is_summarised_with_the_plan_rules():
    dash = week_one_and_rising_readings()
    accept = next(a for a in agent_messages(dash)[-1]['actions'] if a['type'] == 'home_monitoring_accept')
    dash = ok(client.post(f"/api/loop/companion/actions/{accept['id']}", json={'args': {}}))
    started = agent_messages(dash)[-1]
    assert started['kind'] == 'home_monitoring' and started['text'].startswith('Hienoa, aloitetaan! Kotiseuranta 8.9.2026–10.9.2026')
    assert all(a['used'] for a in next(m for m in agent_messages(dash) if m['kind'] == 'outreach_offer')['actions'])
    assert dash['support']['situation']['nextStep']['title'] == 'Kotiseuranta: mittaa aamulla ja illalla (0/6 mittausta)'
    assert section(dash, 'monitor')[0]['text'] == 'Kotiseuranta 8.9.2026–10.9.2026 aamulla ja illalla'
    dash = ok(client.post('/api/support/simulate/home-monitoring'))
    assert dash['currentDate'] == '2026-09-10'
    result = agent_messages(dash)[-1]
    assert result['kind'] == 'home_monitoring_result'
    assert result['text'].startswith('Kotiseuranta on valmis, kiitos! Keskiarvo 140/89 mmHg (6 mittausta) on hieman sovitun tavoitetason '
                                     'yläpuolella. Muutetaan suunnitelmaa pienesti hoitajasi hyväksymissä rajoissa')
    assert check_text(result['text'])['passed']
    latest = engine(dash)['homeMonitoring']['latest']
    assert latest['status'] == 'completed' and latest['result']['direction'] == 'adjust' and latest['readings'] == 6
    assert 'Kotiseurannan keskiarvo 140/89 mmHg oli sovitun tavoitetason yläpuolella.' in direction(dash)['reasons']
    assert section(dash, 'tried')[0]['text'] == '20 minuutin kävely kerran' or any(
        t['text'] == 'Kotiseuranta 8.9.2026–10.9.2026' for t in section(dash, 'tried'))
    assert not dash['support']['escalations']  # adapting inside the plan is enough here
    assert client.post('/api/support/simulate/home-monitoring').status_code == 400


def test_a_clearly_high_home_monitoring_average_brings_in_the_professional():
    dash = week_one_and_rising_readings()
    period_id = engine(dash)['outreach']['offer']['id']
    ok(client.post(f'/api/support/home-monitoring/{period_id}/respond', json={'accept': True}))
    for _ in range(6):
        dash = ok(client.post('/api/support/measurements', json={'systolic': 150, 'diastolic': 95}))
    escalation = dash['support']['escalations'][0]
    assert escalation['rulesApplied'][0]['id'] == 'ESC-BP-004' and escalation['urgencyLabel'] == 'Kiireetön'
    assessment = dash['support']['assessments'][0]
    assert assessment['trigger'] == 'rule' and assessment['urgency'] == 'routine' and assessment['escalationId'] == escalation['id']
    notice = agent_messages(dash)[-1]
    assert notice['kind'] == 'escalation_notice' and notice['text'].startswith('Kotiseuranta on valmis, kiitos! Keskiarvo 150/95 mmHg (6 mittausta).')
    assert 'kolmen päivän kotiseurannan keskiarvo oli suunnitelmassa sovitun rajan yläpuolella.' in notice['text']
    assert any(a['type'] == 'request_human_assessment' for a in notice['actions'])
    assert check_text(notice['text'], allowed_urgency='routine')['passed']
    info = direction(dash)
    assert info['key'] == 'professional' and info['label'] == 'Tarvitaan ammattilaista'
    assert 'Sääntö ESC-BP-004: Kotiseurannan keskiarvo selvästi tavoitetason yläpuolella.' in info['reasons']


def test_a_declined_offer_is_respected_and_not_repeated_right_away():
    dash = week_one_and_rising_readings()
    period_id = engine(dash)['outreach']['offer']['id']
    dash = ok(client.post(f'/api/support/home-monitoring/{period_id}/respond', json={'accept': False}))
    assert agent_messages(dash)[-1]['text'] == 'Selvä, ei tällä viikolla. Seuraan kotimittauksia tavalliseen tapaan ja kysyn kuulumisia 15.9.2026.'
    assert client.post(f'/api/support/home-monitoring/{period_id}/respond', json={'accept': True}).status_code == 400
    dash = ok(client.post('/api/support/simulate/measurement'))
    assert sum(1 for m in agent_messages(dash) if m['kind'] == 'outreach_offer') == 1
    assert client.post('/api/support/home-monitoring/hm-9999/respond', json={'accept': True}).status_code == 400


def test_an_unanswered_offer_expires_after_a_week():
    week_one_and_rising_readings()
    dash = ok(client.post('/api/support/simulate/week'))
    assert engine(dash)['outreach']['offer'] is None
    assert any(e['outcome'] == 'expired' for e in dash['support']['audit']['entries'])
    offer_message = next(m for m in agent_messages(dash) if m['kind'] == 'outreach_offer')
    assert all(a['used'] for a in offer_message['actions'])


def test_gate_3_applies_to_the_agents_own_contact():
    approve_bp()
    ok(client.post('/api/support/simulate/week'))
    answer_all({'goal_progress': 'none', 'barrier': 'time', 'smaller_goal': 'accept'})
    ok(client.put('/api/support/consent', json={'proactiveContact': False}))
    ok(client.post('/api/support/simulate/measurement'))
    dash = ok(client.post('/api/support/simulate/measurement'))
    assert not [m for m in agent_messages(dash) if m['kind'] == 'outreach_offer'] and engine(dash)['outreach']['offer'] is None
    deferred = next(e for e in dash['support']['audit']['entries'] if e['action'] == 'deferred')
    assert 'OUT-BP-001' in deferred['detail'] and 'portti 3' in deferred['detail']


# --- 4 notice when self-care is not enough ---------------------------------------------------------------------------------

def test_the_direction_follows_the_plan_rules_through_the_story():
    dash = state()
    assert direction(dash)['key'] == 'pending' and direction(dash, 'lipids')['key'] == 'continue'
    assert direction(dash, 'lipids')['reasons'] == ['Seuraava laboratoriokontrolli on 12.11.2026.']
    dash = approve_bp()
    assert direction(dash)['key'] == 'continue' and direction(dash)['reasons'] == ['Ensimmäinen askel on käynnissä.']
    watch = {w['label']: w for w in direction(dash)['watch']}
    assert watch['Kotimittausten keskiarvo']['ok'] is False and watch['Turvaraja']['ok'] is True
    when = [w['text'] for w in direction(dash)['professionalWhen']]
    assert 'pyydät itse ammattilaisen arviota tai yhteydenottoa' in when and 'yksittäinen kotimittaus on 180/110 mmHg tai korkeampi' in when
    # week 1: the step did not work -> change the plan; week 2: again, with the average above target -> a professional
    ok(client.post('/api/support/simulate/week'))
    answer_all({'goal_progress': 'none', 'barrier': 'time', 'smaller_goal': 'accept'})
    ok(client.post('/api/support/simulate/measurement'))
    ok(client.post('/api/support/simulate/measurement'))
    ok(client.post('/api/support/simulate/week'))
    dash = answer_all({'goal_progress': 'none', 'barrier': 'time'})
    assert direction(dash)['key'] == 'professional' and engine(dash)['direction']['key'] == 'professional'
    assert engine(dash)['step']['stage'] == 'adaptation'
    # the nurse updates the plan -> self-care continues with version 2
    dash = ok(client.post('/api/support/simulate/professional-decision'))
    info = direction(dash)
    assert info['key'] == 'continue' and info['reasons'] == ['Hoitajasi päivitti suunnitelman (versio 2).']
    # on a tie the plan with a step of its own comes first (the self-care in progress)
    assert engine(dash)['direction']['planId'] == plan(dash)['id']
    assert engine(dash)['step']['text'] == '10 minuutin taukoliikuntahetki kolme kertaa'
    assert engine(dash)['step']['setByLabel'].startswith('Sairaanhoitaja asetti')


# --- the chat is one interface to the same engine ------------------------------------------------------------------------

def test_the_chat_answers_memory_step_and_direction_from_the_rules(monkeypatch):
    result = say('Mitä olemme sopineet?')
    assert result['intent'] == 'SELF_CARE_MEMORY' and result['intentMethod'] == 'deterministic_continuity_rules'
    reply = agent_messages(result['dashboard'])[-1]
    assert reply['text'].startswith(texts.CHAT_MEMORY_INTRO) and reply['textSource'] == 'template'
    assert 'Sovittu ammattilaisen kanssa' in reply['text'] and 'Omahoidon tavoitteeksi sovittiin' in reply['text']
    assert reply['basis']['decisionBy'].startswith('Omahoidon muisti') and 'LDLR' not in reply['text']
    assert agent_messages(say('Mikä on seuraava askel?')['dashboard'])[-1]['text'] == texts.CHAT_STEP_NONE
    approve_bp()
    step = agent_messages(say('Mikä on tämän viikon askel?')['dashboard'])[-1]['text']
    assert step.startswith('Tämän viikon askel: 30 minuutin kävely kaksi kertaa (1.9.2026–7.9.2026). Kysyn 8.9.2026, miten meni.')
    result = say('Riittääkö omahoito?')
    assert result['intent'] == 'SELF_CARE_DIRECTION'
    text = agent_messages(result['dashboard'])[-1]['text']
    assert '• Verenpaineen omaseuranta: Jatketaan omahoitoa. Ensimmäinen askel on käynnissä.' in text
    assert texts.DIRECTION_PROFESSIONAL_WHEN in text and texts.RIGHTS_SENTENCE in text
    # the rules win over the LLM, and a symptom description still goes to the automated assessment
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    monkeypatch.setattr(llm, 'classify_intent', lambda text, intents: 'GENERAL_HEALTH_QUESTION')
    assert say('Mitä olen jo kokeillut?')['intent'] == 'SELF_CARE_MEMORY'
    assert say('Minulla on ollut huimausta, riittääkö omahoito?')['intent'] == 'CARE_NEED_ASSESSMENT'


def test_the_greeting_and_the_engine_texts_state_the_four_core_tasks_safely():
    greeting = companion_texts.GREETING
    for phrase in ('pidän omahoitosi käynnissä arjessa myös vastaanottojen välissä', 'Muistan puolestasi', 'otan itse yhteyttä',
                   'yhden realistisen askeleen kerrallaan', 'milloin omahoito ei enää riitä'):
        assert phrase in greeting
    dash = state()
    assert [t['title'] for t in engine(dash)['coreTasks']] == ['Muistan puolestasi', 'Otan itse yhteyttä', 'Yksi askel kerrallaan',
                                                                'Huomaan, milloin omahoito ei riitä']
    samples = [
        texts.HOME_MONITORING_OFFER.format(now='137/88', before='132/84', days='kolmen päivän'),
        texts.HOME_MONITORING_OFFER_ABOVE.format(now='137/88', days='kolmen päivän'),
        texts.HOME_MONITORING_STARTED.format(start='8.9.2026', end='10.9.2026', total=6, guide=''),
        texts.HOME_MONITORING_DECLINED.format(date='15.9.2026'), texts.HOME_MONITORING_EXPIRED,
        *[t.format(avg='140/89', n=6, total=6, owner='hoitajasi', date='15.9.2026', step='20 minuutin kävely kerran')
          for t in texts.HOME_MONITORING_RESULT.values()],
        texts.HOME_MONITORING_ALREADY_WITH_PROFESSIONAL, texts.CHAT_MEMORY_INTRO, texts.CHAT_MEMORY_NOTE, texts.CHAT_STEP_NONE,
        texts.CHAT_STEP.format(step='20 minuutin kävely kerran', start='8.9.2026', end='14.9.2026', feedback='15.9.2026', owner='hoitajasi'),
        texts.CHAT_DIRECTION_INTRO, texts.CHAT_DIRECTION_NOTE, texts.DIRECTION_PROFESSIONAL_WHEN, texts.PROFESSIONAL_WHEN_SYMPTOMS,
        *texts.MEMORY_EMPTY.values(), texts.MEMORY_NOTES_OFF,
        *[t.format(barrier='', delta='+5', days='kolmen päivän', n=2, total=6, avg='140/89', owner_cap='Hoitajasi', version=2,
                   date='12.11.2026', until='', label='Kiireetön', owner='hoitajasi', handling='5 arkipäivän kuluessa')
          for t in texts.DIRECTION_REASONS.values()],
        *[t.format(systolic=180, diastolic=110, days=21) for t in texts.PROFESSIONAL_WHEN.values()],
        *[t['text'] for t in engine(dash)['coreTasks']], engine(dash)['memory']['notice'],
    ]
    for sample in samples:
        assert check_text(sample)['passed'], sample
    joined = ' '.join(samples).lower()
    for forbidden in ('diagnoosi', 'sairastat', 'riski', 'dna-virhe'):
        assert forbidden not in joined
