"""6단계-1: 룰별 기여도 분석

4개 룰의 알림을 통합해 점유율·정밀도·중복도를 산출한다.
실무 룰 튜닝의 첫 단계 — 어떤 룰이 오탐 공장인지,
어떤 룰이 고유 탐지를 하는지 파악한다.
"""
import pandas as pd

ALERTS = "data/alerts"
REF = "data/reference"

FILES = {
    "R-01": "r01.parquet",
    "R-02": "r02.parquet",
    "R-03": "r03.parquet",
    "R-04": "r04.parquet",
}
BASE = {
    "BASE-01": "baseline_r01.parquet",
    "BASE-04": "baseline_r04.parquet",
}

# 룰별 정답셋 (정답 라벨이 있는 룰만)
R02_PAT = ["STACK", "FAN-IN", "GATHER-SCATTER", "SCATTER-GATHER"]
pat = pd.read_parquet(f"{REF}/pattern_accounts.parquet")
TRUTH = {
    "R-02": set(pat[pat["pattern_type"].isin(R02_PAT)]["account_id"]),
    "R-03": set(pat[pat["pattern_type"] == "CYCLE"]["account_id"]),
}

tx = pd.read_parquet(f"{REF}/transactions.parquet")
BASE_RATE = tx["is_laundering"].mean()
print(f"전체 거래 {len(tx):,}건 / 기저율 {BASE_RATE:.4%}\n")

# ===== 1. 룰별 기본 지표 =====
loaded = {}
rows = []

for tag, f in {**BASE, **FILES}.items():
    try:
        d = pd.read_parquet(f"{ALERTS}/{f}")
    except FileNotFoundError:
        print(f"  {tag}: 파일 없음 — 건너뜀")
        continue
    loaded[tag] = d
    n = len(d)
    tp = int(d["is_true_positive"].sum())
    rows.append({
        "룰": tag,
        "알림": n,
        "진성포함": tp,
        "정밀도": tp / n if n else 0,
        "기저율대비": (tp / n) / BASE_RATE if n else 0,
        "고유계좌": d["account_id"].nunique(),
    })

summary = pd.DataFrame(rows)
print("=" * 72)
print("룰별 기본 지표")
print("=" * 72)
print(summary.to_string(index=False, formatters={
    "알림": "{:,}".format,
    "진성포함": "{:,}".format,
    "정밀도": "{:.2%}".format,
    "기저율대비": "{:.0f}배".format,
    "고유계좌": "{:,}".format,
}))

# ===== 2. 룰 단위 알림 점유율 =====
rule_only = {k: v for k, v in loaded.items() if k in FILES}
total = sum(len(v) for v in rule_only.values())
total_tp = sum(int(v["is_true_positive"].sum()) for v in rule_only.values())

print("\n" + "=" * 72)
print(f"알림 점유율 (룰 4종 합계 {total:,}건, 진성 {total_tp:,}건)")
print("=" * 72)
for tag, d in rule_only.items():
    n, tp = len(d), int(d["is_true_positive"].sum())
    print(f"  {tag}  알림 {n/total:6.1%}  진성 {tp/total_tp if total_tp else 0:6.1%}"
          f"   ({n:,}건 / {tp:,}건)")

# ===== 3. 재현율 (정답셋 있는 룰) =====
print("\n" + "=" * 72)
print("재현율 — 정답 라벨 보유 룰")
print("=" * 72)
for tag, truth in TRUTH.items():
    if tag not in loaded:
        continue
    got = set(loaded[tag]["account_id"])
    hit = len(got & truth)
    print(f"  {tag}  재현율 {hit/len(truth):6.1%} ({hit:,}/{len(truth):,})"
          f"   정밀도 {hit/len(got):6.1%} ({hit:,}/{len(got):,})")

# ===== 4. 룰 간 계좌 중복 =====
print("\n" + "=" * 72)
print("룰 간 계좌 중복 (교집합 크기)")
print("=" * 72)
keys = list(rule_only.keys())
sets = {k: set(v["account_id"]) for k, v in rule_only.items()}

hdr = "        " + "".join(f"{k:>10}" for k in keys)
print(hdr)
for a in keys:
    line = f"  {a:<6}"
    for b in keys:
        line += f"{len(sets[a] & sets[b]):>10,}"
    print(line)

# ===== 5. 고유 탐지 =====
print("\n" + "=" * 72)
print("고유 탐지 — 해당 룰만 잡은 계좌")
print("=" * 72)
for a in keys:
    others = set().union(*[sets[b] for b in keys if b != a]) if len(keys) > 1 else set()
    uniq = sets[a] - others
    d = loaded[a]
    uniq_tp = int(d[d["account_id"].isin(uniq)]["is_true_positive"].sum())
    print(f"  {a}  고유 {len(uniq):,}계좌 ({len(uniq)/len(sets[a]):.1%})"
          f"   그중 진성 {uniq_tp:,}건")

# ===== 6. 통합 알림 =====
print("\n" + "=" * 72)
print("통합 (중복 제거)")
print("=" * 72)
all_acc = set().union(*sets.values())
merged = pd.concat(list(rule_only.values()))
# 계좌 단위로 진성 여부 집계
acc_tp = merged.groupby("account_id")["is_true_positive"].any()
print(f"  고유 알림 계좌 {len(all_acc):,}개")
print(f"  그중 진성 포함 {int(acc_tp.sum()):,}개 ({acc_tp.mean():.2%})")
print(f"  단순 합산 대비 중복 제거: {total:,} → {len(all_acc):,}"
      f" ({1 - len(all_acc)/total:.1%} 감소)")

summary.to_csv("docs/rule_contribution.csv", index=False)
print("\n→ docs/rule_contribution.csv 저장")