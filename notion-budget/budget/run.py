"""한 번에 돌리기: 샘플 폴더의 엑셀·알림 → 해석 → 분류 → 대사 → 인사이트 → 리포트와 노션 페이로드.

노션 토큰이 없어도 결과를 볼 수 있도록, 노션에 보낼 내용은 파일로만 쓴다(--dry-run이 기본).
출력은 개인 금융 정보이므로 data/ 아래(커밋 제외)에만 쓴다.

usage:
  cd notion-budget && python -m budget.run --samples data/samples --out data/out

폴더 규칙:
  data/samples/hana_bank*.xlsx|csv, hana_card*, hyundai_card*, shinhan_card*   기관별 파일 (이름 앞부분으로 형식 선택)
  data/samples/*_statement.csv  카드 이용대금명세서를 옮긴 파일 (statement.py 형식)
  data/samples/alerts.jsonl    알림 원문 한 줄에 하나: {"id", "sender", "text", "received_at": "2026-10-25T14:21:00"}
  data/profile.json            {"own_names": [...], "own_accounts": [...], "business_accounts": [...]}
  data/categories_learned.json 사용자가 고친 카테고리 (없으면 빈 값)
"""
import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from . import alerts, excel, insights, notion, notion_sync, reconcile, rules, statement
from .categories import Categorizer
from .model import Kind, assign_keys


def load_profile(path):
    p = Path(path)
    d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return rules.Profile(own_names=d.get("own_names", []), own_accounts=d.get("own_accounts", []),
                         business_accounts=d.get("business_accounts", []))


def read_excels(folder):
    """(형식 키, 파일, 거래들, 오류) 목록. 형식을 모르는 파일은 오류로 보고만 하고 건너뛴다."""
    out = []
    for f in sorted(Path(folder).glob("*")):
        if f.suffix.lower() not in (".xlsx", ".xlsm", ".csv") or f.name.endswith("_statement.csv"):
            continue
        key = next((k for k in excel.FORMATS if f.name.startswith(k)), None)
        if not key:
            out.append((None, f, [], f"파일 이름이 {', '.join(excel.FORMATS)} 중 하나로 시작해야 합니다"))
            continue
        try:
            out.append((key, f, excel.parse_file(f, excel.FORMATS[key]), None))
        except excel.FormatError as e:
            out.append((key, f, [], str(e)))
    return out


def read_alerts(path):
    p = Path(path)
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [alerts.Alert(r["id"], alerts.sender_key(r["sender"]), r["text"], datetime.fromisoformat(r["received_at"])) for r in rows]


def last_full_week(today):
    return today - timedelta(days=today.weekday() + 7)


def sync_notion(client, keyed, cat, learned_path, push=True):
    """노션과 맞추기: ① 사용자가 노션에서 고친 카테고리·구분을 읽어 이번 실행에 반영하고 가맹점 규칙으로 기억
    (결제 대행은 기억하지 않음) ② 노션에 없는 거래만 새로 만든다. 돌려주는 값: 리포트 줄 목록."""
    ds = client.find_data_sources(["거래"])["거래"]
    ours = {k: (t.category or "미분류", t.kind.value if t.kind else "") for k, t in keyed}
    fixes = notion_sync.pull_corrections(client, ds, ours)
    by_key = dict(keyed)
    learned, skipped_agg = set(), set()
    for key, merchant, new_cat, new_kind in fixes:
        t = by_key[key]
        if new_cat:
            t.category, t.category_reason = new_cat, "노션에서 직접 고침"
            (learned if cat.learn(merchant, new_cat) else skipped_agg).add(merchant)
        if new_kind:
            t.kind = Kind(new_kind)
            t.kind_reason = "노션에서 직접 고침"
    if learned:
        cat.save(learned_path)
    lines = [f"- 노션에서 고친 값 {len(fixes)}건을 반영했습니다. 가맹점 {len(learned)}곳을 기억합니다"
             + (f" (결제 대행이라 기억하지 않음: {', '.join(sorted(skipped_agg))})" if skipped_agg else "")]
    if push:
        created, existed = notion_sync.push_transactions(client, ds, [(k, notion.transaction_properties(k, t)) for k, t in keyed])
        lines.append(f"- 거래 새로 만듦 {created}건, 이미 있어 건너뜀 {existed}건(사용자가 고친 값은 덮어쓰지 않음)")
    return lines


