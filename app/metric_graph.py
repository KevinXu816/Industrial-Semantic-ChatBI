"""Metric dependency graph and governed expression compilation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Set


@dataclass(frozen=True)
class MetricNode:
    name: str
    config: dict


class MetricDependencyGraph:
    """Resolve derived metrics into leaf metrics with cycle detection."""

    def __init__(self, metrics: dict):
        self.metrics: Dict[str, dict] = metrics.get("metrics", metrics)

    def get(self, name: str) -> dict:
        if name not in self.metrics:
            raise KeyError(f"Unknown governed metric: {name}")
        return self.metrics[name]

    def dependencies(self, name: str) -> List[str]:
        return list(self.get(name).get("dependencies") or [])

    def ordered(self, name: str) -> List[str]:
        """Return dependencies first and requested metric last."""
        ordered: List[str] = []
        temporary: Set[str] = set()
        permanent: Set[str] = set()

        def visit(metric_name: str):
            if metric_name in permanent:
                return
            if metric_name in temporary:
                raise ValueError(f"Metric dependency cycle detected at: {metric_name}")
            temporary.add(metric_name)
            for dep in self.dependencies(metric_name):
                visit(dep)
            temporary.remove(metric_name)
            permanent.add(metric_name)
            ordered.append(metric_name)

        visit(name)
        return ordered

    def leaves(self, name: str) -> List[str]:
        return [m for m in self.ordered(name) if not self.dependencies(m)]

    def entities(self, name: str) -> List[str]:
        entities: List[str] = []
        for metric_name in self.ordered(name):
            entity = self.get(metric_name).get("entity")
            if entity and entity not in entities:
                entities.append(entity)
        return entities

    def derived_expression(self, name: str, aliases: Dict[str, str]) -> str:
        """Compile a derived metric expression by replacing governed metric names only."""
        cfg = self.get(name)
        expression = str(cfg.get("expression") or "").strip()
        if not expression:
            raise ValueError(f"Metric {name} has no expression")
        for dep in sorted(self.dependencies(name), key=len, reverse=True):
            if dep not in aliases:
                raise ValueError(f"Missing dependency alias for {dep}")
            expression = re.sub(rf"\b{re.escape(dep)}\b", aliases[dep], expression)
        return expression
