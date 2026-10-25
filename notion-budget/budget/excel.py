"""은행·카드 엑셀/CSV 읽기. 기관마다 열 이름이 달라서 '열 이름 별칭'으로 맞춘다.

기관별 형식(FORMATS)은 실제 샘플을 받은 뒤 확정한다(Phase 0 1-3절). 지금 들어 있는
GENERIC_BANK·GENERIC_CARD 별칭은 흔히 쓰이는 이름을 모은 **추정값**이다.
"""
import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

from .model import Transaction


@dataclass
class Format:
    key: str                       # "hana_bank"
    account: str                   # 노션에 표시할 계정 이름
    card: bool = False             # 카드 이용내역이면 True (양수 금액 = 사용)
    date: tuple = ()
    time: tuple = ()
    withdraw: tuple = ()           # 은행: 출금 열
    deposit: tuple = ()            # 은행: 입금 열
    amount: tuple = ()             # 카드: 이용금액 열
    balance: tuple = ()
    counterparty: tuple = ()
    memo: tuple = ()
    cancel: tuple = ()             # 카드: 취소 여부 열 (값에 '취소'가 있으면 환불)
    extra_cols: dict = field(default_factory=dict)  # {"installment": ("할부",)}


GENERIC_BANK = dict(
    date=("거래일시", "거래일자", "거래일", "일자"), time=("거래시간", "시간"),
    withdraw=("출금액", "출금(원)", "출금", "찾으신금액"), deposit=("입금액", "입금(원)", "입금", "맡기신금액"),
    balance=("거래후잔액", "잔액(원)", "잔액"), counterparty=("적요", "거래내용", "내용", "의뢰인/수취인", "받는분"),
    memo=("메모", "거래메모", "비고"),
)
GENERIC_CARD = dict(
    card=True, date=("이용일자", "이용일", "승인일자", "거래일자"), time=("이용시간", "승인시간"),
    amount=("이용금액", "승인금액", "결제원금", "금액"), counterparty=("가맹점명", "이용가맹점", "가맹점"),
    cancel=("취소여부", "상태", "승인구분"), extra_cols={"installment": ("할부", "할부개월", "이용구분")},
)

# 실제 샘플로 열 이름을 확정하면 GENERIC_* 대신 그 기관의 정확한 열 이름으로 바꾼다.
FORMATS = {
    "hana_bank": Format("hana_bank", "하나은행", **GENERIC_BANK),
    "hana_card": Format("hana_card", "하나카드", **GENERIC_CARD),
    "hyundai_card": Format("hyundai_card", "현대카드", **GENERIC_CARD),
    "shinhan_card": Format("shinhan_card", "신한카드", **GENERIC_CARD),
}


class FormatError(ValueError):
    pass


