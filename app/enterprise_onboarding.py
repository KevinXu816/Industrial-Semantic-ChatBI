from __future__ import annotations
import csv, hashlib, io, ipaddress, json, os, socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from .persistence import Repository
from .datasource import DataSourceConfig

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT / 'data' / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

FIELD_ALIASES = {
 'asset_id':['asset_id','asset','device_id','deviceid','equipment_id','equipment_code','machine_id','设备id','设备编号','设备编码'],
 'name':['name','device_name','equipment_name','machine_name','设备名称'],
 'asset_type':['asset_type','device_type','equipment_type','type','设备类型'],
 'parent_asset_id':['parent_asset_id','parent_id','line_id','line_code','产线编号'],
 'sensor':['sensor','tag','tag_name','point','metric','signal','测点','传感器'],
 'value':['value','tag_value','reading','measurement','数值','值'],
 'timestamp':['timestamp','time','event_time','eventtime','datetime','ts','时间','时间戳'],
 'alarm':['alarm','alarm_name','alarm_code','message','告警','告警名称'],
 'severity':['severity','level','alarm_level','等级'],
 'recommended_action':['recommended_action','action','maintenance_action','description','处理建议','维修建议'],
 'priority':['priority','work_order_priority','优先级'],
}
TARGET_REQUIRED = {'asset':['asset_id'],'condition_series':['asset_id','sensor','value'],'alarm':['asset_id','alarm'],'work_order':['asset_id','recommended_action']}
TARGET_FIELDS = {
 'asset':['asset_id','name','asset_type','parent_asset_id'],
 'condition_series':['asset_id','sensor','value','timestamp'],
 'alarm':['asset_id','alarm','severity','timestamp'],
 'work_order':['asset_id','recommended_action','priority'],
}


def _now(): return datetime.now(timezone.utc).isoformat()
def _norm(s): return ''.join(ch for ch in str(s or '').strip().lower() if ch.isalnum() or '\u4e00' <= ch <= '\u9fff')