def run(samples, out, profile_path, learned_path, today=None, client=None):
    today = today or date.today()
    profile, cat = load_profile(profile_path), Categorizer.load(learned_path)
    files = read_excels(samples)
    txs = [t for _, _, ts, _ in files for t in ts]
    statements = [(f, *statement.parse(f)) for f in sorted(Path(samples).glob("*_statement.csv"))]
    txs += [t for _, ts, _ in statements for t in ts]

    results = [alerts.parse(a) for a in read_alerts(Path(samples) / "alerts.jsonl")]
    watch = alerts.FormatWatch()
    warnings = [w for w in (watch.feed(r) for r in results) if w]
    alert_txs = [r.tx for r in results if r.parsed]

    for t in [*txs, *alert_txs]:
        rules.classify(t, profile)
        t.category, t.category_reason = cat.categorize(t.counterparty)

    keyed, seen = [], set()
    for k, t in assign_keys(txs):
        if k not in seen:
            seen.add(k)
            keyed.append((k, t))
    sync_lines = sync_notion(client, keyed, cat, learned_path) if client else []

    lines = [f"# 가계부 실행 리포트 ({today:%Y-%m-%d})", "", "## 읽은 파일", ""]
    for key, f, ts, err in files:
        lines.append(f"- {f.name}: " + (f"**오류** {err}" if err else f"{key} 형식, {len(ts)}건"))
    for f, ts, totals in statements:
        lines.append(f"- {f.name}: 명세서 {len(totals)}개월, 이용 건 {len(ts)}건")
    if sync_lines:
        lines += ["", "## 노션 동기화", "", *sync_lines]
    lines += ["", "## 대사", ""]
    for f, ts, totals in statements:
        for m, diff in statement.check_totals(ts, totals).items():
            lines.append(f"- {f.name} {m} 명세서 총액 {totals[m]:,}원: " + ("줄 합계와 일치" if diff == 0 else f"**차이 {diff:+,}원**"))
    for key, f, ts, err in files:
        if ts and ts[0].balance is not None:
            br = reconcile.balance_breaks(ts)
            lines.append(f"- {f.name} 잔액 연속성: " + ("이상 없음" if not br else f"**끊김 {len(br)}곳** " + ", ".join(f"{b.source_ref}({b.diff:+,}원)" for b in br)))
    gaps = reconcile.limit_gaps(alert_txs)
    lines.append(f"- 알림 한도 연속성: " + ("이상 없음" if not gaps else "**알림 없이 쓴 금액** " + ", ".join(f"{g.after_ref} 다음 {g.missing:,}원" for g in gaps)))
    card_rows = [t for t in txs if t.extra.get("card")]
    if card_rows and alert_txs:
        cov = reconcile.alert_coverage(card_rows, alert_txs)
        lines.append(f"- 알림이 잡은 카드 거래: {cov.matched}/{cov.matched + len(cov.missed_by_alerts)} ({cov.rate:.0%})")
    unparsed = [r for r in results if not r.parsed]
    lines.append(f"- 알림 {len(results)}건 중 미해석 {len(unparsed)}건")
    lines += [f"- ⚠ {w}" for w in warnings]

    dates = sorted(t.date for _, t in keyed)
    if dates:
        first, last = dates[0], dates[-1]
        lines += ["", f"데이터 범위: {first:%Y-%m-%d} ~ {last:%Y-%m-%d} 이용분. "
                  f"{first:%Y-%m}" + (f"·{last:%Y-%m}" if last.strftime('%Y-%m') != first.strftime('%Y-%m') else "")
                  + " 은 달 전체가 아닐 수 있습니다(앞뒤 명세서가 없으면 일부만 들어감)."]
    lines += ["", "## 월별 합계 (이용일 기준)", "", "| 월 | 지출 | 수입 | 자산 이동 | 법인(업무) |", "|---|---|---|---|---|"]
    for m, d in sorted(rules.monthly_totals([t for _, t in keyed]).items()):
        lines.append(f"| {m} | {d['지출']:,} | {d['수입']:,} | {d['자산 이동']:,} | {d['법인(업무)']:,} |")

    last_data = max((t.date for _, t in keyed), default=today)
    lines += ["", "## 월별 합계 (결제월 기준, 카드 명세서 청구액)", "", "| 결제월 | 지출 |", "|---|---|"]
    for m, d in sorted(rules.monthly_totals([t for _, t in keyed], basis="billed").items()):
        lines.append(f"| {m} | {d['지출']:,} |")

    ws = min(last_full_week(today), last_data - timedelta(days=last_data.weekday()))  # 데이터가 있는 마지막 주
    ins = insights.weekly_insight([t for _, t in keyed], ws)
    lines += ["", f"## 주간 인사이트 ({ws:%m/%d} 주)", "", ins.text if ins else "이번 주에는 눈에 띄는 변화가 없습니다.", ""]
    if ins:
        lines += [f"근거: {ins.evidence}", ""]
    uncategorized = sum(1 for _, t in keyed if t.category == "미분류")
    lines.append(f"미분류 {uncategorized}건 — 노션에서 고치면 다음부터 기억합니다.")

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(out / "notion_pages.jsonl", "w", encoding="utf-8") as f:
        for k, t in keyed:
            f.write(json.dumps({"db": "거래", "properties": notion.transaction_properties(k, t)}, ensure_ascii=False) + "\n")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default="data/samples")
    ap.add_argument("--out", default="data/out")
    ap.add_argument("--profile", default="data/profile.json")
    ap.add_argument("--learned", default="data/categories_learned.json")
    ap.add_argument("--sync", action="store_true", help="환경 변수 NOTION_TOKEN으로 노션과 맞춤(고친 값 읽기 + 새 거래 쓰기)")
    args = ap.parse_args()
    client = None
    if args.sync:
        import os
        client = notion_sync.Client(os.environ["NOTION_TOKEN"])
    print("\n".join(run(args.samples, args.out, args.profile, args.learned, client=client)))


if __name__ == "__main__":
    main()
