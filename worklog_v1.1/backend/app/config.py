"""설정 로딩. 경로는 CWD가 아니라 프로그램(런처) 폴더 기준으로 해석한다.

우선순위: 환경변수 WORKLOG_* > config/config.json > 기본값. config/ 와 data/ 는 소스 업데이트로 덮어쓰지 않는다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]  # <program>/backend/app/config.py -> <program>

IMAGE_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp"}
DOCUMENT_MEDIA_TYPES = {
    "application/pdf": {".pdf"},
    "text/csv": {".csv"},
    "text/plain": {".txt"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": {".pptx"},
}


@dataclass
class Settings:
    app_root: Path = APP_ROOT
    data_dir: Path = field(default_factory=lambda: APP_ROOT / "data")
    backup_dir: Path | None = None
    host: str = "0.0.0.0"
    port: int = 8000
    timezone: str = "Asia/Seoul"
    backup_retention_count: int = 14
    temp_attachment_retention_days: int = 7
    idempotency_retention_days: int = 30
    max_attachment_bytes: int = 20 * 1024 * 1024
    max_image_pixels: int = 50_000_000
    max_document_bytes: int = 2 * 1024 * 1024
    max_document_depth: int = 40
    max_document_nodes: int = 20_000
    sqlite_busy_timeout_ms: int = 5000
    sqlite_synchronous: str = "FULL"
    backup_hardlink_attachments: bool = False
    export_worker_enabled: bool = True
    export_poll_seconds: float = 1.0
    frontend_dist: Path = field(default_factory=lambda: APP_ROOT / "frontend" / "dist")
    # 보고자료(PPT) AI 연결. 주소·키가 모두 있으면 서버가 직접 호출(live), 없으면 화면에서 프롬프트 복사·응답 붙여넣기(paste).
    ai_api_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None
    # 사고형 모델(k-exaone_v2)은 사고 과정까지 만든 뒤 답하므로 입력이 크면 2분을 넘기기 쉽다 → 기본 5분
    ai_timeout_seconds: float = 300.0
    # 응답 길이 한도(max_tokens). 비우면 보내지 않음(서버 기본값). '길이 한도에 걸려 잘림' 오류가 나면 늘린다
    ai_max_tokens: int | None = None
    # 한 번의 AI 호출에 넣을 업무일지 원문 글자 수 상한. 넘으면 기록마다 균등하게 줄이고 확인 보고서에 알린다
    ai_input_chars: int = 24000
    # 호환 형식(system 내용을 user에 합치고 temperature·max_tokens 없이). auto = 5xx가 끝까지 나면 한 번 시도 후 그 작업 동안 유지
    ai_compat_mode: str = "auto"
    # 서버가 읽은 설정 파일 (화면·시작 로그에 "왜 붙여넣기 방식인지" 보여 줄 때 사용)
    config_file: Path | None = None
    config_found: bool = False
    # 요청에 response_format={"type":"json_object"}를 붙일지. 사내 EXAONE 게이트웨이는 이 옵션에 500을 돌려줘서 기본은 끔
    # (프롬프트가 JSON만 요구하고, 응답에 설명·```json이 섞여도 JSON만 골라 읽음)
    ai_json_mode: bool = False
    report_worker_enabled: bool = True
    report_job_retention: int = 200

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def ai_live(self) -> bool:
        return bool(self.ai_api_url and self.ai_api_key)

    @property
    def ai_paste_reason(self) -> str:
        """서버 AI를 쓰지 않는(붙여넣기 방식) 이유. 키 값은 담지 않는다."""
        if self.ai_live:
            return ""
        where = str(self.config_file) if self.config_file else "config\\config.json"
        if self.config_file and not self.config_found:
            return f"설정 파일이 없음: {where} (config.example.json 을 복사해 AI_API_URL·AI_API_KEY 를 넣으세요)"
        missing = [name for name, value in (("AI_API_URL", self.ai_api_url), ("AI_API_KEY", self.ai_api_key)) if not value]
        return f"{where} 의 {'·'.join(missing)} 이(가) 비어 있음"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "worklog.sqlite3"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"

    @property
    def json_dir(self) -> Path:
        return self.data_dir / "json"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "temp"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def backups_root(self) -> Path:
        return self.backup_dir or (self.data_dir / "backups")

    def ensure_dirs(self) -> None:
        for p in (self.db_path.parent, self.json_dir, self.attachments_dir, self.temp_dir,
                  self.logs_dir, self.exports_dir, self.backups_root):
            p.mkdir(parents=True, exist_ok=True)


def _resolve(value: str, base: Path) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (base / p)


def load_settings(config_file: Path | None = None) -> Settings:
    s = Settings()
    cfg_path = config_file or (APP_ROOT / "config" / "config.json")
    raw: dict = {}
    s.config_file, s.config_found = cfg_path, cfg_path.exists()
    if cfg_path.exists():
        raw = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    env = {k[len("WORKLOG_"):].lower(): v for k, v in os.environ.items() if k.startswith("WORKLOG_")}
    merged = {**{k.lower(): v for k, v in raw.items()}, **env}

    if "data_dir" in merged:
        s.data_dir = _resolve(str(merged["data_dir"]), APP_ROOT)
    if merged.get("backup_dir"):
        s.backup_dir = _resolve(str(merged["backup_dir"]), APP_ROOT)
    for key, cast in (("host", str), ("port", int), ("timezone", str), ("sqlite_synchronous", str), ("sqlite_busy_timeout_ms", int),
                      ("backup_retention_count", int), ("temp_attachment_retention_days", int),
                      ("idempotency_retention_days", int)):
        if key in merged:
            setattr(s, key, cast(merged[key]))
    for flag in ("export_worker_enabled", "backup_hardlink_attachments", "report_worker_enabled", "ai_json_mode"):
        if flag in merged:
            setattr(s, flag, str(merged[flag]).lower() in {"1", "true", "yes"})
    for key in ("ai_api_url", "ai_api_key", "ai_model"):
        if merged.get(key):
            setattr(s, key, str(merged[key]).strip())
    for key, cast in (("ai_timeout_seconds", float), ("report_job_retention", int), ("ai_input_chars", int)):
        if key in merged:
            setattr(s, key, cast(merged[key]))
    if str(merged.get("ai_compat_mode") or "").strip():
        value = str(merged["ai_compat_mode"]).strip().lower()
        s.ai_compat_mode = "true" if value in {"1", "true", "yes", "on"} else "false" if value in {"0", "false", "no", "off"} else "auto"
    if str(merged.get("ai_max_tokens") or "").strip() not in ("", "0"):
        s.ai_max_tokens = int(merged["ai_max_tokens"])
    return s
