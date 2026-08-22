from app.persistence import JsonRepository
from app.fmea import FMEAStore
from app.industrial_knowledge_graph import IndustrialKnowledgeGraph
from app.failure_model import FailureModelIngestion
from app.causal_model import CausalGraphReasoner


def sample(**extra):
    row={
        'fmea_id':'FMEA-BRG-001','asset':'A101','component':'Drive End Bearing',
        'failure_mode':'bearing_overheat','cause_code':'bearing_overheat','cause':'lubrication degradation',
        'effect':'temperature and vibration rise','detection_method':'bearing temperature / vibration trend',
        'severity':8,'occurrence':6,'detectability':5,'recommended_action':'inspect lubrication and bearing',
        'alarm_patterns':['bearing temperature high'],'status':'draft'
    }
    row.update(extra); return row


def test_rpn_and_criticality(tmp_path):
    store=FMEAStore(JsonRepository(tmp_path/'repo'))
    row=store.create(sample())
    assert row['rpn']==240
    assert row['criticality']=='high'


def test_fmea_score_validation(tmp_path):
    store=FMEAStore(JsonRepository(tmp_path/'repo'))
    try: store.create(sample(severity=11))
    except ValueError as e: assert 'severity' in str(e)
    else: assert False


def test_only_approved_fmea_enters_failure_graph(tmp_path):
    repo=JsonRepository(tmp_path/'repo'); store=FMEAStore(repo); graph=IndustrialKnowledgeGraph(repo); ing=FailureModelIngestion(graph)
    row=store.create(sample())
    assert ing.ingest_fmea(row)['status']=='skipped'
    row=store.approve(row['fmea_id'])
    out=ing.ingest_fmea(row)
    assert out['status']=='ingested'
    rels={e['relation'] for e in graph.edges()}
    assert {'HAS_COMPONENT','HAS_FAILURE_MODE','CAUSED_BY','HAS_EFFECT','DETECTED_BY','RESOLVED_BY'} <= rels


def test_fmea_graph_reasoning_and_risk_ranking(tmp_path):
    repo=JsonRepository(tmp_path/'repo'); store=FMEAStore(repo); graph=IndustrialKnowledgeGraph(repo); ing=FailureModelIngestion(graph)
    a=store.create(sample(status='approved')); ing.ingest_fmea(a)
    b=store.create(sample(fmea_id='FMEA-FLTR-001',component='Air Filter',failure_mode='filter_restriction',cause_code='filter_restriction',cause='dust blockage',severity=9,occurrence=5,detectability=7,recommended_action='replace filter',alarm_patterns=['High Differential Pressure'],status='approved')); ing.ingest_fmea(b)
    ranked=store.rank()
    assert ranked[0]['fmea_id']=='FMEA-FLTR-001'
    result=CausalGraphReasoner(graph).rank_failure_modes(['High Differential Pressure','dust blockage'])
    assert result and result[0]['cause_code']=='filter_restriction'
    assert result[0]['causal_claim_supported'] is True
