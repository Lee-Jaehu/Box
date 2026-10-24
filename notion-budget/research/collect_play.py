"""Google Play 리뷰 원문 수집 (별점·날짜·버전·개발사 답변 포함).

usage: python collect_play.py [--max 5000] [--only key1,key2]
"""
import argparse
import time

from google_play_scraper import Sort, reviews

from common import load_config, raw_path, write_csv

FIELDS = ["reviewId", "app_key", "app_id", "userName", "score", "content", "thumbsUpCount",
          "reviewCreatedVersion", "appVersion", "at", "replyContent", "repliedAt"]


def collect(app_id, max_count):
    rows, token = [], None
    while len(rows) < max_count:
        batch, token = reviews(app_id, lang="ko", country="kr", sort=Sort.NEWEST,
                               count=min(200, max_count - len(rows)), continuation_token=token)
        if not batch:
            break
        rows.extend(batch)
        if token is None or token.token is None:
            break
        time.sleep(1)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=5000)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = set(filter(None, args.only.split(",")))
    for app in load_config()["apps"]:
        if (only and app["key"] not in only) or not app["play_id"]:
            continue
        rows = collect(app["play_id"], args.max)
        for r in rows:
            r["app_key"], r["app_id"] = app["key"], app["play_id"]
        write_csv(raw_path("play", app["key"]), rows, FIELDS)


if __name__ == "__main__":
    main()
