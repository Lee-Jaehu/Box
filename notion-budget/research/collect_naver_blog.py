"""네이버 블로그 검색 API 수집.

제약: 검색 API는 본문이 아닌 요약(description)만 준다. 쿼리당 최대 1,000건(start<=1000).
본문 원문 수집(블로그 페이지 직접 요청)은 별도 결정 사항이라 이 스크립트는 하지 않는다.
usage: NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python collect_naver_blog.py [--per-query 1000]
"""
import argparse
import os
import re
import time

from common import get_json, load_config, raw_path, write_csv

FIELDS = ["query", "sort", "title", "description", "link", "bloggername", "bloggerlink", "postdate"]
TAG = re.compile(r"<[^>]+>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-query", type=int, default=1000)
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
    write_csv(raw_path("naver_blog", "search"), rows, FIELDS)


if __name__ == "__main__":
    main()
