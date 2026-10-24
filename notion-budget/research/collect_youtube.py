"""YouTube Data API v3 댓글 원문 수집.

쿼터: search.list 1회 = 100 units, commentThreads.list 1회 = 1 unit (기본 일 10,000 units).
usage: YOUTUBE_API_KEY=... python collect_youtube.py [--videos-per-query 15] [--max-comments 1000]
"""
import argparse
import os

from common import get_json, load_config, raw_path, write_csv

API = "https://www.googleapis.com/youtube/v3"
FIELDS = ["commentId", "parentId", "query", "videoId", "videoTitle", "channelTitle", "videoPublishedAt",
          "author", "text", "likeCount", "publishedAt", "updatedAt"]


def search_videos(key, query, n):
    res = get_json(f"{API}/search", {"key": key, "part": "snippet", "q": query, "type": "video",
                                     "regionCode": "KR", "relevanceLanguage": "ko", "maxResults": n})
    return [(i["id"]["videoId"], i["snippet"]) for i in res.get("items", [])]


def comments(key, video_id, max_comments):
    rows, token = [], None
    while len(rows) < max_comments:
        params = {"key": key, "part": "snippet,replies", "videoId": video_id, "maxResults": 100,
                  "textFormat": "plainText", "order": "relevance"}
        if token:
            params["pageToken"] = token
        try:
            res = get_json(f"{API}/commentThreads", params)
        except Exception as e:  # 댓글 비활성 영상은 403
            print(f"  skip {video_id}: {e!r}")
            break
        for t in res.get("items", []):
            top = t["snippet"]["topLevelComment"]
            rows.append(_row(top, None))
            for rep in t.get("replies", {}).get("comments", []):
                rows.append(_row(rep, top["id"]))
        token = res.get("nextPageToken")
        if not token:
            break
    return rows


def _row(c, parent_id):
    s = c["snippet"]
    return {"commentId": c["id"], "parentId": parent_id, "author": s.get("authorDisplayName"),
            "text": s.get("textOriginal") or s.get("textDisplay"), "likeCount": s.get("likeCount"),
            "publishedAt": s.get("publishedAt"), "updatedAt": s.get("updatedAt")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos-per-query", type=int, default=15)
    ap.add_argument("--max-comments", type=int, default=1000)
    args = ap.parse_args()
    key = os.environ["YOUTUBE_API_KEY"]
    rows, seen = [], set()
    for q in load_config()["youtube_queries"]:
        for vid, snip in search_videos(key, q, args.videos_per_query):
            if vid in seen:
                continue
            seen.add(vid)
            for r in comments(key, vid, args.max_comments):
                r.update(query=q, videoId=vid, videoTitle=snip["title"], channelTitle=snip["channelTitle"],
                         videoPublishedAt=snip["publishedAt"])
                rows.append(r)
    write_csv(raw_path("youtube", "comments"), rows, FIELDS)


if __name__ == "__main__":
    main()
