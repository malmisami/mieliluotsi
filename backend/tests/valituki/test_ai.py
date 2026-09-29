"""AIProvider: DEMO_AI_MODE without a key, LIVE_AI_MODE with validated output and deterministic fallbacks."""
from __future__ import annotations

import json

from app.config import settings
from app.valituki import ai, guard, scenes


def test_demo_ai_mode_works_without_api_key(monkeypatch):
    """Test 15: no key → deterministic provider, and the whole demo journey runs."""
    monkeypatch.setattr(settings, 'VALITUKI_AI_MODE', 'DEMO_AI_MODE')
    assert ai.effective_mode() == 'DEMO_AI_MODE'
    assert isinstance(ai.get_provider(), ai.DemoAIProvider)
    state = scenes.build_scene('therapy')
    assert next(c for c in state.clients if c.id == 'cl-aino').journeyState == 'THERAPY_ACTIVE'
    assert {a.aiSource for a in state.actions if a.aiSource} == {'demo'}


def test_live_mode_without_key_falls_back_to_demo(monkeypatch):
    monkeypatch.setattr(settings, 'VALITUKI_AI_MODE', 'LIVE_AI_MODE')
    assert ai.effective_mode() == 'DEMO_AI_MODE'
    assert 'ANTHROPIC_API_KEY puuttuu' in ai.status()['note']


def test_an_auth_token_also_enables_live_mode(monkeypatch):
    monkeypatch.setattr(settings, 'VALITUKI_AI_MODE', 'LIVE_AI_MODE')
    monkeypatch.setenv('ANTHROPIC_AUTH_TOKEN', 'test-token')
    assert ai.key_present() and ai.effective_mode() == 'LIVE_AI_MODE'
    assert isinstance(ai.get_provider(), ai.ClaudeAIProvider)
    assert isinstance(ai.get_provider(interactive=False), ai.DemoAIProvider)  # seeding and simulations stay deterministic


def test_a_key_pasted_into_env_is_picked_up_without_a_restart(monkeypatch):
    calls = []
    monkeypatch.setattr(ai, '_claude', lambda prompt, schema=None, max_tokens=8000: (calls.append(prompt) or
                                                                                     '{"reply": "Yhteys toimii."}', None))
    result = ai.set_mode('LIVE_AI_MODE')
    assert result['effectiveMode'] == 'DEMO_AI_MODE' and not result['keyPresent']
    assert result['check'] == {'ok': False, 'failure': 'API-avain puuttuu', 'reply': None, 'ms': None, 'model': None}
    assert calls == []  # without a key the model is never called
    ai.ENV_FILE.write_text('VALITUKI_AI_MODEL=claude-opus-5\nANTHROPIC_API_KEY=test-key-from-env-file\n')
    check = ai.check_connection()
    assert check['ok'] and check['reply'] == 'Yhteys toimii.' and len(calls) == 1
    assert ai.status()['effectiveMode'] == 'LIVE_AI_MODE' and ai.status()['lastCall']['task'] == 'connectionCheck'
    assert ai.set_mode('DEMO_AI_MODE')['effectiveMode'] == 'DEMO_AI_MODE'


