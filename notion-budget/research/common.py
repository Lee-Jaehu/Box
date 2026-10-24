"""수집 스크립트 공통 유틸. 원본은 notion-budget/data/raw/ 아래에 저장한다(.gitignore 대상)."""
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT.parent / "data" / "raw"


def load_config():
    with open(ROOT / "apps.json", encoding="utf-8") as f:
        return json.load(f)


def raw_path(source, key):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    d = RAW_DIR / source
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}_{stamp}.csv"


def write_csv(path, rows, fields):
    # utf-8-sig: 엑셀에서 바로 열어도 한글이 깨지지 않게
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    print(f"saved {len(rows)} rows -> {path}")


def get_json(url, params=None, headers=None, retries=4):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 404) or i == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if i == retries - 1:
                raise
        time.sleep(2 ** (i + 1))
