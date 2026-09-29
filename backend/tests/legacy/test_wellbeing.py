"""Hyvinvointidata (Apple Health): personal baseline and change detection, the synthetic demo scenario, the sync API
of the HealthKit bridge, gate 3, observations tied to monitoring areas, the chat and the agent's compact context."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.loop import companion_texts, llm
from app.loop.safety import check_text
from app.legacy_api import legacy_app as app
from app.wellbeing import catalog, demo, texts, trends

client = TestClient(app)
WINDOWS = {'currentDays': 7, 'recentDays': 30, 'baselineDays': 90, 'baselineGapDays': 30, 'minBaselineValues': 14,
           'minCurrentValues': 4, 'sparseLookbackDays': 21}


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'LOOP_STATE_PATH', str(tmp_path / 'state.json'))
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'off')
    monkeypatch.setattr(settings, 'HEALTH_DEMO_MODE', 1)
    client.post('/api/loop/demo/reset')


def ok(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()


def summary(period: int = 30) -> dict:
    return ok(client.get(f'/api/health/summary?period={period}'))


def state() -> dict:
    return ok(client.get('/api/loop/state'))


def agent_messages(dash: dict) -> list[dict]:
    return [m for m in dash['companion']['messages'] if m['role'] == 'agent']


def paired_token() -> str:
    code = ok(client.post('/api/health/pairing-code'))['code']
    return ok(client.post('/api/health/devices/pair', json={'code': code, 'deviceName': 'Testi-iPhone'}))['deviceToken']


def sync(token: str, days: list[dict], **extra) -> object:
    return client.post('/api/health/sync', json={'source': 'apple_health', 'dailyMetrics': days, **extra},
                       headers={'Authorization': f'Bearer {token}'})


def flat_days(end: str, days: int, **values) -> list[dict]:
    return [{'date': trends.shift(end, -i), **values} for i in range(days)]


# --- personal baseline and change detection (pure functions) --------------------------------------------------------

def test_rolling_average_and_personal_baseline_leave_the_recent_month_out():
    series = [(trends.shift('2026-09-01', -i), 50.0 if i < 30 else 45.0) for i in range(150)][::-1]
    assert trends.calculate_rolling_average(series, '2026-09-01', 7)['value'] == 50.0
    baseline = trends.calculate_personal_baseline(series, '2026-09-01', WINDOWS, 'daily')
    assert baseline['value'] == 45.0 and baseline['n'] == 90 and baseline['partial'] is False  # days -120..-31
    short = series[-25:]  # a short history: the earlier days before the current week, marked partial
    partial = trends.calculate_personal_baseline(short, '2026-09-01', WINDOWS, 'daily')
    assert partial['partial'] is True and partial['n'] == 18
    assert trends.calculate_personal_baseline(series[-10:], '2026-09-01', WINDOWS, 'daily') is None  # too little history
    assert trends.calculate_current([], '2026-09-01', WINDOWS, 'daily') is None


def test_trend_and_weekly_means():
    rising = [(trends.shift('2026-09-01', -i), 60.0 - i * 0.5) for i in range(30)][::-1]
    assert trends.calculate_trend(rising, '2026-09-01', 30)['slopePerWeek'] == pytest.approx(3.5)
    assert trends.calculate_trend(rising[:5], '2026-09-01', 30) is None
    weekly = trends.weekly_means(rising)
    assert len(weekly) == 5 and weekly[-1][0] == '2026-09-01'


def test_detect_meaningful_change_uses_the_metric_thresholds_and_direction():
    rhr, sleep, weight = catalog.metric('restingHeartRate'), catalog.metric('sleepMinutes'), catalog.metric('weightKg')
    series = [('2026-08-30', 53.0), ('2026-08-31', 54.0), ('2026-09-01', 53.0)]
    change = trends.detect_meaningful_change(rhr, {'value': 53.0}, {'value': 47.0}, series)
    assert change['kind'] == 'concern' and change['direction'] == 'up' and change['delta'] == 6.0 and change['consecutiveDays'] == 3
    assert trends.detect_meaningful_change(rhr, {'value': 49.0}, {'value': 47.0}, series) is None  # under 3 bpm
    assert trends.detect_meaningful_change(sleep, {'value': 470.0}, {'value': 430.0}, [])['kind'] == 'positive'
    assert trends.detect_meaningful_change(weight, {'value': 64.5}, {'value': 62.0}, [])['kind'] == 'neutral'
    assert trends.detect_meaningful_change(rhr, None, {'value': 47.0}, series) is None


def test_values_are_formatted_in_their_own_units_without_percentages():
    assert catalog.format_value('sleepMinutes', 438) == '7 h 18 min'
    assert catalog.format_value('steps', 8421) == '8 421'
    assert catalog.format_value('weightKg', 62.14) == '62,1 kg'
    assert catalog.format_delta('restingHeartRate', 5.6) == '+6 bpm'
    assert catalog.format_delta('sleepMinutes', -41.2) == '−41 min/yö'
    assert catalog.format_delta('steps', -2209.5) == '−2 210 askelta/päivä'


# --- the synthetic demo scenario ---------------------------------------------------------------------------------------

def test_synthetic_data_is_deterministic_and_clearly_marked():
    rows = demo.generate('2026-09-01')
    assert len(rows) == 365 and rows[0]['date'] == '2025-09-02' and rows[-1]['date'] == '2026-09-01'
    assert rows == demo.generate('2026-09-01')
    ok(client.post('/api/health/demo/synthetic'))
    data = summary()
    assert data['connection']['status'] == 'connected' and data['connection']['synthetic'] is True
    assert data['connection']['sourceLabel'] == 'Synteettinen testidata (Apple Health -muotoinen)'
    assert data['dataRange'] == {'from': '2025-09-02', 'to': '2026-09-01', 'days': 365}
    assert [t['label'] for t in data['today']] == ['Askeleet', 'Uni', 'Leposyke', 'HRV']


def test_demo_mode_guards_the_synthetic_data(monkeypatch):
    monkeypatch.setattr(settings, 'HEALTH_DEMO_MODE', 0)
    assert client.post('/api/health/demo/synthetic').status_code == 403
    assert summary()['demoMode'] is False


def test_the_scenario_becomes_one_explainable_observation_of_the_monitored_area():
    result = ok(client.post('/api/health/demo/synthetic'))['result']
    assert result['created'] == 365 and len(result['observations']) == 1
    data = summary()
    changes = {c['metric']: c for c in data['changes']}
    assert {'restingHeartRate', 'hrvMs', 'sleepMinutes', 'steps'} <= set(changes)
    assert changes['restingHeartRate']['kind'] == 'concern' and changes['restingHeartRate']['area'] == 'Palautuminen'
    assert changes['steps']['area'] is None  # a change outside the monitoring areas is listed, but not raised
    observation = data['observations'][0]
    assert observation['title'] == 'Huomasin muutoksen' and observation['areaLabel'] == 'Palautuminen' and observation['priority'] == 'high'
    assert observation['summary'].startswith('Leposykkeesi on noussut omasta tasostasi: viimeisen 7 päivän keskiarvo 53 bpm, oma 90 päivän tasosi 47 bpm.')
    assert 'HRV on laskenut' in observation['summary'] and 'unen määrä on vähentynyt' in observation['summary']
    assert observation['areaNote'] == 'Nämä kuuluvat palautumisen seurantaasi.'
    why = observation['why']
    assert why['reason'] == 'Seuraat palautumistasi hyvinvointikumppanin kanssa.' and why['basis'] == 'Valitsit itse'
    assert [line['label'] for line in why['lines']] == ['Leposyke', 'HRV', 'Uni']
    assert why['lines'][0]['current'] == '53 bpm' and why['lines'][0]['baseline'] == '47 bpm'
    assert 'viimeiset' in (why['lines'][0]['consecutive'] or '') and why['rules'] and why['source'].startswith('Lähde: Synteettinen')
    # the agent raises it on its own in the chat (gate 3 allows), once
    dash = state()
    proactive = [m for m in agent_messages(dash) if m['kind'] == 'health_observation']
    assert len(proactive) == 1 and proactive[0]['initiatedByAgent'] is True
    assert [a['label'] for a in proactive[0]['actions']] == ['Selvitetään yhdessä', 'Ei nyt']
    assert dash['support']['wellbeing']['newObservations'] == 1
    # the same change is not raised again at the next synchronization
    ok(client.post('/api/health/sync-now'))
    assert len(summary()['observations']) == 1
    # every user-facing text passes the same safety check as the rest of the agent
    for text in (observation['summary'], observation['areaNote'], proactive[0]['text'], *why['rules'], why['period'],
                 *[c['text'] for c in data['changes']]):
        assert check_text(text)['passed'], text


def test_trends_follow_the_selected_period():
    ok(client.post('/api/health/demo/synthetic'))
    week, year = summary(7), summary(365)
    sleep = next(t for t in week['trends'] if t['metric'] == 'sleepMinutes')
    assert len(sleep['points']) == 7 and sleep['monitored'] is True and sleep['baseline'] is not None
    yearly = next(t for t in year['trends'] if t['metric'] == 'sleepMinutes')
    assert yearly['weekly'] is True and 50 <= len(yearly['points']) <= 53
    assert [t['monitored'] for t in week['trends']] == sorted([t['monitored'] for t in week['trends']], reverse=True)


def test_monitoring_areas_decide_what_the_agent_raises():
    ok(client.put('/api/health/monitoring', json={'areas': {'recovery': False}}))
    ok(client.post('/api/health/demo/synthetic'))
    assert summary()['observations'] == []  # the recovery change is not raised without the area
    ok(client.put('/api/health/monitoring', json={'areas': {'activity': True}}))
    observation = summary()['observations'][0]
    assert observation['areaId'] == 'activity' and observation['summary'].startswith('Askelmääräsi on vähentynyt omasta tasostasi')
    # a clinician-approved area cannot be switched off from here
    assert client.put('/api/health/monitoring', json={'areas': {'lipids': False}}).status_code == 400


# --- the sync API of the HealthKit bridge ----------------------------------------------------------------------------------

def test_pairing_and_idempotent_sync_from_the_iphone():
    assert client.post('/api/health/devices/pair', json={'code': '000000'}).status_code == 401  # no code created
    token = paired_token()
    data = summary()
    assert data['connection']['status'] == 'connected' and data['connection']['source'] == 'apple_health'
    assert data['connection']['devices'][0]['name'] == 'Testi-iPhone' and 'tokenHash' not in json.dumps(data)
    days = flat_days('2026-09-01', 3, steps=8000, sleepMinutes=430, restingHeartRate=48, hrvMs=52)
    first = ok(sync(token, days, userId='someone-else'))  # a user id in the body is ignored: the device decides
    assert first['created'] == 3 and first['updated'] == 0
    again = ok(sync(token, [{'date': '2026-09-01', 'steps': 9100}]))
    assert again['created'] == 0 and again['updated'] == 1
    stored = [r for r in json.loads(open(settings.LOOP_STATE_PATH, encoding='utf-8').read())['support']['wellbeing']['dailyMetrics']
              if r['date'] == '2026-09-01']
    assert len(stored) == 1 and stored[0]['steps'] == 9100 and stored[0]['sleepMinutes'] == 430 and stored[0]['source'] == 'apple_health'
    assert stored[0]['syncedAt'] and stored[0]['deviceId']
    # the pairing code works once
    assert client.post('/api/health/devices/pair', json={'code': '123456'}).status_code == 401


def test_sync_requires_a_valid_device_token_and_a_valid_payload():
    token = paired_token()
    assert sync('wrong-token', flat_days('2026-09-01', 1, steps=100)).status_code == 401
    assert client.post('/api/health/sync', json={'source': 'apple_health', 'dailyMetrics': []}).status_code == 401
    for bad in (
        [{'date': '2026-09-01', 'restingHeartRate': 400}],  # out of range
        [{'date': '2026-09-01', 'bloodSugarCustom': 5}],  # unknown metric
        [{'date': '31.8.2026', 'steps': 10}],  # not an ISO date
        [{'date': '2099-01-01', 'steps': 10}],  # in the future
        [{'date': '2026-09-01', 'steps': 10}, {'date': '2026-09-01', 'steps': 20}],  # the same day twice
        [{'date': '2026-09-01', 'steps': 'paljon'}],  # not a number
        flat_days('2026-09-01', 401, steps=10),  # too many days at once
    ):
        assert sync(token, bad).status_code == 400, bad
    assert client.post('/api/health/sync', json={'source': 'garmin', 'dailyMetrics': flat_days('2026-09-01', 1, steps=1)},
                       headers={'Authorization': f'Bearer {token}'}).status_code == 400
    extra = ok(sync(token, [{'date': '2026-09-01', 'extra': {'respiratoryRate': 14.5}}]))  # a future metric is accepted
    assert extra['created'] == 1


def test_permissions_minimize_what_is_stored_and_used():
    token = paired_token()
    ok(client.put('/api/health/permissions', json={'permissions': {'weightKg': False}}))
    result = ok(sync(token, [{'date': '2026-09-01', 'steps': 8000, 'weightKg': 62.0}]))
    assert result['droppedMetrics'] == ['weightKg']
    ok(client.post('/api/health/disconnect'))
    assert sync(token, [{'date': '2026-09-01', 'steps': 1}]).status_code == 401  # the device was revoked
    assert client.put('/api/health/permissions', json={'permissions': {'unknown': True}}).status_code == 400


# --- gate 3, disconnect and delete ---------------------------------------------------------------------------------------

def test_without_consent_nothing_reaches_the_agent_or_the_llm_context():
    ok(client.put('/api/support/consent', json={'dataSources': {'wellbeingData': False}}))
    ok(client.post('/api/health/demo/synthetic'))
    data = summary()
    assert data['consentAllowed'] is False and data['inUse'] is False and data['observations'] == [] and data['agentContext'] is None
    dash = state()
    assert dash['companion']['userContext']['wellbeingData'] is None
    reply = client.post('/api/loop/companion/messages', json={'text': 'Miten leposykkeeni on kehittynyt?'}).json()
    assert agent_messages(reply['dashboard'])[-1]['text'] == texts.CHAT_SUMMARY_NOT_ALLOWED
    assert 'Hyvinvointidata: Apple Health (vapaaehtoinen)' in dash['support']['consent']['sourceLabels'].values()


def test_disconnect_stops_the_use_and_delete_removes_the_data():
    ok(client.post('/api/health/demo/synthetic'))
    ok(client.post('/api/health/disconnect'))
    data = summary()
    assert data['connection']['status'] == 'disconnected' and data['inUse'] is False and data['agentContext'] is None
    deleted = ok(client.delete('/api/health/data'))
    assert deleted['result'] == 365
    data = summary()
    assert data['connection']['status'] == 'not_connected' and data['dataRange'] is None and data['observations'] == []
    entries = [e['detail'] for e in state()['support']['audit']['entries']]
    assert any('poistettiin' in e for e in entries) and any('katkaistiin' in e for e in entries)
    assert not any('bpm' in e or 'min/yö' in e for e in entries)  # health values stay out of the audit log


# --- the conversation and the agent's context ---------------------------------------------------------------------------

def test_discussing_an_observation_opens_the_chat_with_data_interpretation_and_next_actions():
    ok(client.post('/api/health/demo/synthetic'))
    observation = summary()['observations'][0]
    dash = ok(client.post(f"/api/health/observations/{observation['id']}/discuss"))['dashboard']
    reply = agent_messages(dash)[-1]
    assert reply['kind'] == 'health_discussion' and reply['text'].startswith('Katsotaan yhdessä.')
    assert '• Leposyke: viimeiset 7 päivää 53 bpm, oma tasosi 47 bpm (+5 bpm)' in reply['text']
    assert texts.INTERPRETATION in reply['text']  # data and interpretation kept apart
    assert [a['label'] for a in reply['actions']] == ['Käydään läpi mahdollisia syitä', 'Seurataan viikon ajan', 'Haluan ammattilaisen arvion']
    assert check_text(reply['text'])['passed']
    context = dash['companion']['userContext']['wellbeingData']
    assert context['observationUnderDiscussion']['area'] == 'Palautuminen'
    proactive = next(m for m in agent_messages(dash) if m['kind'] == 'health_observation')
    assert all(a['used'] for a in proactive['actions'])  # answered in the tab, the chat buttons close
    # reasons -> one approved guide and a week of self-monitoring
    reasons = next(a for a in reply['actions'] if a['type'] == 'health_reasons')
    dash = ok(client.post(f"/api/loop/companion/actions/{reasons['id']}", json={'args': {}}))['dashboard']
    options = agent_messages(dash)[-1]['actions']
    assert [a['label'] for a in options][:2] == ['Kiireinen tai kuormittava jakso', 'Olen nukkunut huonommin']
    sleep = next(a for a in options if a['args']['reason'] == 'sleep')
    dash = ok(client.post(f"/api/loop/companion/actions/{sleep['id']}", json={'args': {}}))['dashboard']
    text = agent_messages(dash)[-1]['text']
    assert 'Säännöllinen unirytmi:' in text and 'Seuraan leposykettä, HRV:tä ja unen määrää ja kerron 8.9.2026, miten viikko meni.' in text
    assert check_text(text)['passed']
    data = summary()
    assert data['observations'][0]['status'] == 'discussed' and data['observations'][0]['followUpAt'] == '2026-09-08'


def test_illness_as_the_reason_points_to_the_symptom_assessment_not_to_a_plan():
    ok(client.post('/api/health/demo/synthetic'))
    observation = summary()['observations'][0]
    dash = ok(client.post(f"/api/health/observations/{observation['id']}/discuss"))['dashboard']
    reasons = next(a for a in agent_messages(dash)[-1]['actions'] if a['type'] == 'health_reasons')
    dash = ok(client.post(f"/api/loop/companion/actions/{reasons['id']}", json={'args': {}}))['dashboard']
    ill = next(a for a in agent_messages(dash)[-1]['actions'] if a['args']['reason'] == 'ill')
    dash = ok(client.post(f"/api/loop/companion/actions/{ill['id']}", json={'args': {}}))['dashboard']
    assert agent_messages(dash)[-1]['text'] == texts.REASON_REPLIES['ill']
    assert summary()['observations'][0]['followUpAt'] is None


def test_the_chat_answers_from_the_compact_summary_and_the_llm_gets_no_history(monkeypatch):
    ok(client.post('/api/health/demo/synthetic'))
    reply = client.post('/api/loop/companion/messages', json={'text': 'Miten uneni on kehittynyt?'}).json()
    assert reply['intent'] == 'WELLBEING_DATA' and reply['intentMethod'] == 'deterministic_wellbeing_rules'
    text = agent_messages(reply['dashboard'])[-1]['text']
    assert text.startswith('Hyvinvointidatasi (Synteettinen testidata (Apple Health -muotoinen)) viimeiset 7 päivää')
    assert '• Leposyke: 53 bpm, oma tasosi 47 bpm (+5 bpm)' in text and check_text(text)['passed']
    # with the LLM on, the prompt carries the bounded context: the compact summary, never the daily history
    monkeypatch.setattr(settings, 'LOOP_LLM_PROVIDER', 'anthropic')
    prompts: list[str] = []
    monkeypatch.setattr(llm, '_call', lambda prompt, output_schema=None: prompts.append(prompt) or 'Leposykkeesi on noussut omasta tasostasi.')
    reply = client.post('/api/loop/companion/messages', json={'text': 'Mitä hyvinvointidatani kertoo?'}).json()
    assert agent_messages(reply['dashboard'])[-1]['textSource'] == 'llm'
    prompt = prompts[-1]
    context = json.loads(prompt[prompt.index('{'):])
    wellbeing = context['wellbeingData']
    assert wellbeing['current']['Leposyke'] == '53 bpm' and wellbeing['personalBaseline']['Leposyke'] == '47 bpm'
    assert any(c['metric'] == 'Leposyke' and c['change'] == '+5 bpm' for c in wellbeing['recentChanges'])
    assert '2025-10-01' not in prompt and 'dailyMetrics' not in prompt and 'Aino' not in prompt
    assert set(context) >= {'activeSupportPlans', 'activeGenomicFindings', 'wellbeingData'}  # combined with the other context
    # an unsafe LLM text falls back to the template
    monkeypatch.setattr(llm, '_call', lambda prompt, output_schema=None: 'Sinulla on todettu sairaus, riski 30 %.')
    reply = client.post('/api/loop/companion/messages', json={'text': 'Miten leposykkeeni on kehittynyt?'}).json()
    assert agent_messages(reply['dashboard'])[-1]['textSource'] == 'template'


def test_symptoms_keep_the_existing_safety_path():
    ok(client.post('/api/health/demo/synthetic'))
    reply = client.post('/api/loop/companion/messages', json={'text': 'Minulla on rintakipua ja leposyke on korkea.'}).json()
    assert reply['intent'] == 'EMERGENCY_OR_URGENT'
    reply = client.post('/api/loop/companion/messages', json={'text': 'Olen väsynyt ja leposykkeeni on noussut.'}).json()
    assert reply['intent'] == 'CARE_NEED_ASSESSMENT'


def test_wellbeing_texts_pass_the_safety_check():
    samples = [
        texts.INTERPRETATION, texts.INTERPRETATION_POSITIVE, texts.DISCUSS_QUESTION, texts.REASON_QUESTION, texts.DISMISSED,
        *texts.REASON_REPLIES.values(), texts.FOLLOW_UP.format(metrics='leposykettä', date='8.9.2026'),
        texts.FOLLOW_UP_POSITIVE.format(metrics='askelmäärää'), texts.CHAT_SUMMARY_NONE, texts.CHAT_SUMMARY_NOT_ALLOWED,
        texts.CHAT_SUMMARY_NO_CHANGES, texts.CHAT_SUMMARY_NOTE, catalog.config()['permissionText'],
        texts.WHY_RULE.format(thresholds='leposyke vähintään 3 bpm'), texts.WHY_PERIOD.format(days=90),
    ]
    for sample in samples:
        assert check_text(sample)['passed'], sample
    joined = ' '.join(samples).lower()
    for forbidden in ('diagnosoi', 'sairastat', 'riski', 'sinulla on sairaus'):
        assert forbidden not in joined
    assert check_text(companion_texts.GREETING)['passed']
