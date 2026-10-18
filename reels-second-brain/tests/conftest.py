import hashlib
import hmac
import json
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from rsb import db
from rsb.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"
TABLES = "jobs, intakes, extractions, processing_runs, webhook_events, reels, kakao_tokens, oauth_states"


@pytest.fixture(scope="session")
def database_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL 미설정")
    with db.connect(url) as conn:
        db.migrate(conn)
    return url


@pytest.fixture
def conn(database_url):
    with db.connect(database_url) as c:
        c.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
        c.commit()
        yield c


@pytest.fixture
def settings(database_url, tmp_path):
    return Settings(
        database_url=database_url, data_dir=tmp_path / "data", public_base_url="https://rsb.test",
        admin_token="admin-secret", token_key=Fernet.generate_key().decode(),
        ig_app_secret="app-secret", ig_verify_token="verify-me", ig_account_id="17841400000000001",
        ig_allowed_senders=frozenset({"1000000000000001"}), ig_access_token="ig-token",
        kakao_rest_api_key="kakao-key", kakao_redirect_uri="https://rsb.test/oauth/kakao/callback",
        kakao_allowed_user_id="4242",
    )


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / "mock" / name).read_text(encoding="utf-8"))
