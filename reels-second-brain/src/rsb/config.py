"""환경변수 설정. 비밀값은 환경변수로만 받는다(PRD 10장)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _csv(name: str) -> frozenset[str]:
    return frozenset(v.strip() for v in os.environ.get(name, "").split(",") if v.strip())


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("DATABASE_URL", ""))
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("RSB_DATA_DIR", "data")))
    public_base_url: str = field(default_factory=lambda: os.environ.get("PUBLIC_BASE_URL", ""))
    admin_token: str = field(default_factory=lambda: os.environ.get("RSB_ADMIN_TOKEN", ""))
    token_key: str = field(default_factory=lambda: os.environ.get("RSB_TOKEN_KEY", ""))

    # Instagram API with Instagram Login (D14)
    ig_app_secret: str = field(default_factory=lambda: os.environ.get("IG_APP_SECRET", ""))
    ig_verify_token: str = field(default_factory=lambda: os.environ.get("IG_VERIFY_TOKEN", ""))
    ig_account_id: str = field(default_factory=lambda: os.environ.get("IG_ACCOUNT_ID", ""))
    ig_allowed_senders: frozenset[str] = field(default_factory=lambda: _csv("IG_ALLOWED_SENDER_IDS"))
    ig_access_token: str = field(default_factory=lambda: os.environ.get("IG_ACCESS_TOKEN", ""))
    ig_graph_version: str = field(default_factory=lambda: os.environ.get("IG_GRAPH_VERSION", "v23.0"))

    # 카카오 나에게 보내기 (D8 보관 경로)
    kakao_rest_api_key: str = field(default_factory=lambda: os.environ.get("KAKAO_REST_API_KEY", ""))
    kakao_client_secret: str = field(default_factory=lambda: os.environ.get("KAKAO_CLIENT_SECRET", ""))
    kakao_redirect_uri: str = field(default_factory=lambda: os.environ.get("KAKAO_REDIRECT_URI", ""))
    kakao_allowed_user_id: str = field(default_factory=lambda: os.environ.get("KAKAO_ALLOWED_USER_ID", ""))

    # 워커
    job_max_attempts: int = field(default_factory=lambda: int(os.environ.get("RSB_JOB_MAX_ATTEMPTS", "3")))
    job_lease_s: int = field(default_factory=lambda: int(os.environ.get("RSB_JOB_LEASE_S", "900")))
    transcriber: str = field(default_factory=lambda: os.environ.get("RSB_TRANSCRIBER", "openai"))


def get_settings() -> Settings:
    return Settings()
