from app.persistence import JsonRepository
from app.data_binding import DataBindingStore
from app.integration_runtime import IntegrationRuntimeService
from app.pilot_validation import PilotCustomerDataValidator


def test_customer_data_validation_and_dry_run(tmp_path):
    repo=JsonRepository(str(tmp_path/'repo')); bindings=DataBindingStore(repo); runtime=IntegrationRuntimeService(repo,bindings)
    b=bindings.upsert({'name':'IoT','source_type':'influxdb','source_id':'iot_condition_series','target':'condition_series','mappings':{'asset_id':'device_id','sensor':'tag','value':'value','timestamp':'event_time'}})
    v=PilotCustomerDataValidator(repo,bindings,runtime)
    rows=[{'device_id':'A101','tag':'filter_dp','value':12.3,'event_time':'2026-08-23T08:00:00Z'} for _ in range(10)]
    out=v.validate(b['binding_id'],rows)
    assert out['ready_for_approval'] is True
    assert out['readiness_score'] == 100
    dry=v.dry_run(b['binding_id'],rows)
    assert dry['write_performed'] is False
    assert len(dry['preview']['records']) == 10


def test_customer_data_validation_detects_bad_mapping(tmp_path):
    repo=JsonRepository(str(tmp_path/'repo')); bindings=DataBindingStore(repo); runtime=IntegrationRuntimeService(repo,bindings)
    b=bindings.upsert({'name':'MES','source_type':'mysql','source_id':'asset_master','target':'asset','mappings':{'asset_id':'equipment_code','name':'equipment_name'}})
    v=PilotCustomerDataValidator(repo,bindings,runtime)
    out=v.validate(b['binding_id'],[{'wrong_code':'A101','equipment_name':'Compressor'}])
    assert out['ready_for_approval'] is False
    assert 'equipment_code' in out['missing_source_fields']
