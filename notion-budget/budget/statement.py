"""카드 이용대금명세서 읽기. 명세서는 '결제월마다 무엇이 얼마 청구됐나'의 원본이다.

입력은 명세서 한 줄 = 한 행인 CSV(`*_statement.csv`)다. 카드사 엑셀을 받기 전에는 앱 화면을 옮겨 적은 파일을 쓴다.
  열: 결제월, 이용일, 가맹점, 카드, 구분, 결제금액, 거래금액, 할인
  - 구분: 일시불 / 할부(n/N) / 명세서합계(이 행의 결제금액이 그 달 명세서 총액)
  - 결제금액: 이번 명세서에 청구된 금액(할인 후). 거래금액: 할부면 원래 이용 금액 전체

2026-10 확인 (사용자 명세서 화면 3개월분):
  - 명세서 각 줄의 결제금액을 더하면 명세서 총액과 원 단위로 같다. 줄 금액은 '이용금액할인' 뒤의 값이다.
  - 할부 회차 금액은 나머지를 1회차에 몰아 낸다(예: 거래금액 777,100원 → 259,100 / 259,000 / 259,000).
    그래서 회차 금액은 계산하지 않고 명세서 값을 그대로 쓴다.
  - 같은 할부 이용 건이 회차마다 다른 명세서에 다시 나온다. 이 모듈은 이것을 **이용 건 하나**로 합치고,
    회차별 청구는 Transaction.bills에 [(결제월, 회차, 청구액)]으로 모은다(설계 문서 6절의 남은 과제).
"""
import csv
import re
from datetime import date

from .model import Transaction

INSTALLMENT = re.compile(r"할부\((\d+)/(\d+)\)")


def _int(v):
    v = (v or "").replace(",", "").replace("원", "").strip()
    return int(v) if v else 0


ISSUERS = {"shinhan_card": "신한카드", "hyundai_card": "현대카드", "hana_card": "하나카드"}


def parse(path, account_prefix=None):
    """(거래 목록, {결제월: 명세서 총액}). 계정 이름은 '카드사 카드끝번호'(예: 신한카드 785).
    카드사는 파일 이름 앞부분(shinhan_card_… 등)으로 정하고, 모르면 '카드'로 둔다."""
    name = getattr(path, "name", str(path))
    account_prefix = account_prefix or next((v for k, v in ISSUERS.items() if name.startswith(k)), "카드")
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    totals, txs, merged = {}, [], {}
    for i, r in enumerate(rows, start=2):
        month, kind = r["결제월"].strip(), r["구분"].strip()
        if kind == "명세서합계":
            totals[month] = _int(r["결제금액"])
            continue
        billed = _int(r["결제금액"])
        d = date.fromisoformat(r["이용일"].strip())
        account = f"{account_prefix} {r['카드'].strip()}"
        m = INSTALLMENT.search(kind)
        if m:
            n, total_n = int(m.group(1)), int(m.group(2))
            full = _int(r["거래금액"]) or billed
            key = (account, d, r["가맹점"].strip(), full, total_n)
            tx = merged.get(key)
            if tx is None:
                tx = Transaction(date=d, amount=-full, account=account, counterparty=r["가맹점"].strip(),
                                 source="statement", source_ref=f"{path.name if hasattr(path, 'name') else path}:{i}",
                                 extra={"card": True})
                merged[key] = tx
                txs.append(tx)
            tx.bills.append((month, n, -billed))
            latest = max(tx.bills)
            tx.billing_month, tx.installment, tx.billed = latest[0], (latest[1], total_n), latest[2]
            continue
        txs.append(Transaction(date=d, amount=-billed, account=account, counterparty=r["가맹점"].strip(),
                               source="statement", source_ref=f"{getattr(path, 'name', path)}:{i}",
                               billed=-billed, billing_month=month, bills=[(month, 1, -billed)],
                               extra={"card": True, "discount": _int(r.get("할인"))}))
    return txs, totals


def check_totals(txs, totals):
    """결제월마다 명세서 줄의 청구액 합계와 명세서 총액의 차이(원). 0이면 원 단위로 맞는다."""
    billed = {}
    for t in txs:
        for month, _, amt in t.bills:
            billed[month] = billed.get(month, 0) - amt
    return {m: totals[m] - billed.get(m, 0) for m in sorted(totals)}
