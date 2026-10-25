"""카테고리 자동 분류. 가맹점 이름 규칙으로 기본값을 주고, 사용자가 고친 값을 기억해 우선 적용한다
(Phase 1 T04: "고친 걸 기억하지 못함"). 규칙은 흔한 가맹점 이름만 담은 출발점이고, 틀리면 사용자가 고친 값이 이긴다.
"""
import json
import re
from pathlib import Path

# (카테고리, 가맹점 이름에 들어 있으면 해당하는 낱말). 위에 있는 규칙이 먼저 적용된다.
RULES = [
    ("통신", ("LG유플러스", "LGU+", "유플러스", "SK텔레콤", "SKT", "KT통신", "통신요금", "알뜰폰")),
    ("교통", ("버스", "택시", "카카오T", "티맵", "코레일", "SRT", "지하철", "교통카드", "주유", "주차", "하이패스", "현장발권")),
    ("카페·간식", ("스타벅스", "투썸", "이디야", "메가커피", "메가엠지씨", "컴포즈", "빽다방", "폴바셋", "카페", "베이커리", "파리바게뜨", "뚜레쥬르", "던킨", "배스킨")),
    ("식비", ("배달의민족", "우아한형제들", "요기요", "쿠팡이츠", "식당", "치킨", "피자", "김밥", "국밥", "고기", "이마트", "홈플러스", "롯데마트", "GS25", "CU", "세븐일레븐", "이마트24", "편의점", "식자재")),
    ("의료", ("병원", "의원", "약국", "치과", "한의원", "정형외과", "내과")),
    ("문화·여가", ("CGV", "롯데시네마", "메가박스", "넷플릭스", "유튜브프리미엄", "멜론", "티켓", "야놀자", "여기어때")),
    ("교육", ("학원", "교보문고", "알라딘", "예스24", "인강", "클래스101")),
    ("생활용품", ("다이소", "아성다이소", "쿠팡", "올리브영", "무신사", "11번가", "G마켓", "옥션", "SSG")),
    ("보험", ("보험", "화재", "생명")),
    ("주거·관리비", ("관리비", "도시가스", "한국전력", "수도", "월세")),
]


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
        key = _norm(merchant)
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
        self.learned[_norm(merchant)] = category

    def save(self, path):
        Path(path).write_text(json.dumps(self.learned, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path):
        p = Path(path)
        return cls(json.loads(p.read_text(encoding="utf-8")) if p.exists() else {})
