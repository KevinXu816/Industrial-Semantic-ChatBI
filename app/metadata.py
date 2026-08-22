import os
from typing import List
from .models import MetadataCatalog, MetadataDatabase, MetadataTable, MetadataColumn, MetadataSnapshot


def _qid(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


class MockMetadataScanner:
    def scan(self, include_catalogs: List[str] | None = None) -> MetadataSnapshot:
        catalogs = [
            MetadataCatalog(
                name="internal",
                type="internal",
                databases=[MetadataDatabase(name="industrial_ai", tables=[
                    MetadataTable(name="energy_5min", columns=[
                        MetadataColumn(name="machine_id", data_type="VARCHAR", nullable=False),
                        MetadataColumn(name="ts", data_type="DATETIME", nullable=False),
                        MetadataColumn(name="active_power_kw", data_type="DOUBLE", nullable=True),
                        MetadataColumn(name="energy_kwh", data_type="DOUBLE", nullable=True),
                    ]),
                ])],
            ),
            MetadataCatalog(
                name="mysql_mes",
                type="jdbc:mysql",
                databases=[MetadataDatabase(name="production", tables=[
                    MetadataTable(name="device_master", columns=[
                        MetadataColumn(name="device_id", data_type="VARCHAR", nullable=False),
                        MetadataColumn(name="device_code", data_type="VARCHAR", nullable=False),
                        MetadataColumn(name="device_name", data_type="VARCHAR", nullable=True),
                        MetadataColumn(name="device_type", data_type="VARCHAR", nullable=True),
                        MetadataColumn(name="factory_id", data_type="VARCHAR", nullable=True),
                    ]),
                    MetadataTable(name="production_hourly", columns=[
                        MetadataColumn(name="device_id", data_type="VARCHAR", nullable=False),
                        MetadataColumn(name="stat_time", data_type="DATETIME", nullable=False),
                        MetadataColumn(name="good_qty", data_type="BIGINT", nullable=True),
                        MetadataColumn(name="total_qty", data_type="BIGINT", nullable=True),
                    ]),
                ])],
            ),
            MetadataCatalog(
                name="pg_cmms",
                type="jdbc:postgresql",
                databases=[MetadataDatabase(name="public", tables=[
                    MetadataTable(name="alarm_event", columns=[
                        MetadataColumn(name="id", data_type="BIGINT", nullable=False),
                        MetadataColumn(name="device_id", data_type="VARCHAR", nullable=False),
                        MetadataColumn(name="alarm_code", data_type="VARCHAR", nullable=True),
                        MetadataColumn(name="alarm_name", data_type="VARCHAR", nullable=True),
                        MetadataColumn(name="event_time", data_type="DATETIME", nullable=False),
                        MetadataColumn(name="severity", data_type="VARCHAR", nullable=True),
                    ]),
                    MetadataTable(name="work_order", columns=[
                        MetadataColumn(name="id", data_type="BIGINT", nullable=False),
                        MetadataColumn(name="device_id", data_type="VARCHAR", nullable=False),
                        MetadataColumn(name="created_at", data_type="DATETIME", nullable=False),
                        MetadataColumn(name="fault_desc", data_type="TEXT", nullable=True),
                        MetadataColumn(name="maintenance_action", data_type="TEXT", nullable=True),
                    ]),
                ])],
            ),
        ]
        if include_catalogs:
            wanted = set(include_catalogs)
            catalogs = [c for c in catalogs if c.name in wanted]
        return MetadataSnapshot(source="mock", catalogs=catalogs)


class DorisMetadataScanner:
    """Best-effort scanner over Doris Multi-Catalog metadata using SHOW statements."""

    def __init__(self):
        import pymysql
        self.pymysql = pymysql
        self.cfg = {
            "host": os.getenv("DORIS_HOST", "127.0.0.1"),
            "port": int(os.getenv("DORIS_PORT", "9030")),
            "user": os.getenv("DORIS_USER", "root"),
            "password": os.getenv("DORIS_PASSWORD", ""),
            "cursorclass": pymysql.cursors.DictCursor,
            "connect_timeout": int(os.getenv("DORIS_CONNECT_TIMEOUT", "5")),
            "read_timeout": int(os.getenv("DORIS_READ_TIMEOUT", "15")),
        }

    @staticmethod
    def _first_value(row: dict) -> str:
        return str(next(iter(row.values())))

    def scan(self, include_catalogs: List[str] | None = None) -> MetadataSnapshot:
        conn = self.pymysql.connect(**self.cfg)
        catalogs: List[MetadataCatalog] = []
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW CATALOGS")
                catalog_rows = cur.fetchall()
                for crow in catalog_rows:
                    name = str(crow.get("CatalogName") or crow.get("Catalog") or self._first_value(crow))
                    if include_catalogs and name not in set(include_catalogs):
                        continue
                    ctype = str(crow.get("Type") or crow.get("type") or "unknown")
                    databases: List[MetadataDatabase] = []
                    try:
                        cur.execute(f"SHOW DATABASES FROM {_qid(name)}")
                    except Exception:
                        # Some Doris versions prefer SWITCH + SHOW DATABASES; don't hide the catalog itself.
                        catalogs.append(MetadataCatalog(name=name, type=ctype, databases=[], scan_warning="Unable to enumerate databases"))
                        continue
                    for drow in cur.fetchall():
                        db = self._first_value(drow)
                        if db.lower() in {"information_schema", "mysql"}:
                            continue
                        tables: List[MetadataTable] = []
                        try:
                            cur.execute(f"SHOW TABLES FROM {_qid(name)}.{_qid(db)}")
                            trows = cur.fetchall()
                        except Exception:
                            databases.append(MetadataDatabase(name=db, tables=[], scan_warning="Unable to enumerate tables"))
                            continue
                        for trow in trows:
                            table = self._first_value(trow)
                            columns: List[MetadataColumn] = []
                            try:
                                cur.execute(f"DESC {_qid(name)}.{_qid(db)}.{_qid(table)}")
                                for col in cur.fetchall():
                                    col_name = str(col.get("Field") or col.get("field") or self._first_value(col))
                                    dtype = str(col.get("Type") or col.get("type") or "UNKNOWN")
                                    null_val = str(col.get("Null") or col.get("null") or "YES").upper()
                                    columns.append(MetadataColumn(
                                        name=col_name,
                                        data_type=dtype,
                                        nullable=(null_val != "NO"),
                                        comment=str(col.get("Comment") or col.get("comment") or "") or None,
                                    ))
                            except Exception:
                                pass
                            tables.append(MetadataTable(name=table, columns=columns))
                        databases.append(MetadataDatabase(name=db, tables=tables))
                    catalogs.append(MetadataCatalog(name=name, type=ctype, databases=databases))
        finally:
            conn.close()
        return MetadataSnapshot(source="doris", catalogs=catalogs)


def get_metadata_scanner():
    if os.getenv("METADATA_MODE", os.getenv("EXECUTION_MODE", "mock")).lower() == "doris":
        return DorisMetadataScanner()
    return MockMetadataScanner()
