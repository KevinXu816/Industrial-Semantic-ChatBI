from app.persistence import JsonRepository
from app.pilot_data_alignment import PilotDataAlignmentService


def test_asset_alias_and_timezone_normalization(tmp_path):
    repo=JsonRepository(str(tmp_path/'repo')); svc=PilotDataAlignmentService(repo)
    svc.upsert_asset_alias({'source_system':'mes','source_asset_id':'CMP-01','canonical_asset_id':'A101'})
    out=svc.normalize_records([{'asset_id':'CMP-01','timestamp':'2026-08-23T16:00:00+08:00','value':1}],source_system='mes')
    assert out['failed']==0
    assert out['records'][0]['asset_id']=='A101'
    assert out['records'][0]['timestamp']=='2026-08-23T08:00:00Z'


def test_series_alignment_excludes_stop_and_zero_production(tmp_path):
    svc=PilotDataAlignmentService(JsonRepository(str(tmp_path/'repo')))
    rows=[]
    for sensor,value in [('active_power',100),('production_output',50),('filter_dp',12),('discharge_temp',80),('load_pct',70)]:
        rows.append({'sensor':sensor,'value':value,'timestamp':'2026-08-23T08:01:00Z'})
    for sensor,value in [('active_power',30),('production_output',0),('filter_dp',10),('discharge_temp',60),('load_pct',5)]:
        rows.append({'sensor':sensor,'value':value,'timestamp':'2026-08-23T08:06:00Z'})
    out=svc.assess_series(rows,bucket_minutes=5)
    assert out['sensor_completeness']==1.0
    assert out['stopped_buckets_excluded_from_baseline']==1
    assert out['baseline_candidate_buckets']==1
    assert out['items'][0]['specific_energy']==2.0
    assert out['items'][1]['specific_energy'] is None
    assert out['ready_for_baseline'] is True


def test_series_alignment_detects_missing_sensor(tmp_path):
    svc=PilotDataAlignmentService(JsonRepository(str(tmp_path/'repo')))
    out=svc.assess_series([{'sensor':'active_power','value':100,'timestamp':'2026-08-23T08:01:00Z'}])
    assert 'production_output' in out['missing_sensors']
    assert out['ready_for_baseline'] is False


def test_failure_code_mapping(tmp_path):
    svc=PilotDataAlignmentService(JsonRepository(str(tmp_path/'repo')))
    row=svc.upsert_failure_code({'source_system':'cmms','source_code':'F-001','canonical_code':'FILTER_RESTRICTION','failure_mode':'Filter Restriction'})
    assert row['canonical_code']=='FILTER_RESTRICTION'
