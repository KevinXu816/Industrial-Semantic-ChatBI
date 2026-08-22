"""Configuration export/import and credential encryption."""
import base64
import json
import os
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]

# Simple reversible obfuscation for stored passwords (not cryptographically secure,
# but prevents plaintext exposure in JSON files). For production, use a proper vault.
_KEY = os.getenv("CHATBI_SECRET_KEY", "chatbi-demo-key-2024").encode()


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def encrypt_password(plaintext: str) -> str:
    if not plaintext:
        return ""
    encrypted = _xor_bytes(plaintext.encode("utf-8"), _KEY)
    return "enc:" + base64.b64encode(encrypted).decode()


def decrypt_password(stored: str) -> str:
    if not stored:
        return ""
    if not stored.startswith("enc:"):
        return stored  # legacy plaintext
    encrypted = base64.b64decode(stored[4:])
    return _xor_bytes(encrypted, _KEY).decode("utf-8")


def export_config() -> Dict[str, Any]:
    """Export all configuration as a single JSON structure."""
    import yaml
    result = {}

    # Ontology
    ontology_path = ROOT / "config" / "ontology.yaml"
    if ontology_path.exists():
        result["ontology"] = yaml.safe_load(ontology_path.read_text(encoding="utf-8"))

    # Custom ontology
    custom_ont = ROOT / "config" / "custom_ontology.yaml"
    if custom_ont.exists():
        result["custom_ontology"] = yaml.safe_load(custom_ont.read_text(encoding="utf-8"))

    # Metrics
    metrics_path = ROOT / "config" / "metrics.yaml"
    if metrics_path.exists():
        result["metrics"] = yaml.safe_load(metrics_path.read_text(encoding="utf-8"))

    # Custom metrics
    custom_met = ROOT / "config" / "custom_metrics.yaml"
    if custom_met.exists():
        result["custom_metrics"] = yaml.safe_load(custom_met.read_text(encoding="utf-8"))

    # Approved semantic
    approved = ROOT / "config" / "approved_semantic.yaml"
    if approved.exists():
        result["approved_semantic"] = yaml.safe_load(approved.read_text(encoding="utf-8"))

    # Datasources (mask passwords)
    ds_path = ROOT / "data" / "datasources.json"
    if ds_path.exists():
        ds = json.loads(ds_path.read_text(encoding="utf-8"))
        for k, v in ds.items():
            v["password"] = "***"
        result["datasources"] = ds

    # LLM config (mask key)
    llm_path = ROOT / "data" / "llm_config.json"
    if llm_path.exists():
        llm = json.loads(llm_path.read_text(encoding="utf-8"))
        llm["api_key"] = "***"
        result["llm_config"] = llm

    # Candidates
    reviews_path = ROOT / "data" / "semantic_reviews.json"
    if reviews_path.exists():
        result["candidates"] = json.loads(reviews_path.read_text(encoding="utf-8"))

    return result


def import_config(config: Dict[str, Any]) -> Dict[str, str]:
    """Import configuration. Returns summary of what was imported."""
    import yaml
    imported = []

    if "ontology" in config:
        path = ROOT / "config" / "ontology.yaml"
        path.write_text(yaml.dump(config["ontology"], allow_unicode=True, default_flow_style=False), encoding="utf-8")
        imported.append("ontology")

    if "custom_ontology" in config:
        path = ROOT / "config" / "custom_ontology.yaml"
        path.write_text(yaml.dump(config["custom_ontology"], allow_unicode=True, default_flow_style=False), encoding="utf-8")
        imported.append("custom_ontology")

    if "metrics" in config:
        path = ROOT / "config" / "metrics.yaml"
        path.write_text(yaml.dump(config["metrics"], allow_unicode=True, default_flow_style=False), encoding="utf-8")
        imported.append("metrics")

    if "custom_metrics" in config:
        path = ROOT / "config" / "custom_metrics.yaml"
        path.write_text(yaml.dump(config["custom_metrics"], allow_unicode=True, default_flow_style=False), encoding="utf-8")
        imported.append("custom_metrics")

    if "approved_semantic" in config:
        path = ROOT / "config" / "approved_semantic.yaml"
        path.write_text(yaml.dump(config["approved_semantic"], allow_unicode=True, default_flow_style=False), encoding="utf-8")
        imported.append("approved_semantic")

    if "candidates" in config:
        path = ROOT / "data" / "semantic_reviews.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config["candidates"], ensure_ascii=False, indent=2), encoding="utf-8")
        imported.append("candidates")

    # Note: datasources and llm_config passwords are masked in export, so we skip import
    # unless full credentials are provided
    if "datasources" in config:
        ds = config["datasources"]
        has_real_pw = all(v.get("password", "***") != "***" for v in ds.values())
        if has_real_pw:
            path = ROOT / "data" / "datasources.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(ds, ensure_ascii=False, indent=2), encoding="utf-8")
            imported.append("datasources")

    return {"imported": imported, "count": len(imported)}
