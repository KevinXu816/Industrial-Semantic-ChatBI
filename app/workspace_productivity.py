"""V4.1 工程师效率层：统一搜索、统一待办和快捷操作。"""
from __future__ import annotations
from typing import Any, Dict, List

class WorkspaceProductivityService:
    def __init__(self, asset_registry, asset_cockpit, rca_store, cmms_store, fmea_store, model_registry, connectors, edge_agents, repository=None):
        self.asset_registry=asset_registry; self.asset_cockpit=asset_cockpit; self.rca_store=rca_store; self.cmms_store=cmms_store
        self.fmea_store=fmea_store; self.model_registry=model_registry; self.connectors=connectors; self.edge_agents=edge_agents; self.repository=repository
    @staticmethod
    def _text(*values): return " ".join(str(v or "") for v in values).lower()
    @staticmethod
    def _safe_list(fn, **kwargs):
        try: return list(fn(**kwargs) or [])
        except Exception: return []
    def search(self, query:str, limit:int=20)->Dict[str,Any]:
        q=(query or "").strip().lower()
        if not q: return {"query":"","results":[],"total":0}
        results=[]
        for row in self._safe_list(self.asset_registry.list_assets, limit=5000):
            if q in self._text(row.get('asset_id'),row.get('name'),row.get('asset_type'),row.get('site_id')):
                results.append({"type":"asset","id":row.get('asset_id'),"title":row.get('name') or row.get('asset_id'),"subtitle":row.get('asset_type') or 'Asset',"panel":"assets","asset_id":row.get('asset_id'),"score":100})
        for row in self._safe_list(self.rca_store.list, limit=5000):
            subject=row.get('subject') or {}
            if q in self._text(row.get('case_id'),row.get('title'),row.get('confirmed_root_cause'),subject.get('reference')):
                results.append({"type":"rca","id":row.get('case_id'),"title":row.get('title') or row.get('case_id'),"subtitle":f"{subject.get('reference') or ''} · {row.get('status') or ''}".strip(' ·'),"panel":"rcaworkflow","case_id":row.get('case_id'),"asset_id":subject.get('reference'),"score":95})
        for row in self._safe_list(self.fmea_store.list, limit=5000):
            if q in self._text(row.get('fmea_id'),row.get('failure_mode'),row.get('cause'),row.get('component'),row.get('asset')):
                results.append({"type":"fmea","id":row.get('fmea_id'),"title":row.get('failure_mode') or row.get('fmea_id'),"subtitle":f"{row.get('asset') or ''} · {row.get('component') or ''}".strip(' ·'),"panel":"assets","asset_id":row.get('asset'),"score":90})
        for row in self._safe_list(self.cmms_store.list, limit=5000):
            if q in self._text(row.get('candidate_id'),row.get('asset'),row.get('recommended_action'),row.get('description'),row.get('priority')):
                results.append({"type":"work_order","id":row.get('candidate_id'),"title":row.get('recommended_action') or row.get('description') or row.get('candidate_id'),"subtitle":f"{row.get('asset') or ''} · {row.get('priority') or ''}".strip(' ·'),"panel":"assets","asset_id":row.get('asset'),"score":85})
        for row in self._safe_list(self.model_registry.list, limit=5000):
            if q in self._text(row.get('model_id'),row.get('name'),row.get('model_type'),row.get('version')):
                results.append({"type":"model","id":row.get('model_id'),"title":row.get('name') or row.get('model_id'),"subtitle":f"{row.get('model_type') or ''} · v{row.get('version') or ''}".strip(' ·v'),"panel":"modelops","score":70})
        results.sort(key=lambda x:(-int(x.get('score') or 0),str(x.get('title') or '')))
        results=results[:max(1,min(int(limit or 20),100))]
        return {"query":query,"results":results,"total":len(results)}
    def inbox(self, limit:int=30)->Dict[str,Any]:
        items=[]
        try: fleet=self.asset_cockpit.fleet(limit=5000).get('assets',[])
        except Exception: fleet=[]
        for row in fleet:
            risk=float(row.get('dynamic_risk') or 0)
            if row.get('health_class')=='critical' or risk>=80:
                items.append({"kind":"critical_asset","severity":"critical","panel":"assets","asset_id":row.get('asset_id'),"title":row.get('name') or row.get('asset_id'),"detail":f"Risk {risk:.0f} · {row.get('maintenance_priority') or 'P1'}"})
            elif row.get('risk_trend')=='deteriorating':
                items.append({"kind":"deteriorating_asset","severity":"warning","panel":"assets","asset_id":row.get('asset_id'),"title":row.get('name') or row.get('asset_id'),"detail":f"Risk trend deteriorating · {risk:.0f}"})
        for row in self._safe_list(self.rca_store.list, limit=5000):
            if row.get('status') not in {'resolved','closed'}:
                subject=row.get('subject') or {}
                items.append({"kind":"open_rca","severity":"warning","panel":"rcaworkflow","case_id":row.get('case_id'),"asset_id":subject.get('reference'),"title":row.get('title') or row.get('case_id'),"detail":f"RCA · {row.get('status')}"})
        for row in self._safe_list(self.cmms_store.list, limit=5000):
            if row.get('status') in {'draft','approved'}:
                items.append({"kind":"pending_work_order","severity":"info","panel":"assets","asset_id":row.get('asset'),"id":row.get('candidate_id'),"title":row.get('recommended_action') or row.get('description') or row.get('candidate_id'),"detail":f"{row.get('priority') or ''} · {row.get('status') or ''}".strip(' ·')})
        try:
            health=self.edge_agents.health()
            for row in health.get('agents',[]) if isinstance(health,dict) else []:
                if row.get('health') in {'stale','unknown'}:
                    items.append({"kind":"edge_agent","severity":"warning","panel":"bindings","id":row.get('agent_id'),"title":row.get('name') or row.get('agent_id'),"detail":f"Edge Agent · {row.get('health')}"})
        except Exception: pass
        rank={'critical':0,'warning':1,'info':2}; items.sort(key=lambda x:(rank.get(x.get('severity'),9),str(x.get('title') or '')))
        items=items[:max(1,min(int(limit or 30),200))]
        summary={"total":len(items),"critical":sum(1 for x in items if x.get('severity')=='critical'),"warning":sum(1 for x in items if x.get('severity')=='warning'),"info":sum(1 for x in items if x.get('severity')=='info')}
        return {"summary":summary,"items":items,"semantics":"Read-only unified work inbox derived from governed source-of-truth services."}
    @staticmethod
    def quick_actions():
        actions=[
            {"id":"open_workspace","label":"打开可靠性工作台","panel":"workspace","keywords":"workspace reliability home"},
            {"id":"open_assets","label":"打开资产可靠性","panel":"assets","keywords":"asset health reliability"},
            {"id":"open_rca","label":"打开 RCA 工作流","panel":"rcaworkflow","keywords":"rca root cause"},
            {"id":"open_benchmark","label":"打开同类设备对标","panel":"benchmark","keywords":"peer benchmark energy"},
            {"id":"open_collaboration","label":"打开团队协作","panel":"collaboration","keywords":"team collaboration assignee sla comments"},
            {"id":"open_reports","label":"打开运营班报","panel":"reports","keywords":"shift daily operations report supervisor"},
            {"id":"open_bindings","label":"打开数据绑定","panel":"bindings","keywords":"binding integration connector"},
            {"id":"open_pilot","label":"打开企业 Pilot","panel":"pilot","keywords":"pilot demo acceptance"},
            {"id":"open_sre","label":"打开可观测性 / SRE","panel":"observability","keywords":"sre observability metrics"},
            {"id":"open_admin","label":"打开系统管理","panel":"admin","keywords":"admin system settings"},
        ]
        return {"actions":actions}

    def _pref_key(self, principal_id: str) -> str:
        return (principal_id or "local-user").strip() or "local-user"

    def preferences(self, principal_id: str = "local-user") -> Dict[str, Any]:
        key=self._pref_key(principal_id)
        data=self.repository.get("workspace_preferences", key) if self.repository else None
        base={"principal_id":key,"favorites":[],"recent":[],"pinned_actions":[]}
        if isinstance(data,dict): base.update(data)
        return base

    def update_preferences(self, principal_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data=self.preferences(principal_id)
        for field in ("favorites","recent","pinned_actions"):
            if field in payload and isinstance(payload[field],list): data[field]=payload[field][:30]
        if self.repository: self.repository.put("workspace_preferences", self._pref_key(principal_id), data)
        return data

    def record_recent(self, principal_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
        data=self.preferences(principal_id); recent=[x for x in data.get("recent",[]) if not (x.get("type")==item.get("type") and x.get("id")==item.get("id"))]
        recent.insert(0,item); data["recent"]=recent[:12]
        if self.repository: self.repository.put("workspace_preferences", self._pref_key(principal_id), data)
        return data

    def toggle_favorite(self, principal_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
        data=self.preferences(principal_id); fav=list(data.get("favorites",[])); exists=next((i for i,x in enumerate(fav) if x.get("type")==item.get("type") and x.get("id")==item.get("id")),None)
        if exists is None: fav.insert(0,item)
        else: fav.pop(exists)
        data["favorites"]=fav[:20]
        if self.repository: self.repository.put("workspace_preferences", self._pref_key(principal_id), data)
        return data

    def personalized_home(self, role: str = "reliability_engineer", principal_id: str = "local-user", limit: int = 8) -> Dict[str, Any]:
        prefs=self.preferences(principal_id); inbox=self.inbox(limit=80); items=list(inbox.get("items",[]))
        role_order={
          "reliability_engineer":["critical_asset","deteriorating_asset","open_rca","pending_work_order","edge_agent"],
          "maintenance_planner":["pending_work_order","critical_asset","open_rca","deteriorating_asset","edge_agent"],
          "operator":["critical_asset","deteriorating_asset","edge_agent","open_rca","pending_work_order"],
        }.get(role,["critical_asset","open_rca","pending_work_order","deteriorating_asset","edge_agent"])
        rank={k:i for i,k in enumerate(role_order)}
        items.sort(key=lambda x:(rank.get(x.get("kind"),99), {"critical":0,"warning":1,"info":2}.get(x.get("severity"),9), str(x.get("title") or "")))
        focus=items[:max(1,min(int(limit or 8),20))]
        return {"role":role,"principal_id":principal_id,"focus":focus,"summary":inbox.get("summary",{}),"favorites":prefs.get("favorites",[]),"recent":prefs.get("recent",[]),"quick_actions":self.quick_actions().get("actions",[]),"semantics":"Role-aware ordering over live source-of-truth data; only user preferences are persisted."}


    @staticmethod
    def default_dashboard(role: str = "reliability_engineer") -> Dict[str, Any]:
        role_widgets={
            "reliability_engineer":["focus","inbox","fleet","recent","favorites","quick_actions"],
            "maintenance_planner":["focus","inbox","recent","fleet","quick_actions","favorites"],
            "operator":["focus","fleet","inbox","recent","quick_actions","favorites"],
        }
        widgets=role_widgets.get(role,role_widgets["reliability_engineer"])
        return {"role":role,"widgets":widgets,"compact":False,"version":1}

    def dashboard(self, principal_id: str = "local-user", role: str = "reliability_engineer") -> Dict[str, Any]:
        prefs=self.preferences(principal_id)
        configured=prefs.get("dashboard") if isinstance(prefs.get("dashboard"),dict) else None
        data=self.default_dashboard(role)
        if configured:
            data.update(configured)
            data["role"]=role
        data["available_widgets"]=["focus","inbox","fleet","recent","favorites","quick_actions"]
        return data

    def update_dashboard(self, principal_id: str, role: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        allowed={"focus","inbox","fleet","recent","favorites","quick_actions"}
        widgets=[x for x in payload.get("widgets",[]) if x in allowed]
        if not widgets: widgets=self.default_dashboard(role)["widgets"]
        prefs=self.preferences(principal_id)
        prefs["dashboard"]={"widgets":widgets,"compact":bool(payload.get("compact",False)),"version":1}
        if self.repository: self.repository.put("workspace_preferences", self._pref_key(principal_id), prefs)
        return self.dashboard(principal_id,role)

    def action_center(self, role: str = "reliability_engineer", principal_id: str = "local-user", limit: int = 20) -> Dict[str, Any]:
        inbox=self.inbox(limit=max(50,limit*3)); rows=[]
        for item in inbox.get("items",[]):
            kind=item.get("kind")
            steps=[]
            if kind in {"critical_asset","deteriorating_asset"}:
                steps=["查看资产健康与趋势","检查同工况 Peer Benchmark","如证据充分则进入 RCA"]
            elif kind=="open_rca":
                steps=["查看 RCA 证据","工程师确认根因","关联维护动作并跟踪闭环"]
            elif kind=="pending_work_order":
                steps=["复核维护优先级","确认维护窗口","审批后由 CMMS Adapter 下发"]
            elif kind=="edge_agent":
                steps=["查看 Edge Agent 心跳与诊断","检查 Connector / Binding 状态","恢复后验证增量 Cursor"]
            rows.append({**item,"recommended_steps":steps,"action_mode":"guided","requires_domain_approval":kind in {"open_rca","pending_work_order"}})
        prefs=self.preferences(principal_id)
        return {"role":role,"principal_id":principal_id,"summary":inbox.get("summary",{}),"actions":rows[:limit],"resume":(prefs.get("recent") or [])[:3],"semantics":"Guided orchestration only; domain mutations still require governed RCA/CMMS APIs."}

    def pin_action(self, principal_id: str, action_id: str) -> Dict[str, Any]:
        valid={x["id"] for x in self.quick_actions().get("actions",[])}
        if action_id not in valid: raise ValueError("unknown action_id")
        prefs=self.preferences(principal_id); pins=list(prefs.get("pinned_actions",[]))
        if action_id in pins: pins.remove(action_id)
        else: pins.insert(0,action_id)
        prefs["pinned_actions"]=pins[:8]
        if self.repository: self.repository.put("workspace_preferences",self._pref_key(principal_id),prefs)
        return prefs

    def context(self, asset_id: str = "", case_id: str = "") -> Dict[str, Any]:
        asset=None; rca=[]; fmea=[]; work_orders=[]
        if asset_id:
            try: asset=self.asset_registry.get_asset(asset_id)
            except Exception: asset=None
            rca=[x for x in self._safe_list(self.rca_store.list, limit=1000) if (x.get("subject") or {}).get("reference")==asset_id]
            fmea=[x for x in self._safe_list(self.fmea_store.list, limit=1000) if x.get("asset")==asset_id]
            work_orders=[x for x in self._safe_list(self.cmms_store.list, limit=1000) if x.get("asset")==asset_id]
        if case_id and not rca:
            rca=[x for x in self._safe_list(self.rca_store.list, limit=1000) if x.get("case_id")==case_id]
            if rca and not asset_id: asset_id=(rca[0].get("subject") or {}).get("reference") or ""
        links=[]
        if asset_id: links.append({"label":"资产可靠性","panel":"assets","asset_id":asset_id})
        if rca: links.append({"label":"RCA 工作流","panel":"rcaworkflow","case_id":rca[0].get("case_id"),"asset_id":asset_id})
        links.append({"label":"同类设备对标","panel":"benchmark","asset_id":asset_id})
        if work_orders: links.append({"label":"维护工单","panel":"assets","asset_id":asset_id})
        return {"asset_id":asset_id,"asset":asset,"rca":rca[:10],"fmea":fmea[:10],"work_orders":work_orders[:10],"links":links}

