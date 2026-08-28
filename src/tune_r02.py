"""6단계-2: R-02 파라미터 민감도 실험

알림의 91%를 차지하면서 진성은 52%만 포착하는 R-02를
파라미터별로 스윕해 트레이드오프 곡선을 산출한다.
"""
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules.r02_passthrough import passthrough, TARGET_PATTERNS  # noqa: E402

REF = "data/reference"

cfg = yaml.safe_load(open("config/thresholds.yaml"))
base_p = cfg["r02_passthrough"]

tx = pd.read_parquet(f"{REF}/transactions.parquet")
pat = pd.read_parquet(f"{REF}/pattern_accounts.parquet")
truth = set(pat[pat["pattern_type"].isin(TARGET_PATTERNS)]["account_id"])

print(f"거래 {len(tx):,}건 / 정답 계좌 {len(truth):,}개\n")

GRID = {
    "window_hours": [24, 48, 72, 120],
    "pass_ratio": [0.5, 0.7, 0.9],
    "min_in_parties": [2, 3, 5],
    "min_in": [3, 5, 8],
}

rows = []
for param, values in GRID.items():
    print(f"\n{'='*60}\n{param} 스윕\n{'='*60}")
    for v in values:
        p = dict(base_p)
        p[param] = v
        r = passthrough(tx, p)
        got = set(r["account_id"]) if len(r) else set()
        hit = len(got & truth)
        rows.append({
            "param": param, "value": v,
            "alerts": len(r),
            "recall": hit / len(truth),
            "precision": hit / len(got) if got else 0,
            "tp": hit,
        })
        print(f"  {param}={v}: 알림 {len(r):,} / "
              f"재현율 {hit/len(truth):.1%} / "
              f"정밀도 {hit/len(got) if got else 0:.1%}")

res = pd.DataFrame(rows)
res.to_csv("docs/r02_tuning.csv", index=False)

print("\n" + "=" * 72)
print("전체 결과")
print("=" * 72)
print(res.to_string(index=False, formatters={
    "alerts": "{:,}".format,
    "recall": "{:.1%}".format,
    "precision": "{:.1%}".format,
}))
print("\n→ docs/r02_tuning.csv 저장")