"""6단계-3: R-03 파라미터 민감도 실험

특히 max_duration_days는 '임계값 회피' 문제와 직결된다.
기간을 늘리면 얼마나 더 잡고 오탐이 얼마나 느는지 측정한다.
"""
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules.r03_circular import (build_graph, prune, find_cycles,  # noqa: E402
                                validate, to_alerts)

REF = "data/reference"

cfg = yaml.safe_load(open("config/thresholds.yaml"))
base_p = cfg["r03_circular"]

tx = pd.read_parquet(f"{REF}/transactions.parquet")
pat = pd.read_parquet(f"{REF}/pattern_accounts.parquet")
truth = set(pat[pat["pattern_type"] == "CYCLE"]["account_id"])

print(f"거래 {len(tx):,}건 / 정답 계좌 {len(truth):,}개")
print(f"기준 설정: {base_p}\n")

GRID = {
    "max_duration_days": [7, 14, 30, 60],
    "amount_tolerance": [0.2, 0.5, 0.8],
    "max_len": [4, 6, 8, 10],
    "min_amount": [1000, 5000, 20000],
}

rows = []
for param, values in GRID.items():
    print(f"\n{'=' * 64}")
    print(f"{param} 스윕  (기준값 {base_p[param]})")
    print("=" * 64)

    for v in values:
        p = dict(base_p)
        p[param] = v

        t0 = time.time()
        G = build_graph(tx, p["min_amount"])
        G = prune(G.copy())
        if G.number_of_nodes() == 0:
            print(f"  {param}={v}: 노드 0개 — 건너뜀")
            continue
        cycles = find_cycles(G, p)
        valid = validate(G, cycles, p)
        r = to_alerts(tx, valid)
        elapsed = time.time() - t0

        got = set(r["account_id"]) if len(r) else set()
        hit = len(got & truth)
        recall = hit / len(truth)
        prec = hit / len(got) if got else 0

        rows.append({
            "param": param, "value": v,
            "cycles_raw": len(cycles),
            "cycles_valid": len(valid),
            "alerts": len(r),
            "tp": hit,
            "recall": recall,
            "precision": prec,
            "sec": round(elapsed, 1),
        })
        print(f"  → {param}={v}: 순환 {len(valid):,} / 알림 {len(r):,} / "
              f"재현율 {recall:.1%} / 정밀도 {prec:.1%} [{elapsed:.0f}초]")

res = pd.DataFrame(rows)
res.to_csv("docs/r03_tuning.csv", index=False)

print("\n" + "=" * 78)
print("전체 결과")
print("=" * 78)
print(res.to_string(index=False, formatters={
    "cycles_raw": "{:,}".format,
    "cycles_valid": "{:,}".format,
    "alerts": "{:,}".format,
    "recall": "{:.1%}".format,
    "precision": "{:.1%}".format,
}))

# 회피 시나리오 해석
print("\n" + "=" * 78)
print("임계값 회피 분석 — max_duration_days")
print("=" * 78)
d = res[res["param"] == "max_duration_days"].sort_values("value")
prev = None
for _, r in d.iterrows():
    delta = f"(+{r['tp'] - prev:,})" if prev is not None else ""
    print(f"  {int(r['value']):>3}일: 진성 {r['tp']:>4,} {delta:>8}  "
          f"알림 {r['alerts']:>6,}  정밀도 {r['precision']:.1%}")
    prev = r["tp"]

print("\n→ docs/r03_tuning.csv 저장")