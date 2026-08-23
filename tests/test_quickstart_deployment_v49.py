from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app


def test_v49_version_and_quickstart_contract():
    c = TestClient(app)
    assert c.get('/health').json()['version'] == '4.9.0'
    root = Path('.')
    assert (root/'install.sh').exists()
    assert (root/'deploy/quickstart/install.sh').exists()
    assert (root/'deploy/quickstart/docker-compose.production.yml').exists()
    text=(root/'deploy/quickstart/install.sh').read_text(encoding='utf-8')
    assert 'local | saas' in text
    assert 'AUTH_JWT_SECRET' in text or 'auth_jwt_secret' in text
    assert '/health/ready' in text
    assert 'bootstrap_token' in text


def test_v49_production_compose_and_ui_bootstrap_token():
    compose=Path('deploy/quickstart/docker-compose.production.yml').read_text(encoding='utf-8')
    assert 'postgres:16' in compose
    assert 'caddy:2.10-alpine' in compose
    assert 'DEPLOYMENT_ENV: production' in compose
    assert 'AUTH_MODE: jwt' in compose
    assert 'AUTH_JWT_SECRET_REF: secret://file/auth_jwt_secret' in compose
    ui=Path('app/static/index.html').read_text(encoding='utf-8')
    assert 'bootstrap_token' in ui
    assert "sessionStorage.setItem('enterprise_access_token'" in ui
    assert 'history.replaceState' in ui


def test_v49_readme_one_command_and_author():
    text=Path('README.md').read_text(encoding='utf-8')
    assert './install.sh local' in text
    assert 'DOMAIN=ai.example.com ./install.sh saas' in text
    assert '开发者** | 良晞' in text
    assert 'xhongliang@163.com' in text
    assert '@KevinXu816' in text


def test_v49_secrets_excluded_from_docker_build():
    text=Path('.dockerignore').read_text(encoding='utf-8')
    assert '/deploy/quickstart/.env.production' in text
    assert '/deploy/quickstart/runtime-secrets/' in text
    assert '/deploy/quickstart/bootstrap-admin.token' in text
