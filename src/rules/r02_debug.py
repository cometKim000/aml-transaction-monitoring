"""R-02 조건별 정답 계좌 통과율 진단"""
import pandas as pd
import yaml
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rules.r02_passthrough import build_flows, TARGET_PATTERNS  # noqa

cfg = yaml.safe_load(open("config/thresholds.yaml"))
p = cfg["r02_passthrough"]

tx = pd.read_parquet("data/reference/transactions.parquet")
flows = build_flows(tx)

pat = pd.read_parquet("data/reference/pattern_accounts.parquet")
truth = set(pat[pat["pattern_type"].isin(TARGET_PATTERNS)]["account_id"])

flows["is_truth"] = flows["account_id"].isin(truth)
t = flows[flows["is_truth"]]
print(f"정답 계좌 {len(truth):,}개 중 유입·유출 모두 있는 계좌: {len(t):,}개\n")

conds = {
    f"① in_cnt >= {p['min_in']}": t["in_cnt"] >= p["min_in"],
    f"② pass_ratio >= {p['pass_ratio']}": t["pass_ratio"] >= p["pass_ratio"],
    f"③ in_parties >= {p['min_in_parties']}": t["in_parties"] >= p["min_in_parties"],
    f"④ out_parties >= {p['min_out_parties']}": t["out_parties"] >= p["min_out_parties"],
    f"⑤ lag <= {p['max_lag_hours']}h": t["lag_hours"] <= p["max_lag_hours"],
}
print("정답 계좌의 조건별 개별 통과율")
for k, v in conds.items():
    print(f"  {k:<28} {v.sum():>6,} / {len(t):,}  ({v.mean():.1%})")

print("\n정답 계좌 지표 분포 (중앙값 / 90퍼센타일)")
for c in ["in_cnt", "out_cnt", "in_parties", "out_parties",
          "pass_ratio", "lag_hours"]:
    print(f"  {c:<12} {t[c].median():>10.2f} {t[c].quantile(0.9):>12.2f}")

print("\n전체 계좌 지표 분포 (비교용)")
for c in ["in_cnt", "out_cnt", "in_parties", "out_parties",
          "pass_ratio", "lag_hours"]:
    print(f"  {c:<12} {flows[c].median():>10.2f} {flows[c].quantile(0.9):>12.2f}")