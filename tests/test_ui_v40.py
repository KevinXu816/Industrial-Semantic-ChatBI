from pathlib import Path
import json, struct

ROOT=Path(__file__).resolve().parents[1]


def _png_size(path: Path):
    b=path.read_bytes()
    assert b[:8] == b'\x89PNG\r\n\x1a\n'
    return struct.unpack('>II', b[16:24])


def test_v40_brand_author_and_language_resources_are_consistent():
    html=(ROOT/'app/static/index.html').read_text(encoding='utf-8')
    assert '<strong>工业语义智能平台</strong>' in html
    assert '🏭 ChatBI' not in html
    assert '工业语义 ChatBI 助手' not in html
    assert '开发者：<strong>良晞</strong>' in html
    assert 'xhongliang@163.com' in html
    assert 'github.com/KevinXu816' in html
    packs=[]
    for loc in ['zh-CN','en-US','de-DE','ja-JP']:
        data=json.loads((ROOT/f'app/static/i18n/{loc}.json').read_text(encoding='utf-8'))
        assert data['locale']==loc
        packs.append(set(data['phrases']))
        assert '工业语义智能平台' in data['phrases']
    assert all(x==packs[0] for x in packs[1:])


def test_v40_all_primary_ui_screenshots_are_current_full_hd():
    names=[
        '01-workspace.png','02-chat.png','03-llm.png','04-datasources.png','05-bindings.png',
        '06-graph.png','07-metrics.png','08-scan.png','09-candidates.png','10-templates.png',
        '11-assets.png','12-rcaworkflow.png','13-modelops.png','14-identity.png','15-auditcenter.png',
        '16-pilot.png','17-benchmark.png','18-observability.png','19-admin.png','20-graph-editor.png'
    ]
    for name in names:
        p=ROOT/'docs/images'/name
        assert p.exists() and p.stat().st_size > 20_000, name
        assert _png_size(p)==(1600,1000), name


def test_readme_has_real_deployment_boundaries_and_requested_author_table():
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    assert 'V4.1 部署说明（与当前仓库实际行为一致）' in readme
    assert 'PostgreSQL + Mock Query + Local Knowledge' in readme
    assert 'EXECUTION_MODE=doris' in readme
    assert 'KNOWLEDGE_BACKEND=qdrant' in readme
    assert '生产部署骨架' in readme
    assert '| **开发者** | 良晞 |' in readme
    assert '| **邮箱** | xhongliang@163.com |' in readme
    assert '[@KevinXu816](https://github.com/KevinXu816)' in readme
