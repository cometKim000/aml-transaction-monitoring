"""R-01 분할입금 (Structuring)

CTR 보고 회피를 목적으로 기준액 미만으로 쪼개 입금하는 패턴.
근거: 특금법 제4조의2 / 시행령 제8조의2 제1항 (고액현금거래보고)

베이스라인: 1거래일 합산액이 법정 기준액 이상 (법정 기준 그대로)
R-01      : 위 조건 + 회피 의도 지표 3종 결합
"""
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alerts import make_alert, finalize, summarize   # noqa: E402

REF = "data/reference"


def load_config():
    with open("config/thresholds.yaml") as f:
        return yaml.safe_load(f)


def baseline(tx, threshold, window_days=1):
    """CTR 법정 기준 — 1거래일 합산액이 기준액 이상이면 보고 대상

    시행령 제8조의2 제1항: 동일인 명의로 1거래일 동안
    합산 1천만원 이상 현금 입금 또는 출금
    """
    sub = tx.copy()
    sub["day"] = sub["ts"].dt.floor(f"{window_days}D")

    alerts = []
    for (acct, day), g in sub.groupby(["to_account", "day"]):
        if g["amount"].sum() < threshold:
            continue
        alerts.append(make_alert(
            "BASE-01", acct, g,
            {"rule": "CTR 1거래일 합산 기준액 이상",
             "threshold": threshold,
             "window_days": window_days,
             "sum_amount": round(g["amount"].sum(), 2),
             "txn_count": len(g),
             "max_single": round(g["amount"].max(), 2)},
        ))
    return finalize(alerts)


def structuring(tx, threshold, window_days, min_count, near_ratio):
    """분할입금 탐지 — 베이스라인의 부분집합

      ① 창 내 합산액 >= 기준액                 베이스라인과 동일
      ② 개별 거래액 < 기준액                    보고 회피 (단건 보고 회피)
      ③ 건수 >= min_count                      반복성
      ④ 개별 거래액 >= 기준액 * near_ratio      기준액 근접 (의도성)
    """
    sub = tx.copy()
    sub["day"] = sub["ts"].dt.floor(f"{window_days}D")

    alerts = []
    for (acct, day), g in sub.groupby(["to_account", "day"]):
        if g["amount"].sum() < threshold:           # ①
            continue
        if (g["amount"] >= threshold).any():        # ② 단건 초과가 있으면 회피가 아님
            continue
        near = g[g["amount"] >= threshold * near_ratio]   # ④
        if len(near) < min_count:                   # ③
            continue
        alerts.append(make_alert(
            "R-01", acct, g,
            {"window_days": window_days,
             "threshold": threshold,
             "near_ratio": near_ratio,
             "min_count": min_count,
             "txn_count": len(g),
             "near_count": len(near),
             "sum_amount": round(g["amount"].sum(), 2),
             "max_single": round(g["amount"].max(), 2)},
        ))
    return finalize(alerts)


if __name__ == "__main__":
    cfg = load_config()
    THRESHOLD = cfg["ctr"]["threshold_usd"]
    p = cfg["r01_structuring"]

    tx = pd.read_parquet(f"{REF}/cash_usd.parquet")
    print(f"USD 현금거래 {len(tx):,}건 / 진성 {tx['is_laundering'].sum():,}건\n")

    print("=" * 62)
    print("베이스라인 — CTR 법정 기준 (1거래일 합산)")
    print("=" * 62)
    base = baseline(tx, THRESHOLD, window_days=cfg["ctr"]["window_days"])
    summarize(base, "BASE-01")

    print("\n" + "=" * 62)
    print("R-01 — 분할입금 탐지")
    print("=" * 62)
    r01 = structuring(tx, THRESHOLD,
                      window_days=p["window_days"],
                      min_count=p["min_count"],
                      near_ratio=p["near_ratio"])
    summarize(r01, "R-01")

    if len(base):
        keep = (r01["is_true_positive"].sum() /
                base["is_true_positive"].sum()) if base["is_true_positive"].sum() else 0
        print(f"\n알림 감축: {len(base):,} → {len(r01):,} "
              f"({1 - len(r01)/len(base):.1%})")
        print(f"진성 유지율: {keep:.1%}")

    Path("data/alerts").mkdir(parents=True, exist_ok=True)
    base.to_parquet("data/alerts/baseline_r01.parquet", index=False)
    r01.to_parquet("data/alerts/r01.parquet", index=False)
    print("\n→ data/alerts/ 저장")

    if len(r01):
        print("\n샘플 3건:")
        print(r01[["account_id", "txn_count", "total_amount",
                   "is_true_positive"]].head(3).to_string())