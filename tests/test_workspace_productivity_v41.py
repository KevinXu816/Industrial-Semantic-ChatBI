import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
ROOT=Path(__file__).resolve().parents[1]

def test_v41_workspace_productivity_api_contract():
    c=TestClient(app)
    assert c.get('/health').json()['version']=='4.9.0'
    a=c.get('/workspace/quick-actions'); assert a.status_code==200 and any(x['panel']=='assets' for x in a.json()['actions'])
    i=c.get('/workspace/inbox'); assert i.status_code==200 and 'summary' in i.json() and 'items' in i.json()
    s=c.get('/workspace/search',params={'q':'A101'}); assert s.status_code==200 and 'results' in s.json()

def test_v41_command_palette_inbox_and_i18n_are_present():
    html=(ROOT/'app/static/index.html').read_text(encoding='utf-8')
    for token in ['id="command-overlay"','id="inbox-drawer"','Ctrl+K','/workspace/search?q=','/workspace/inbox?limit=50']:
        assert token in html
    sets=[]
    required={'全局搜索','统一待办与通知','快速操作','打开资产可靠性','打开 RCA 工作流'}
    for loc in ['zh-CN','en-US','de-DE','ja-JP']:
        d=json.loads((ROOT/f'app/static/i18n/{loc}.json').read_text(encoding='utf-8'))['phrases']
        assert required<=set(d); sets.append(set(d))
    assert all(x==sets[0] for x in sets[1:])

def test_v41_readme_deployment_and_version_are_current():
    t=(ROOT/'README.md').read_text(encoding='utf-8')
    assert 'V4.1' in t and 'Docker Compose 企业 Pilot' in t
    assert 'EXECUTION_MODE=doris' in t and 'KNOWLEDGE_BACKEND=qdrant' in t and '生产部署骨架' in t
    assert '| **开发者** | 良晞 |' in t
