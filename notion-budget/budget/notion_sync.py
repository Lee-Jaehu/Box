"""노션 API 동기화. 구매자 PC에서 구매자 토큰으로만 실행한다(판매자는 토큰·데이터에 접근하지 않음, Phase 0 5-1절).

- API 버전 2025-09-03 (database와 data source 분리). 페이지는 data source 아래에 만든다.
- 초당 3회 제한: 호출 간격을 1/3초 이상으로 두고, 429면 Retry-After만큼 기다렸다 다시 한다. 5xx는 짧게 몇 번 재시도.
- 사용자가 노션에서 고친 값이 항상 이긴다: 이미 있는 원본키는 다시 쓰지 않고(새 거래만 만든다),
  사용자가 고친 카테고리·구분은 읽어 와서 다음 분류에 반영한다(categories.Categorizer.learn).
- 첫 실행 때 DB를 제목으로 찾는다. 구매자가 템플릿을 복제하면 ID가 바뀌기 때문이다(Phase 0 3절).

**주의:** 이 모듈은 가짜 응답으로만 시험했다(tests/test_budget.py). 실제 노션 API에 대고는 토큰을 받은 뒤 확인한다.
"""
import time

API = "https://api.notion.com/v1"
VERSION = "2025-09-03"


class NotionError(RuntimeError):
    pass


class Client:
    def __init__(self, token, session=None, min_interval=1 / 3, max_retries=5, sleep=time.sleep, clock=time.monotonic):
        if session is None:
            import requests
            session = requests.Session()
        self.session, self.min_interval, self.max_retries = session, min_interval, max_retries
        self.sleep, self.clock, self._last = sleep, clock, None
        self.headers = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION, "Content-Type": "application/json"}

    def request(self, method, path, body=None):
        for attempt in range(self.max_retries + 1):
            if self._last is not None:
                wait = self.min_interval - (self.clock() - self._last)
                if wait > 0:
                    self.sleep(wait)
            self._last = self.clock()
            r = self.session.request(method, API + path, headers=self.headers, json=body, timeout=30)
            if r.status_code == 429:
                self.sleep(float(r.headers.get("Retry-After", 1)))
                continue
            if r.status_code >= 500 and attempt < self.max_retries:
                self.sleep(min(2 ** attempt, 16))
                continue
            if r.status_code >= 400:
                raise NotionError(f"{method} {path} → {r.status_code}: {r.text[:300]}")
            return r.json()
        raise NotionError(f"{method} {path}: 재시도 {self.max_retries}회 후에도 실패")

    def find_data_sources(self, titles):
        """{제목: data source id}. 통합(integration)에 공유된 것 중 제목이 정확히 같은 것만 찾는다."""
        found = {}
        for title in titles:
            res = self.request("POST", "/search", {"query": title, "filter": {"property": "object", "value": "data_source"}})
            for obj in res.get("results", []):
                name = "".join(t.get("plain_text", "") for t in obj.get("title", []))
                if name == title:
                    found[title] = obj["id"]
                    break
        missing = [t for t in titles if t not in found]
        if missing:
            raise NotionError(f"노션에서 찾지 못한 DB: {', '.join(missing)}. 템플릿을 복제한 페이지를 통합(integration)에 공유했는지 확인해 주세요.")
        return found

    def query_all(self, ds_id, body=None):
        body, out = dict(body or {}), []
        while True:
            res = self.request("POST", f"/data_sources/{ds_id}/query", body)
            out += res.get("results", [])
            if not res.get("has_more"):
                return out
            body["start_cursor"] = res["next_cursor"]

    def create_page(self, ds_id, properties):
        return self.request("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": ds_id}, "properties": properties})


def _plain(prop):
    if not prop:
        return ""
    if prop.get("type") == "select" or "select" in prop:
        return (prop.get("select") or {}).get("name", "")
    items = prop.get("rich_text") or prop.get("title") or []
    return "".join(t.get("plain_text", "") for t in items)


def existing_by_key(client, ds_id):
    """{원본키: 노션 페이지}. 원본키가 빈 페이지(사용자가 직접 넣은 행)는 건드리지 않으므로 뺀다."""
    out = {}
    for page in client.query_all(ds_id):
        key = _plain(page.get("properties", {}).get("원본키"))
        if key:
            out[key] = page
    return out


def push_transactions(client, ds_id, rows, dry_run=False):
    """rows: [(원본키, properties)]. 노션에 없는 원본키만 새로 만든다. 돌려주는 값: (새로 만든 수, 이미 있어 건너뛴 수)."""
    have = existing_by_key(client, ds_id)
    created = skipped = 0
    for key, props in rows:
        if key in have:
            skipped += 1
            continue
        if not dry_run:
            client.create_page(ds_id, props)
        created += 1
    return created, skipped


def pull_corrections(client, ds_id, ours):
    """사용자가 노션에서 고친 카테고리·구분을 찾는다. ours: {원본키: (우리가 넣은 카테고리, 우리가 넣은 구분)}.
    돌려주는 값: [(원본키, 가맹점, 고친 카테고리 또는 None, 고친 구분 또는 None)]."""
    out = []
    for key, page in existing_by_key(client, ds_id).items():
        if key not in ours:
            continue
        p = page.get("properties", {})
        cat, kind = _plain(p.get("카테고리")), _plain(p.get("구분"))
        our_cat, our_kind = ours[key]
        if cat != our_cat or kind != our_kind:
            out.append((key, _plain(p.get("이름")), cat if cat != our_cat else None, kind if kind != our_kind else None))
    return out
