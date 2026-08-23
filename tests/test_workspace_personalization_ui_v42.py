import json
from pathlib import Path


def test_v42_personal_workspace_dom_and_i18n_contract():
    html = Path('app/static/index.html').read_text(encoding='utf-8')
    for marker in ['id="personal-focus"','id="workspace-memory"','id="context-drawer"','loadPersonalWorkspace','openContextDrawer']:
        assert marker in html
    required = {'今日重点','我的工作区','最近访问','收藏','上下文导航','维护工单'}
    key_sets=[]
    for locale in ['zh-CN','en-US','de-DE','ja-JP']:
        data=json.loads(Path(f'app/static/i18n/{locale}.json').read_text(encoding='utf-8'))
        keys=set(data['phrases'])
        assert required <= keys
        key_sets.append(keys)
    assert all(s == key_sets[0] for s in key_sets[1:])
