"""Persistence abstraction for Enterprise Pilot.

Default backend is JSON for zero-dependency demos. PostgreSQL is enabled with
PERSISTENCE_BACKEND=postgres and DATABASE_URL/PG* environment variables.
"""
from __future__ import annotations
import json, os, threading
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]

class Repository:
    def put(self, collection: str, key: str, value: Dict[str, Any]) -> Dict[str, Any]: raise NotImplementedError
    def get(self, collection: str, key: str) -> Optional[Dict[str, Any]]: raise NotImplementedError
    def list(self, collection: str, limit: int = 100) -> List[Dict[str, Any]]: raise NotImplementedError
    def delete(self, collection: str, key: str) -> bool: raise NotImplementedError
    def health(self) -> Dict[str, Any]: raise NotImplementedError

class JsonRepository(Repository):
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else ROOT / "data" / "repository"
        self.root.mkdir(parents=True, exist_ok=True); self.lock = threading.RLock()
    def _path(self, collection): return self.root / f"{collection}.json"
    def _load(self, collection):
        p = self._path(collection)
        if not p.exists(): return {}
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: return {}
    def _save(self, collection, data):
        p = self._path(collection); tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"); tmp.replace(p)
    def put(self, collection, key, value):
        with self.lock:
            data=self._load(collection); data[str(key)]=value; self._save(collection,data); return value
    def get(self, collection, key): return self._load(collection).get(str(key))
    def list(self, collection, limit=100):
        rows=list(self._load(collection).values()); rows.sort(key=lambda x:str(x.get("updated_at",x.get("created_at",""))), reverse=True)
        return rows[:max(1,min(int(limit),1000))]
    def delete(self, collection, key):
        with self.lock:
            data=self._load(collection)
            if str(key) not in data: return False
            del data[str(key)]; self._save(collection,data); return True
    def health(self): return {"backend":"json","status":"ok","path":str(self.root)}

class PostgresRepository(Repository):
    """Generic JSONB repository. Requires psycopg>=3 when selected."""
    def __init__(self, dsn: str | None = None):
        try: import psycopg
        except ImportError as exc: raise RuntimeError("PostgreSQL backend requires: pip install -e '.[postgres]'") from exc
        self.psycopg=psycopg; self.dsn=dsn or os.getenv("DATABASE_URL") or self._dsn_from_env(); self._ensure_schema()
    @staticmethod
    def _dsn_from_env():
        return "host={host} port={port} dbname={db} user={user} password={pw}".format(
            host=os.getenv("PGHOST","127.0.0.1"), port=os.getenv("PGPORT","5432"), db=os.getenv("PGDATABASE","industrial_semantic"),
            user=os.getenv("PGUSER","industrial_semantic"), pw=os.getenv("PGPASSWORD","industrial_semantic"))
    def _connect(self): return self.psycopg.connect(self.dsn)
    def _ensure_schema(self):
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS platform_documents(
              collection text NOT NULL, key text NOT NULL, payload jsonb NOT NULL,
              created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
              PRIMARY KEY(collection,key))"""); conn.commit()
    def put(self, collection,key,value):
        from psycopg.types.json import Jsonb
        with self._connect() as conn:
            conn.execute("""INSERT INTO platform_documents(collection,key,payload) VALUES(%s,%s,%s)
              ON CONFLICT(collection,key) DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()""",(collection,str(key),Jsonb(value))); conn.commit()
        return value
    def get(self, collection,key):
        with self._connect() as conn:
            row=conn.execute("SELECT payload FROM platform_documents WHERE collection=%s AND key=%s",(collection,str(key))).fetchone()
            return row[0] if row else None
    def list(self, collection,limit=100):
        with self._connect() as conn:
            rows=conn.execute("SELECT payload FROM platform_documents WHERE collection=%s ORDER BY updated_at DESC LIMIT %s",(collection,max(1,min(int(limit),1000)))).fetchall()
            return [r[0] for r in rows]
    def delete(self, collection,key):
        with self._connect() as conn:
            cur=conn.execute("DELETE FROM platform_documents WHERE collection=%s AND key=%s",(collection,str(key))); conn.commit(); return cur.rowcount>0
    def health(self):
        try:
            with self._connect() as conn: conn.execute("SELECT 1").fetchone()
            return {"backend":"postgres","status":"ok"}
        except Exception as exc: return {"backend":"postgres","status":"error","error":str(exc)}

def get_repository() -> Repository:
    backend=os.getenv("PERSISTENCE_BACKEND","json").lower()
    return PostgresRepository() if backend in {"postgres","postgresql"} else JsonRepository()
