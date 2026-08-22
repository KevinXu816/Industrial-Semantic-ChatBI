from app.persistence import JsonRepository
from app.industrial_knowledge_graph import IndustrialKnowledgeGraph
from app.graph_bootstrap import bootstrap_graph
from app.causal_model import CausalGraphReasoner
from app.graph_ingestion import GraphIngestionService


def test_graph_bootstrap_and_reason(tmp_path):
    repo=JsonRepository(tmp_path/'repo')
    graph=IndustrialKnowledgeGraph(repo); bootstrap_graph(graph)
    assert len(graph.nodes()) >= 5
    result=CausalGraphReasoner(graph).rank_failure_modes(['High Differential Pressure','filter differential pressure rising'])
    assert result
    assert result[0]['cause_code']=='filter_restriction'
    assert result[0]['graph_score'] > 0


def test_governed_causal_edge_is_distinguished(tmp_path):
    repo=JsonRepository(tmp_path/'repo'); graph=IndustrialKnowledgeGraph(repo); bootstrap_graph(graph)
    result=CausalGraphReasoner(graph).rank_failure_modes(['Air Filter'])
    assert result[0]['causal_claim_supported'] is True


def test_unapproved_document_not_ingested(tmp_path):
    repo=JsonRepository(tmp_path/'repo'); graph=IndustrialKnowledgeGraph(repo)
    svc=GraphIngestionService(graph)
    out=svc.ingest_knowledge({'id':'F1','status':'candidate','failure_mode':'bearing_fault','title':'candidate'})
    assert out['status']=='skipped'
    assert not graph.nodes()


def test_approved_document_builds_failure_graph(tmp_path):
    repo=JsonRepository(tmp_path/'repo'); graph=IndustrialKnowledgeGraph(repo)
    svc=GraphIngestionService(graph)
    out=svc.ingest_knowledge({'id':'F1','version':'1.0','status':'approved','failure_mode':'bearing_fault','title':'Bearing FMEA','alarm_patterns':['bearing temperature high'],'sensor_patterns':['vibration rising'],'components':['Bearing'],'recommended_actions':['inspect bearing']})
    assert out['status']=='ingested'
    rels={x['relation'] for x in graph.edges()}
    assert {'CAUSED_BY','INDICATED_BY','DETECTED_BY','RESOLVED_BY'} <= rels
