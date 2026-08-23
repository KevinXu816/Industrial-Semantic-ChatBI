from fastapi.testclient import TestClient
from app.main import app
import uuid

client = TestClient(app)


def test_v42_version_and_personalized_workspace_contract():
    assert client.get('/health').json()['version'] == '4.9.0'
    r = client.get('/workspace/personalized?role=reliability_engineer&principal_id=test-v42')
    assert r.status_code == 200
    body = r.json()
    assert body['role'] == 'reliability_engineer'
    assert 'focus' in body and 'favorites' in body and 'recent' in body


def test_recent_and_favorite_preferences_are_persisted():
    principal = 'test-v42-pref-' + uuid.uuid4().hex
    item = {'principal_id': principal, 'type': 'asset', 'id': 'A101', 'title': 'A101', 'panel': 'assets', 'asset_id': 'A101'}
    r = client.post('/workspace/preferences/recent', json=item)
    assert r.status_code == 200
    assert r.json()['recent'][0]['id'] == 'A101'
    r = client.post('/workspace/preferences/favorite', json=item)
    assert r.status_code == 200
    assert r.json()['favorites'][0]['id'] == 'A101'
    r = client.get('/workspace/preferences', params={'principal_id': principal})
    assert r.status_code == 200
    assert r.json()['favorites'][0]['id'] == 'A101'


def test_workspace_context_contract():
    # Context API should stay safe even when the asset is absent in a clean repository.
    r = client.get('/workspace/context', params={'asset_id': 'A101'})
    assert r.status_code == 200
    body = r.json()
    assert body['asset_id'] == 'A101'
    assert isinstance(body['links'], list)