class EnterpriseOnboardingService:
    COLLECTION='onboarding_sessions'
    def __init__(self, repo:Repository, datasource_store, data_bindings):
        self.repo=repo; self.datasource_store=datasource_store; self.data_bindings=data_bindings

    def contract(self):
        return {
          'version':'4.8','steps':2,
          'step_1':'连接或上传数据源','step_2':'确认自动识别的字段映射并完成接入',
          'sources':{
            'excel':{'mode':'browser_upload','formats':['.xlsx','.csv'],'recommended':True},
            'api':{'mode':'saas_https_pull','security':'public HTTPS only by default; private networks use Edge Agent'},
            'database':{'mode':'edge_agent_outbound','types':['mysql','postgresql','doris'],'recommended_for_private_network':True},
            'iot':{'mode':'edge_agent_outbound','types':['influxdb','mqtt','historian']},
          },
          'security':{
            'credentials':'Secret Reference only; no plaintext persistence',
            'saas_private_network':'Edge/Data Agent outbound TLS; no inbound DB port required',
            'api_ssrf_guard':True,'tenant_scope':True,
          }
        }

    def _session(self, payload):
        sid='ONB-'+hashlib.sha1((json.dumps(payload,sort_keys=True,default=str)+_now()).encode()).hexdigest()[:16]
        row={'session_id':sid,'status':'discovered','created_at':_now(),**payload}
        self.repo.put(self.COLLECTION,sid,row); return row

    def discover_excel(self, filename:str, content:bytes, target:str='asset', sheet:str=''):
        suffix=Path(filename).suffix.lower()
        if suffix not in {'.xlsx','.csv'}: raise ValueError('仅支持 .xlsx / .csv')
        safe=hashlib.sha1((filename+_now()).encode()).hexdigest()[:10]+'-'+Path(filename).name
        path=UPLOAD_DIR/safe; path.write_bytes(content)
        tables=[]
        if suffix=='.csv':
            text=content.decode('utf-8-sig',errors='replace'); reader=csv.DictReader(io.StringIO(text)); headers=reader.fieldnames or []; rows=[]
            for i,r in enumerate(reader):
                if i>=20: break
                rows.append(r)
            tables=[{'sheet':Path(filename).stem,'columns':headers,'rows':rows[:5]}]
        else:
            try: import openpyxl
            except ImportError as e: raise RuntimeError('Excel 接入需要 openpyxl') from e
            wb=openpyxl.load_workbook(path,read_only=True,data_only=True)
            names=[sheet] if sheet and sheet in wb.sheetnames else wb.sheetnames
            for name in names:
                ws=wb[name]; it=ws.iter_rows(values_only=True); head=next(it,None)
                if not head: continue
                headers=[str(v or f'col_{i+1}') for i,v in enumerate(head)]; rows=[]
                for i,r in enumerate(it):
                    if i>=5: break
                    rows.append({headers[j]:(r[j] if j<len(r) else None) for j in range(len(headers))})
                tables.append({'sheet':name,'columns':headers,'rows':rows})
            wb.close()
        if not tables: raise ValueError('未发现可读取的数据表/Sheet')
        selected=tables[0]
        mapping=self.recommend_mapping(selected['columns'],target)
        score=self.mapping_score(mapping,target)
        return self._session({'source_type':'excel','filename':safe,'file_path':str(path),'sheet':selected['sheet'],'target':target,'columns':selected['columns'],'preview':selected['rows'],'recommended_mapping':mapping,'readiness_score':score,'all_sheets':[t['sheet'] for t in tables]})

    def validate_api_url(self,url:str, resolve_dns: bool = True):
        p=urlparse(url)
        if p.scheme not in {'https','http'} or not p.hostname: raise ValueError('API URL 必须为 http/https URL')
        if p.scheme!='https' and os.getenv('ALLOW_INSECURE_API_HTTP','false').lower()!='true': raise ValueError('SaaS API Pull 默认仅允许 HTTPS')
        host=p.hostname.lower()
        if host in {'localhost','metadata.google.internal'}: raise ValueError('禁止访问本机/云元数据地址；内网 API 请使用 Edge Agent')
        if os.getenv('ALLOW_PRIVATE_API_PULL','false').lower()!='true':
            try:
                literal = ipaddress.ip_address(host)
                if literal.is_private or literal.is_loopback or literal.is_link_local or literal.is_reserved or literal.is_multicast:
                    raise ValueError('SaaS 默认禁止直接访问私网 API；请使用企业 Edge Agent 主动出站连接')
            except ValueError as exc:
                if 'SaaS 默认禁止' in str(exc):
                    raise
                if resolve_dns:
                    try:
                        for info in socket.getaddrinfo(host,p.port or 443,type=socket.SOCK_STREAM):
                            ip=ipaddress.ip_address(info[4][0])
                            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                                raise ValueError('SaaS 默认禁止直接访问私网 API；请使用企业 Edge Agent 主动出站连接')
                    except socket.gaierror as e: raise ValueError('API 主机无法解析') from e
        return True

    def discover_api(self,payload:Dict[str,Any]):
        url=str(payload.get('url') or '').strip()
        if not url: raise ValueError('API URL 不能为空')
        headers=payload.get('headers') or {}
        for k,v in headers.items():
            if k.lower() in {'authorization','x-api-key','api-key'} and isinstance(v,str) and v and not v.startswith('secret://'):
                raise ValueError('认证 Header 必须使用 secret:// 引用，禁止保存明文 Token/API Key')
        # Discovery supports supplied sample to avoid executing credentials in UI; live fetch only when no sample.
        body=payload.get('sample_response')
        self.validate_api_url(url, resolve_dns=(body is None))
        if body is None:
            req=Request(url,method=str(payload.get('method') or 'GET').upper())
            # Secret refs are not resolved here; secure discovery without credential should be via sample/Edge Agent.
            for k,v in headers.items():
                if not str(v).startswith('secret://'): req.add_header(k,str(v))
            with urlopen(req,timeout=min(int(payload.get('timeout',10)),20)) as resp:
                body=json.loads(resp.read(2_000_000).decode('utf-8'))
        data_path=str(payload.get('data_path') or '').strip()
        data=body
        for part in [x for x in data_path.split('.') if x]:
            if isinstance(data,dict): data=data.get(part)
        if isinstance(data,dict): records=[data]
        elif isinstance(data,list): records=[x for x in data if isinstance(x,dict)]
        else: records=[]
        if not records: raise ValueError('API 响应中未识别到对象记录，请设置 data_path 或提供样例响应')
        columns=list(records[0].keys()); target=str(payload.get('target') or 'asset')
        mapping=self.recommend_mapping(columns,target); score=self.mapping_score(mapping,target)
        return self._session({'source_type':'api','url':url,'method':str(payload.get('method') or 'GET').upper(),'data_path':data_path,'headers':headers,'target':target,'columns':columns,'preview':records[:5],'recommended_mapping':mapping,'readiness_score':score,'connectivity':'saas_https_pull'})

    def discover_edge(self,payload):
        source_type=str(payload.get('source_type') or 'database')
        target=str(payload.get('target') or 'asset')
        columns=payload.get('sample_columns') or []
        mapping=self.recommend_mapping(columns,target)
        return self._session({'source_type':source_type,'connectivity':'edge_agent_outbound','target':target,'columns':columns,'preview':payload.get('sample_records') or [],'recommended_mapping':mapping,'readiness_score':self.mapping_score(mapping,target),'security_note':'企业 Edge/Data Agent 主动出站 TLS；无需开放数据库/API 入站端口；凭据保留在企业侧或使用 Secret Ref。'})

    def recommend_mapping(self,columns:List[str],target:str):
        norm_cols={_norm(c):c for c in columns}; result={}
        fields=TARGET_FIELDS.get(target, TARGET_REQUIRED.get(target,[]))
        for f in fields:
            aliases=[f]+FIELD_ALIASES.get(f,[])
            for alias in aliases:
                n=_norm(alias)
                if n in norm_cols: result[f]=norm_cols[n]; break
        return result

    def mapping_score(self,mapping,target):
        req=TARGET_REQUIRED.get(target,[])
        if not req: return 100
        return round(100*sum(1 for f in req if mapping.get(f))/len(req),1)

    def confirm(self,session_id:str,payload:Dict[str,Any]):
        s=self.repo.get(self.COLLECTION,session_id)
        if not s: raise KeyError(session_id)
        target=str(payload.get('target') or s.get('target') or 'asset'); mapping=payload.get('mappings') or s.get('recommended_mapping') or {}
        missing=[f for f in TARGET_REQUIRED.get(target,[]) if not mapping.get(f)]
        if missing: raise ValueError('仍缺少必要字段映射: '+', '.join(missing))
        name=str(payload.get('name') or ('Quick '+s.get('source_type','source')))
        ds_id='DS-'+hashlib.sha1((session_id+name).encode()).hexdigest()[:12]
        st=s.get('source_type')
        if st=='excel':
            cfg=DataSourceConfig(id=ds_id,name=name,type='excel',file_path=s.get('file_path'),extra={'sheet':s.get('sheet'),'onboarding_session_id':session_id})
            source_type='excel'
        elif st=='api':
            cfg=DataSourceConfig(id=ds_id,name=name,type='api',api_url=s.get('url'),api_method=s.get('method','GET'),api_headers=s.get('headers') or {},extra={'data_path':s.get('data_path'),'onboarding_session_id':session_id})
            source_type='api'
        else:
            # Edge mode registers the governed logical source; real credential/network remains enterprise-side.
            cfg=DataSourceConfig(id=ds_id,name=name,type='api',enabled=True,extra={'edge_managed':True,'source_type':st,'onboarding_session_id':session_id})
            source_type=st
        self.datasource_store.save(cfg)
        binding=self.data_bindings.upsert({'name':name+' Binding','source_type':source_type,'source_id':ds_id,'target':target,'mappings':mapping,'tenant_id':payload.get('tenant_id','default'),'site_id':payload.get('site_id','')},actor=str(payload.get('actor','data_engineer')))
        # Step 2 is explicit human confirmation; it is safe to approve the reviewed mapping now.
        binding=self.data_bindings.approve(binding['binding_id'],actor=str(payload.get('actor','data_engineer')))
        s.update({'status':'connected','confirmed_at':_now(),'datasource_id':ds_id,'binding_id':binding['binding_id'],'final_mapping':mapping,'target':target})
        self.repo.put(self.COLLECTION,session_id,s)
        return {'status':'connected','steps_completed':2,'session_id':session_id,'datasource_id':ds_id,'binding':binding,'next':'数据源已接入；可直接进入运行监控或业务分析。'}

    def get(self,sid): return self.repo.get(self.COLLECTION,sid)
    def list(self,limit=100): return self.repo.list(self.COLLECTION,limit=limit)
