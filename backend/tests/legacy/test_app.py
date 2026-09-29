from __future__ import annotations

from fastapi.testclient import TestClient

from app.legacy_api import legacy_app as app

client = TestClient(app)


def test_health():
    response = client.get('/api/health')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'


def test_create_session_from_demo_and_end_to_end():
    session_response = client.post(
        '/api/analysis/sessions/from-demo',
        json={'kind': 'quick_snippet', 'mode': 'demo', 'resource_profile': 'light'},
    )
    assert session_response.status_code == 200
    session_id = session_response.json()['session_id']

    preflight = client.post(f'/api/analysis/sessions/{session_id}/preflight')
    assert preflight.status_code == 200

    parsed = client.post(f'/api/analysis/sessions/{session_id}/parse-next')
    assert parsed.status_code == 200
    parsed_data = parsed.json()
    assert parsed_data['valid_rows'] >= 1

    matched = client.post(f'/api/analysis/sessions/{session_id}/match-next')
    assert matched.status_code == 200
    matched_data = matched.json()
    assert matched_data['position_matches'] >= 1

    classified = client.post(f'/api/analysis/sessions/{session_id}/classify')
    assert classified.status_code == 200

    finalized = client.post(f'/api/analysis/sessions/{session_id}/finalize')
    assert finalized.status_code == 200

    report = client.get(f'/api/analysis/sessions/{session_id}/report')
    assert report.status_code == 200
    report_data = report.json()
    assert report_data['analysis']['variants_analyzed'] >= 1