def test_a_failed_connection_check_names_the_reason(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    monkeypatch.setattr(ai, '_claude', lambda prompt, schema=None, max_tokens=8000: (None, 'API-avain ei kelpaa (401)'))
    check = ai.check_connection()
    assert check['ok'] is False and check['failure'] == 'API-avain ei kelpaa (401)'
    assert ai.status()['lastCall']['ok'] is False


def test_api_errors_become_readable_reasons():
    class Error:
        def __init__(self, status, message):
            self.status_code, self.body = status, {'type': 'error', 'error': {'type': 'x', 'message': message}}

    assert ai._status_failure(Error(401, 'invalid x-api-key')) == 'API-avain ei kelpaa (401)'
    assert ai._status_failure(Error(404, 'model: claude-x')) == 'mallia tai osoitetta ei löydy (404): model: claude-x'
    assert ai._status_failure(Error(500, 'boom')) == 'API-virhe (500)'


def test_the_live_reply_gets_the_conversation_so_far(monkeypatch):
    from app.valituki import client_actions

    state = scenes.build_scene('intake')
    client = next(c for c in state.clients if c.id == 'cl-aino')
    prompts = []

    def fake(prompt, schema=None, max_tokens=8000):
        prompts.append(prompt)
        return ('{"supportiveResponse": "Kiitos, että kerroit. Mikä siinä tuntuu raskaimmalta?", "acknowledgedUserNeed": "x", '
                '"approvedActivityId": null, "suggestedTool": "NONE", "suggestedNextAction": "NONE", "safetyHint": "NONE", '
                '"uncertainty": null}', None)

    monkeypatch.setattr(ai, '_claude', fake)
    client_actions.send_message(state, client, 'Olen ollut tosi väsynyt tällä viikolla.', ai.ClaudeAIProvider())
    reply = client_actions.send_message(state, client, 'Nukun huonosti.', ai.ClaudeAIProvider())
    message = next(m for m in state.chat if m.id == reply['messageId'])
    assert message.textSource == 'live'
    context = json.loads(prompts[-1].split('Input (JSON):\n', 1)[1])
    assert context['message'] == 'Nukun huonosti.'
    texts = [m['text'] for m in context['recentConversation']]
    assert 'Olen ollut tosi väsynyt tällä viikolla.' in texts and 'Nukun huonosti.' not in texts


def test_live_provider_rejects_unsafe_model_text(monkeypatch):
    monkeypatch.setattr(ai, '_claude', lambda prompt, schema=None, max_tokens=8000: (
        '{"supportiveResponse": "Sinulla on masennus. Olen aina täällä sinua varten.", "acknowledgedUserNeed": "x", '
        '"approvedActivityId": null, "suggestedNextAction": "NONE", "safetyHint": "NONE", "uncertainty": null}', None))
    response = ai.ClaudeAIProvider().generate_support_response({'message': 'Olen väsynyt', 'allowedActivityIds': []})
    assert response.source == 'fallback'
    assert 'diagnoosiväite' in response.violations and 'riippuvuutta lisäävä lupaus' in response.violations
    assert 'masennus' not in response.supportiveResponse


def test_live_intake_summary_falls_back_when_the_model_fails(monkeypatch):
    monkeypatch.setattr(ai, '_claude', lambda prompt, schema=None, max_tokens=8000: (None, 'yhteysvirhe'))
    summary = ai.ClaudeAIProvider().summarise_client_statement({'answers': {'reason': 'Työ ahdistaa', 'change': 'Haluan hallita '
                                                                            'työtilanteisiin liittyvää ahdistusta'}})
    assert summary.source == 'fallback' and summary.proposals


def test_guard_blocks_clinical_claims_and_allows_neutral_text():
    assert 'kliininen väite' in guard.check('Tilasi on pahentunut.')
    assert 'lääkkeen nimi' in guard.check('Kokeile melatoniinia.')
    assert 'lääkitys' in guard.check('Ota tabletti illalla.')
    assert 'kiireellisyyspäätös' in guard.check('Nostin hoitosi kiireellisyyttä.')
    assert 'väite ammattilaisen tarkistuksesta, jota ei ole' in guard.check('Ammattilainen on jo tarkistanut tilanteesi.')
    assert guard.check('Ammattilainen on jo tarkistanut tilanteesi.', review_exists=True) == []
    assert guard.check('Check-iniesi perusteella vointisi on ollut hieman tavanomaista matalampi.') == []


def test_system_prompt_states_the_boundaries():
    prompt = ai.VALITUKI_SYSTEM_PROMPT
    for rule in ('You are not a therapist, doctor, psychologist or emergency service', 'Do not diagnose',
                 'Do not provide medication advice', 'Do not make clinical urgency decisions',
                 'Only recommend activities from the approved activity library', 'Vaikuttaa siltä, että',
                 'Never say "I am always here for you"', 'Ask at most one meaningful follow-up question at a time'):
        assert rule in prompt
