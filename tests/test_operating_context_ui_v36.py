import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app


def test_v36_version_and_operating_context_api():
    c=TestClient(app)
    assert c.get('/health').json()['version']=='4.9.0'
    payload={
      'current': {'load_pct':80,'production_output':100,'ambient_temp':28,'shift':'A','product_type':'P1','operating_mode':'auto','specific_energy':12},
      'history': [
        {'load_pct':80,'production_output':100,'ambient_temp':28,'shift':'A','product_type':'P1','operating_mode':'auto','specific_energy':10},
        {'load_pct':82,'production_output':102,'ambient_temp':29,'shift':'B','product_type':'P1','operating_mode':'auto','specific_energy':10.2},
        {'load_pct':78,'production_output':98,'ambient_temp':27,'shift':'A','product_type':'P1','operating_mode':'auto','specific_energy':9.8},
      ]}
    r=c.post('/pilot/operating-context/assess',json=payload)
    assert r.status_code==200
    assert r.json()['ready_for_rca'] is True


def test_i18n_resource_packs_and_author_footer():
    root=Path(__file__).resolve().parents[1]
    for loc in ['zh-CN','en-US','de-DE','ja-JP']:
        p=root/'app'/'static'/'i18n'/f'{loc}.json'
        assert p.exists()
        d=json.loads(p.read_text(encoding='utf-8'))
        assert d['locale']==loc
        assert '可靠性工作台' in d['phrases']
    html=(root/'app'/'static'/'index.html').read_text(encoding='utf-8')
    assert 'id="language-selector"' in html
    assert '开发者：<strong>良晞</strong>' in html
    assert '/static/i18n.js' in html
