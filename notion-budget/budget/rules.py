"""기록 규칙: 무엇이 지출이고 무엇이 자산 이동인가 (Phase 1 결과 4절 7번, codebook T05·T20).

사용자가 예외만 고치게 하려고 기본값을 넣지만, 판단 근거(kind_reason)를 항상 남겨
노션에서 "왜 이렇게 분류됐는지"를 볼 수 있게 한다. 이것은 기록 규칙이고 투자 조언이 아니다.
"""
from dataclasses import dataclass, field

from .model import Kind

CARD_ISSUERS = ("하나카드", "현대카드", "신한카드", "삼성카드", "KB국민카드", "국민카드", "롯데카드", "우리카드", "BC카드", "비씨카드", "NH카드", "농협카드")
LOAN_WORDS = ("대출원금", "원금상환", "대출상환", "대출금상환", "주담대")
SAVINGS_WORDS = ("적금", "청약", "정기예금", "저축")


@dataclass
class Profile:
    """사용자별 설정. 첫 실행 때 묻는다."""
    own_names: list = field(default_factory=list)       # 본인 이름(입출금 상대가 본인일 때 이체로 판정)
    own_accounts: list = field(default_factory=list)    # 내 계좌 별칭이나 끝자리 ("1234", "생활비통장")
    card_issuers: tuple = CARD_ISSUERS
    business_accounts: list = field(default_factory=list)  # 법인카드 계정 이름 ("신한카드(1234)"). 알림의 '신한법인'은 자동 인식


def classify(tx, profile):
    """tx.kind와 tx.kind_reason을 채우고 tx를 돌려준다. 이미 kind가 있으면(사용자가 고친 값) 건드리지 않는다."""
    if tx.kind is not None:
        return tx
    if tx.extra.get("product") == "법인" or tx.account in profile.business_accounts:
        return _set(tx, Kind.BUSINESS, "법인카드 사용 (개인 지출이면 '지출'로 바꾸세요)")
    text = f"{tx.counterparty} {tx.memo}"
    is_bank = tx.source.startswith("excel:") and tx.balance is not None
    if tx.amount < 0 and is_bank:
        issuer = next((c for c in profile.card_issuers if c in text), None)
        if issuer:
            return _set(tx, Kind.CARD_PAYMENT, f"은행 출금 상대가 카드사({issuer})")
        word = next((w for w in LOAN_WORDS if w in text), None)
        if word:
            return _set(tx, Kind.LOAN_REPAYMENT, f"적요에 '{word}'")
        word = next((w for w in SAVINGS_WORDS if w in text), None)
        if word:
            return _set(tx, Kind.SAVINGS, f"적요에 '{word}'")
    own = next((n for n in [*profile.own_names, *profile.own_accounts] if n and n in text), None)
    if own and is_bank:
        return _set(tx, Kind.TRANSFER, f"입출금 상대가 본인('{own}')")
    if tx.amount < 0:
        return _set(tx, Kind.EXPENSE, "출금·결제")
    if tx.extra.get("card"):
        return _set(tx, Kind.EXPENSE, "카드 취소·환불 (지출에서 차감)")
    return _set(tx, Kind.INCOME, "입금")


def _set(tx, kind, reason):
    tx.kind, tx.kind_reason = kind, reason
    return tx


def monthly_totals(txs, basis="usage"):
    """월별 지출·수입 합계(원). 자산 이동은 빼고 따로 집계하고, 카드 취소는 지출에서 뺀다.
    법인카드 사용(Kind.BUSINESS)은 '법인(업무)'에 따로 모은다(사용액 양수, 취소는 차감).
    basis="usage"(기본): 이용일의 달에 전액. basis="billed": 명세서가 있는 카드 거래는 결제월에 청구액만
    (할부는 회차만, 수수료 포함). 명세서 정보가 없는 거래는 두 기준 모두 이용일로 센다."""
    out = {}
    for tx in txs:
        amt, m = tx.amount, tx.date.strftime("%Y-%m")
        if basis == "billed" and tx.billed is not None and tx.billing_month:
            amt, m = tx.billed, tx.billing_month
        d = out.setdefault(m, {"지출": 0, "수입": 0, "자산 이동": 0, "법인(업무)": 0})
        if tx.kind == Kind.BUSINESS:
            d["법인(업무)"] += -amt
        elif tx.kind and tx.kind.is_asset_move:
            d["자산 이동"] += amt
        elif amt < 0 or tx.extra.get("card"):
            d["지출"] += -amt
        else:
            d["수입"] += amt
    return out
