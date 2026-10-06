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


def _doc(text: str) -> dict:
    return {"documentVersion": 1, "format": "tiptap-json",
            "doc": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}}


def test_people_owner_members_then_log_authors(env):
    call, team_id, owner = env
    member = call("POST", "/users", {"name": "나참여", "teamId": team_id})["id"]
    writer = call("POST", "/users", {"name": "가작성", "teamId": team_id})["id"]
    gone = call("POST", "/users", {"name": "다삭제", "teamId": team_id})["id"]
    project = call("POST", "/projects", {"name": "사람 과제", "teamId": team_id, "ownerUserId": owner, "memberIds": [member],
                                         "status": "in_progress"}, owner)
    general = [m for m in call("GET", f"/projects/{project['id']}")["milestones"] if m["isGeneral"]][0]
    body = {"expectedRevision": 0, "tasks": [{"milestoneId": general["id"], "content": _doc("일지")}]}
    call("PUT", f"/projects/{project['id']}/logs/2026-09-29/{writer}", body, writer)   # 참여자가 아닌 작성자
    call("PUT", f"/projects/{project['id']}/logs/2026-09-29/{member}", body, member)   # 참여자 (중복으로 넣지 않음)
    log = call("PUT", f"/projects/{project['id']}/logs/2026-09-29/{gone}", body, gone)
    call("DELETE", f"/logs/{log['id']}?expectedRevision={log['revision']}", None, gone)  # 삭제한 일지만 있으면 빠짐

    listed = [p for p in call("GET", "/projects?limit=200")["items"] if p["name"] == "사람 과제"][0]
    assert [(x["name"], x["role"]) for x in listed["people"]] == [("담당자", "owner"), ("나참여", "member"), ("가작성", "author")]
    assert call("GET", f"/projects/{project['id']}")["people"] == listed["people"]
