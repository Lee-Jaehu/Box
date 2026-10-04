"""웹 테스트 화면의 작업공간 로직 (메모 편집 → 주간 정리 → PPT).

- 작업공간(workspace/)은 저장소 입력을 복사한 시험용 폴더다. 웹에서 고치는 것은 작업공간뿐이고
  저장소의 data/master·data/raw·예시 derived는 바뀌지 않는다 (웹이 시연용 Worklog 역할).
- EXAONE API가 없을 때는 AI 응답 파일이 없으면 프롬프트를 돌려주고 멈춘다. 사용자가 다른 AI에서 받은
  응답 JSON을 붙여 넣으면 mock 응답으로 저장해 다시 실행한다.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .ai import RESPONSE_SHAPES, AIError, ExaoneClient, MockResponseMissing, ResponseFormatError, read_payload
from .core import KST, ValidationError, atomic_json, load_json, validate_schema, week_range
from .ppt.budget import BudgetError
from .pptgen import TEMPLATE_NAME, find_template, generate_ppt
from .weekly import run_weekly

REPO = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = REPO / "workspace"
MARKER = ".workspace"
RESPONSE_RE = re.compile(r"^(weekly_rollup|cumulative_update|fit_to_budget)__[A-Za-z0-9-]+__\d{4}-W\d{2}(__[a-z_]+)?\.json$")
AUTHOR_RE = re.compile(r"^[a-z0-9]+$")
CATEGORIES = {"DEV", "ROLL", "OPS", "INV", "DATA", "RPT"}


class WorkbenchError(ValueError):
    """사용자에게 그대로 보여 줄 수 있는 입력 오류."""


# ---------------------------------------------------------------- 작업공간

# 작업공간이 쓸 수 있는 상태인지 확인할 때 보는 파일
# 실행에 필요한 저장소 파일 (사용자가 고치거나 지우는 data/raw·data/derived·prompts/mock_responses는 제외)
RUNTIME_TREES = ("config", "schemas", "prompts", "data/master")
USER_MANAGED = ("prompts/mock_responses",)
# 초기화 전에 백업하는 사용자 입력·결과
BACKUP_ITEMS = ("data/raw", "data/derived", "prompts/mock_responses", "output")


def _copy(src: Path, dst: Path, *, overwrite: bool) -> None:
    """파일 하나 복사. overwrite=False면 이미 있는 파일(사용자가 고친 메모 등)은 건드리지 않는다."""
    if overwrite or not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path, *, overwrite: bool) -> None:
    for path in src.rglob("*"):
        if path.is_file():
            _copy(path, dst / path.relative_to(src), overwrite=overwrite)


def runtime_files(repo: Path = REPO) -> list[str]:
    """작업공간에 반드시 있어야 하는 파일 목록 (저장소 기준 상대 경로)."""
    files = [TEMPLATE_NAME, *(p.name for p in repo.glob("LGSM*.[tT][tT][fF]"))]
    for tree in RUNTIME_TREES:
        for path in (repo / tree).rglob("*"):
            rel = path.relative_to(repo).as_posix()
            if path.is_file() and not rel.startswith(USER_MANAGED):
                files.append(rel)
    return files


def missing_files(ws: Path, repo: Path = REPO) -> list[str]:
    return [rel for rel in runtime_files(repo) if not (ws / rel).exists()]


def stale_files(ws: Path, repo: Path = REPO) -> list[str]:
    """저장소에서 바뀐 실행 파일(프롬프트·스키마·설정·기준정보). 템플릿·글꼴은 비교하지 않는다."""
    stale = []
    for rel in runtime_files(repo):
        if rel.startswith(RUNTIME_TREES) and (ws / rel).is_file() and (ws / rel).read_bytes() != (repo / rel).read_bytes():
            stale.append(rel)
    return stale


def refresh_runtime(ws: Path, repo: Path = REPO) -> list[str]:
    """저장소가 갱신되면(예: 프롬프트 v0.4) 작업공간의 실행 파일도 맞춘다. 사용자 입력·응답·결과는 건드리지 않는다."""
    updated = stale_files(ws, repo)
    for rel in updated:
        _copy(repo / rel, ws / rel, overwrite=True)
    return updated


def workspace_ok(ws: Path, repo: Path = REPO) -> bool:
    return (ws / MARKER).exists() and not missing_files(ws, repo)


def _remove_tree(path: Path) -> list[str]:
    """지울 수 있는 것은 모두 지우고, 지우지 못한 파일(예: Windows에서 열려 있는 PPT)은 목록으로 돌려준다."""
    failed: list[str] = []
    if not path.exists():
        return failed
    for item in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            if item.is_dir() and not item.is_symlink():
                item.rmdir()
            else:
                item.unlink()
        except OSError:
            if item.is_file():
                failed.append(item.relative_to(path).as_posix())
    return failed


def _backup(ws: Path) -> Path | None:
    """초기화 전 사용자 입력·결과를 workspace_backups/날짜시각[-n]/ 에 복사한다.

    백업 폴더는 매번 새로 만든다(같은 초에 두 번 초기화해도 덮어쓰지 않음).
    하나라도 복사하지 못하면 WorkbenchError → 호출한 쪽은 아무것도 지우지 않는다.
    """
    items = [rel for rel in BACKUP_ITEMS if (ws / rel).exists()]
    if not items:
        return None
    root = ws.parent / "workspace_backups"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y%m%d-%H%M%S")
    for n in range(1000):
        target = root / (stamp if n == 0 else f"{stamp}-{n}")
        try:
            target.mkdir()
            break
        except FileExistsError:
            continue
    else:
        raise WorkbenchError("백업 폴더를 만들 수 없습니다")
    failed: list[str] = []
    for rel in items:
        try:
            shutil.copytree(ws / rel, target / rel)
        except shutil.Error as exc:
            failed += [str(err[0]) for err in exc.args[0]]
        except OSError as exc:
            failed.append(f"{rel} ({exc.strerror or exc})")
    if failed:
        raise WorkbenchError(f"백업에 실패해 초기화를 중단했습니다 (지운 파일 없음). 실패: {', '.join(failed[:5])}"
                             + (f" 외 {len(failed) - 5}건" if len(failed) > 5 else "") + f" / 백업 위치: {target}")
    return target


def init_workspace(ws: Path, *, force: bool = False, repo: Path = REPO) -> dict[str, Any]:
    """작업공간을 준비한다.

    - 처음이거나 파일이 빠져 있으면(예: 초기화가 중간에 실패) 저장소 입력 + W40 데모를 다시 채운다.
    - force=True(초기화)면 사용자 입력·결과를 백업한 뒤 지우고 다시 만든다.
      Windows에서 열려 있어 지우지 못한 파일은 건너뛰고 결과에 알린다.
    """
    result: dict[str, Any] = {"restored": False, "backup": None, "locked": [], "updated": []}
    if workspace_ok(ws, repo) and not force:
        result["updated"] = refresh_runtime(ws, repo)
        return result
    ws.mkdir(parents=True, exist_ok=True)
    if force:
        backup = _backup(ws)  # 실패하면 여기서 중단 (아무것도 지우지 않음)
        result["backup"] = str(backup) if backup else None
    (ws / MARKER).unlink(missing_ok=True)  # 표시 파일은 지우기 전에 없애고 마지막에 다시 쓴다
    if force:
        for name in ("config", "schemas", "prompts", "data", "output"):
            result["locked"] += [f"{name}/{rel}" for rel in _remove_tree(ws / name)]
    # 초기화(force)는 저장소 상태로 덮어쓰고, 복구(빠진 파일 채우기)는 있는 파일을 그대로 둔다
    for name in ("config", "schemas", "prompts", "data"):
        _copy_tree(repo / name, ws / name, overwrite=force)
    if not force:
        result["updated"] = refresh_runtime(ws, repo)
    for source in [find_template(repo), *repo.glob("LGSM*.[tT][tT][fF]")]:
        try:
            _copy(source, ws / source.name, overwrite=force)
        except PermissionError:
            if not (ws / source.name).exists():
                raise
            result["locked"].append(source.name)  # 같은 파일이 이미 있고 열려 있음 → 그대로 사용
    demo = repo / "demo/w40"
    if (demo / "raw").is_dir():
        _copy_tree(demo / "raw", ws / "data/raw", overwrite=force)
    for path in (demo / "mock_responses").glob("*.json"):
        _copy(path, ws / "prompts/mock_responses" / path.name, overwrite=force)
    (ws / MARKER).write_text("weekly-report 웹 테스트 작업공간 (지워도 다시 만들어짐)\n", encoding="utf-8")
    result["restored"] = True
    return result


def list_projects(ws: Path) -> list[dict[str, str]]:
    projects = []
    for path in sorted((ws / "data/master/projects").glob("*.json")):
        value = load_json(path)
        projects.append({"project_id": value["project_id"], "name": value["name"]})
    return projects


# ---------------------------------------------------------------- Daily 메모

def _daily_paths(ws: Path) -> list[Path]:
    return sorted((ws / "data/raw/daily").rglob("*.json"))


def _find_daily(ws: Path, daily_id: str) -> Path:
    for path in _daily_paths(ws):
        if path.stem == daily_id:
            return path
    raise WorkbenchError(f"메모를 찾을 수 없음: {daily_id}")


def exclusion_reason(daily: dict[str, Any], project_id: str) -> str | None:
    """주간 정리 대상이 아닌 이유 (weekly.select_dailies와 같은 기준)."""
    if daily.get("deleted") is True:
        return "삭제됨"
    if daily.get("visibility") != "project" or not daily.get("project_id"):
        return "개인 메모"
    if daily.get("project_id") != project_id:
        return "다른 과제"
    return None


def list_dailies(ws: Path, project_id: str, week: str) -> list[dict[str, Any]]:
    """그 주의 메모: 이 과제 메모 + 개인 메모(제외 표시). 다른 과제 메모는 보이지 않는다."""
    start, end = week_range(week)
    result = []
    for path in _daily_paths(ws):
        daily = load_json(path)
        try:
            day = date.fromisoformat(daily["date"])
        except (KeyError, ValueError):
            continue
        if not (start <= day <= end) or daily.get("project_id") not in (project_id, None):
            continue
        result.append({**daily, "excluded": exclusion_reason(daily, project_id)})
    return sorted(result, key=lambda d: (d["date"], d["daily_id"]))


def _number(value: str) -> Any:
    text = value.strip()
    if text == "":
        return None
    try:
        return int(text) if re.fullmatch(r"-?\d+", text) else float(text) if re.fullmatch(r"-?\d+\.\d+", text) else text
    except ValueError:
        return text


def parse_table(text: str) -> tuple[list[str], list[list[Any]]]:
    """첫 줄 = 열 이름. 탭이 있으면 탭, 없으면 쉼표로 나눈다. 숫자는 값으로 저장."""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return [], []
    sep = "\t" if "\t" in lines[0] else ","
    columns = [c.strip() for c in lines[0].split(sep)]
    rows = []
    for line in lines[1:]:
        cells = [_number(c) for c in line.split(sep)]
        if len(cells) != len(columns):
            raise WorkbenchError(f"표 행의 칸 수({len(cells)})가 열 수({len(columns)})와 다름: {line}")
        rows.append(cells)
    return columns, rows


def table_text(daily: dict[str, Any]) -> tuple[str, str]:
    """화면 편집용: 첫 번째 표 → (제목, 탭 구분 텍스트)."""
    if not daily.get("tables"):
        return "", ""
    table = daily["tables"][0]
    lines = ["\t".join(table["columns"])] + ["\t".join("" if v is None else str(v) for v in row) for row in table["rows"]]
    return table["title"], "\n".join(lines)


def save_daily(ws: Path, form: dict[str, Any]) -> dict[str, Any]:
    """새 메모 저장 또는 수정 (ID 자동 부여, revision 증가, 스키마 검증)."""
    author = str(form.get("author", "")).strip()
    if not AUTHOR_RE.fullmatch(author):
        raise WorkbenchError("작성자는 영문 소문자·숫자 ID여야 합니다 (예: ljh)")
    try:
        day = date.fromisoformat(str(form.get("date", "")))
    except ValueError as exc:
        raise WorkbenchError("날짜 형식은 YYYY-MM-DD 입니다") from exc
    visibility = form.get("visibility") or "project"
    project_id = (form.get("project_id") or None) if visibility == "project" else None
    if visibility == "project" and not project_id:
        raise WorkbenchError("과제 공개 메모는 과제를 선택해야 합니다")
    category = form.get("category") or None
    if category is not None and category not in CATEGORIES:
        raise WorkbenchError(f"카테고리는 {', '.join(sorted(CATEGORIES))} 중 하나")
    raw_text = str(form.get("raw_text", "")).strip()
    if not raw_text:
        raise WorkbenchError("본문을 입력하세요")
    columns, rows = parse_table(str(form.get("table_text", "")))
    tables = [{"table_id": "T1", "title": str(form.get("table_title") or "표").strip(), "columns": columns, "rows": rows}] if columns else []

    now = datetime.now(KST).replace(microsecond=0).isoformat()
    old_path, old = None, None
    if form.get("daily_id"):
        old_path = _find_daily(ws, form["daily_id"])
        old = load_json(old_path)
    tag = day.strftime("%y-%m-%d")
    if old and old["date"] == day.isoformat() and old["author"] == author:
        daily_id = old["daily_id"]
    else:
        prefix = f"D-{day.strftime('%y%m%d')}-{author}-"
        used = {p.stem for p in _daily_paths(ws) if p.stem.startswith(prefix)}
        daily_id = next(f"{prefix}{n:02d}" for n in range(1, 100) if f"{prefix}{n:02d}" not in used)
    meta = {"schema": "daily", "schema_version": "0.1", "revision": (old["meta"]["revision"] + 1) if old else 1,
            "created_at": old["meta"]["created_at"] if old else now, "updated_at": now, "updated_by": author}
    daily = {"meta": meta, "daily_id": daily_id, "date": day.isoformat(), "tag": tag, "author": author,
             "project_id": project_id, "category": category, "visibility": visibility, "raw_text": raw_text,
             "tables": tables, "pics": [], "links": [], "deleted": bool(form.get("deleted"))}
    try:
        validate_schema(daily, ws / "schemas/daily.schema.json")
    except ValidationError as exc:
        raise WorkbenchError(f"메모 형식 오류: {exc}") from exc
    path = ws / f"data/raw/daily/{day.year}/{tag}/{daily_id}.json"
    atomic_json(path, daily, updated_by=author)
    if old_path and old_path != path:
        old_path.unlink()
    return load_json(path)


def mark_deleted(ws: Path, daily_id: str) -> None:
    """삭제는 파일을 지우지 않고 deleted=true로 표시한다 (인터페이스 규칙)."""
    path = _find_daily(ws, daily_id)
    daily = load_json(path)
    daily["deleted"] = True
    daily["meta"]["revision"] += 1
    atomic_json(path, daily, updated_by=daily["author"])


# ---------------------------------------------------------------- AI 응답

def response_format(prompt_id: str) -> str:
    """화면 안내용: 이 단계 응답에 꼭 있어야 하는 키."""
    shape = RESPONSE_SHAPES[prompt_id]
    need = [f'"{k}": {{...}}' for k in shape["objects"]] + [f'"{k}": [...]' for k in shape["lists"]]
    return "{" + ", ".join(need) + "}" + (f" (선택: {', '.join(shape['optional'])})" if shape["optional"] else "")


def save_response(ws: Path, name: str, text: str) -> None:
    """붙여 넣은 AI 응답을 형식 검사 후 저장한다 (틀리면 저장하지 않고 이유를 알려 준다)."""
    match = RESPONSE_RE.fullmatch(name)
    if not match:
        raise WorkbenchError(f"응답 파일 이름이 올바르지 않음: {name}")
    prompt_id = match.group(1)
    try:
        value = read_payload(text, prompt_id)
    except json.JSONDecodeError as exc:
        raise WorkbenchError(f"JSON 형식이 아닙니다: {exc}") from exc
    except ResponseFormatError as exc:
        raise WorkbenchError(f"{exc}. 필요한 형식: {response_format(prompt_id)} — 저장하지 않았습니다") from exc
    path = ws / "prompts/mock_responses" / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clear_responses(ws: Path, project_id: str, week: str) -> list[str]:
    removed = []
    for path in (ws / "prompts/mock_responses").glob(f"*__{project_id}__{week}*.json"):
        path.unlink()
        removed.append(path.name)
    return sorted(removed)


# ---------------------------------------------------------------- 실행

class PromptCapturingClient(ExaoneClient):
    """응답이 없을 때 보낼 프롬프트를 함께 알려 주는 클라이언트."""

    last: dict[str, str] | None = None

    def complete(self, prompt_id, project_id, week, system, user, variant=None):
        name = f"{prompt_id}__{project_id}__{week}" + (f"__{variant}" if variant else "") + ".json"
        self.last = {"prompt_id": prompt_id, "response_name": name, "prompt": f"{system}\n\n{user}"}
        return super().complete(prompt_id, project_id, week, system, user, variant)


def _rel(ws: Path, path: Path) -> str:
    return path.resolve().relative_to(ws.resolve()).as_posix()


def _need_response(client: PromptCapturingClient) -> dict[str, Any]:
    last = client.last or {}
    return {"status": "need_response", **last, "format": response_format(last["prompt_id"]) if last.get("prompt_id") in RESPONSE_SHAPES else ""}


def run(ws: Path, project_id: str, week: str, mode: str = "mock") -> dict[str, Any]:
    client = PromptCapturingClient(ws, mode)
    try:
        weekly_path, cum_path, report = run_weekly(ws, project_id, week, ws, mode, client=client)
    except MockResponseMissing:
        return _need_response(client)
    except ResponseFormatError as exc:
        # 저장돼 있던 응답이 형식에 맞지 않음 → 그 단계만 다시 붙여 넣게 한다 (다른 단계 응답은 그대로)
        need = _need_response(client)
        saved = ws / "prompts/mock_responses" / need.get("response_name", "")
        return {**need, "error": str(exc), "previous": saved.read_text(encoding="utf-8") if saved.is_file() else ""}
    except (ValidationError, AIError, FileNotFoundError) as exc:
        return {"status": "error", "stage": "주간 정리", "message": str(exc)}
    pptx = ws / f"output/{project_id}_{week}.pptx"
    try:
        notes = generate_ppt(ws, ws / f"data/master/projects/{project_id}.json", weekly_path, cum_path,
                             find_template(ws), pptx, client=client)
    except PermissionError:
        return {"status": "error", "stage": "PPT", "message": f"{pptx.name}이(가) PowerPoint에서 열려 있습니다. 파일을 닫고 다시 실행하세요."}
    except (ValidationError, BudgetError, FileNotFoundError) as exc:
        return {"status": "error", "stage": "PPT", "message": str(exc)}
    check = pptx.with_name(f"{pptx.stem}_ppt_check.txt")
    return {
        "status": "ok",
        "problems": [n for n in notes if n.startswith("PPT 검사 문제")],
        "files": {"pptx": _rel(ws, pptx), "weekly": _rel(ws, weekly_path), "cumulative": _rel(ws, cum_path),
                  "validation": _rel(ws, report), "ppt_check": _rel(ws, check)},
        "validation": report.read_text(encoding="utf-8"),
        "ppt_check": check.read_text(encoding="utf-8"),
    }


def resolve_file(ws: Path, rel: str) -> Path:
    """작업공간 안의 파일만 내려준다."""
    path = (ws / rel).resolve()
    if not path.is_relative_to(ws.resolve()) or not path.is_file():
        raise WorkbenchError("파일을 찾을 수 없습니다")
    return path
