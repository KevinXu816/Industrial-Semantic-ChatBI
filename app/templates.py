"""Industry templates for quick semantic model initialization."""

TEMPLATES = {
    "manufacturing": {
        "name": "制造业通用",
        "description": "适用于离散制造、流程制造企业，包含设备、能耗、产量、告警、工单等核心实体",
        "entities": {
            "Machine": {
                "description": "生产设备/资产",
                "properties": {"machine_id": {"type": "string"}, "machine_code": {"type": "string"}, "machine_name": {"type": "string"}, "machine_type": {"type": "string"}, "workshop": {"type": "string"}},
            },
            "EnergyObservation": {
                "description": "设备能耗采集数据",
                "properties": {"machine_id": {"type": "string"}, "ts": {"type": "datetime"}, "active_power_kw": {"type": "number"}, "energy_kwh": {"type": "number"}},
            },
            "ProductionRecord": {
                "description": "生产记录/产量数据",
                "properties": {"machine_id": {"type": "string"}, "ts": {"type": "datetime"}, "output_qty": {"type": "number"}, "defect_qty": {"type": "number"}},
            },
            "AlarmEvent": {
                "description": "设备告警/故障事件",
                "properties": {"alarm_id": {"type": "string"}, "machine_id": {"type": "string"}, "alarm_code": {"type": "string"}, "alarm_name": {"type": "string"}, "event_time": {"type": "datetime"}, "severity": {"type": "string"}},
            },
            "WorkOrder": {
                "description": "维修/保养工单",
                "properties": {"work_order_id": {"type": "string"}, "machine_id": {"type": "string"}, "created_at": {"type": "datetime"}, "fault_description": {"type": "string"}, "action": {"type": "string"}},
            },
        },
        "relationships": [
            {"from": "Machine", "relation": "HAS_ENERGY", "to": "EnergyObservation", "on": "machine_id"},
            {"from": "Machine", "relation": "HAS_PRODUCTION", "to": "ProductionRecord", "on": "machine_id"},
            {"from": "Machine", "relation": "HAS_ALARM", "to": "AlarmEvent", "on": "machine_id"},
            {"from": "Machine", "relation": "HAS_WORK_ORDER", "to": "WorkOrder", "on": "machine_id"},
        ],
        "metrics": {
            "energy_consumption": {"description": "设备总能耗", "expression": "SUM(energy_kwh)", "unit": "kWh", "synonyms": ["能耗", "耗电", "电量"]},
            "production_output": {"description": "总产量", "expression": "SUM(output_qty)", "unit": "件", "synonyms": ["产量", "产出"]},
            "specific_energy": {"description": "单位产量能耗", "expression": "SUM(energy_kwh)/NULLIF(SUM(output_qty),0)", "unit": "kWh/件", "synonyms": ["单耗", "单位能耗"]},
            "oee": {"description": "设备综合效率", "expression": "availability * performance * quality", "unit": "%", "synonyms": ["OEE", "设备效率"]},
            "alarm_count": {"description": "告警次数", "expression": "COUNT(*)", "unit": "次", "synonyms": ["报警次数", "告警数"]},
        },
        "aliases": {"设备编号": "machine_code", "资产编号": "machine_code", "设备名称": "machine_name", "车间": "workshop"},
    },
    "energy": {
        "name": "能源管理",
        "description": "适用于能源管理系统，包含计量表、能耗数据、费用统计等",
        "entities": {
            "EnergyMeter": {
                "description": "能源计量表（电表/水表/气表）",
                "properties": {"meter_id": {"type": "string"}, "meter_name": {"type": "string"}, "meter_type": {"type": "string"}, "location": {"type": "string"}, "rated_capacity": {"type": "number"}},
            },
            "EnergyReading": {
                "description": "表计读数/采集数据",
                "properties": {"meter_id": {"type": "string"}, "ts": {"type": "datetime"}, "reading": {"type": "number"}, "consumption": {"type": "number"}, "demand_kw": {"type": "number"}},
            },
            "EnergyCost": {
                "description": "能源费用统计",
                "properties": {"meter_id": {"type": "string"}, "period": {"type": "string"}, "cost": {"type": "number"}, "tariff_type": {"type": "string"}},
            },
            "CarbonEmission": {
                "description": "碳排放记录",
                "properties": {"source_id": {"type": "string"}, "ts": {"type": "datetime"}, "co2_kg": {"type": "number"}, "emission_factor": {"type": "number"}},
            },
        },
        "relationships": [
            {"from": "EnergyMeter", "relation": "HAS_READING", "to": "EnergyReading", "on": "meter_id"},
            {"from": "EnergyMeter", "relation": "HAS_COST", "to": "EnergyCost", "on": "meter_id"},
        ],
        "metrics": {
            "total_consumption": {"description": "总能耗", "expression": "SUM(consumption)", "unit": "kWh", "synonyms": ["总用电", "总能耗"]},
            "peak_demand": {"description": "最大需量", "expression": "MAX(demand_kw)", "unit": "kW", "synonyms": ["最大负荷", "峰值"]},
            "energy_cost": {"description": "能源费用", "expression": "SUM(cost)", "unit": "元", "synonyms": ["电费", "能源费"]},
            "carbon_total": {"description": "碳排放总量", "expression": "SUM(co2_kg)", "unit": "kg", "synonyms": ["碳排放", "CO2"]},
        },
        "aliases": {"电表": "meter_name", "计量点": "meter_name", "位置": "location"},
    },
    "logistics": {
        "name": "仓储物流",
        "description": "适用于仓储和物流管理，包含库存、出入库、运输等",
        "entities": {
            "Warehouse": {
                "description": "仓库/库位",
                "properties": {"warehouse_id": {"type": "string"}, "warehouse_name": {"type": "string"}, "location": {"type": "string"}, "capacity": {"type": "number"}},
            },
            "InventoryItem": {
                "description": "库存物料",
                "properties": {"item_id": {"type": "string"}, "item_name": {"type": "string"}, "warehouse_id": {"type": "string"}, "quantity": {"type": "number"}, "unit": {"type": "string"}},
            },
            "StockMovement": {
                "description": "出入库记录",
                "properties": {"movement_id": {"type": "string"}, "item_id": {"type": "string"}, "direction": {"type": "string"}, "quantity": {"type": "number"}, "ts": {"type": "datetime"}},
            },
        },
        "relationships": [
            {"from": "Warehouse", "relation": "STORES", "to": "InventoryItem", "on": "warehouse_id"},
            {"from": "InventoryItem", "relation": "HAS_MOVEMENT", "to": "StockMovement", "on": "item_id"},
        ],
        "metrics": {
            "total_inventory": {"description": "总库存量", "expression": "SUM(quantity)", "unit": "件", "synonyms": ["库存", "存量"]},
            "inbound_qty": {"description": "入库量", "expression": "SUM(CASE WHEN direction='IN' THEN quantity END)", "unit": "件", "synonyms": ["入库", "收货"]},
            "outbound_qty": {"description": "出库量", "expression": "SUM(CASE WHEN direction='OUT' THEN quantity END)", "unit": "件", "synonyms": ["出库", "发货"]},
        },
        "aliases": {"物料": "item_name", "仓库": "warehouse_name"},
    },
}


def list_templates():
    return [{"id": k, "name": v["name"], "description": v["description"], "entities": len(v["entities"]), "metrics": len(v["metrics"])} for k, v in TEMPLATES.items()]


def get_template(template_id: str):
    return TEMPLATES.get(template_id)
