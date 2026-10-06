"""입력 읽기를 한 곳으로: 내부 형식 파일 + WorkLog export.

- 내부 형식: data/master/projects/{project_id}.json, data/raw/daily/**/{daily_id}.json (기존 예시·웹 테스트 메모)
- WorkLog export: config/sources.json의 worklog_dirs(기본 data/worklog) 아래 모든 *.json을 찾아
  fileType으로 구분한다 (WORKLOG_PROJECT_EXPORT / WORKLOG_DAILY_EXPORT). 폴더·파일 이름 규칙에 기대지 않는다.
- 같은 과제의 project export가 여러 개면 generatedAt(같으면 sourceRevision)이 가장 최근인 것을 쓴다.
원본은 읽기만 하고, 변환 결과는 메모리에서만 쓴다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import load_json, validate_schema
from .worklog import DAILY_TYPE, PROJECT_TYPE, WorklogError, load_mapping, to_dailies, to_project

_cache: dict[tuple[str, int, int], dict[str, Any] | None] = {}


def worklog_dirs(root: Path) -> list[Path]:
    config = root / "config/sources.json"
    names = load_json(config).get("worklog_dirs", []) if config.exists() else ["data/worklog"]
    return [root / name for name in names]


def _read(path: Path) -> dict[str, Any] | None:
    """fileType이 있는 WorkLog export만 돌려준다 (수정 시각·크기로 캐시)."""
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _cache:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = None
        _cache[key] = value if isinstance(value, dict) and value.get("fileType") in (PROJECT_TYPE, DAILY_TYPE) else None
    return _cache[key]


def worklog_exports(root: Path, file_type: str) -> list[tuple[Path, dict[str, Any]]]:
    found = []
    for base in worklog_dirs(root):
        if base.is_dir():
            for path in sorted(base.rglob("*.json")):
                value = _read(path)
                if value and value["fileType"] == file_type:
                    found.append((path, value))
    return found


def _project_export(root: Path, project_id: str) -> tuple[Path, dict[str, Any]] | None:
    matches = [(p, v) for p, v in worklog_exports(root, PROJECT_TYPE) if (v.get("project") or {}).get("id") == project_id]
    return max(matches, key=lambda pv: (pv[1].get("generatedAt") or "", pv[1].get("sourceRevision") or 0)) if matches else None


def list_projects(root: Path) -> list[dict[str, str]]:
    """과제 목록 (내부 형식 먼저, WorkLog 과제는 이름순). 삭제된 WorkLog 과제는 뺀다."""
    projects = []
    for path in sorted((root / "data/master/projects").glob("*.json")):
        value = load_json(path)
        projects.append({"project_id": value["project_id"], "name": value["name"], "source": "internal"})
    seen = {p["project_id"] for p in projects}
    worklog = {}
    for _path, export in worklog_exports(root, PROJECT_TYPE):
        project = export.get("project") or {}
        if project.get("id") and project["id"] not in seen and not project.get("deletedAt"):
            worklog[project["id"]] = {"project_id": project["id"], "name": project.get("name") or project["id"], "source": "worklog"}
    return projects + sorted(worklog.values(), key=lambda p: p["name"])


def load_project(root: Path, project_id: str, notes: list[str] | None = None) -> dict[str, Any]:
    """내부 기준정보 또는 WorkLog export를 내부 형식으로 읽고 스키마를 검증한다."""
    path = root / f"data/master/projects/{project_id}.json"
    if path.exists():
        project = load_json(path)
    else:
        found = _project_export(root, project_id)
        if found is None:
            raise FileNotFoundError(f"과제 기준정보 없음: {project_id} (data/master/projects 또는 WorkLog export)")
        source, export = found
        local: list[str] = []
        try:
            project = to_project(export, load_mapping(root), local)
        except (WorklogError, KeyError, ValueError) as exc:
            raise WorklogError(f"{source.name}: WorkLog 과제 변환 실패 ({exc})") from exc
        if notes is not None:
            notes += [f"WorkLog {source.name} (rev {export.get('sourceRevision')}): {n}" for n in local]
    validate_schema(project, root / "schemas/project.schema.json")
    return project


def worklog_dailies(root: Path, project: dict[str, Any], notes: list[str] | None = None) -> list[dict[str, Any]]:
    """그 과제의 WorkLog 업무일지 → 내부 daily 목록 (스키마 검증 포함)."""
    if (project.get("source") or {}).get("system") != "worklog":
        return []
    mapping = load_mapping(root)
    dailies = []
    for path, export in worklog_exports(root, DAILY_TYPE):
        if (export.get("project") or {}).get("id") != project["project_id"]:
            continue
        local: list[str] = []
        try:
            converted = to_dailies(export, project, mapping, local)
            for daily in converted:
                validate_schema(daily, root / "schemas/daily.schema.json")
        except (WorklogError, KeyError, ValueError) as exc:
            raise WorklogError(f"{path.name}: WorkLog 업무일지 변환 실패 ({exc})") from exc
        dailies += converted
        if notes is not None:
            notes += [f"WorkLog {path.name}: {n}" for n in local]
    ids = [d["daily_id"] for d in dailies]
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        raise WorklogError(f"같은 날짜 업무일지 export가 둘 이상 있어 기록 ID가 겹침: {', '.join(duplicated)} (최신 파일만 두세요)")
    return dailies
