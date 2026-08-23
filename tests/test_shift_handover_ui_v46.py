import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app


def test_v46_handover_ui_i18n_and_readme_contract():
    c=TestClient(app)
    assert c.get('/health').json()['version']=='4.9.0'
    html=Path('app/static/index.html').read_text(encoding='utf-8')
    assert 'data-panel="handover"' in html
    assert '交接班日志与责任连续性' in html
    assert '/operations/handover-dashboard' in html
    locales=['zh-CN','en-US','de-DE','ja-JP']
    keysets=[]
    for loc in locales:
        data=json.loads(Path(f'app/static/i18n/{loc}.json').read_text(encoding='utf-8'))
        keysets.append(set(data['phrases']))
        assert '交接班日志' in data['phrases']
        assert '接班确认' in data['phrases']
    assert all(k==keysets[0] for k in keysets[1:])
    readme=Path('README.md').read_text(encoding='utf-8')
    assert 'V4.9.0 —— 一键生产部署与 SaaS/本地统一交付版' in readme
    assert 'upgrade-check --from-version 4.5.0' in readme
    assert readme.rstrip().endswith('| **GitHub** | [@KevinXu816](https://github.com/KevinXu816) |')
