"""Real process kill scenario: save -> force-kill the server -> restart -> pending JSON export resumes and the DB is intact.

  python scripts/kill_restart_check.py <temp data dir> [port]
Use a port that is not excluded on this PC (netsh interface ipv4 show excludedportrange protocol=tcp).
"""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

RUN_PY = Path(__file__).resolve().parents[1] / "backend" / "run.py"

import httpx

PY = sys.executable
DATA = Path(sys.argv[1])
PORT = sys.argv[2] if len(sys.argv) > 2 else "18766"
env = {**os.environ, "WORKLOG_DATA_DIR": str(DATA), "WORKLOG_HOST": "127.0.0.1", "WORKLOG_PORT": PORT, "PYTHONUTF8": "1"}


def start(worker: bool):
    e = {**env, "WORKLOG_EXPORT_WORKER_ENABLED": "true" if worker else "false"}
    p = subprocess.Popen([PY, str(RUN_PY)], env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(RUN_PY.parents[1]))
    for _ in range(60):
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/api/v1/health", timeout=2).status_code == 200:
                return p
        except httpx.HTTPError:
            time.sleep(0.5)
    raise SystemExit("server did not start")


def post(c, path, body, actor=None, method="POST"):
    r = c.request(method, path, json=body, headers={"Idempotency-Key": uuid.uuid4().hex, **({"X-Actor-Id": actor} if actor else {})})
    r.raise_for_status()
    return r.json()["data"]


DOC = lambda t: {"documentVersion": 1, "format": "tiptap-json", "doc": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": t}]}]}}

p = start(worker=False)  # export worker 를 꺼서 'DB 는 저장됐지만 JSON 은 아직'인 상태를 만든다
with httpx.Client(base_url=f"http://127.0.0.1:{PORT}/api/v1", timeout=30) as c:
    d = post(c, "/organizations", {"name": "d", "kind": "division"})
    t = post(c, "/organizations", {"name": "t", "kind": "team", "parentId": d["id"]})
    u = post(c, "/users", {"name": "kill", "teamId": t["id"]})
    pr = post(c, "/projects", {"name": "kill-test", "teamId": t["id"], "ownerUserId": u["id"]}, u["id"])
    ms = next(m for m in pr["milestones"] if m["isGeneral"])["id"]
    log = post(c, f"/projects/{pr['id']}/logs/2026-10-04/{u['id']}", {"expectedRevision": 0, "tasks": [{"milestoneId": ms, "content": DOC("강제 종료 직전 저장")}]}, u["id"], method="PUT")
daily = DATA / "json" / "projects" / pr["id"] / "2026-10-04" / "daily.json"
print("before kill: daily.json exists =", daily.exists(), "| saved revision =", log["revision"])
p.kill()  # TerminateProcess: 정리 코드 없이 즉시 종료
p.wait()
print("killed; daily.json exists =", daily.exists())

p2 = start(worker=True)  # 다음 수동 실행
try:
    with httpx.Client(base_url=f"http://127.0.0.1:{PORT}/api/v1", timeout=30) as c:
        got = c.get(f"/projects/{pr['id']}/logs", params={"date": "2026-10-04"}).json()["data"]["items"]
        print("after restart: log readable =", len(got) == 1 and got[0]["tasks"][0]["titlePreview"] == "강제 종료 직전 저장", "| revision =", got[0]["revision"])
        for _ in range(40):
            if daily.exists() and json.loads(daily.read_text(encoding="utf-8"))["logs"]:
                break
            time.sleep(0.5)
        data = json.loads(daily.read_text(encoding="utf-8"))
        print("after restart: daily.json regenerated =", data["logs"][0]["tasks"][0]["content"]["doc"]["content"][0]["content"][0]["text"], "| sourceRevision =", data["sourceRevision"])
        st = c.get("/exports/status").json()["data"]
        print("export status pending/failed =", st["pendingCount"], st["failedCount"])
finally:
    p2.kill()
