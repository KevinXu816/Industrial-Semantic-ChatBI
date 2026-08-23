from app.persistence import JsonRepository
from app.asset_reliability import AssetRegistry
from app.fmea import FMEAStore
from app.reliability_intelligence import FailureSensorMappingStore, ReliabilityIntelligenceService
from app.rca_cases import RCACaseStore
from app.data_binding import DataBindingStore
from app.integration_runtime import IntegrationRuntimeService
from app.pilot_pack import PilotPackService
from app.pilot_delivery import PilotDeliveryService


def services(tmp_path):
    repo=JsonRepository(str(tmp_path/'repo'))
    assets=AssetRegistry(repo); fmea=FMEAStore(repo); mappings=FailureSensorMappingStore(repo)
    reliability=ReliabilityIntelligenceService(repo,fmea,mappings); rca=RCACaseStore(repo)
    bindings=DataBindingStore(repo); runtime=IntegrationRuntimeService(repo,bindings)
    pilot=PilotPackService(repo,assets,fmea,mappings,reliability,rca)
    delivery=PilotDeliveryService(repo,bindings,runtime,rca)
    return repo,pilot,delivery,bindings


def test_data_contract_and_binding_blueprints(tmp_path):
    _,_,delivery,bindings=services(tmp_path)
    contract=delivery.data_contract()
    assert len(contract['bindings']) == 5
    out=delivery.prepare_bindings({'site_id':'F01'})
    assert len(out['bindings']) == 5
    assert delivery.onboarding_status()['configured'] == 5
    assert delivery.onboarding_status()['approved'] == 0
    for row in bindings.list(limit=20): bindings.approve(row['binding_id'])
    assert delivery.onboarding_status()['ready_for_customer_data'] is True


def test_structured_rca_evidence_quality(tmp_path):
    _,pilot,delivery,_=services(tmp_path)
    out=pilot.run_demo()
    q=delivery.evidence_quality(out['rca_case'])
    assert q['evidence_count'] >= 5
    assert q['quality_pass'] is True
    assert 'fmea' in q['categories'] and 'sensor' in q['categories']


def test_report_requires_bindings_and_business_kpis(tmp_path):
    _,pilot,delivery,bindings=services(tmp_path)
    pilot.bootstrap('air-compressor-energy-maintenance')
    pilot.run_demo()
    delivery.prepare_bindings({'site_id':'F01'})
    vals={'data_onboarding_days':4,'rca_engineer_acceptance_rate':0.8,'rca_evidence_coverage':0.9,'maintenance_lead_time_reduction':0.25,'specific_energy_improvement':0.06}
    for k,v in vals.items(): pilot.record_kpi({'kpi':k,'value':v})
    r=delivery.report(pilot.readiness(),pilot.kpis())
    assert r['decision']=='NO_GO'
    for row in bindings.list(limit=20): bindings.approve(row['binding_id'])
    r=delivery.report(pilot.readiness(),pilot.kpis())
    assert r['decision']=='GO'
    assert 'Enterprise Pilot Acceptance Report' in delivery.report_markdown(pilot.readiness(),pilot.kpis())
