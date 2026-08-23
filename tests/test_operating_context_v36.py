from pathlib import Path
from app.persistence import JsonRepository
from app.operating_context import OperatingContextService


def test_comparable_context_baseline(tmp_path: Path):
    svc=OperatingContextService(JsonRepository(tmp_path))
    history=[
      {"load_pct":80,"production_output":100,"ambient_temp":28,"shift":"A","product_type":"P1","operating_mode":"auto","specific_energy":10.0},
      {"load_pct":82,"production_output":102,"ambient_temp":29,"shift":"B","product_type":"P1","operating_mode":"auto","specific_energy":10.2},
      {"load_pct":78,"production_output":98,"ambient_temp":27,"shift":"A","product_type":"P1","operating_mode":"auto","specific_energy":9.8},
      {"load_pct":30,"production_output":40,"ambient_temp":28,"shift":"A","product_type":"P1","operating_mode":"auto","specific_energy":15.0},
      {"load_pct":81,"production_output":100,"ambient_temp":28,"shift":"A","product_type":"P2","operating_mode":"auto","specific_energy":12.0},
    ]
    out=svc.assess({"current":{"load_pct":80,"production_output":100,"ambient_temp":28,"shift":"A","product_type":"P1","operating_mode":"auto","specific_energy":12.0},"history":history})
    assert out["comparable_count"]==3
    assert out["baseline_median"]==10.0
    assert out["normalized_deviation_pct"]==20.0
    assert out["ready_for_rca"] is True


def test_insufficient_context_blocks_rca(tmp_path: Path):
    svc=OperatingContextService(JsonRepository(tmp_path))
    out=svc.assess({"current":{"load_pct":80,"product_type":"P1","operating_mode":"auto","specific_energy":12},"history":[{"load_pct":80,"product_type":"P2","operating_mode":"auto","specific_energy":10}]})
    assert out["comparison_quality"]=="insufficient"
    assert out["ready_for_rca"] is False
