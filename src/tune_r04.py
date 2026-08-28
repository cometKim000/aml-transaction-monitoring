"""6단계-4: R-04 기준액 민감도 실험

기준액을 5천/1만/2만으로 바꿔가며 알림·진성 변화를 측정한다.
창 크기도 함께 스윕한다. 베이스라인과 룰이 동일하므로
(조건 추가 없음이 확정안) 기준액 자체가 유일한 파라미터다.
"""
import pandas as pd

REF = "data/reference"

tx = pd.read_parquet(f"{REF}/transactions.parquet")
usd = tx[tx["currency"] == "US Dollar"]
cb = usd[usd["is_cross_border"]]
print(f"USD 국경간 거래 {len(cb):,}건 / 진성 {cb['is_laundering'].sum():,}건\n")

rows = []
for th in [5_000, 10_000, 20_000]:
    for win in [1, 7, 14]:
        sub = cb[cb["amount"] >= th].copy()
        sub["win"] = sub["ts"].dt.floor(f"{win}D")
        g = sub.groupby(["from_account", "win"])["is_laundering"].max()
        n = len(g)
        tp = int(g.sum())
        rows.append({
            "threshold": th, "window_days": win,
            "alerts": n, "tp": tp,
            "precision": tp / n if n else 0,
        })
        print(f"  기준액 {th:>6,} / 창 {win:>2}일: "
              f"알림 {n:>5,} / 진성 {tp:>3,} / 정밀도 {tp/n if n else 0:.2%}")

res = pd.DataFrame(rows)
res.to_csv("docs/r04_tuning.csv", index=False)

print("\n기준액별 요약 (7일 창 기준)")
d = res[res["window_days"] == 7]
for _, r in d.iterrows():
    print(f"  {int(r['threshold']):>6,}: 알림 {r['alerts']:,} / "
          f"진성 {r['tp']:,} / 정밀도 {r['precision']:.2%}")

print("\n→ docs/r04_tuning.csv 저장")