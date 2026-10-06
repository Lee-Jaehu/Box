"""프로젝트 목록의 마일스톤 집계 milestoneSummary (내비게이션 트리의 완료 PJT 검회색 판정용)."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def env(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", export_worker_enabled=False, report_worker_enabled=False)
    with TestClient(create_app(settings)) as client:
        def call(method: str, path: str, body: dict | None = None, actor: str | None = None) -> dict:
            headers = {"Idempotency-Key": uuid.uuid4().hex}
            if actor:
                headers["X-Actor-Id"] = actor
            r = client.request(method, f"/api/v1{path}", json=body, headers=headers)
            assert r.status_code in (200, 201), r.text
            return r.json()["data"]

        division = call("POST", "/organizations", {"name": "담당", "kind": "division"})
        team = call("POST", "/organizations", {"name": "팀", "kind": "team", "parentId": division["id"]})
        user = call("POST", "/users", {"name": "담당자", "teamId": team["id"]})
        yield call, team["id"], user["id"]


def _project(call, team_id: str, actor: str, name: str) -> dict:
    return call("POST", "/projects", {"name": name, "teamId": team_id, "ownerUserId": actor, "status": "in_progress"}, actor)


def _summaries(call) -> dict[str, dict]:
    return {p["name"]: p["milestoneSummary"] for p in call("GET", "/projects?limit=200")["items"]}


def test_milestone_summary_excludes_general_and_deleted(env):
    call, team_id, actor = env
    done = _project(call, team_id, actor, "완료 과제")
    open_ = _project(call, team_id, actor, "진행 과제")
    _project(call, team_id, actor, "마일스톤 없음")
    ms = [call("POST", f"/projects/{done['id']}/milestones", {"name": f"단계{i}"}, actor) for i in range(3)]
    call("PATCH", f"/milestones/{ms[0]['id']}", {"expectedRevision": ms[0]["revision"], "status": "completed"}, actor)
    call("PATCH", f"/milestones/{ms[1]['id']}", {"expectedRevision": ms[1]["revision"], "status": "cancelled"}, actor)
    call("DELETE", f"/milestones/{ms[2]['id']}?expectedRevision={ms[2]['revision']}", None, actor)  # 삭제된 단계는 세지 않음
    call("POST", f"/projects/{open_['id']}/milestones", {"name": "진행 단계"}, actor)

    summary = _summaries(call)
    assert summary["완료 과제"] == {"total": 2, "completed": 1, "cancelled": 1}
    assert summary["진행 과제"] == {"total": 1, "completed": 0, "cancelled": 0}
    assert summary["마일스톤 없음"] == {"total": 0, "completed": 0, "cancelled": 0}  # 일반·수시 업무 마일스톤은 제외
    detail = call("GET", f"/projects/{done['id']}")
    assert detail["milestoneSummary"] == summary["완료 과제"]
