"""Small governed industrial causal model used by the demo and tests."""
from .industrial_knowledge_graph import IndustrialKnowledgeGraph

def bootstrap_graph(graph:IndustrialKnowledgeGraph):
    if graph.nodes(limit=1): return
    f=graph.upsert_node("FailureMode","过滤器阻力增加/堵塞",{"cause_code":"filter_restriction"})
    c=graph.upsert_node("Component","Air Filter")
    a=graph.upsert_node("Alarm","High Differential Pressure")
    s=graph.upsert_node("SensorPattern","filter differential pressure rising")
    r=graph.upsert_node("MaintenanceAction","replace air filter")
    graph.upsert_edge(f["id"],c["id"],"CAUSED_BY",provenance="FMEA-AIR-001@1.0")
    graph.upsert_edge(f["id"],a["id"],"INDICATED_BY",provenance="FMEA-AIR-001@1.0")
    graph.upsert_edge(f["id"],s["id"],"DETECTED_BY",provenance="FMEA-AIR-001@1.0")
    graph.upsert_edge(f["id"],r["id"],"RESOLVED_BY",provenance="SOP-AIR-017@1.0")
