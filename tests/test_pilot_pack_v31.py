from app.persistence import JsonRepository
from app.asset_reliability import AssetRegistry
from app.fmea import FMEAStore
from app.reliability_intelligence import FailureSensorMappingStore, ReliabilityIntelligenceService
from app.rca_cases import RCACaseStore
from app.pilot_pack import PilotPackService


def svc(tmp_path):
    repo=JsonRepository(str(tmp_path/'repo'))
    assets=AssetRegistry(repo); fmea=FMEAStore(repo); mappings=FailureSensorMappingStore(repo)
    reliability=ReliabilityIntelligenceService(repo,fmea,mappings); rca=RCACaseStore(repo)
    return PilotPackService(repo,assets,fmea,mappings,reliability,rca)


def test_bootstrap_is_idempotent_and_ready(tmp_path):
    s=svc(tmp_path)
    s.bootstrap('air-compressor-energy-maintenance')
    s.bootstrap('air-compressor-energy-maintenance')
    r=s.readiness()
    assert r['status']=='ready'
    assert r['checks']['approved_fmea'] is True


def test_synthetic_series_contains_degradation(tmp_path):
    s=svc(tmp_path); out=s.synthetic_series(48); pts=out['points']
    assert len(pts)==48
    assert pts[-1]['filter_dp'] > pts[0]['filter_dp']
    assert pts[-1]['specific_energy'] > pts[0]['specific_energy']


def test_demo_creates_assessment_and_rca(tmp_path):
    s=svc(tmp_path); out=s.run_demo()
    assert out['assessment']['top_risk']['cause_code']=='filter_restriction'
    assert out['rca_case']['status']=='analyzed'


def test_pilot_kpi_go_no_go(tmp_path):
    s=svc(tmp_path)
    vals={
      'data_onboarding_days':4,
      'rca_engineer_acceptance_rate':0.8,
      'rca_evidence_coverage':0.9,
      'maintenance_lead_time_reduction':0.25,
      'specific_energy_improvement':0.06,
    }
    for k,v in vals.items(): s.record_kpi({'kpi':k,'value':v})
    k=s.kpis(); assert k['measured']==5 and k['met']==5 and k['pilot_go'] is True
