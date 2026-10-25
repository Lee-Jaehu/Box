"""노션 DB 정의와 페이지 속성 페이로드. 노션은 화면이고, 숫자는 Python이 계산해 숫자 속성으로 쓴다(Phase 0 3절).

- relation·rollup·formula에 계산을 맡기지 않는다. API에서 relation은 25개까지만 보이고 그에 걸린 formula도 틀릴 수 있다.
  사용자가 수식을 만들거나 고칠 일도 없게 한다(Phase 1 T21: 노션 템플릿 수식 오류).
- 거래와 알림은 '원본키' 텍스트로 잇는다.
- 실제 API 호출(토큰, 첫 실행 DB 자동 연결, 초당 3회 제한·Retry-After 처리)은 토큰을 받은 뒤 붙인다.
"""
from .model import Kind

CATEGORIES = ["식비", "카페·간식", "생활용품", "교통", "주거·관리비", "통신", "의료", "교육", "문화·여가", "경조사", "보험", "미분류"]

DATABASES = {
    "거래": {
        "이름": "title",
        "날짜": "date",
        "금액": "number",              # 원, 지출 음수
        "계정": "select",
        "구분": ("select", [k.value for k in Kind]),
        "카테고리": ("select", CATEGORIES),
        "출처": ("select", ["엑셀", "알림"]),
        "분류 근거": "rich_text",
        "메모": "rich_text",
        "원본키": "rich_text",          # 중복 입력 방지. model.assign_keys
        "원본 위치": "rich_text",       # 파일명:행, 알림 id
        "청구 금액": "number",          # 이번 명세서 청구액. 할부면 회차 금액 + 수수료
        "결제월": "rich_text",          # "2026-10"
        "할부": "rich_text",            # "1/3"
        "할부 수수료": "number",
    },
    "알림 수신함": {
        "원문": "title",
        "발신처": "select",
        "받은 시각": "date",
        "상태": ("select", ["미해석", "해석됨", "엑셀과 대사됨", "형식 변경 의심"]),
        "원본키": "rich_text",
    },
    "월별 대사": {
        "월": "title",                 # "2026-10 하나은행"
        "계정": "select",
        "엑셀 기준 잔액": "number",
        "계산 잔액": "number",
        "차이": "number",
        "잔액 끊김": "number",          # reconcile.balance_breaks 건수
        "알림 누락": "number",          # reconcile.alert_coverage
        "청구액 차이": "number",        # 카드만
    },
    "주간 인사이트": {
        "주": "title",                 # "2026-W43"
        "내용": "rich_text",
        "근거": "rich_text",           # 숫자가 어디서 왔는지
    },
}


def schema_payload(db):
    """노션 data source 생성용 properties 정의."""
    out = {}
    for name, spec in DATABASES[db].items():
        typ, options = spec if isinstance(spec, tuple) else (spec, None)
        if options:
            out[name] = {typ: {"options": [{"name": o} for o in options]}}
        elif typ == "number":
            out[name] = {"number": {"format": "won"}}
        else:
            out[name] = {typ: {}}
    return out


def _text(s):
    s = str(s or "")
    return [{"type": "text", "text": {"content": s[i:i + 2000]}} for i in range(0, len(s), 2000)] or []


def transaction_properties(key, tx, category=None):
    """Transaction → 거래 DB 페이지 properties. rich_text 2,000자 제한은 나눠 담는다."""
    when = tx.date.isoformat() + (f"T{tx.time.strftime('%H:%M')}:00+09:00" if tx.time else "")
    return {
        "이름": {"title": _text(tx.counterparty or tx.memo or "(내용 없음)")},
        "날짜": {"date": {"start": when}},
        "금액": {"number": tx.amount},
        "계정": {"select": {"name": tx.account}},
        "구분": {"select": {"name": tx.kind.value}} if tx.kind else {"select": None},
        "카테고리": {"select": {"name": category or "미분류"}},
        "출처": {"select": {"name": "알림" if tx.source.startswith("alert:") else "엑셀"}},
        "분류 근거": {"rich_text": _text(tx.kind_reason)},
        "메모": {"rich_text": _text(tx.memo)},
        "원본키": {"rich_text": _text(key)},
        "원본 위치": {"rich_text": _text(tx.source_ref)},
        "청구 금액": {"number": tx.billed},
        "결제월": {"rich_text": _text(tx.billing_month)},
        "할부": {"rich_text": _text(f"{tx.installment[0]}/{tx.installment[1]}" if tx.installment else "")},
        "할부 수수료": {"number": tx.fee or None},
    }
