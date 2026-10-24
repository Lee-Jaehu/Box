"""App Store 리뷰 원문 수집 (공식 RSS).

제약: RSS는 앱당 최대 10페이지 x 50건 = 500건이며 개발사 답변을 포함하지 않는다.
usage: python collect_appstore.py [--only key1,key2]
"""
import argparse
import time

from common import get_json, load_config, raw_path, write_csv

FIELDS = ["reviewId", "app_key", "app_id", "author", "rating", "title", "content",
          "version", "updated", "voteSum", "voteCount"]


def label(entry, key):
    v = entry.get(key)
    return v.get("label") if isinstance(v, dict) else None


def collect(app_id):
    rows = []
    for page in range(1, 11):
        url = f"https://itunes.apple.com/kr/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
        entries = get_json(url).get("feed", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        # 첫 페이지 첫 항목이 앱 메타데이터인 경우가 있어 리뷰 필드가 있는 것만 받는다
        entries = [e for e in entries if "im:rating" in e]
        if not entries:
            break
        for e in entries:
            rows.append({
                "reviewId": label(e, "id"),
                "author": e.get("author", {}).get("name", {}).get("label"),
                "rating": label(e, "im:rating"),
                "title": label(e, "title"),
                "content": label(e, "content"),
                "version": label(e, "im:version"),
                "updated": label(e, "updated"),
                "voteSum": label(e, "im:voteSum"),
                "voteCount": label(e, "im:voteCount"),
            })
        time.sleep(3)  # 빠른 연속 호출 시 403
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = set(filter(None, args.only.split(",")))
    for app in load_config()["apps"]:
        if (only and app["key"] not in only) or not app["ios_id"]:
            continue
        rows = collect(app["ios_id"])
        for r in rows:
            r["app_key"], r["app_id"] = app["key"], app["ios_id"]
        write_csv(raw_path("appstore", app["key"]), rows, FIELDS)


if __name__ == "__main__":
    main()
