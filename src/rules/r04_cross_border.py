"""R-04 국경 간 고액거래

국경을 넘는 거래는 강화된 고객확인(EDD) 대상이며,
자금 출처 추적이 어려워 자금세탁 경로로 이용된다.

근거: 업무규정상 강화된 고객확인 대상 거래

설계 경위
  - 원안은 FATF 고위험 관할권 거래 탐지였으나, 본 데이터의 국가
    구성이 전부 주요국이어서 탐지 대상이 0건. 국경 간 거래로 전환.
  - 상대국 분산 조건(min_countries)은 진단 결과 계좌당 상대국이
    예외 없이 1개국으로 나타나 변별 조건으로 성립하지 않아 제외.
  - 베이스라인과 룰의 집계 단위를 (계좌 × 창)으로 통일. 단위가
    다르면 감축률이 의미를 잃는다.
"""
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alerts import make_alert, finalize, summarize   # noqa: E402

REF = "data/reference"


def baseline(tx, threshold, window_days):
    """무튜닝 — 국경 간이면서 기준액 이상인 거래 전부

    R-04와 동일한 집계 단위(계좌 × 창)를 사용해
    R-04가 베이스라인의 부분집합이 되도록 한다.
    """
    hit = tx[tx["is_cross_border"] & (tx["amount"] >= threshold)].copy()
    hit["win"] = hit["ts"].dt.floor(f"{window_days}D")
    print(f"베이스라인 대상 거래: {len(hit):,}건")

    alerts = []
    for (acct, win), g in hit.groupby(["from_account", "win"]):
        alerts.append(make_alert(
            "BASE-04", acct, g,
            {"rule": "국경간 + 기준액 이상",
             "threshold": threshold,
             "window_days": window_days,
             "txn_count": len(g)},
        ))
    return finalize(alerts)


def cross_border(tx, p):
    """
      ① 국경 간 거래
      ② 금액 >= 기준액                  EDD 대상
      ③ 창 내 건수 >= min_txns          반복성

    조건 ④(상대국 분산)는 제외 — 데이터상 계좌당 상대국이
    항상 1개국이어서 변별력이 없음을 진단으로 확인함.
    """
    sub = tx[tx["is_cross_border"] &
             (tx["amount"] >= p["amount_threshold_usd"])].copy()
    sub["win"] = sub["ts"].dt.floor(f"{p['window_days']}D")

    alerts = []
    for (acct, win), g in sub.groupby(["from_account", "win"]):
        if len(g) < p["min_txns"]:
            continue
        alerts.append(make_alert(
            "R-04", acct, g,
            {"window_days": p["window_days"],
             "threshold": p["amount_threshold_usd"],
             "min_txns": p["min_txns"],
             "txn_count": len(g),
             "n_countries": int(g["to_country"].nunique()),
             "countries": sorted(g["to_country"].unique().tolist()),
             "total_amount": round(g["amount"].sum(), 2),
             "avg_amount": round(g["amount"].mean(), 2)},
        ))
    return finalize(alerts)


if __name__ == "__main__":
    cfg = yaml.safe_load(open("config/thresholds.yaml"))
    p = cfg["r04_cross_border"]
    TH = p["amount_threshold_usd"]
    WIN = p["window_days"]

    tx = pd.read_parquet(f"{REF}/transactions.parquet")
    usd = tx[tx["currency"] == "US Dollar"]
    print(f"USD 거래 {len(usd):,}건 / 진성 {usd['is_laundering'].sum():,}건")
    print(f"  국경 간: {usd['is_cross_border'].sum():,}건\n")

    print("=" * 62)
    print(f"베이스라인 — 국경간 + 기준액 이상 (무튜닝, {WIN}일 창)")
    print("=" * 62)
    base = baseline(usd, TH, WIN)
    summarize(base, "BASE-04")

    print("\n" + "=" * 62)
    print("R-04 — 국경 간 고액거래")
    print("=" * 62)
    r04 = cross_border(usd, p)
    summarize(r04, "R-04")

    if len(base):
        b_tp = int(base["is_true_positive"].sum())
        r_tp = int(r04["is_true_positive"].sum()) if len(r04) else 0
        print(f"\n알림 감축: {len(base):,} → {len(r04):,} "
              f"({1 - len(r04)/len(base):.1%})")
        print(f"진성 유지: {b_tp:,} → {r_tp:,} "
              f"({r_tp/b_tp:.1%})" if b_tp else "")

    Path("data/alerts").mkdir(parents=True, exist_ok=True)
    base.to_parquet("data/alerts/baseline_r04.parquet", index=False)
    r04.to_parquet("data/alerts/r04.parquet", index=False)
    print("\n→ data/alerts/ 저장")

    if len(r04):
        print("\n샘플 3건:")
        print(r04[["account_id", "txn_count", "total_amount",
                   "is_true_positive"]].head(3).to_string())