"""DB/첨부 백업과 수동 복원.

백업: SQLite backup API 로 일관된 DB snapshot → snapshot 이 참조하는 정식 첨부(휴지통 참조 포함)를 모아
      manifest(hash/size/schema/instance) 작성 → 전체 검증 → 성공으로 표시 → 그 뒤에만 초과분(최근 성공 14개 초과) 정리.
      실패하면 부분 폴더만 지우고 이전 정상 백업은 건드리지 않는다. 누락 파일이 있으면 실패(정상 백업 수에 미포함).
복원: 대상 검증 → maintenance mode → 현재 상태 pre-restore 백업 → 연결 종료 → DB/첨부 교체(실패 시 되돌림)
      → 스키마 호환(upgrade) → restoreGeneration 증가 → 전체 export dirty → 재개.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ApiError, conflict, not_found
from ..migrate import is_known_revision, upgrade
from ..models import Attachment, BackupRun, utcnow
from ..runtime import Runtime, get_meta, set_meta
from .attachments import attachment_abs_path
from .common import iso, iso_date
from .exports import request_rebuild

KEEP_KINDS = ("daily", "manual")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def ser_backup(b: BackupRun) -> dict:
    return {"id": b.id, "kind": b.kind, "localDate": iso_date(b.local_date), "status": b.status,
            "startedAt": iso(b.started_at), "finishedAt": iso(b.finished_at), "schemaVersion": b.schema_version,
            "error": b.error, "attachmentCount": len((b.manifest or {}).get("attachments", [])) if b.manifest else None}


def list_backups(s: Session) -> dict:
    rows = s.execute(select(BackupRun).order_by(BackupRun.created_at.desc())).scalars().all()
    return {"items": [ser_backup(b) for b in rows]}


def request_manual_backup(s: Session) -> BackupRun:
    b = BackupRun(kind="manual", status="scheduled")
    s.add(b)
    s.flush()
    return b


# ── 실행 ────────────────────────────────────────────────────────────────────

def _snapshot_db(src_path: Path, dst_path: Path) -> None:
    src = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True, timeout=10)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)  # 일관된 snapshot (WAL 포함)
    finally:
        dst.close()
        src.close()


def _verify_dir(root: Path, manifest: dict) -> None:
    db = root / manifest["dbFile"]["name"]
    if not db.exists() or _sha256(db) != manifest["dbFile"]["sha256"]:
        raise ApiError(409, "BACKUP_CORRUPT", "백업 DB 파일의 hash가 맞지 않습니다.")
    for a in manifest["attachments"]:
        f = root / "attachments" / a["relativePath"]
        if not f.exists() or _sha256(f) != a["sha256"]:
            raise ApiError(409, "BACKUP_CORRUPT", f"백업 첨부 파일이 없거나 손상되었습니다: {a['relativePath']}")


def run_backup(rt: Runtime, run_id: str) -> dict:
    """scheduled/failed 상태의 backup_runs 행 하나를 실제로 실행한다. 동시에 하나만 실행."""
    s = rt.settings
    if not rt.backup_lock.acquire(blocking=False):
        return {"status": "busy"}
    target_dir: Path | None = None
    try:
        with rt.write_factory() as ws:
            run = ws.get(BackupRun, run_id)
            if run is None or run.status == "succeeded":
                return {"status": run.status if run else "missing"}
            run.status, run.started_at, run.error = "running", utcnow(), None
            kind = run.kind
            ws.commit()
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        target_dir = s.backups_root / f"{stamp}-{kind}-{run_id[:8]}"
        target_dir.mkdir(parents=True, exist_ok=False)
        db_copy = target_dir / "worklog.sqlite3"
        _snapshot_db(s.db_path, db_copy)

        con = sqlite3.connect(db_copy)
        try:
            ok = con.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise ApiError(500, "BACKUP_INTEGRITY", f"snapshot integrity_check 실패: {ok}")
            version = (con.execute("SELECT version_num FROM alembic_version").fetchone() or ["?"])[0]
            refs = con.execute("SELECT id, stored_relative_path, sha256, size_bytes FROM attachments WHERE state='committed'").fetchall()
            gen = (con.execute("SELECT value FROM app_metadata WHERE key='restore_generation'").fetchone() or ["0"])[0]
            inst = (con.execute("SELECT value FROM app_metadata WHERE key='instance_id'").fetchone() or [None])[0]
        finally:
            con.close()

        missing: list[str] = []
        damaged: list[str] = []  # pre_restore 에서만 허용: 복원이 바로 그 손상을 고치는 수단이기 때문
        tolerant = kind == "pre_restore"
        files = []
        for aid, rel, sha, size in refs:
            src = attachment_abs_path(s, rel)
            if not src.exists():
                (damaged if tolerant else missing).append(rel)
                continue
            if tolerant and _sha256(src) != sha:
                damaged.append(rel)
                continue
            dst = target_dir / "attachments" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            # 기본은 실제 복사: hard link 는 원본이 제자리에서 손상되면 백업본도 함께 손상된다.
            # 공간이 부족한 운영자는 BACKUP_HARDLINK_ATTACHMENTS=true 로 켤 수 있다(손상 대비 약화를 감수).
            linked = False
            if s.backup_hardlink_attachments:
                try:
                    os.link(src, dst)
                    linked = True
                except OSError:
                    linked = False
            if not linked:
                shutil.copy2(src, dst)
            files.append({"attachmentId": aid, "relativePath": rel, "sha256": sha, "size": size})
        if missing:
            raise ApiError(500, "BACKUP_INCOMPLETE", f"참조된 첨부 파일이 없어 백업을 완료할 수 없습니다: {len(missing)}개")

        manifest = {
            "backupId": run_id, "kind": kind, "createdAt": iso(utcnow()), "instanceId": inst, "schemaVersion": version,
            "restoreGeneration": int(gen or 0),
            "dbFile": {"name": db_copy.name, "sha256": _sha256(db_copy), "size": db_copy.stat().st_size},
            "attachments": files,
            "incompleteAttachments": damaged,  # 비어 있지 않으면 이 백업은 복원 전 안전망일 뿐 완전한 백업이 아니다
        }
        (target_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        _verify_dir(target_dir, manifest)  # 성공 표시 전에 hash 재검증

        with rt.write_factory() as ws:
            run = ws.get(BackupRun, run_id)
            run.status, run.finished_at, run.path = "succeeded", utcnow(), str(target_dir)
            run.manifest, run.schema_version = manifest, version
            ws.commit()
        prune(rt)  # 새 백업이 검증 완료된 뒤에만 초과분 정리
        return {"status": "succeeded", "path": str(target_dir)}
    except BaseException as e:  # noqa: BLE001
        if target_dir is not None:
            shutil.rmtree(target_dir, ignore_errors=True)  # 부분 폴더만 제거, 이전 정상 백업은 그대로
        with rt.write_factory() as ws:
            run = ws.get(BackupRun, run_id)
            if run is not None:
                run.status, run.finished_at = "failed", utcnow()
                run.error = f"{type(e).__name__}: {getattr(e, 'message', e)}"[:500]
            ws.commit()
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        return {"status": "failed", "error": str(e)}
    finally:
        rt.backup_lock.release()


def prune(rt: Runtime) -> int:
    keep = rt.settings.backup_retention_count
    removed = 0
    with rt.write_factory() as ws:
        rows = ws.execute(select(BackupRun).where(BackupRun.status == "succeeded", BackupRun.kind.in_(KEEP_KINDS))
                          .order_by(BackupRun.finished_at.desc())).scalars().all()
        for old in rows[keep:]:
            if old.path:
                shutil.rmtree(old.path, ignore_errors=True)
            ws.delete(old)
            removed += 1
        ws.commit()
    return removed


def run_due_backups(rt: Runtime) -> int:
    with rt.read_factory() as rs:
        ids = [b for b in rs.execute(select(BackupRun.id).where(BackupRun.status == "scheduled")).scalars()]
    n = 0
    for rid in ids:
        if run_backup(rt, rid).get("status") == "succeeded":
            n += 1
    return n


# ── 복원 ────────────────────────────────────────────────────────────────────

def restore_backup(rt: Runtime, backup_id: str, actor_id: str | None) -> dict:
    s = rt.settings
    with rt.read_factory() as rs:
        b = rs.get(BackupRun, backup_id)
        if b is None:
            raise not_found("백업", backup_id)
        if b.status != "succeeded" or not b.path or not b.manifest:
            raise conflict("BACKUP_NOT_USABLE", "정상 완료된 백업만 복원할 수 있습니다.")
        root, manifest = Path(b.path), b.manifest
        live_gen = int(get_meta(rs, "restore_generation", "0") or 0)
    if not root.exists():
        raise conflict("BACKUP_MISSING", "백업 폴더를 찾을 수 없습니다.")
    _verify_dir(root, manifest)
    if manifest["schemaVersion"] not in ("?", None) and not is_known_revision(manifest["schemaVersion"]):
        raise conflict("SCHEMA_TOO_NEW", "이 프로그램보다 새로운 버전에서 만든 백업입니다.")

    rt.maintenance, rt.maintenance_reason = True, "복원 중입니다. 잠시 후 다시 시도해 주세요."
    try:
        with rt.write_factory() as ws:  # 현재 상태 pre-restore 백업
            pre = BackupRun(kind="pre_restore", status="scheduled")
            ws.add(pre)
            ws.commit()
            pre_id = pre.id
        res = run_backup(rt, pre_id)
        if res.get("status") != "succeeded":
            raise ApiError(500, "PRE_RESTORE_BACKUP_FAILED", "복원 전 현재 상태 백업에 실패했습니다. 복원을 중단했습니다.")

        rt.dispose_engines()
        live = s.db_path
        moved: list[tuple[Path, Path]] = []
        stage = live.with_name(live.name + ".restoring")
        try:
            shutil.copy2(root / manifest["dbFile"]["name"], stage)
            for suffix in ("", "-wal", "-shm"):
                src = live.with_name(live.name + suffix)
                if src.exists():
                    dst = live.with_name(live.name + suffix + ".replaced")
                    _replace_with_retry(src, dst)
                    moved.append((dst, src))
            _replace_with_retry(stage, live)
            _restore_attachments(s, root, manifest)
        except BaseException:
            stage.unlink(missing_ok=True)
            for dst, src in reversed(moved):  # 실패하면 이전 상태로 되돌린다
                if live.exists() and src == live:
                    live.unlink(missing_ok=True)
                _replace_with_retry(dst, src)
            raise
        for dst, _ in moved:
            dst.unlink(missing_ok=True)

        upgrade(s.db_url)  # 구버전 백업이면 스키마 올림
        with rt.write_factory() as ws:
            restored_gen = int(get_meta(ws, "restore_generation", "0") or 0)
            set_meta(ws, "restore_generation", str(max(live_gen, restored_gen) + 1))
            reindex_backups(ws, s.backups_root)  # 복원된 DB 의 오래된 backup_runs 이력을 디스크 상태에 맞춘다
            request_rebuild(ws, None, True)  # JSON 사본 전체 재생성
            ws.commit()
        return {"restoredFrom": backup_id, "preRestoreBackupId": pre_id, "restoreGeneration": max(live_gen, restored_gen) + 1}
    finally:
        rt.maintenance, rt.maintenance_reason = False, ""


def reindex_backups(ws: Session, root: Path) -> int:
    """백업 폴더의 manifest 를 기준으로 backup_runs 를 재구성한다. 복원 후 이력이 되돌아간 경우를 바로잡는다."""
    seen: set[str] = set()
    added = 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []:
        mf = d / "manifest.json"
        if not mf.exists():
            continue
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
            bid = m["backupId"]
        except (ValueError, KeyError, OSError):
            continue
        seen.add(bid)
        row = ws.get(BackupRun, bid)
        if row is None:
            finished = datetime.fromisoformat(m["createdAt"].replace("Z", "+00:00")) if m.get("createdAt") else utcnow()
            ws.add(BackupRun(id=bid, kind=m.get("kind", "manual"), status="succeeded", started_at=finished, finished_at=finished,
                             path=str(d), manifest=m, schema_version=m.get("schemaVersion")))
            added += 1
        elif row.status != "succeeded" or row.path != str(d):
            row.status, row.path, row.manifest = "succeeded", str(d), m
    for row in ws.execute(select(BackupRun).where(BackupRun.status == "succeeded")).scalars():
        if row.id not in seen:  # 폴더가 없는 '성공' 행은 정상 백업 수에 넣지 않는다
            row.status, row.error = "failed", "백업 폴더를 찾을 수 없습니다."
    return added


def _replace_with_retry(src: Path, dst: Path, attempts: int = 20) -> None:
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise ApiError(503, "RESTORE_FILE_BUSY", "DB 파일이 사용 중이라 복원할 수 없습니다. 진행 중인 요청이 끝난 뒤 다시 시도해 주세요.") from None
            time.sleep(0.25)


def _restore_attachments(s, root: Path, manifest: dict) -> None:
    for a in manifest["attachments"]:
        src = root / "attachments" / a["relativePath"]
        dst = attachment_abs_path(s, a["relativePath"])
        if dst.exists() and _sha256(dst) == a["sha256"]:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".restoring")
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)


def verify_attachments_match_db(rt: Runtime) -> list[str]:
    """복원/검증용: DB 가 참조하는 정식 첨부가 모두 존재하고 hash 가 일치하는지 확인한다. 문제 목록 반환."""
    problems = []
    with rt.read_factory() as rs:
        for a in rs.execute(select(Attachment).where(Attachment.state == "committed")).scalars():
            p = attachment_abs_path(rt.settings, a.stored_relative_path)
            if not p.exists():
                problems.append(f"missing:{a.stored_relative_path}")
            elif _sha256(p) != a.sha256:
                problems.append(f"hash:{a.stored_relative_path}")
    return problems
