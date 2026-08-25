"""R-02 자금 통과 계좌 (Pass-through / Mule Account)

여러 계좌로부터 자금이 집중 유입된 뒤, 짧은 시간 안에
또 다른 여러 계좌로 분산 유출되는 패턴.

근거: 업무규정상 의심거래 유형 (자금 이동 경로 은닉)
실무 참조: Fan-in → Fan-out 결합, 고속 정산(Velocity) 감시

대응 패턴: STACK, FAN-IN, GATHER-SCATTER, SCATTER-GATHER

집계 단위: 계좌 × 슬라이딩 윈도우(창)
  전 기간 합산은 국소적 세탁 신호를 평범한 거래 이력에 묻어버려
  변별력이 사라진다. 각 유입 거래를 창의 시작점으로 삼아
  창 단위로 판정한다.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alerts import make_alert, finalize, summarize   # noqa: E402

REF = "data/reference"
TARGET_PATTERNS = ["STACK", "FAN-IN", "GATHER-SCATTER", "SCATTER-GATHER"]


def select_candidates(tx, min_txns):
    """1차 필터 — 유입·유출이 모두 있고 거래가 일정 수 이상인 계좌"""
    in_acc = tx.groupby("to_account").size()
    out_acc = tx.groupby("from_account").size()
    both = in_acc.index.intersection(out_acc.index)
    total = in_acc.reindex(both).fillna(0) + out_acc.reindex(both).fillna(0)
    return set(total[total >= min_txns].index)


def scan_account(acc_in, acc_out, p):
    """한 계좌의 모든 창을 검사해 가장 강한 창 하나를 반환

    acc_in  : 이 계좌로 들어온 거래 (ts 정렬)
    acc_out : 이 계좌에서 나간 거래 (ts 정렬)
    """
    if len(acc_in) < p["min_in"] or len(acc_out) == 0:
        return None

    win = pd.Timedelta(hours=p["window_hours"])
    in_ts = acc_in["ts"].values
    out_ts = acc_out["ts"].values

    best = None
    n = len(acc_in)

    for i in range(n):
        start = in_ts[i]
        end = start + win.to_timedelta64()

        # 창 내 유입
        j = np.searchsorted(in_ts, end, side="right")
        if j - i < p["min_in"]:                      # ① 유입 건수
            continue
        w_in = acc_in.iloc[i:j]

        in_amt = w_in["amount"].sum()
        if in_amt < p["min_amount"]:
            continue
        if w_in["from_account"].nunique() < p["min_in_parties"]:   # ③
            continue

        # 창 내 유출 (첫 유입 이후 ~ 창 끝)
        a = np.searchsorted(out_ts, start, side="left")
        b = np.searchsorted(out_ts, end, side="right")
        if b - a == 0:
            continue
        w_out = acc_out.iloc[a:b]

        if w_out["to_account"].nunique() < p["min_out_parties"]:   # ④
            continue

        ratio = w_out["amount"].sum() / in_amt
        if ratio < p["pass_ratio"]:                                # ②
            continue

        # 강도 점수 — 상대방 분산도 × 통과율
        score = (w_in["from_account"].nunique()
                 * w_out["to_account"].nunique()
                 * min(ratio, 2.0))
        if best is None or score > best["score"]:
            best = {
                "score": score,
                "w_in": w_in,
                "w_out": w_out,
                "start": pd.Timestamp(start),
                "in_amt": in_amt,
                "out_amt": w_out["amount"].sum(),
                "ratio": ratio,
            }
    return best


def passthrough(tx, p):
    cands = select_candidates(tx, p["candidate_min_txns"])
    print(f"1차 후보 계좌: {len(cands):,}개")

    sub = tx[tx["to_account"].isin(cands) | tx["from_account"].isin(cands)]
    sub = sub.sort_values("ts")

    by_in = {k: v for k, v in sub.groupby("to_account") if k in cands}
    by_out = {k: v for k, v in sub.groupby("from_account") if k in cands}

    alerts = []
    for n, acct in enumerate(cands, 1):
        if n % 20000 == 0:
            print(f"  검사 중... {n:,}/{len(cands):,}", end="\r")

        acc_in = by_in.get(acct)
        acc_out = by_out.get(acct)
        if acc_in is None or acc_out is None:
            continue

        best = scan_account(acc_in, acc_out, p)
        if best is None:
            continue

        g = pd.concat([best["w_in"], best["w_out"]])
        alerts.append(make_alert(
            "R-02", acct, g,
            {"window_hours": p["window_hours"],
             "window_start": best["start"],
             "in_cnt": len(best["w_in"]),
             "out_cnt": len(best["w_out"]),
             "in_parties": int(best["w_in"]["from_account"].nunique()),
             "out_parties": int(best["w_out"]["to_account"].nunique()),
             "pass_ratio": round(best["ratio"], 3),
             "in_amount": round(best["in_amt"], 2),
             "out_amount": round(best["out_amt"], 2)},
        ))
    print(f"\n조건 통과 계좌: {len(alerts):,}개")
    return finalize(alerts)


def evaluate(alerts, truth_accounts, label):
    if not len(alerts):
        print(f"[{label}] 알림 0건")
        return
    got = set(alerts["account_id"])
    truth = set(truth_accounts)
    tp = len(got & truth)
    print(f"[{label}] 알림 {len(got):,}계좌 / 정답 {len(truth):,}계좌")
    print(f"  재현율 {tp/len(truth):.1%}  ({tp:,}/{len(truth):,})")
    print(f"  정밀도 {tp/len(got):.1%}  ({tp:,}/{len(got):,})")


if __name__ == "__main__":
    cfg = yaml.safe_load(open("config/thresholds.yaml"))
    p = cfg["r02_passthrough"]

    tx = pd.read_parquet(f"{REF}/transactions.parquet")
    print(f"거래 {len(tx):,}건\n")

    r02 = passthrough(tx, p)
    summarize(r02, "R-02")

    pat_acc = pd.read_parquet(f"{REF}/pattern_accounts.parquet")
    truth = pat_acc[pat_acc["pattern_type"].isin(TARGET_PATTERNS)]["account_id"]
    print()
    evaluate(r02, truth, "R-02")

    Path("data/alerts").mkdir(parents=True, exist_ok=True)
    r02.to_parquet("data/alerts/r02.parquet", index=False)
    print("\n→ data/alerts/r02.parquet 저장")