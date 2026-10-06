"""약 20명 혼합 사용 부하 확인 (httpx + 스레드). 실행 중인 서버(기본 http://127.0.0.1:8000)에 대해 실행한다.

  python scripts/loadtest.py --base http://127.0.0.1:8001 --users 20 --rounds 5

시나리오: 사용자 N명이 각자 일지를 저장/수정/조회하고 To-Do를 등록·완료(+일지 TASK 추가)한다.
          모든 사용자가 같은 순간 저장하는 burst 구간도 포함한다. 마지막에 데이터 유실/중복이 없는지 검증한다.
결과(p50/p95)는 '이 PC에서 이 시점에 측정한 값'이며 운영 PC 성능을 보장하지 않는다. 300명 시험은 범위 밖이다.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import threading
import time
import uuid

import httpx

DOC = lambda text: {"documentVersion": 1, "format": "tiptap-json", "doc": {"type": "doc", "content": [  # noqa: E731
    {"type": "paragraph", "content": [{"type": "text", "text": text}]},
    {"type": "table", "content": [{"type": "tableRow", "content": [
        {"type": "tableHeader", "attrs": {"colspan": 1, "rowspan": 1}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "항목"}]}]},
        {"type": "tableHeader", "attrs": {"colspan": 1, "rowspan": 1}, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "결과"}]}]}]}]}]}}


class Recorder:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lat: dict[str, list[float]] = {}
        self.errors: list[str] = []

    def add(self, op: str, seconds: float) -> None:
        with self.lock:
            self.lat.setdefault(op, []).append(seconds)

    def err(self, msg: str) -> None:
        with self.lock:
            self.errors.append(msg)


THINK = 0.0  # 사용자 생각 시간(초, 0~THINK 균등). 0이면 쉬지 않고 두드리는 최악 시나리오.


def call(rec: Recorder, client: httpx.Client, op: str, method: str, path: str, actor: str | None = None, expect=(200, 201, 202), think: bool = True, **kw):
    if THINK and think:
        time.sleep(random.uniform(0, THINK))  # 지연 측정에 포함하지 않는다
    headers = {"Idempotency-Key": uuid.uuid4().hex}
    if actor:
        headers["X-Actor-Id"] = actor
    t0 = time.perf_counter()
    for attempt in range(3):  # 503 STORAGE_BUSY 는 같은 key 로 재시도하도록 설계됨
        r = client.request(method, path, headers=headers, **kw)
        if r.status_code != 503:
            break
        time.sleep(0.2 * (attempt + 1))
    rec.add(op, time.perf_counter() - t0)
    if r.status_code not in expect:
        rec.err(f"{op} {method} {path} -> {r.status_code} {r.text[:200]}")
    return r


def worker(base: str, rec: Recorder, u: dict, project: dict, rounds: int, barrier: threading.Barrier, results: dict) -> None:
    uid, pid, ms = u["id"], project["id"], project["general"]
    expected_text = ""
    with httpx.Client(base_url=base + "/api/v1", timeout=30) as c:
        rev = 0
        date = "2026-10-04"
        for rnd in range(rounds):
            call(rec, c, "list_projects", "GET", "/projects?limit=50")
            expected_text = f"{u['name']} 라운드 {rnd} " + "내용 " * 40
            body = {"expectedRevision": rev, "tasks": [{"id": u["task"], "milestoneId": ms, "content": DOC(expected_text)}],
                    "newTodos": ([{"clientEntryId": uuid.uuid4().hex, "content": DOC(f"{u['name']} 할 일 {rnd}")}] if rnd % 2 == 0 else [])}
            r = call(rec, c, "save_log", "PUT", f"/projects/{pid}/logs/{date}/{uid}", uid, json=body)
            if r.status_code == 200:
                rev = r.json()["data"]["revision"]
            call(rec, c, "get_log", "GET", f"/projects/{pid}/logs?date={date}&authorId={uid}")
            call(rec, c, "list_todos", "GET", f"/projects/{pid}/todos?limit=50")
            if rnd == 1:  # To-Do 완료 + 내 일지에 결과 TASK 추가(원자적)
                todos = c.get(f"/projects/{pid}/todos?limit=50").json()["data"]["items"]
                mine = [t for t in todos if t["status"] == "open" and t["sourceLogId"]]
                if mine:
                    t = mine[0]
                    cur = c.get(f"/projects/{pid}/logs?date={date}&authorId={uid}").json()["data"]["items"][0]
                    r = call(rec, c, "complete_todo", "POST", f"/todos/{t['id']}/complete", uid, expect=(200, 409), json={
                        "expectedRevision": t["revision"], "resultText": "부하 시험 완료",
                        "appendToDailyLog": {"date": date, "authorId": uid, "milestoneId": ms, "expectedLogRevision": cur["revision"]}})
                    if r.status_code == 200:
                        rev = r.json()["data"]["log"]["revision"]
        # burst: 모두 같은 순간 저장 (서로 다른 날짜/일지 → 충돌 없이 모두 성공해야 함)
        barrier.wait()
        body = {"expectedRevision": 0, "tasks": [{"milestoneId": ms, "content": DOC(f"burst {u['name']}")}]}
        call(rec, c, "burst_save", "PUT", f"/projects/{pid}/logs/2026-10-05/{uid}", uid, think=False, json=body)
        # burst 2: 모두 같은 일지(공유 작성자 1명)에 동시 저장 → 하나만 성공, 나머지는 명확한 409
        barrier.wait()
        shared = {"expectedRevision": 0, "tasks": [{"milestoneId": ms, "content": DOC(f"shared {u['name']}")}]}
        r = call(rec, c, "shared_create", "PUT", f"/projects/{pid}/logs/2026-10-06/{project['sharedAuthor']}", uid, expect=(200, 409), think=False, json=shared)
        results[uid] = {"expected_text": expected_text, "shared_status": r.status_code}


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--p95-target", type=float, default=2.0)
    ap.add_argument("--think", type=float, default=0.0, help="사용자 생각 시간 상한(초). 예: 3")
    a = ap.parse_args()
    global THINK
    THINK = a.think
    rec = Recorder()
    suffix = uuid.uuid4().hex[:6]
    with httpx.Client(base_url=a.base + "/api/v1", timeout=30) as c:
        def post(path, body, actor=None):
            r = c.post(path, json=body, headers={"Idempotency-Key": uuid.uuid4().hex, **({"X-Actor-Id": actor} if actor else {})})
            r.raise_for_status()
            return r.json()["data"]
        div = post("/organizations", {"name": f"부하담당-{suffix}", "kind": "division"})
        team = post("/organizations", {"name": f"부하팀-{suffix}", "kind": "team", "parentId": div["id"]})
        users = [post("/users", {"name": f"사용자{i:02d}-{suffix}", "teamId": team["id"]}) for i in range(a.users)]
        for u in users:
            u["task"] = str(uuid.uuid4())
        proj = post("/projects", {"name": f"부하 프로젝트-{suffix}", "teamId": team["id"], "ownerUserId": users[0]["id"],
                                  "memberIds": [u["id"] for u in users]}, users[0]["id"])
        proj["general"] = next(m for m in proj["milestones"] if m["isGeneral"])["id"]
        proj["sharedAuthor"] = users[0]["id"]
        barrier = threading.Barrier(a.users)
        results: dict = {}
        threads = [threading.Thread(target=worker, args=(a.base, rec, u, proj, a.rounds, barrier, results)) for u in users]
        t0 = time.perf_counter()
        [t.start() for t in threads]
        [t.join() for t in threads]
        wall = time.perf_counter() - t0

        # ── 검증: 유실/중복 ──
        problems: list[str] = []
        logs = c.get(f"/projects/{proj['id']}/logs?limit=200").json()["data"]["items"]
        by_key = {}
        for lg in logs:
            by_key.setdefault((lg["authorId"], lg["workDate"]), []).append(lg)
        for k, v in by_key.items():
            if len(v) != 1:
                problems.append(f"duplicate log {k}")
        for u in users:
            mine = by_key.get((u["id"], "2026-10-04"))
            if not mine:
                problems.append(f"missing log {u['name']}")
                continue
            tasks = mine[0]["tasks"]
            text = "".join(t["titlePreview"] for t in tasks)
            if "부하 시험 완료" not in text and not any(results[u["id"]]["expected_text"][:15] in t["titlePreview"] for t in tasks):
                problems.append(f"lost text {u['name']}")
            if not by_key.get((u["id"], "2026-10-05")):
                problems.append(f"missing burst log {u['name']}")
        shared = by_key.get((users[0]["id"], "2026-10-06"), [])
        wins = sum(1 for r in results.values() if r["shared_status"] == 200)
        if len(shared) != 1 or wins != 1:
            problems.append(f"shared create: logs={len(shared)} winners={wins}")
        todos = c.get(f"/projects/{proj['id']}/todos?limit=200").json()["data"]["items"]
        if len(todos) != len(users) * ((a.rounds + 1) // 2):
            problems.append(f"todo count {len(todos)} != {len(users) * ((a.rounds + 1) // 2)}")

    summary = {"users": a.users, "rounds": a.rounds, "think_max_seconds": a.think, "wall_seconds": round(wall, 2), "ops": {}, "errors": rec.errors[:10], "problems": problems}
    worst = 0.0
    for op, vals in sorted(rec.lat.items()):
        p95 = pct(vals, 95)
        worst = max(worst, p95) if op in {"save_log", "get_log", "burst_save", "complete_todo"} else worst
        summary["ops"][op] = {"n": len(vals), "p50": round(statistics.median(vals), 3), "p95": round(p95, 3), "max": round(max(vals), 3)}
    summary["save_worst_p95"] = round(worst, 3)
    summary["target_p95_seconds"] = a.p95_target
    summary["p95_within_target"] = worst <= a.p95_target
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not rec.errors and not problems else 1


if __name__ == "__main__":
    sys.exit(main())
