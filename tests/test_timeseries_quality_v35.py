from app.persistence import JsonRepository
from app.pilot_timeseries_quality import PilotTimeSeriesQualityService


def svc(tmp_path):
    return PilotTimeSeriesQualityService(JsonRepository(str(tmp_path / "repo")))


def test_gap_frozen_late_and_shift_detection(tmp_path):
    s = svc(tmp_path)
    s.upsert_policy({"policy_id":"p1","expected_interval_seconds":60,"gap_factor":2,"frozen_min_points":4,"late_arrival_seconds":300})
    rows = [
        {"sensor":"temp","value":10,"timestamp":"2026-08-23T00:00:00Z","received_at":"2026-08-23T00:00:05Z"},
        {"sensor":"temp","value":10,"timestamp":"2026-08-23T00:01:00Z","received_at":"2026-08-23T00:01:05Z"},
        {"sensor":"temp","value":10,"timestamp":"2026-08-23T00:02:00Z","received_at":"2026-08-23T00:02:05Z"},
        {"sensor":"temp","value":10,"timestamp":"2026-08-23T00:03:00Z","received_at":"2026-08-23T00:20:00Z"},
        {"sensor":"temp","value":12,"timestamp":"2026-08-23T00:10:00Z","received_at":"2026-08-23T00:10:05Z"},
    ]
    out=s.assess(rows,policy_id="p1")
    assert len(out["gaps"]) == 1
    assert len(out["frozen_segments"]) == 1
    assert len(out["late_arrivals"]) == 1
    assert out["ready_for_baseline"] is False
    assert out["reconciled_records"][0]["shift"].startswith("shift-1")


def test_counter_reset_and_outlier(tmp_path):
    s=svc(tmp_path)
    s.upsert_policy({"policy_id":"p2","outlier_mad_z":3,"expected_interval_seconds":60})
    rows=[
        {"sensor":"energy_total","value":100,"counter":True,"timestamp":"2026-08-23T08:00:00Z"},
        {"sensor":"energy_total","value":110,"counter":True,"timestamp":"2026-08-23T08:01:00Z"},
        {"sensor":"energy_total","value":5,"counter":True,"timestamp":"2026-08-23T08:02:00Z"},
        {"sensor":"temp","value":10,"timestamp":"2026-08-23T08:00:00Z"},
        {"sensor":"temp","value":11,"timestamp":"2026-08-23T08:01:00Z"},
        {"sensor":"temp","value":10,"timestamp":"2026-08-23T08:02:00Z"},
        {"sensor":"temp","value":80,"timestamp":"2026-08-23T08:03:00Z"},
    ]
    out=s.assess(rows,policy_id="p2")
    assert len(out["counter_resets"]) == 1
    assert len(out["outliers"]) >= 1


def test_clock_drift_is_distinct_from_late_arrival(tmp_path):
    s=svc(tmp_path)
    s.upsert_policy({"policy_id":"p3","clock_drift_seconds":30,"late_arrival_seconds":300})
    rows=[
        {"sensor":"power","value":10,"timestamp":"2026-08-23T08:00:00Z", "source_clock_at":"2026-08-23T08:02:00Z", "received_at":"2026-08-23T08:00:00Z"},
        {"sensor":"power","value":11,"timestamp":"2026-08-23T08:01:00Z", "received_at":"2026-08-23T08:20:00Z"},
    ]
    out=s.assess(rows,policy_id="p3")
    assert len(out["clock_drift"]) == 1
    assert len(out["late_arrivals"]) == 1


def test_maintenance_window_excluded_from_baseline(tmp_path):
    s=svc(tmp_path)
    s.add_maintenance_window({"asset_id":"A101","start":"2026-08-23T08:00:00Z","end":"2026-08-23T09:00:00Z","reason":"replace filter"})
    out=s.assess([
        {"sensor":"filter_dp","value":12,"timestamp":"2026-08-23T08:30:00Z"},
        {"sensor":"filter_dp","value":13,"timestamp":"2026-08-23T09:30:00Z"},
    ],asset_id="A101")
    assert out["maintenance_records_excluded"] == 1
    assert out["reconciled_records"][0]["baseline_eligible"] is False
    assert out["reconciled_records"][1]["baseline_eligible"] is True
