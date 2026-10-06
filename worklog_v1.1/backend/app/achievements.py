"""정량 성과 프리셋 검증과 서버 재계산.

- Decimal 사용, 문자열 직렬화로 부동소수 오차를 피한다.
- 클라이언트가 보낸 derived 는 무시하고 서버가 다시 계산한다.
- before=0 이면 상대 변화율은 null. 단위/기간이 다르면 비교하지 않고 오류.
- improvement 는 "좋아진 방향"을 양수로 표시한 값이다(감소가 좋은 프리셋은 before-after). difference 는 항상 after-before.
- % 단위는 %p 차이를 별도로 제공한다(5%→3% = -2%p, 상대 변화율 -40%).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import validation

CALCULATION_VERSION = "1"

PRESETS: dict[str, dict[str, Any]] = {
    "time_reduction": {"kind": "compare", "good": "decrease", "label": "시간 단축"},
    "cost_reduction": {"kind": "compare", "good": "decrease", "label": "비용 절감", "needs_currency": True},
    "throughput_increase": {"kind": "compare", "good": "increase", "label": "처리량 증가"},
    "defect_reduction": {"kind": "compare", "good": "decrease", "label": "오류/불량 감소"},
    "goal_achievement": {"kind": "goal", "label": "목표 달성"},
    "custom": {"kind": "single", "label": "직접 입력"},
}
QUALITATIVE_PRESETS = {
    "standardization", "quality_stability", "risk_prevention", "collaboration", "usability", "knowledge", "custom",
}


def _dec(value: Any, field: str) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise validation("필수 숫자 값이 비어 있습니다.", [{"field": field, "code": "REQUIRED", "message": "값을 입력해 주세요."}])
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        raise validation("숫자 형식이 올바르지 않습니다.", [{"field": field, "code": "NOT_A_NUMBER", "message": "숫자를 입력해 주세요."}]) from None
    if not d.is_finite():
        raise validation("숫자 형식이 올바르지 않습니다.", [{"field": field, "code": "NOT_A_NUMBER", "message": "유한한 숫자를 입력해 주세요."}])
    return d


def fmt(d: Decimal | None) -> str | None:
    if d is None:
        return None
    q = d.quantize(Decimal("0.000001")).normalize()
    s = format(q, "f")
    return "0" if s in {"-0", ""} else s


def _same(payload: dict, a: str, b: str, generic: str, label: str, field: str) -> str | None:
    va, vb = payload.get(a), payload.get(b)
    if va and vb and va != vb:
        raise validation(f"{label}이(가) 기존/현재 값에서 다릅니다. 같은 {label}으로 비교해 주세요.",
                         [{"field": field, "code": "MISMATCH", "message": f"{label} 불일치"}])
    return va or vb or payload.get(generic)


def compute_quantitative(preset_key: str, payload: dict[str, Any], field: str = "numericPayload") -> dict[str, Any]:
    spec = PRESETS.get(preset_key)
    if spec is None:
        raise validation("알 수 없는 정량 프리셋입니다.", [{"field": f"{field}.presetKey", "code": "UNKNOWN_PRESET", "message": preset_key}])
    metric = str(payload.get("metricName") or "").strip()
    if not metric and preset_key == "custom":
        raise validation("지표명이 필요합니다.", [{"field": f"{field}.metricName", "code": "REQUIRED", "message": "지표명을 입력해 주세요."}])
    unit = _same(payload, "beforeUnit", "afterUnit", "unit", "단위", f"{field}.unit")
    period = _same(payload, "beforePeriod", "afterPeriod", "comparisonBasis", "비교 기간", f"{field}.comparisonBasis")
    if spec.get("needs_currency") and not payload.get("currency"):
        raise validation("통화가 필요합니다.", [{"field": f"{field}.currency", "code": "REQUIRED", "message": "통화를 입력해 주세요."}])

    out: dict[str, Any] = {
        "metricName": metric or spec["label"], "unit": unit, "currency": payload.get("currency"),
        "comparisonBasis": period, "measurementScope": payload.get("measurementScope"),
        "frequency": payload.get("frequency"), "summaryText": payload.get("summaryText"),
        "calculationVersion": CALCULATION_VERSION,
    }
    derived: dict[str, Any] = {}
    if spec["kind"] == "compare":
        before = _dec(payload.get("beforeValue"), f"{field}.beforeValue")
        after = _dec(payload.get("afterValue"), f"{field}.afterValue")
        diff = after - before
        out.update(beforeValue=fmt(before), afterValue=fmt(after))
        derived["difference"] = fmt(diff)
        derived["improvement"] = fmt(-diff if spec["good"] == "decrease" else diff)
        derived["improved"] = (diff < 0) if spec["good"] == "decrease" else (diff > 0) if diff != 0 else None
        derived["relativeChangePercent"] = fmt(diff / before * 100) if before != 0 else None
        derived["percentagePointChange"] = fmt(diff) if unit == "%" else None
    elif spec["kind"] == "goal":
        target = _dec(payload.get("targetValue"), f"{field}.targetValue")
        actual = _dec(payload.get("value", payload.get("afterValue")), f"{field}.value")
        out.update(targetValue=fmt(target), value=fmt(actual))
        derived["difference"] = fmt(actual - target)
        derived["attainmentPercent"] = fmt(actual / target * 100) if target != 0 else None
        # 지표 방향(KPI direction)을 모르면 달성 여부를 판정하지 않는다.
        direction = payload.get("direction")
        if direction == "increase":
            derived["achieved"] = actual >= target
        elif direction == "decrease":
            derived["achieved"] = actual <= target
        else:
            derived["achieved"] = None
    else:
        out["value"] = fmt(_dec(payload.get("value"), f"{field}.value"))
    out["derived"] = derived
    return out
