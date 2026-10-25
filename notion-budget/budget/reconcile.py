"""대사: 계산한 숫자가 원본과 원 단위로 맞는지 확인한다(Phase 0 평가 기준 ②, Phase 1 T07)."""
from dataclasses import dataclass
from datetime import time


@dataclass
class BalanceBreak:
    source_ref: str
    expected: int
    actual: int

    @property
    def diff(self):
        return self.actual - self.expected


def balance_breaks(txs):
    """은행 거래내역의 잔액 열로 연속성을 확인한다: 앞 행 잔액 + 이번 금액 = 이번 잔액.
    파일이 최신순이면 뒤집어서 본다. 깨진 곳은 누락 행이나 금액 해석 오류를 뜻한다."""
    rows = [t for t in txs if t.balance is not None]
    if len(rows) < 2:
        return []
    if (rows[0].date, rows[0].time or time.min) > (rows[-1].date, rows[-1].time or time.min):
        rows = rows[::-1]
    out = []
    for prev, cur in zip(rows, rows[1:]):
        exp = prev.balance + cur.amount
        if exp != cur.balance:
            out.append(BalanceBreak(cur.source_ref, exp, cur.balance))
    return out


@dataclass
class LimitGap:
    after_ref: str      # 이 알림 다음에
    missing: int        # 알림 없이 사용된 금액(원)


def limit_gaps(alert_txs):
    """카드 알림의 '남은 한도'로 빠진 알림을 찾는다. 같은 카드의 연속된 승인 알림에서
    앞 한도 - 이번 금액이 이번 한도보다 크면, 그 차이만큼 알림 없이 쓴 거래가 있다는 뜻이다.
    한도가 늘어난 경우(결제·취소 반영)는 끊김으로 보지 않는다. 월말 엑셀 전에 T17(알림 누락)을 잡는 장치다."""
    out, last = [], {}
    for tx in sorted(alert_txs, key=lambda t: (t.date, t.time or time.min)):
        left = tx.extra.get("limit_left")
        if left is None or tx.amount >= 0:
            continue
        prev = last.get(tx.account)
        if prev is not None:
            expected = prev.extra["limit_left"] + tx.amount
            if left < expected:
                out.append(LimitGap(prev.source_ref, expected - left))
        last[tx.account] = tx
    return out


@dataclass
class Coverage:
    matched: int
    missed_by_alerts: list      # 엑셀에는 있는데 알림이 없던 거래
    alerts_without_row: list    # 알림은 왔는데 엑셀에 없는 거래 (승인 후 취소, 결제 보류 등)

    @property
    def rate(self):
        total = self.matched + len(self.missed_by_alerts)
        return self.matched / total if total else 1.0


def alert_coverage(excel_txs, alert_txs, days=1):
    """알림이 엑셀 거래를 얼마나 잡았는지. 같은 계정 이름으로 시작하고 금액이 같으며 날짜가 ±days 안이면 같은 거래로 본다.
    월말 리포트에 '알림 누락 n건'으로 쓴다."""
    pool = list(alert_txs)
    matched, missed = 0, []
    for tx in excel_txs:
        hit = next((a for a in pool if a.amount == tx.amount and a.account.startswith(tx.account)
                    and abs((a.date - tx.date).days) <= days), None)
        if hit:
            pool.remove(hit)
            matched += 1
        else:
            missed.append(tx)
    return Coverage(matched, missed, pool)


def card_statement_diff(card_txs, statement_total, start, end):
    """카드 이용내역(start~end 이용분) 합계와 청구 명세서 총액의 차이(원). 0이 아니면 할부 회차·수수료·연회비·이월을
    이용내역만으로 설명할 수 없다는 뜻이다(Phase 0 1-3절). 명세서 해석은 샘플을 받은 뒤 붙인다."""
    used = -sum(t.amount for t in card_txs if start <= t.date <= end)
    return statement_total - used
