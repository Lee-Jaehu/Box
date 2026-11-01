"""카테고리 자동 분류. 가맹점 이름 규칙으로 기본값을 주고, 사용자가 고친 값을 기억해 우선 적용한다
(Phase 1 T04: "고친 걸 기억하지 못함"). 규칙은 흔한 가맹점 이름만 담은 출발점이고, 틀리면 사용자가 고친 값이 이긴다.
"""
import json
import re
from pathlib import Path

# (카테고리, 가맹점 이름에 들어 있으면 해당하는 낱말). 위에 있는 규칙이 먼저 적용된다.
RULES = [
    ("통신", ("LG유플러스", "LGU+", "유플러스", "SK텔레콤", "SKT", "KT통신", "통신요금", "알뜰폰")),
    ("교통", ("버스", "택시", "카카오T", "티맵", "코레일", "SRT", "지하철", "교통카드", "주유", "주차", "하이패스", "현장발권", "통행료", "고속도로")),
    ("카페·간식", ("스타벅스", "투썸", "이디야", "메가커피", "메가엠지씨", "컴포즈", "빽다방", "폴바셋", "카페", "베이커리", "파리바게뜨", "뚜레쥬르", "던킨", "배스킨", "공차", "꽈배기")),
    ("식비", ("배달의민족", "우아한형제들", "요기요", "쿠팡이츠", "식당", "치킨", "피자", "김밥", "국밥", "고기", "이마트", "홈플러스", "롯데마트", "GS25", "CU", "세븐일레븐", "이마트24", "편의점", "식자재", "휴게소")),
    ("의료", ("병원", "의원", "약국", "치과", "한의원", "정형외과", "내과")),
    ("문화·여가", ("CGV", "롯데시네마", "메가박스", "넷플릭스", "유튜브프리미엄", "멜론", "티켓", "야놀자", "여기어때")),
    ("교육", ("학원", "교보문고", "알라딘", "예스24", "인강", "클래스101")),
    ("생활용품", ("다이소", "아성다이소", "쿠팡", "올리브영", "무신사", "11번가", "G마켓", "옥션", "SSG")),
    ("보험", ("보험", "화재", "생명")),
    ("주거·관리비", ("관리비", "도시가스", "한국전력", "수도", "월세")),
]


# 결제 대행(간편결제·PG). 실제 가게가 아니라서 가맹점 규칙으로 학습하면 다른 거래까지 잘못 분류된다
# (2026-11: 사용자가 네이버페이 할부 한 건을 '육아'로 고침 → 네이버페이 전체를 육아로 기억하면 안 됨).
# 명세서에 'PG - 실제 가맹점' 형태로 나오면 실제 가맹점 쪽을 쓴다(현대카드 명세서에서 확인).
AGGREGATORS = ("네이버페이", "카카오페이", "토스페이", "페이코", "PAYCO", "쿠페이", "쿠팡페이", "스마일페이", "SSG페이",
               "KCP", "이니시스", "토스페이먼츠", "나이스정보통신", "한국정보통신", "KG모빌리언스", "다날",
               "비바리퍼블리")  # 토스 운영사. 'PG - (주)비바리퍼블리카'는 토스페이 결제·토스머니 충전 등이 섞여 가게를 알 수 없음


def merchant_part(name):
    """'토스페이먼츠주식회사 - (주)비바리퍼블리카' → '(주)비바리퍼블리카'. 구분자가 없으면 그대로."""
    parts = re.split(r"\s+-\s+", name or "")
    return parts[-1] if len(parts) > 1 else (name or "")


def is_aggregator(name):
    n = _norm(merchant_part(name))
    return any(_norm(a) in n for a in AGGREGATORS)


def _norm(s):
    s = re.sub(r"\(주\)|㈜|주식회사|\s+|[()（）]", "", s or "")  # (주)를 괄호보다 먼저 지운다
    return s.upper()


class Categorizer:
    """learned: {정규화된 가맹점: 카테고리}. 노션에서 사용자가 카테고리를 고치면 learn()으로 저장한다."""

    def __init__(self, learned=None, rules=RULES):
        self.learned = dict(learned or {})
        self.rules = [(c, tuple(_norm(w) for w in ws)) for c, ws in rules]

    def categorize(self, merchant):
        """(카테고리, 근거)를 돌려준다."""
        key = _norm(merchant_part(merchant))
        if not key:
            return "미분류", "가맹점 이름 없음"
        if key in self.learned:
            return self.learned[key], "직접 고친 분류를 기억함"
        for cat, words in self.rules:
            w = next((w for w in words if w and w in key), None)
            if w:
                return cat, f"가맹점에 '{w}' 포함"
        return "미분류", "규칙 없음"

    def learn(self, merchant, category):
        """사용자가 고친 카테고리를 기억한다. 결제 대행은 기억하지 않고 False를 돌려준다(그 거래에만 반영)."""
        if is_aggregator(merchant):
            return False
        self.learned[_norm(merchant_part(merchant))] = category
        return True

    def save(self, path):
        Path(path).write_text(json.dumps(self.learned, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path):
        p = Path(path)
        return cls(json.loads(p.read_text(encoding="utf-8")) if p.exists() else {})
