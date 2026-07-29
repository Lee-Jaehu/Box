# -*- coding: utf-8 -*-
"""
gemini_studio_automation.py
------------------------------
사내 SSO로 자동 로그인되는 환경을 전제로, 매 호출마다 새 브라우저를 띄워
Gemini Enterprise **Agent Designer**로 만든 에이전트의 채팅(Preview) 화면에
프롬프트를 자동으로 입력하고 답변을 긁어오는 모듈.

★ GEMINI_STUDIO_URL 찾는 법 ★
1) Gemini Enterprise – Business edition (business.gemini.google/) 접속
2) 좌측 메뉴 Agents → 우리가 만든 요약용 에이전트 선택
3) Agent Designer 화면에서 "Preview" 탭 클릭 (실제로 대화하는 화면)
4) 그 화면의 주소창 URL을 그대로 GEMINI_STUDIO_URL로 사용
   (Agent Designer 빌더 화면 URL이 아니라, 반드시 Preview/대화창 URL이어야 합니다)

세션을 로컬에 저장하지 않습니다 (사내망/SSO라 브라우저를 열면 자동 로그인되는
환경이라는 전제이므로, 로그인 상태를 유지해둘 필요가 없습니다). 매번 완전히
새 브라우저 프로필로 시작하고 종료 시 아무 흔적도 남기지 않습니다.

★★★ 사용 전 반드시 확인 ★★★
1) 사내 보안/법무팀에 "브라우저 자동화로 Agent Designer 채팅을 조작해도 되는지"
   확인받으세요. (이 방식은 정식 API가 아니라 웹 UI 자동화입니다 - Google이나
   회사가 API 대신 Agent Designer를 통한 사용만 승인한 경우, 이 우회가 그
   승인 범위를 벗어날 수 있습니다.)
2) 아래 CSS 선택자(SELECTOR)들은 예시입니다. 실제 Agent Designer Preview 화면의
   DOM 구조를 보고 반드시 교체해야 동작합니다. (브라우저 개발자도구 F12로 확인)
3) Agent Designer UI가 업데이트되면 선택자가 깨질 수 있습니다 - 주기적으로 점검하세요.
4) SSO가 완전히 silent(별도 화면 없이 네트워크 신원만으로 인증)해야 headless로
   잘 동작합니다. 로그인 과정에서 뭔가 화면이 잠깐이라도 뜬다면 GEMINI_HEADLESS=false로
   먼저 확인해보세요.
5) Preview 화면은 계정에 대화 이력이 남아있을 수 있어서, 매 배치 시작 전
   "새 채팅"을 눌러 이전 프롬프트의 맥락이 섞이지 않도록 처리합니다
   (NEW_CHAT_BEFORE_EACH_BATCH, 기본 활성화).
"""
import os
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

# ── 환경설정 (환경변수로 오버라이드 가능) ────────────────────────────────
# 기본값은 예시입니다 - 위 안내대로 실제 에이전트의 Preview URL로 반드시 교체하세요.
STUDIO_URL = os.environ.get("GEMINI_STUDIO_URL", "https://business.gemini.google/agents")
HEADLESS = os.environ.get("GEMINI_HEADLESS", "true").lower() == "true"
NEW_CHAT_BEFORE_EACH_BATCH = os.environ.get("GEMINI_NEW_CHAT_EACH_BATCH", "true").lower() == "true"

# ★ 실제 studio의 DOM에 맞게 반드시 교체하세요 (F12 개발자도구로 확인) ★
SELECTORS = {
    # Gemini Enterprise Preview 화면의 실제 DOM 기준
    # Playwright CSS locator는 open Shadow DOM을 자동으로 탐색합니다.
    "prompt_input": os.environ.get(
        "SEL_PROMPT_INPUT",
        "ucs-prosemirror-editor .ProseMirror[contenteditable='true']",
    ),
    "submit_button": os.environ.get(
        "SEL_SUBMIT_BUTTON",
        "md-icon-button.send-button",
    ),
    "response_container": os.environ.get(
        "SEL_RESPONSE_CONTAINER",
        "ucs-fast-markdown .markdown-document",
    ),
}

RESPONSE_TIMEOUT_MS = int(os.environ.get("GEMINI_RESPONSE_TIMEOUT_MS", "120000"))  # 2분
LOGIN_WAIT_TIMEOUT_MS = int(os.environ.get("GEMINI_LOGIN_WAIT_TIMEOUT_MS", "15000"))  # SSO 리다이렉트 대기


class StudioAutomationError(Exception):
    pass


