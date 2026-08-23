"""V4.7 班报 / 日报与运营摘要。

报告层只聚合已有 Source of Truth，不复制 RCA/CMMS/协作领域状态。
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
import uuid

UTC = timezone.utc


def _now():
    return datetime.now(UTC)


def _iso(dt):
    return dt.astimezone(UTC).isoformat().replace('+00:00','Z')


def _parse(value):
    if not value: return None
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if d.tzinfo is None: d=d.replace(tzinfo=UTC)
        return d.astimezone(UTC)
    except Exception: return None


class OperationsReportService:
    REPORTS='operations_reports'
    def __init__(self, repository, handover, collaboration, escalation, rca_store, cmms_store, peer_benchmark):
        self.repo=repository; self.handover=handover; self.collaboration=collaboration
        self.escalation=escalation; self.rca=rca_store; self.cmms=cmms_store; self.peer=peer_benchmark

    def _window(self, kind:str, site_id:str='', shift_id:str='', date:str=''):
        kind=(kind or 'shift').lower()
        if kind=='daily':
            if date:
                try: start=datetime.fromisoformat(date).replace(tzinfo=UTC)
                except Exception: start=_now().replace(hour=0,minute=0,second=0,microsecond=0)
            else: start=_now().replace(hour=0,minute=0,second=0,microsecond=0)
            return start,start+timedelta(days=1),''
        current=self.handover.current_shift(site_id) or {}
        sid=shift_id or current.get('shift_id','')
        start=_parse(current.get('current_start')) if not shift_id or shift_id==current.get('shift_id') else None
        end=_parse(current.get('current_end')) if not shift_id or shift_id==current.get('shift_id') else None
        if not start:
            end=_now(); start=end-timedelta(hours=float(current.get('duration_hours') or 8))
        if not end: end=start+timedelta(hours=float(current.get('duration_hours') or 8))
        return start,end,sid

    @staticmethod
    def _within(row,start,end,fields=('created_at','updated_at','executed_at','analyzed_at')):
        for f in fields:
            d=_parse(row.get(f))
            if d and start<=d<end: return True
        return False

    def generate(self, payload:Dict[str,Any], actor='system'):
        kind=str(payload.get('kind') or 'shift').lower()
        if kind not in {'shift','daily'}: raise ValueError('kind must be shift or daily')
        site_id=str(payload.get('site_id') or '')
        start,end,shift_id=self._window(kind,site_id,str(payload.get('shift_id') or ''),str(payload.get('date') or ''))
        board=self.collaboration.board('__report__',limit=1000)
        responsibility=[x for x in board.get('all',[]) if not site_id or not x.get('site_id') or x.get('site_id')==site_id]
        logs=[x for x in self.handover.logs(site_id=site_id,shift_id=shift_id if kind=='shift' else '',limit=1000) if self._within(x,start,end,('created_at',))]
        rcas=[x for x in self.rca.list(limit=1000) if self._within(x,start,end)]
        open_rcas=[x for x in self.rca.list(limit=1000) if str(x.get('status') or '') not in {'closed','resolved'}]
        if site_id: open_rcas=[x for x in open_rcas if not x.get('site_id') or x.get('site_id')==site_id]
        work_orders=self.cmms.list(limit=1000)
        pending_wo=[x for x in work_orders if str(x.get('status') or '') in {'draft','approved'}]
        if site_id: pending_wo=[x for x in pending_wo if not x.get('site_id') or x.get('site_id')==site_id]
        completed_wo=[x for x in work_orders if str(x.get('status') or '') in {'dispatched','completed'} and self._within(x,start,end)]
        escalations=[x for x in self.escalation.escalations('open') if not site_id or not x.get('site_id') or x.get('site_id')==site_id]
        peer=[x for x in self.peer.assessments(limit=1000) if x.get('ready')]
        peer.sort(key=lambda x: float(x.get('priority_score') or 0), reverse=True)
        risk_top=sorted(responsibility,key=lambda x: ({'overdue':4,'due_soon':3,'on_track':2,'no_sla':1}.get(x.get('sla_state'),0), str(x.get('due_at') or '')), reverse=True)[:5]
        energy_top=[x for x in peer if float(x.get('deviation_vs_peer_median_pct') or 0)>0][:5]
        next_focus=[]
        for x in risk_top[:3]:
            next_focus.append({'type':x.get('resource_type'),'id':x.get('resource_id'),'title':x.get('title') or x.get('resource_id'),'reason':x.get('sla_state')})
        for x in energy_top[:2]:
            next_focus.append({'type':'asset','id':x.get('current_asset'),'title':x.get('current_asset'),'reason':f"peer_deviation={x.get('deviation_vs_peer_median_pct')}%"})
        summary={
            'new_logs':len(logs),'new_rca':len(rcas),'open_rca':len(open_rcas),'pending_work_orders':len(pending_wo),
            'completed_work_orders':len(completed_wo),'overdue_items':sum(1 for x in responsibility if x.get('sla_state')=='overdue'),
            'due_soon_items':sum(1 for x in responsibility if x.get('sla_state')=='due_soon'),'open_escalations':len(escalations),
            'peer_anomalies':sum(1 for x in peer if x.get('rca_candidate')),
        }
        report={
            'report_id':'OPS-'+uuid.uuid4().hex[:12].upper(),'kind':kind,'site_id':site_id,'shift_id':shift_id,
            'window':{'start':_iso(start),'end':_iso(end)},'summary':summary,'risk_top5':risk_top,
            'energy_anomaly_top5':energy_top,'open_rca':open_rcas[:10],'pending_work_orders':pending_wo[:10],
            'completed_work_orders':completed_wo[:10],'shift_logs':logs[-20:],'open_escalations':escalations[:10],
            'next_shift_focus':next_focus,'source_counts':{'responsibility':len(responsibility),'peer_assessments':len(peer),'work_orders':len(work_orders)},
            'generated_by':actor,'generated_at':_iso(_now())
        }
        self.repo.put(self.REPORTS,report['report_id'],report); return report

    def list_reports(self, kind='', site_id='', limit=100):
        rows=self.repo.list(self.REPORTS,limit=1000)
        if kind: rows=[x for x in rows if x.get('kind')==kind]
        if site_id: rows=[x for x in rows if x.get('site_id')==site_id]
        return rows[:limit]

    def get(self, report_id): return self.repo.get(self.REPORTS,report_id)

    def markdown(self, report_id):
        r=self.get(report_id)
        if not r: raise ValueError('report not found')
        s=r.get('summary') or {}; w=r.get('window') or {}
        lines=[f"# 工业语义智能平台运营{'班报' if r.get('kind')=='shift' else '日报'}",'',f"- 报告：`{r['report_id']}`",f"- Site：`{r.get('site_id') or 'ALL'}`",f"- 时间窗口：{w.get('start')} ～ {w.get('end')}",'', '## 核心摘要',
               f"- 新增运行日志：{s.get('new_logs',0)}",f"- 新增 RCA：{s.get('new_rca',0)}",f"- 未闭环 RCA：{s.get('open_rca',0)}",f"- 待处理工单：{s.get('pending_work_orders',0)}",f"- 本窗口完成/下发工单：{s.get('completed_work_orders',0)}",f"- 已超时责任项：{s.get('overdue_items',0)}",f"- 开放升级：{s.get('open_escalations',0)}",f"- Peer 异常候选：{s.get('peer_anomalies',0)}",'', '## 下一班 / 下一工作日重点']
        for x in r.get('next_shift_focus') or []: lines.append(f"- {x.get('title')}: {x.get('reason')}")
        return '\n'.join(lines)+'\n'
