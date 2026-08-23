import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_v44_collaboration_assignment_sla_handoff_and_comment():
    assert client.get('/health').json()['version'] == '4.9.0'
    rid = 'V44-ASSET-001'
    r = client.post(f'/collaboration/resources/asset/{rid}/assign', json={
        'assignee': 'engineer-f01', 'title': 'A101 filter follow-up', 'actor': 'lead-f01'
    })
    assert r.status_code == 200
    assert r.json()['assignee'] == 'engineer-f01'

    r = client.post(f'/collaboration/resources/asset/{rid}/sla', json={'sla_hours': 24, 'actor': 'lead-f01'})
    assert r.status_code == 200
    assert r.json()['sla_state'] in {'on_track', 'due_soon'}

    r = client.post(f'/collaboration/resources/asset/{rid}/watch', json={'principal_id': 'planner-f01', 'enabled': True, 'actor': 'planner-f01'})
    assert r.status_code == 200
    assert 'planner-f01' in r.json()['watchers']

    r = client.post(f'/collaboration/resources/asset/{rid}/comments', json={
        'actor': 'engineer-f01', 'body': '@planner-f01 请确认维护窗口'
    })
    assert r.status_code == 200
    assert r.json()['mentions'] == ['planner-f01']

    r = client.post(f'/collaboration/resources/asset/{rid}/handoff', json={
        'to_principal': 'planner-f01', 'actor': 'engineer-f01', 'note': 'RCA 已确认，转维护计划'
    })
    assert r.status_code == 200
    assert r.json()['assignee'] == 'planner-f01'

    thread = client.get(f'/collaboration/resources/asset/{rid}').json()
    assert thread['comments']
    assert any(x['event_type'] == 'handoff' for x in thread['events'])


def test_v44_team_board_and_ui_i18n_contract():
    board = client.get('/collaboration/board?principal_id=planner-f01').json()
    assert 'summary' in board
    assert board['semantics'].startswith('Collaboration metadata only')

    html = client.get('/').text
    for token in ['data-panel="collaboration"', 'panel-collaboration', 'loadCollaborationBoard', 'teamHandoff', 'teamComment']:
        assert token in html

    base = Path('app/static/i18n')
    packs = {}
    for loc in ['zh-CN', 'en-US', 'de-DE', 'ja-JP']:
        packs[loc] = json.loads((base / f'{loc}.json').read_text(encoding='utf-8'))['phrases']
        assert '团队协作' in packs[loc]
        assert '团队协作与责任闭环' in packs[loc]
        assert '发表评论' in packs[loc]
    assert len({len(x) for x in packs.values()}) == 1
    assert set(packs['zh-CN']) == set(packs['en-US']) == set(packs['de-DE']) == set(packs['ja-JP'])


def test_v44_readme_deployment_and_author_contract():
    text = Path('README.md').read_text(encoding='utf-8')
    assert 'V4.9.0' in text
    assert 'PostgreSQL + Mock Query + Local Knowledge' in text
    assert 'EXECUTION_MODE=doris' in text
    assert 'KNOWLEDGE_BACKEND=qdrant' in text
    assert '生产部署骨架' in text
    assert '| **开发者** | 良晞 |' in text