def read_rows(path):
    """파일의 모든 행을 문자열·숫자·날짜 셀 리스트로 돌려준다."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception as e:  # 암호가 걸린 파일은 zip이 아니라서 여기서 실패한다
            raise FormatError(f"{path.name}을 열 수 없습니다. 암호가 걸린 파일이면 은행 사이트에서 암호 없이 다시 받거나, 엑셀에서 암호를 풀고 저장해 주세요. ({e})") from e
        try:
            return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
        finally:
            wb.close()
    if path.suffix.lower() == ".csv":
        for enc in ("utf-8-sig", "cp949"):
            try:
                with open(path, encoding=enc, newline="") as f:
                    return list(csv.reader(f))
            except UnicodeDecodeError:
                continue
    raise FormatError(f"{path.name}: 지원하지 않는 형식입니다 (.xlsx, .csv만 지원). .xls라면 엑셀에서 .xlsx로 다시 저장해 주세요.")


def _norm(h):
    return re.sub(r"\s+", "", str(h or ""))


def _find(header, aliases):
    hn = [_norm(h) for h in header]
    for a in aliases:
        if _norm(a) in hn:
            return hn.index(_norm(a))
    return None


def locate_header(rows, fmt, scan=30):
    """위쪽 안내 문구를 건너뛰고, 날짜 열과 금액 열이 모두 있는 첫 행을 머리글로 본다."""
    money = fmt.amount or fmt.withdraw
    for i, row in enumerate(rows[:scan]):
        if _find(row, fmt.date) is not None and _find(row, money) is not None:
            return i
    raise FormatError(f"{fmt.account}: 머리글 행을 찾지 못했습니다. 날짜 열 {fmt.date} 와 금액 열 {money} 중 하나가 있어야 합니다.")


def parse_amount(v):
    """'12,300' '-12,300' '(12,300)' '12,300원' 12300 12300.0 → int. 빈 칸은 0."""
    if v is None or v == "":
        return 0
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not v.is_integer():
            raise FormatError(f"원 단위가 아닌 금액: {v}")
        return int(v)
    s = str(v).strip().replace(",", "").replace("원", "").replace(" ", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if not re.fullmatch(r"[-+]?\d+(\.0+)?", s):
        raise FormatError(f"금액으로 읽을 수 없음: {v!r}")
    n = int(float(s))
    return -n if neg else n


def parse_date(v):
    if isinstance(v, datetime):
        return v.date(), (v.time() if (v.hour or v.minute or v.second) else None)
    if isinstance(v, date):
        return v, None
    s = str(v).strip()
    m = re.match(r"(\d{4})[.\-/년 ]\s*(\d{1,2})[.\-/월 ]\s*(\d{1,2})일?(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
    if not m:
        m2 = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s)
        if not m2:
            raise FormatError(f"날짜로 읽을 수 없음: {v!r}")
        return date(*map(int, m2.groups())), None
    y, mo, d, hh, mm, ss = m.groups()
    t = time(int(hh), int(mm), int(ss or 0)) if hh else None
    return date(int(y), int(mo), int(d)), t


def parse_time(v):
    if v in (None, ""):
        return None
    if isinstance(v, time):
        return v
    m = re.match(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", str(v).strip())
    return time(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)) if m else None


def parse_file(path, fmt):
    """파일 → Transaction 리스트(파일에 나온 순서 그대로). 합계 행이나 빈 행은 건너뛴다."""
    rows = read_rows(path)
    h = locate_header(rows, fmt)
    header = rows[h]
    col = {name: _find(header, getattr(fmt, name)) for name in
           ("date", "time", "withdraw", "deposit", "amount", "balance", "counterparty", "memo", "cancel")}
    extra_col = {k: _find(header, v) for k, v in fmt.extra_cols.items()}
    out = []
    for i, row in enumerate(rows[h + 1:], start=h + 2):
        cell = lambda name: row[col[name]] if col[name] is not None and col[name] < len(row) else None
        raw_date = cell("date")
        if raw_date in (None, ""):
            continue
        try:
            d, t = parse_date(raw_date)
        except FormatError:
            continue  # "합계" 같은 요약 행
        t = parse_time(cell("time")) or t
        if fmt.card:
            amt = -parse_amount(cell("amount"))
            if col["cancel"] is not None and "취소" in str(cell("cancel") or ""):
                amt = abs(amt)
        else:
            amt = parse_amount(cell("deposit")) - abs(parse_amount(cell("withdraw")))
        bal = parse_amount(cell("balance")) if col["balance"] is not None and cell("balance") not in (None, "") else None
        tx = Transaction(date=d, time=t, amount=amt, account=fmt.account, balance=bal,
                         counterparty=str(cell("counterparty") or "").strip(), memo=str(cell("memo") or "").strip(),
                         source=f"excel:{fmt.key}", source_ref=f"{Path(path).name}:{i}",
                         extra={"card": fmt.card, **{k: row[c] for k, c in extra_col.items() if c is not None and c < len(row) and row[c] not in (None, "")}})
        out.append(tx)
    return out
