"""R-01 조건별 통과 건수 진단"""
import pandas as pd
import yaml

cfg = yaml.safe_load(open("config/thresholds.yaml"))
TH = cfg["ctr"]["threshold_usd"]
p = cfg["r01_structuring"]

tx = pd.read_parquet("data/reference/cash_usd.parquet")
tx["day"] = tx["ts"].dt.floor("1D")

g = tx.groupby(["to_account", "day"])
agg = g.agg(n=("amount", "size"),
            total=("amount", "sum"),
            mx=("amount", "max")).reset_index()

print(f"전체 (계좌,일) 그룹: {len(agg):,}\n")

c1 = agg["total"] >= TH
print(f"① 합산 >= {TH:,}          : {c1.sum():,}")

c2 = c1 & (agg["mx"] < TH)
print(f"② + 단건 전부 기준액 미만  : {c2.sum():,}")

# 근접 거래 건수
near = tx[tx["amount"] >= TH * p["near_ratio"]]
nc = near.groupby(["to_account", "day"]).size().rename("near_n")
agg = agg.merge(nc, on=["to_account", "day"], how="left").fillna({"near_n": 0})

c3 = c2 & (agg["near_n"] >= p["min_count"])
print(f"③ + 근접거래 {p['min_count']}건 이상     : {c3.sum():,}")

print("\n--- ②까지 통과한 그룹의 분포 ---")
sub = agg[c2]
if len(sub):
    print("거래 건수:")
    print(sub["n"].value_counts().sort_index().head(10).to_string())
    print("\n근접거래 건수:")
    print(sub["near_n"].value_counts().sort_index().to_string())
else:
    print("없음")

print("\n--- 계좌당 일일 현금 거래 건수 전체 분포 ---")
print(agg["n"].value_counts().sort_index().head(10).to_string())