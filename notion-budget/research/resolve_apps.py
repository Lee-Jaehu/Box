"""apps.json에 적힌 스토어 ID가 실제 앱을 가리키는지 확인한다(이름·개발사·리뷰 수 출력).

usage: python resolve_apps.py
"""
import time

from google_play_scraper import app as play_app

from common import get_json, load_config


def main():
    for a in load_config()["apps"]:
        print(f"\n## {a['name']} ({a['key']})")
        if a["play_id"]:
            try:
                d = play_app(a["play_id"], lang="ko", country="kr")
                print(f"  play  {a['play_id']:<36} {d['title']} / {d['developer']} / reviews={d['reviews']}")
            except Exception as e:
                print(f"  play  {a['play_id']:<36} ERROR {e!r}")
        if a["ios_id"]:
            time.sleep(3)  # iTunes API는 빠르게 연속 호출하면 403을 준다
            try:
                r = get_json("https://itunes.apple.com/lookup", {"id": a["ios_id"], "country": "kr"})["results"][0]
                print(f"  ios   {a['ios_id']:<36} {r['trackName']} / {r.get('artistName')} / ratings={r.get('userRatingCount')}")
            except Exception as e:
                print(f"  ios   {a['ios_id']:<36} ERROR {e!r}")


if __name__ == "__main__":
    main()
