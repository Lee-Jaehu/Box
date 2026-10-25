"""labels_primary.jsonl + weights.jsonl로 codebook 6절 지표를 계산한다.

- 모든 비율은 층 가중치(weights.jsonl)로 모집단 비율을 복원한다.
- ODI: Imp = 주제 언급(가중치 × (1+ln(1+공감수))) 비율을 최댓값 10으로 스케일. 공감수를 그대로 곱하면 공감 수백 개짜리 리뷰 한 건이
  주제 순위를 바꿔서(2026-10-25 확인: 은행 T19, 전체 T18) 로그로 완화한다, Sat = 10·POS/(POS+NEG), Opp = Imp + max(Imp−Sat, 0)
- 선정 조건: Opp 상위 · NEG 리뷰가 2건 이상인 앱이 3개 이상 · 최근 6개월 NEG 비율이 직전 18개월보다 줄지 않음
- Kano: 관련 리뷰의 별점을 주제별 NEG·POS 더미로 가중 회귀(벌점-보상 대비 분석), 부트스트랩 95% 구간

usage:
  python analyze.py                # 결과를 data/work/analysis.json에 저장하고 표로 출력
  python analyze.py --group budget # 가계부 앱만 (bank: 은행·토스만)
"""
import argparse
import json
import math
from collections import defaultdict

import numpy as np

from classify import TOPICS, WORK

BUDGET_APPS = {"banksalad", "naver_moneybook", "pyeonhan", "ttokttok", "weple"}
RECENT_FROM, PRIOR_FROM = "2026-04-25", "2024-10-25"
MIN_NEG_PER_APP, MIN_APPS, KANO_MIN = 2, 3, 20
SEED = 20261025


def _load(group):
    items = {r["cid"]: r for r in map(json.loads, open(WORK / "items.jsonl", encoding="utf-8"))}
    weights = {r["cid"]: r["weight"] for r in map(json.loads, open(WORK / "weights.jsonl", encoding="utf-8"))}
    rows = []
    for lab in map(json.loads, open(WORK / "labels_primary.jsonl", encoding="utf-8")):
        it = items[lab["cid"]]
        if group == "budget" and it["app_key"] not in BUDGET_APPS or group == "bank" and it["app_key"] in BUDGET_APPS:
            continue
        rows.append({**it, **lab, "w": weights[lab["cid"]], "thumbs": int(it["thumbs"] or 0)})
    return rows


def _tw(r):
    return 1 + math.log1p(r["thumbs"])


def odi(rows):
    rel = [r for r in rows if r["relevant"] == "Y"]
    imp_raw, pos, neg, neg_apps = defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(lambda: defaultdict(int))
    total = sum(r["w"] * _tw(r) for r in rel)
    for r in rel:
        for t in {x["code"] for x in r["topics"]}:
            imp_raw[t] += r["w"] * _tw(r) / total
        for x in r["topics"]:
            if x["polarity"] == "POS":
                pos[x["code"]] += r["w"]
            elif x["polarity"] == "NEG":
                neg[x["code"]] += r["w"]
                neg_apps[x["code"]][r["app_key"]] += 1
    top = max(imp_raw.values())
    out = {}
    for t in TOPICS:
        if t not in imp_raw:
            continue
        imp = 10 * imp_raw[t] / top
        sat = 10 * pos[t] / (pos[t] + neg[t]) if pos[t] + neg[t] else float("nan")
        out[t] = {"share": imp_raw[t], "imp": imp, "sat": sat, "opp": imp + max(imp - (0 if sat != sat else sat), 0),
                  "n_reviews": sum(1 for r in rel if any(x["code"] == t for x in r["topics"])),
                  "neg_apps": sorted(a for a, n in neg_apps[t].items() if n >= MIN_NEG_PER_APP)}
    return out


