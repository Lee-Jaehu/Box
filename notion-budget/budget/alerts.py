"""알림 원문 해석. 휴대폰(iOS 단축어, Android MacroDroid)은 원문을 노션 수신함에 넣기만 하고
해석은 여기서 한다(Phase 0 결정 Q5-1).

기존 앱의 가장 큰 불만(T09)은 카드사가 알림 형식을 바꾸면 인식이 조용히 멈추는 것이다.
그래서 이 모듈은 세 가지를 지킨다.
1. 해석하지 못한 알림도 버리지 않고 '미해석'으로 돌려준다.
2. 같은 발신처에서 돈 알림처럼 보이는 미해석이 연속으로 쌓이면 '형식 변경 의심'을 낸다.
3. 알림은 미리보기일 뿐이고, 숫자의 기준은 월말 엑셀이다(reconcile.alert_coverage).

발신처별 패턴(PATTERNS)은 실제 알림 원문 샘플을 받은 뒤 채운다. 지금은 비어 있다.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .model import Transaction

MONEY_HINT = re.compile(r"\d[\d,]*\s*원")


@dataclass
class Pattern:
    """한 발신처의 한 가지 알림 형식. regex는 이름 붙은 그룹 amount(필수), merchant, month, day, hour, minute,
    card_tail, cancel을 쓸 수 있다. cancel 그룹이 매칭되면 환불(양수)로 본다."""
    name: str
    account: str
    regex: re.Pattern
    sign: int = -1            # 승인 알림은 지출(음수)
    card: bool = True


@dataclass
class Alert:
    id: str
    sender: str
    text: str
    received_at: datetime


@dataclass
class Result:
    alert: Alert
    tx: Optional[Transaction] = None
    pattern: str = ""
    looks_financial: bool = False

    @property
    def parsed(self):
        return self.tx is not None


PATTERNS = {}  # {"shinhan_card": [Pattern, ...]} — 실제 샘플로 채움


def parse(alert, patterns=None):
    patterns = PATTERNS if patterns is None else patterns
    text = alert.text.replace("\r", "")
    for p in patterns.get(alert.sender, []):
        m = p.regex.search(text)
        if not m:
            continue
        g = m.groupdict()
        amt = int(g["amount"].replace(",", ""))
        refund = bool(g.get("cancel"))
        d = alert.received_at
        if g.get("month") and g.get("day"):
            y = d.year - (1 if int(g["month"]) > d.month else 0)  # 1월에 받은 12월 승인
            d = d.replace(year=y, month=int(g["month"]), day=int(g["day"]))
        if g.get("hour") and g.get("minute"):
            d = d.replace(hour=int(g["hour"]), minute=int(g["minute"]), second=0)
        tx = Transaction(date=d.date(), time=d.time().replace(second=0, microsecond=0), amount=amt if refund else p.sign * amt,
                         account=p.account + (f"({g['card_tail']})" if g.get("card_tail") else ""),
                         counterparty=(g.get("merchant") or "").strip(), source=f"alert:{alert.sender}",
                         source_ref=alert.id, extra={"card": p.card, "pattern": p.name})
        return Result(alert, tx, p.name, True)
    return Result(alert, None, "", bool(MONEY_HINT.search(text)))


@dataclass
class FormatWatch:
    """발신처별로 '돈 알림처럼 보이는데 해석 실패'가 연속 몇 번인지 센다. 한 번이라도 해석되면 0으로 돌아간다."""
    threshold: int = 3
    streak: dict = field(default_factory=dict)

    def feed(self, result):
        """경고 문구를 돌려주거나 None. 연속 횟수가 threshold에 처음 닿을 때 한 번만 낸다."""
        s = result.alert.sender
        if result.parsed:
            self.streak[s] = 0
            return None
        if not result.looks_financial:
            return None
        self.streak[s] = self.streak.get(s, 0) + 1
        if self.streak[s] == self.threshold:
            return (f"{s}: 금액이 들어 있는 알림 {self.threshold}건을 연속으로 해석하지 못했습니다. "
                    "알림 형식이 바뀌었을 수 있습니다. 수신함의 '미해석' 원문을 확인해 주세요. "
                    "월말 엑셀 대사에서 빠진 거래는 채워집니다.")
        return None
