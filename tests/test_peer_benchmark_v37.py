from fastapi.testclient import TestClient
from app.main import app

def test_peer_benchmark_and_version():
 c=TestClient(app); assert c.get('/health').json()['version']=='4.9.0'
 payload={'current':{'asset_id':'A101','load_pct':84,'ambient_temp':29,'product_type':'P1','operating_mode':'auto','specific_energy':12},'peers':[{'asset_id':'A102','load_pct':82,'ambient_temp':28,'product_type':'P1','operating_mode':'auto','specific_energy':10},{'asset_id':'A103','load_pct':85,'ambient_temp':30,'product_type':'P1','operating_mode':'auto','specific_energy':10.2},{'asset_id':'A104','load_pct':81,'ambient_temp':29,'product_type':'P1','operating_mode':'auto','specific_energy':9.8},{'asset_id':'B1','load_pct':30,'ambient_temp':15,'product_type':'P2','operating_mode':'manual','specific_energy':15}]}
 d=c.post('/pilot/peer-benchmark/assess',json=payload).json(); assert d['comparable_peer_count']==3; assert d['peer_median']==10.0; assert d['ready'] is True

def test_v37_ui_and_languages():
 c=TestClient(app); html=c.get('/').text; assert '同类设备对标中心' in html; assert 'loadPeerBenchmark' in html
 for loc in ('zh-CN','en-US','de-DE','ja-JP'):
  d=c.get('/static/i18n/'+loc+'.json').json(); assert '同类设备对标' in d['phrases']
