"""주간 인사이트: 매주 '행동할 수 있는' 한 가지를 고른다(Phase 0 평가 기준 ③).

- 후보를 몇 가지 방식으로 찾고, 금액 영향(원)이 가장 큰 하나만 보여 준다. 여러 개를 늘어놓지 않는다.
- 모든 문장에 근거 숫자와 기간을 붙인다(노션 '주간 인사이트' DB의 '근거').
- 지출 기록에 대한 관찰만 말한다. 투자 상품·종목·비중에 대한 판단은 하지 않는다(Phase 0 5-2절 가드레일).
- 법인(업무)·자산 이동은 개인 지출이 아니므로 보지 않는다.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from statistics import median

from .model import Kind

MIN_IMPACT = 20000      # 이보다 작은 차이는 인사이트로 내지 않는다(원)
BASE_WEEKS = 8


@dataclass
class Insight:
    kind: str
    impact: int          # 원. 후보끼리 비교하는 값
    text: str
    evidence: str


def _spending(txs):
    """개인 지출만: 지출 구분이고 금액이 있는 것. 카드 취소(양수)는 같은 카테고리에서 뺀다."""
    return [t for t in txs if t.kind == Kind.EXPENSE]


def _week_start(d):
    return d - timedelta(days=d.weekday())


def category_spike(txs, week_start):
    """이번 주 카테고리 지출이 지난 8주 중앙값보다 크게 늘었는가."""
    weeks = defaultdict(lambda: defaultdict(int))
    for t in _spending(txs):
        weeks[_week_start(t.date)][t.category or "미분류"] += -t.amount
    this = weeks.get(week_start, {})
    best = None
    for cat, amt in this.items():
        if cat == "미분류":
            continue
        base = [weeks.get(week_start - timedelta(weeks=i), {}).get(cat, 0) for i in range(1, BASE_WEEKS + 1)]
        med = median(base)
        if amt - med >= MIN_IMPACT and amt >= 1.5 * max(med, 1):
            cand = Insight("카테고리 급증", amt - med,
                           f"이번 주 {cat} 지출이 {amt:,}원으로, 평소 한 주(지난 {BASE_WEEKS}주 중앙값 {med:,.0f}원)보다 {amt - med:,.0f}원 많습니다.",
                           f"{week_start:%m/%d}~{week_start + timedelta(days=6):%m/%d} {cat} 합계 {amt:,}원 · 지난 {BASE_WEEKS}주 주별 합계 {', '.join(f'{b:,}' for b in base)}원")
            if best is None or cand.impact > best.impact:
                best = cand
    return best


def frequent_small(txs, week_start, min_count=4, max_each=15000):
    """이번 달 들어 같은 가맹점의 소액 결제가 잦은가 (월초~이번 주 끝)."""
    end = week_start + timedelta(days=6)
    start = end.replace(day=1)
    by = defaultdict(list)
    for t in _spending(txs):
        if start <= t.date <= end and 0 < -t.amount <= max_each and t.counterparty:
            by[t.counterparty].append(-t.amount)
    best = None
    for m, amts in by.items():
        if len(amts) >= min_count and sum(amts) >= MIN_IMPACT:
            cand = Insight("잦은 소액 결제", sum(amts),
                           f"이번 달 {m}에서 {len(amts)}번, 모두 {sum(amts):,}원을 썼습니다. 한 번에 평균 {sum(amts) // len(amts):,}원입니다.",
                           f"{start:%m/%d}~{end:%m/%d} {m} 결제 {len(amts)}건: {', '.join(f'{a:,}' for a in amts)}원")
            if best is None or cand.impact > best.impact:
                best = cand
    return best


def new_recurring(txs, week_start):
    """지난달과 이번 달에 같은 가맹점·같은 금액이 나왔고, 그 전 달에는 없던 결제 → 새 정기결제 후보."""
    end = week_start + timedelta(days=6)
    this_m = end.replace(day=1)
    last_m = (this_m - timedelta(days=1)).replace(day=1)
    before_m = (last_m - timedelta(days=1)).replace(day=1)
    seen = defaultdict(set)
    for t in _spending(txs):
        seen[(t.counterparty, -t.amount)].add(t.date.replace(day=1))
    best = None
    for (m, amt), months in seen.items():
        if this_m in months and last_m in months and before_m not in months and amt >= 3000 and m:
            cand = Insight("새 정기결제", amt * 12,
                           f"{m} {amt:,}원이 두 달 연속 결제됐습니다. 새로 시작한 정기결제라면 1년에 {amt * 12:,}원입니다.",
                           f"{last_m:%Y-%m}, {this_m:%Y-%m}에 같은 금액 결제 · {before_m:%Y-%m}에는 없음")
            if best is None or cand.impact > best.impact:
                best = cand
    return best


def weekly_insight(txs, week_start):
    """한 주(월요일 시작)의 인사이트 하나. 없으면 None. tx.kind와 tx.category가 채워져 있어야 한다."""
    cands = [c for c in (category_spike(txs, week_start), frequent_small(txs, week_start),
                         new_recurring(txs, week_start)) if c]
    return max(cands, key=lambda c: c.impact) if cands else None
