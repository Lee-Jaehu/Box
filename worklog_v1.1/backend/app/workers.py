"""같은 프로세스 안의 작업 루프. export / 예약 백업 / 임시 첨부·멱등 키 정리. Redis·Celery 없음.

서버가 종료되면 루프도 멈추고, 미완료 작업은 DB(export_jobs/backup_runs)에 남아 다음 수동 실행에서 재개된다.
"""
from __future__ import annotations

import logging
import threading
import time

from .runtime import Runtime
from .services import attachments as att_svc
from .services import backups as backup_svc
from .services import exports as export_svc
from .services.common import purge_expired_idempotency

log = logging.getLogger("worklog.worker")
CLEANUP_INTERVAL = 3600.0


def run_once(rt: Runtime) -> dict:
    """작업 한 사이클. 테스트에서 직접 호출할 수 있다."""
    done = {"exports": 0, "backups": 0}
    if rt.maintenance:
        return done
    done["exports"] = export_svc.process_pending(rt.read_factory, rt.write_factory, rt.settings)
    done["backups"] = backup_svc.run_due_backups(rt)
    return done


def cleanup(rt: Runtime) -> None:
    with rt.write_factory() as s:
        att_svc.cleanup_temp(s, rt.settings)
        purge_expired_idempotency(s)
        s.commit()


def _loop(rt: Runtime) -> None:
    last_cleanup = 0.0
    while not rt.stop_event.is_set():
        try:
            run_once(rt)
            if time.monotonic() - last_cleanup > CLEANUP_INTERVAL:
                cleanup(rt)
                last_cleanup = time.monotonic()
        except Exception:  # noqa: BLE001 - 루프는 계속 돈다
            log.exception("worker cycle failed")
        rt.stop_event.wait(rt.settings.export_poll_seconds)


def start_worker(rt: Runtime) -> threading.Thread:
    t = threading.Thread(target=_loop, args=(rt,), name="worklog-worker", daemon=True)
    t.start()
    return t
