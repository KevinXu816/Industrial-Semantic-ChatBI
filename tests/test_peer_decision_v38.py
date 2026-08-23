from fastapi.testclient import TestClient
from app.main import app

def test_peer_explain_priority_and_promote_to_rca():
    c=TestClient(app)
    payload={
      "current":{"asset_id":"A101","load_pct":84,"ambient_temp":29,"product_type":"P1","operating_mode":"auto","specific_energy":12.0},
      "peers":[
        {"asset_id":"A102","load_pct":85,"ambient_temp":30,"product_type":"P1","operating_mode":"auto","specific_energy":9.9},
        {"asset_id":"A103","load_pct":81,"ambient_temp":29,"product_type":"P1","operating_mode":"auto","specific_energy":10.1},
        {"asset_id":"A104","load_pct":82,"ambient_temp":28,"product_type":"P1","operating_mode":"auto","specific_energy":9.6},
        {"asset_id":"A105","load_pct":86,"ambient_temp":30,"product_type":"P1","operating_mode":"auto","specific_energy":10.4},
        {"asset_id":"B201","load_pct":45,"ambient_temp":18,"product_type":"P2","operating_mode":"manual","specific_energy":13.8}
      ],"metric":"specific_energy"}
    r=c.post('/pilot/peer-benchmark/assess',json=payload); assert r.status_code==200
    d=r.json(); assert d['ready'] is True and d['rca_candidate'] is True
    assert d['priority'] in {'P1','P2'} and d['excluded_peer_count']==1
    assert d['comparability_explanation']['dimensions']==['product_type','operating_mode','load_band','ambient_band']
    r=c.post(f"/pilot/peer-benchmark/{d['assessment_id']}/promote-to-rca",json={"actor":"test"}); assert r.status_code==200
    case=r.json()['rca_case']; assert case['status']=='analyzed' and case['subject']['reference']=='A101'

def test_v38_i18n_resources_have_new_peer_ui():
    import json, pathlib
    for loc in ['zh-CN','en-US','de-DE','ja-JP']:
      p=pathlib.Path('app/static/i18n')/f'{loc}.json'; phrases=json.loads(p.read_text())['phrases']
      for key in ['创建 RCA Case','对标可比性解释','异常优先级']:
        assert key in phrases and phrases[key]