def trend(rows):
    """주제별 NEG 언급 리뷰 비율(관련 리뷰 대비, 가중) — 최근 6개월 vs 직전 18개월."""
    per = {}
    for name, lo, hi in (("recent", RECENT_FROM, "9999"), ("prior", PRIOR_FROM, RECENT_FROM)):
        rel = [r for r in rows if r["relevant"] == "Y" and lo <= r["date"][:10] < hi]
        den = sum(r["w"] for r in rel)
        per[name] = {"n": len(rel), "rate": {t: sum(r["w"] for r in rel if any(x["code"] == t and x["polarity"] == "NEG" for x in r["topics"])) / den for t in TOPICS} if den else {}}
    return per


def kano(rows, n_boot=500):
    rel = [r for r in rows if r["relevant"] == "Y"]
    cols = []
    for t in TOPICS:
        for p in ("NEG", "POS"):
            if sum(any(x["code"] == t and x["polarity"] == p for x in r["topics"]) for r in rel) >= KANO_MIN:
                cols.append((t, p))
    X = np.array([[1.0] + [float(any(x["code"] == t and x["polarity"] == p for x in r["topics"])) for t, p in cols] for r in rel])
    y = np.array([float(r["score"]) for r in rel])
    w = np.array([r["w"] for r in rel])

    def fit(idx):
        sw = np.sqrt(w[idx])[:, None]
        return np.linalg.lstsq(X[idx] * sw, y[idx] * sw[:, 0], rcond=None)[0]

    beta = fit(np.arange(len(y)))
    rng = np.random.default_rng(SEED)
    boots = np.array([fit(rng.integers(0, len(y), len(y))) for _ in range(n_boot)])
    lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)
    res = {}
    for i, (t, p) in enumerate(cols, start=1):
        res.setdefault(t, {})[p] = {"coef": beta[i], "lo": lo[i], "hi": hi[i]}
    for t, d in res.items():
        pen = -d["NEG"]["coef"] if "NEG" in d and d["NEG"]["hi"] < 0 else 0.0  # 유의한 벌점만
        rew = d["POS"]["coef"] if "POS" in d and d["POS"]["lo"] > 0 else 0.0
        if pen and rew:
            d["kano"] = "Performance"
        elif pen:
            d["kano"] = "Must-be"
        elif rew:
            d["kano"] = "Attractive"
        else:
            d["kano"] = "Indifferent" if "NEG" in d and "POS" in d else "판정 보류(한쪽 표본 부족)"
    return {"n": len(y), "intercept": beta[0], "topics": res}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=["all", "budget", "bank"], default="all")
    args = ap.parse_args()
    rows = _load(args.group)
    n_rel = sum(r["w"] for r in rows if r["relevant"] == "Y") / sum(r["w"] for r in rows)
    o, tr, k = odi(rows), trend(rows), kano(rows)
    for t, d in o.items():
        rr, pr = tr["recent"]["rate"].get(t, 0), tr["prior"]["rate"].get(t, 0)
        d["neg_recent"], d["neg_prior"] = rr, pr
        d["not_declining"] = pr == 0 or rr >= pr
        d["kano"] = k["topics"].get(t, {}).get("kano", "-")
        d["selected"] = len(d["neg_apps"]) >= MIN_APPS and d["not_declining"]
    print(f"group={args.group} sampled={len(rows)} weighted relevant share={n_rel:.3f} | trend n recent={tr['recent']['n']} prior={tr['prior']['n']} | kano n={k['n']}")
    print(f"{'topic':5} {'n':>4} {'Imp':>5} {'Sat':>5} {'Opp':>5} {'NEG앱':>5} {'NEG최근':>7} {'NEG직전':>7} {'Kano':<12} 선정조건2·3")
    for t, d in sorted(o.items(), key=lambda kv: -kv[1]["opp"]):
        print(f"{t:5} {d['n_reviews']:4d} {d['imp']:5.1f} {d['sat']:5.1f} {d['opp']:5.1f} {len(d['neg_apps']):5d} {d['neg_recent']:7.3f} {d['neg_prior']:7.3f} {d['kano']:<12} {'O' if d['selected'] else '-'}")
    (WORK / f"analysis_{args.group}.json").write_text(json.dumps({"odi": o, "trend": tr, "kano": k}, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
