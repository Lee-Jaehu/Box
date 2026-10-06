"""Alembic을 프로그램에서 실행한다. 실행.bat/서버 시작 시 upgrade head."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    return cfg


def upgrade(db_url: str, revision: str = "head") -> None:
    command.upgrade(_config(db_url), revision)


def head_revision() -> str:
    return ScriptDirectory.from_config(_config("sqlite://")).get_current_head() or ""


def is_known_revision(version: str) -> bool:
    """이 프로그램의 migration 이력에 있는 버전인지(= 더 새로운 버전에서 만든 DB가 아닌지)."""
    try:
        return ScriptDirectory.from_config(_config("sqlite://")).get_revision(version) is not None
    except Exception:  # noqa: BLE001
        return False
