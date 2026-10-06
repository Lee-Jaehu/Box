"""Task 에디터 섹션 입력 (## 진행 현황 / ## 이슈 / ## 향후계획 → contents{}) 과 원문 예산 (결정 I38·I39)."""
from weekly_report import prompt_vars as pv
from weekly_report.worklog import DAILY_TYPE, log_text, merge_contents, task_contents, task_sections, to_dailies

MD = "## 진행 현황 : 데이터 수집 완료\n- 3개 라인 적용\n## 이슈: 센서 오검출\n### 향후 계획\n10/8 전 라인 확대"
WANT = {"진행 현황": ["데이터 수집 완료", "- 3개 라인 적용"], "이슈": ["센서 오검출"], "향후계획": ["10/8 전 라인 확대"]}


def para(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def envelope(*nodes: dict) -> dict:
    return {"documentVersion": 1, "format": "tiptap-json", "doc": {"type": "doc", "content": list(nodes)}}


def test_three_input_formats_give_the_same_sections():
    as_dict = {"진행현황": "데이터 수집 완료\n- 3개 라인 적용", "이슈 사항": ["센서 오검출"], "계획": "10/8 전 라인 확대"}
    heading = {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "진행 현황 : 데이터 수집 완료"}]}
    bullet = {"type": "bulletList", "content": [{"type": "listItem", "content": [para("3개 라인 적용")]}]}
    tiptap = envelope(heading, bullet, para("## 이슈 : 센서 오검출"), para("## 향후계획 : 10/8 전 라인 확대"))
    assert task_sections(MD) == WANT
    assert task_sections(as_dict) == WANT
    assert task_sections(tiptap) == WANT


def test_text_without_sections_and_heading_like_body():
    assert task_sections(envelope(para("그냥 적은 업무 내용"))) == {"내용": ["그냥 적은 업무 내용"]}
    # 붙여 쓴 '##이슈'는 알려진 이름이라 제목, '#1 개선'은 본문, 모르는 이름은 그 이름 그대로 섹션
    assert task_sections("##이슈:a\n#1 개선 완료\n## 기타 메모\nm") == {"이슈": ["a", "#1 개선 완료"], "기타 메모": ["m"]}
    assert task_sections({"진행 현황": "", "이슈": None}) == {}
    assert task_sections(None) == {}


def test_contents_field_is_preferred_and_tasks_merge_in_order():
    task = {"contents": {"이슈": "x"}, "content": envelope(para("## 진행 현황 : y"))}
    assert task_contents(task) == {"이슈": ["x"]}
    assert task_contents({"content": envelope(para("## 진행 현황 : y"))}) == {"진행 현황": ["y"]}
    merged = merge_contents([{"내용": ["a"], "이슈": ["b"]}, {"향후계획": ["c"], "진행 현황": ["d"]}])
    assert list(merged) == ["진행 현황", "이슈", "향후계획", "내용"]


def test_log_text_is_sectioned_and_old_records_are_tolerated():
    log = {"tasks": [{"title": "로직 개발", "milestone": {"nameSnapshot": "1단계"}, "content": MD}],
           "todoRecords": [{"originalSnapshot": {"content": envelope(para("옛 할 일")), "status": "open"}}]}
    text = log_text(log, {}, {"record_status": {"open": "진행"}})
    assert text.splitlines() == ["[수행] (1단계) 로직 개발 (-)", "  [진행 현황] 데이터 수집 완료 / - 3개 라인 적용",
                                 "  [이슈] 센서 오검출", "  [향후계획] 10/8 전 라인 확대", "[할 일] 옛 할 일 (상태 진행)"]


def test_daily_carries_contents():
    export = {"fileType": DAILY_TYPE, "schemaVersion": "1", "generatedAt": "2026-10-01T09:00:00+09:00", "date": "2026-09-30",
              "project": {"id": "P1"},
              "logs": [{"id": "L1", "author": {"id": "U1", "name": "홍길동", "employeeNumber": "E001"},
                        "tasks": [{"id": "T1", "sortOrder": 1, "content": envelope(para("## 이슈 : 센서")), "title": "a"},
                                  {"id": "T2", "sortOrder": 0, "contents": {"진행 현황": "수집"}, "title": "b"}]}]}
    [daily] = to_dailies(export, {"milestones": []}, {"schema_versions": ["1"]})
    assert daily["contents"] == {"진행 현황": ["수집"], "이슈": ["센서"]}
    assert daily["source_refs"]["tasks"] == ["T1", "T2"]


def _daily(i: int, progress_chars: int) -> dict:
    return {"daily_id": f"D-2609{i:02d}-a-01", "date": "2026-09-30", "author": "a",
            "raw_text": f"[수행] (단계) 제목\n  [진행 현황] {'가' * progress_chars}\n  [이슈] 장비 고장 {i}"}


def test_daily_blocks_budget_trims_evenly_and_keeps_issue_lines():
    dailies = [_daily(i, 200 + 600 * i) for i in range(6)]
    full = pv.daily_blocks(dailies)
    assert pv.daily_blocks(dailies, budget=len(full)) == full  # 예산 안이면 그대로
    notes: list[str] = []
    text = pv.daily_blocks(dailies, budget=4000, notes=notes, focus=True)
    assert len(text) <= 4400 and len(full) > 10000
    assert all(f"D-2609{i:02d}-a-01" in text and f"[이슈] 장비 고장 {i}" in text for i in range(6))  # 기록 ID·이슈 줄은 남김
    assert "가" * 200 in text.split("D-260901")[0]  # 작은 기록은 그대로
    assert text.count(pv.TRIM_MARK) >= 4 and "AI 입력 상한 4,000자" in notes[0]
    tiny = pv.daily_blocks(dailies, budget=300)  # 이슈 줄만으로도 넘으면 전체를 균등하게
    assert len(tiny) < len(full) and "D-260905-a-01" in tiny
