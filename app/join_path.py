"""Automatic JOIN path discovery between entities via relationships."""
from typing import List, Optional, Tuple
from collections import deque


class JoinPathFinder:
    """Find shortest JOIN path between two entities using ontology relationships."""

    def __init__(self, ontology: dict):
        self.graph = self._build_graph(ontology)

    def _build_graph(self, ontology: dict) -> dict:
        """Build adjacency list from relationships."""
        g = {}
        for rel in ontology.get("relationships", []):
            f, t = rel["from"], rel["to"]
            if f not in g:
                g[f] = []
            if t not in g:
                g[t] = []
            g[f].append({"to": t, "relation": rel.get("relation", ""), "on": rel.get("on", "")})
            g[t].append({"to": f, "relation": rel.get("relation", "") + "_INV", "on": rel.get("on", "")})
        return g

    def find_path(self, source: str, target: str, max_hops: int = 4) -> Optional[List[dict]]:
        """BFS to find shortest path from source to target entity."""
        if source == target:
            return []
        if source not in self.graph or target not in self.graph:
            return None
        visited = {source}
        queue = deque([(source, [])])
        while queue:
            current, path = queue.popleft()
            if len(path) >= max_hops:
                continue
            for edge in self.graph.get(current, []):
                neighbor = edge["to"]
                if neighbor in visited:
                    continue
                new_path = path + [{"from": current, "to": neighbor, "relation": edge["relation"], "on": edge["on"]}]
                if neighbor == target:
                    return new_path
                visited.add(neighbor)
                queue.append((neighbor, new_path))
        return None

    def find_all_paths(self, source: str, targets: List[str]) -> dict:
        """Find paths to multiple targets."""
        results = {}
        for t in targets:
            path = self.find_path(source, t)
            results[t] = path
        return results

    def generate_join_sql(self, path: List[dict], ontology: dict) -> str:
        """Generate JOIN clause from a path."""
        if not path:
            return ""
        entities = ontology.get("entities", {})
        joins = []
        for step in path:
            to_entity = entities.get(step["to"], {})
            pm = to_entity.get("physical_mapping", {})
            table_ref = f"{pm.get('catalog','')}.{pm.get('schema','')}.{pm.get('table','')}"
            join_field = step["on"]
            from_entity = entities.get(step["from"], {})
            from_pm = from_entity.get("physical_mapping", {})
            from_col = from_pm.get("columns", {}).get(join_field, join_field)
            to_col = pm.get("columns", {}).get(join_field, join_field)
            joins.append(f"JOIN {table_ref} ON {from_col} = {to_col}")
        return " ".join(joins)
