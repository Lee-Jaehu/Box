"""첨부 업로드/조회. 파일 처리는 DB 트랜잭션 밖에서 하고, 정식 연결(committed)은 일지 저장 트랜잭션에서 한다.

- 저장 경로는 서버가 만든 UUID: attachments/{projectId}/{attachmentId}.{ext}. 원본 파일명은 표시 메타데이터일 뿐이다.
- 업로드 시점에 최종 경로에 파일을 두고 state=temp 로 등록한다. 일지 저장은 state 만 committed 로 바꾸므로
  "DB commit 뒤 파일 이동"이 필요하지 않다.
- SVG, HTML, 실행 파일은 허용하지 않는다. 이미지는 Pillow 로 실제 바이트와 픽셀 수를 검증한다.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DOCUMENT_MEDIA_TYPES, IMAGE_MEDIA_TYPES, Settings
from ..errors import ApiError, not_found
from ..models import Attachment, TaskAttachment, utcnow
from .common import iso

_PIL_FORMATS = {"PNG": ("image/png", ".png"), "JPEG": ("image/jpeg", ".jpg"), "WEBP": ("image/webp", ".webp")}
_EXT_TO_MEDIA = {ext: mt for mt, exts in DOCUMENT_MEDIA_TYPES.items() for ext in exts}
_ZIP_EXTS = {".xlsx", ".docx", ".pptx"}


@dataclass
class StoredFile:
    attachment_id: str
    project_id: str
    original_name: str
    relative_path: str
    media_type: str
    size_bytes: int
    sha256: str
    width: int | None
    height: int | None


def _safe_name(name: str) -> str:
    name = os.path.basename((name or "file").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f]", "", name).strip()
    return (name or "file")[:200]


def attachment_abs_path(settings: Settings, relative: str) -> Path:
    """data/attachments 아래로 제한된 경로만 허용 (path traversal 차단)."""
    base = settings.attachments_dir.resolve()
    p = (base / relative).resolve()
    if base != p and base not in p.parents:
        raise ApiError(400, "INVALID_PATH", "잘못된 첨부 경로입니다.")
    return p


def store_upload(settings: Settings, project_id: str, filename: str, stream: BinaryIO, new_id: str) -> StoredFile:
    """업로드 스트림을 검증하며 temp 에 쓴 뒤 최종 경로로 원자적 이동한다. DB 는 건드리지 않는다."""
    original = _safe_name(filename)
    ext = Path(original).suffix.lower()
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=settings.temp_dir, prefix="upload-", suffix=".part")
    tmp = Path(tmp_name)
    sha = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_attachment_bytes:
                    raise ApiError(413, "FILE_TOO_LARGE", f"파일당 {settings.max_attachment_bytes // (1024 * 1024)}MB를 넘을 수 없습니다.")
                sha.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        if size == 0:
            raise ApiError(422, "EMPTY_FILE", "빈 파일입니다.")

        media_type, width, height = _detect(settings, tmp, ext)
        if media_type in IMAGE_MEDIA_TYPES:
            ext = dict((m, e) for m, e in _PIL_FORMATS.values())[media_type]
        rel = f"{project_id}/{new_id}{ext}"
        final = attachment_abs_path(settings, rel)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, final)
        return StoredFile(new_id, project_id, original, rel, media_type, size, sha.hexdigest(), width, height)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _detect(settings: Settings, path: Path, ext: str) -> tuple[str, int | None, int | None]:
    head = path.read_bytes()[:8]
    if ext in {".png", ".jpg", ".jpeg", ".webp"} or head[:4] in {b"\x89PNG", b"RIFF"} or head[:3] == b"\xff\xd8\xff":
        try:
            with Image.open(path) as img:
                fmt = img.format or ""
                if fmt not in _PIL_FORMATS:
                    raise ApiError(415, "UNSUPPORTED_MEDIA", "PNG, JPEG, WebP 이미지만 첨부할 수 있습니다.")
                w, h = img.size
                if w * h > settings.max_image_pixels:
                    raise ApiError(413, "IMAGE_TOO_LARGE", "이미지 해상도가 너무 큽니다.")
                img.verify()
            return _PIL_FORMATS[fmt][0], w, h
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
            raise ApiError(415, "UNSUPPORTED_MEDIA", "이미지 파일을 읽을 수 없습니다.") from None
    media = _EXT_TO_MEDIA.get(ext)
    if media is None:
        raise ApiError(415, "UNSUPPORTED_MEDIA", "허용되지 않는 파일 형식입니다. (이미지: PNG/JPEG/WebP, 문서: PDF/XLSX/CSV/DOCX/PPTX/TXT)")
    if ext == ".pdf" and head[:4] != b"%PDF":
        raise ApiError(415, "UNSUPPORTED_MEDIA", "PDF 파일이 아닙니다.")
    if ext in _ZIP_EXTS and head[:2] != b"PK":
        raise ApiError(415, "UNSUPPORTED_MEDIA", "Office 파일 형식이 올바르지 않습니다.")
    return media, None, None


def register(s: Session, sf: StoredFile, actor_id: str) -> Attachment:
    att = Attachment(id=sf.attachment_id, project_id=sf.project_id, original_name=sf.original_name,
                     stored_relative_path=sf.relative_path, media_type=sf.media_type, size_bytes=sf.size_bytes,
                     sha256=sf.sha256, width=sf.width, height=sf.height, state="temp", uploaded_by=actor_id)
    s.add(att)
    s.flush()
    return att


def ser_attachment(a: Attachment) -> dict:
    return {"id": a.id, "projectId": a.project_id, "originalName": a.original_name, "mediaType": a.media_type,
            "sizeBytes": a.size_bytes, "width": a.width, "height": a.height, "state": a.state,
            "isImage": a.media_type in IMAGE_MEDIA_TYPES, "uploadedAt": iso(a.uploaded_at)}


def get_attachment(s: Session, attachment_id: str) -> Attachment:
    a = s.get(Attachment, attachment_id)
    if a is None:
        raise not_found("첨부 파일", attachment_id)
    return a


def resolve_use(s: Session, use_id: str) -> Attachment:
    use = s.get(TaskAttachment, use_id)
    if use is None:
        raise not_found("첨부 사용처", use_id)
    return use.attachment


def cleanup_temp(s: Session, settings: Settings) -> int:
    """오래된 임시 첨부 정리. 어떤 사용처에서든 참조 중인 파일은 건드리지 않는다."""
    cutoff = utcnow() - timedelta(days=settings.temp_attachment_retention_days)
    stale = s.execute(select(Attachment).where(Attachment.state == "temp", Attachment.uploaded_at < cutoff)).scalars().all()
    removed = 0
    for a in stale:
        referenced = s.execute(select(TaskAttachment.id).where(TaskAttachment.attachment_id == a.id).limit(1)).first()
        if referenced:
            continue
        attachment_abs_path(settings, a.stored_relative_path).unlink(missing_ok=True)
        s.delete(a)
        removed += 1
    return removed
