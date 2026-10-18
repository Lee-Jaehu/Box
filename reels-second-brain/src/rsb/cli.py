"""운영 명령. python -m rsb.cli <명령>

  migrate   마이그레이션 적용
  senders   웹훅으로 들어온 송신자 ID 목록(허용 목록 IG_ALLOWED_SENDER_IDS 설정용)
  status    릴스별 확보·추출 상태와 작업 상태
"""

from __future__ import annotations

import sys

from . import db
from .config import get_settings


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    s = get_settings()
    with db.connect(s.database_url) as conn:
        if cmd == "migrate":
            print("applied:", db.migrate(conn) or "none")
        elif cmd == "senders":
            for r in conn.execute(
                """SELECT sender_id, recipient_id, count(*) n, max(received_at) last, bool_or(kind='ignored') ignored
                   FROM webhook_events GROUP BY 1, 2 ORDER BY last DESC"""
            ):
                print(f"{r['sender_id']}\trecipient={r['recipient_id']}\tn={r['n']}\tlast={r['last']:%F %T}"
                      f"\t{'ignored' if r['ignored'] else 'allowed'}")
        elif cmd == "status":
            for r in conn.execute(
                """SELECT r.id, r.fetch_status, r.fetch_method, r.fetch_error,
                          (SELECT string_agg(e.medium || '=' || e.status, ' ' ORDER BY e.medium)
                             FROM extractions e WHERE e.reel_id=r.id) AS ext,
                          (SELECT string_agg(j.kind || ':' || j.status || '(' || j.attempts || ')', ' ' ORDER BY j.id)
                             FROM jobs j WHERE j.reel_id=r.id) AS jobs
                   FROM reels r ORDER BY r.id"""
            ):
                print(f"reel {r['id']}\tfetch={r['fetch_status']}/{r['fetch_method'] or '-'}"
                      f"\t{r['ext'] or ''}\t{r['jobs'] or ''}\t{r['fetch_error'] or ''}")
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
