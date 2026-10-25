"""거래 한 건. 금액은 원 단위 정수(지출 음수, 수입 양수)로만 다룬다. float는 쓰지 않는다."""
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, time
from enum import Enum
from typing import Optional


class Kind(str, Enum):
    EXPENSE = "지출"
    INCOME = "수입"
    TRANSFER = "내 계좌 이체"
    CARD_PAYMENT = "카드대금"
    LOAN_REPAYMENT = "대출 상환"
    SAVINGS = "저축"
    BUSINESS = "법인(업무)"   # 법인카드 사용. 개인 지출 합계에서 빼고 따로 집계 (2026-10-25 결정)

    @property
    def is_asset_move(self):
        """지출·수입 합계에서 빼야 하는 자산 이동인지 (codebook T05·T20)."""
        return self in (Kind.TRANSFER, Kind.CARD_PAYMENT, Kind.LOAN_REPAYMENT, Kind.SAVINGS)


@dataclass
class Transaction:
    """amount는 이용일 기준 전액이다. 할부면 이번 명세서에 청구된 회차 금액을 billed에 따로 둔다
    (2026-10-25 결정: 둘 다 저장하고 화면 기본값은 이용일 기준). 회차 금액은 카드사마다 반올림이 달라
    계산하지 않고 명세서 값을 그대로 쓴다."""
    date: date
    amount: int
    account: str
    counterparty: str = ""
    memo: str = ""
    time: Optional[time] = None
    balance: Optional[int] = None
    kind: Optional[Kind] = None
    kind_reason: str = ""
    source: str = ""          # "excel:hana_bank", "alert:shinhan_card"
    source_ref: str = ""      # 파일명:행 번호, 알림 id
    billed: Optional[int] = None          # 이번 명세서 청구액(원, 지출 음수, 수수료 포함)
    billing_month: Optional[str] = None   # 그 명세서의 결제월 "2026-10"
    installment: Optional[tuple] = None   # (이번 회차, 전체 회차)
    fee: int = 0                          # 할부 수수료(원, 양수)
    extra: dict = field(default_factory=dict)

    def base_key(self):
        cp = re.sub(r"\s+", "", self.counterparty)
        t = self.time.strftime("%H%M") if self.time else ""
        return f"{self.account}|{self.date.isoformat()}|{t}|{self.amount}|{cp}"


def assign_keys(txs):
    """중복 판정 키를 붙인다. 같은 날 같은 곳에서 같은 금액을 두 번 쓴 경우는 실제 두 건이므로
    파일 안 등장 순서(#1, #2)로 구분해 합치지 않는다 (리뷰에서 반복된 '같은 금액 두 건이 한 건으로 합쳐짐' 문제).
    같은 파일을 다시 넣으면 같은 키가 나와 중복 입력이 막힌다."""
    seen = Counter()
    out = []
    for tx in txs:
        k = tx.base_key()
        seen[k] += 1
        out.append((f"{k}#{seen[k]}", tx))
    return out