def run_batch_prompt(prompt: str) -> str:
    """
    매 호출마다 새 브라우저를 띄워(세션 저장 없음) SSO 자동 로그인 상태로
    studio에 접속, 프롬프트를 입력하고 답변 텍스트를 반환한다.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        try:
            page = context.new_page()
            page.goto(STUDIO_URL, wait_until="domcontentloaded")

            # SSO 리다이렉트가 끝나고 실제 studio 입력창이 뜰 때까지 대기
            try:
                page.locator(SELECTORS["prompt_input"]).first.wait_for(
                    state="visible", timeout=LOGIN_WAIT_TIMEOUT_MS
                )
            except PWTimeoutError:
                raise StudioAutomationError(
                    "SSO 로그인/리다이렉트 후에도 프롬프트 입력창을 찾지 못했습니다. "
                    "GEMINI_HEADLESS=false로 실제 화면을 확인해보세요 "
                    "(SSO가 완전히 silent하지 않을 수 있습니다)."
                )

            _try_start_new_chat(page)

            # 새 응답이 추가되는 시점을 정확히 구분하기 위해 전송 전 응답 수를 기록한다.
            initial_response_count = page.locator(
                SELECTORS["response_container"]
            ).count()

            _type_prompt(page, prompt)
            _submit(page)
            text = _wait_for_response(page, initial_response_count)
            return text
        finally:
            context.close()
            browser.close()


def _try_start_new_chat(page):
    """'새 채팅' 버튼이 있다면 눌러 이전 프롬프트의 대화 맥락이 섞이지 않게 한다.
    없거나 실패해도 조용히 넘어간다 (Preview 화면에 해당 버튼이 없을 수도 있음)."""
    if not NEW_CHAT_BEFORE_EACH_BATCH:
        return
    try:
        new_chat_sel = os.environ.get(
            "SEL_NEW_CHAT",
            'ucs-nav-panel button[aria-label="새 채팅"]',
        )
        page.locator(new_chat_sel).first.click(timeout=3000)
        page.wait_for_timeout(500)
    except PWTimeoutError:
        pass


def _type_prompt(page, prompt: str):
    box = page.locator(SELECTORS["prompt_input"]).first
    box.wait_for(state="visible", timeout=15000)
    box.click()
    # 매우 긴 프롬프트는 fill()이 더 안정적 (type()은 키 이벤트를 하나씩 보내 느리고 끊길 수 있음)
    box.fill(prompt)


def _submit(page):
    try:
        page.click(SELECTORS["submit_button"], timeout=5000)
    except PWTimeoutError:
        # 전송 버튼을 못 찾으면 Enter 키로 대체 시도
        page.keyboard.press("Control+Enter")


def _wait_for_response(page, initial_response_count: int) -> str:
    """
    새 모델 응답이 나타난 뒤 텍스트가 일정 시간 변하지 않을 때까지 기다린다.

    생성 중 아이콘이나 중지 버튼은 UI 업데이트에 따라 자주 바뀌므로 사용하지 않는다.
    대신 응답 컨테이너 수가 증가했는지 확인하고, 마지막 응답의 텍스트가
    연속으로 여러 번 동일할 때 생성을 완료한 것으로 판단한다.
    """
    deadline = time.monotonic() + (RESPONSE_TIMEOUT_MS / 1000)
    responses = page.locator(SELECTORS["response_container"])

    # 스트리밍 중 잠깐 멈추는 구간을 완료로 오인하지 않도록 약 4초간 안정 상태를 확인한다.
    stable_checks_required = 5
    stable_checks = 0
    previous_text = ""

    while time.monotonic() < deadline:
        count = responses.count()

        # 새 채팅 버튼이 정상 동작했으면 0 -> 1, 실패했더라도 기존 수보다 증가해야 한다.
        if count <= initial_response_count:
            page.wait_for_timeout(500)
            continue

        current_text = responses.nth(count - 1).inner_text().strip()

        if not current_text:
            stable_checks = 0
            page.wait_for_timeout(500)
            continue

        if current_text == previous_text:
            stable_checks += 1
            if stable_checks >= stable_checks_required:
                return current_text
        else:
            previous_text = current_text
            stable_checks = 0

        page.wait_for_timeout(800)

    raise StudioAutomationError(
        "응답 생성 대기 시간 초과 또는 새 응답을 찾지 못했습니다. "
        "GEMINI_RESPONSE_TIMEOUT_MS와 SEL_RESPONSE_CONTAINER를 확인하세요."
    )
