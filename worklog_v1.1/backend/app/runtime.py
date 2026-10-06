"""프로세스 런타임: 설정, 엔진/세션 팩토리, maintenance mode, 잠금."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .db import create_db_engine, make_session_factory
from .migrate import upgrade
from .models import AppMetadata


@dataclass
class Runtime:
    settings: Settings
    write_engine: Engine
    read_engine: Engine
    write_factory: sessionmaker[Session]
    read_factory: sessionmaker[Session]
    maintenance: bool = False
    maintenance_reason: str = ""
    backup_lock: threading.Lock = field(default_factory=threading.Lock)
    stop_event: threading.Event = field(default_factory=threading.Event)

    def dispose_engines(self) -> None:
        self.write_engine.dispose()
        self.read_engine.dispose()


def get_meta(s: Session, key: str, default: str | None = None) -> str | None:
    row = s.get(AppMetadata, key)
    return row.value if row else default


def set_meta(s: Session, key: str, value: str) -> None:
    row = s.get(AppMetadata, key)
    if row is None:
        s.add(AppMetadata(key=key, value=value))
    else:
        row.value = value


def build_runtime(settings: Settings, *, migrate: bool = True) -> Runtime:
    settings.ensure_dirs()
    if migrate:
        upgrade(settings.db_url)
    we = create_db_engine(settings, write=True)
    re_ = create_db_engine(settings, write=False)
    rt = Runtime(settings, we, re_, make_session_factory(we), make_session_factory(re_))
    with rt.write_factory() as s:
        if get_meta(s, "instance_id") is None:
            set_meta(s, "instance_id", str(uuid.uuid4()))
        if get_meta(s, "restore_generation") is None:
            set_meta(s, "restore_generation", "0")
        s.commit()
    return rt


def instance_info(rt: Runtime) -> dict:
    with rt.read_factory() as s:
        return {"instanceId": get_meta(s, "instance_id"), "restoreGeneration": int(get_meta(s, "restore_generation", "0") or 0)}
