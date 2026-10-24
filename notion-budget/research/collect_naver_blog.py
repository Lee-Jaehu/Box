"""네이버 블로그 검색 API 수집.

제약: 검색 API는 본문이 아닌 요약(description)만 준다. 쿼리당 최대 1,000건(start<=1000).
--fetch-body를 주면 blog.naver.com 본문을 받는다. 단 robots.txt가 해당 경로를 허용할 때만 받고,
허용하지 않으면 본문 수집을 건너뛰고 그 사실을 출력한다.
usage: NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python collect_naver_blog.py [--per-query 1000] [--fetch-body]
"""
import argparse
import html
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser

from common import get_json, load_config, raw_path, write_csv

FIELDS = ["query", "sort", "title", "description", "link", "bloggername", "bloggerlink", "postdate", "body"]
TAG = re.compile(r"<[^>]+>")
UA = "Mozilla/5.0"
BLOG = re.compile(r"blog\.naver\.com/([^/?#]+)/(\d+)")


def robots_allows(url):
    rp = urllib.robotparser.RobotFileParser("https://blog.naver.com/robots.txt")
    rp.read()
    return rp.can_fetch(UA, url)


def fetch_body(link):
    m = BLOG.search(link)
    if not m:
        return None
    url = f"https://blog.naver.com/PostView.naver?blogId={m.group(1)}&logNo={m.group(2)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    # 스마트에디터 ONE 본문 영역. 구형 에디터 글은 비어 있을 수 있음
    main = page.split('class="se-main-container"', 1)
    if len(main) < 2:
        return None
    body = main[1].split('class="comment_area', 1)[0]
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", body, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", body))).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-query", type=int, default=1000)
    ap.add_argument("--fetch-body", action="store_true")
    args = ap.parse_args()
    headers = {"X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
               "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"]}
    rows, seen = [], set()
    for q in load_config()["naver_blog_queries"]:
        for sort in ("sim", "date"):
            for start in range(1, min(args.per_query, 1000) + 1, 100):
                res = get_json("https://openapi.naver.com/v1/search/blog.json",
                               {"query": q, "display": 100, "start": start, "sort": sort}, headers)
                items = res.get("items", [])
                for it in items:
                    if it["link"] in seen:
                        continue
                    seen.add(it["link"])
                    it.update(query=q, sort=sort, title=TAG.sub("", it["title"]),
                              description=TAG.sub("", it["description"]))
                    rows.append(it)
                if len(items) < 100:
                    break
                time.sleep(0.2)
    if args.fetch_body:
        sample = next((r["link"] for r in rows if BLOG.search(r["link"])), None)
        probe = None
        if sample:
            m = BLOG.search(sample)
            probe = f"https://blog.naver.com/PostView.naver?blogId={m.group(1)}&logNo={m.group(2)}"
        if probe and robots_allows(probe):
            for i, r in enumerate(rows):
                try:
                    r["body"] = fetch_body(r["link"])
                except Exception as e:
                    print(f"  body skip {r['link']}: {e!r}")
                if i % 100 == 0:
                    print(f"  body {i}/{len(rows)}")
                time.sleep(1)
        else:
            print("robots.txt가 블로그 본문 경로를 허용하지 않아 본문 수집을 건너뜀 (요약만 저장)")
    write_csv(raw_path("naver_blog", "search"), rows, FIELDS)


if __name__ == "__main__":
    main()
