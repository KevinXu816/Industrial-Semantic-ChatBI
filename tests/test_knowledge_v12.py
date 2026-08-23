from pathlib import Path
from fastapi.testclient import TestClient
from app.persistence import JsonRepository
from app.knowledge_store import KnowledgeStore
from app.knowledge_backends import LocalHybridBackend
from app.knowledge_ingestion import KnowledgeIngestionPipeline
from app.knowledge_workflow import KnowledgeWorkflow
from app.retrieval_quality import RetrievalEvaluator
from app.rca_cases import RCACaseStore
from app.rca_similarity import RCASimilaritySearch


def stack(tmp_path):
    repo=JsonRepository(tmp_path/'repo'); store=KnowledgeStore(repo); backend=LocalHybridBackend(store)
    ingestion=KnowledgeIngestionPipeline(store,backend); wf=KnowledgeWorkflow(store,repo,ingestion)
    return repo,store,backend,wf

def test_candidate_not_retrieved_until_approved(tmp_path):
    _,_,backend,wf=stack(tmp_path)
    wf.submit_document({'id':'K1','version':'1.0','type':'FMEA','title':'过滤器堵塞','content':'过滤器压差升高会导致能耗增加'})
    assert backend.search('过滤器 压差') == []
    wf.approve('K1','1.0')
    assert backend.search('过滤器 压差')[0]['document_id']=='K1'

def test_supersede_preserves_lineage(tmp_path):
    _,store,_,wf=stack(tmp_path)
    store.put_document({'id':'SOP1','version':'1.0','title':'旧SOP','content':'旧检查步骤','status':'approved'})
    result=wf.supersede('SOP1','1.0',{'version':'2.0','title':'新SOP','content':'新检查步骤'})
    assert result['superseded']['status']=='superseded'
    assert result['replacement']['document']['status']=='approved'
    assert result['replacement']['chunks'][0]['parent_citation'].startswith('SOP1@2.0#')

def test_retrieval_evaluation_metrics(tmp_path):
    _,store,backend,_=stack(tmp_path)
    ingestion=KnowledgeIngestionPipeline(store,backend)
    ingestion.ingest_documents([{'id':'F1','title':'过滤器压差','content':'过滤器堵塞 压差升高 能耗增加','status':'approved'}])
    class R:
        def search(self,*a,**kw): return backend.search(*a,**kw)
    ev=RetrievalEvaluator(R()).evaluate([{'query':'过滤器压差','expected_ids':['F1']}],top_k=3)
    assert ev['recall_at_k']==1.0 and ev['mrr']==1.0

def test_rca_case_promotes_to_knowledge(tmp_path):
    repo,_,backend,wf=stack(tmp_path); cases=RCACaseStore(repo)
    c=cases.create({'question':'单位能耗升高','subject':{'entity':'Machine','reference':'A1'}})
    cases.review(c['case_id'],{'accepted':True,'predicted_cause':'filter_restriction'})
    cases.resolve(c['case_id'],{'confirmed_root_cause':'filter_restriction','action':'replace_filter','comment':'恢复正常'})
    cand=wf.candidate_from_case(cases.get(c['case_id']))
    promoted=wf.promote_candidate(cand['candidate_id'])
    assert promoted['knowledge']['document']['source_case_id']==c['case_id']
    assert backend.search('filter_restriction')

def test_rca_similarity(tmp_path):
    repo,_,_,_=stack(tmp_path); cases=RCACaseStore(repo)
    c=cases.create({'question':'空压机过滤器压差高能耗上升','subject':{'entity':'Machine','reference':'A1'}})
    cases.resolve(c['case_id'],{'confirmed_root_cause':'filter_restriction','action':'replace filter','comment':'energy normal'})
    hits=RCASimilaritySearch(repo).search('过滤器压差 能耗',top_k=3)
    assert hits and hits[0]['case_id']==c['case_id']

def test_v12_api_version_and_workflow():
    from app.main import app
    client=TestClient(app)
    assert client.get('/health').json()['version']=='3.3.0'
