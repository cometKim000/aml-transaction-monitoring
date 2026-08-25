"""Patterns.txt → 패턴 유형별 거래 매핑

각 자금세탁 패턴 블록에 속한 거래를 식별해
룰별 재현율 측정의 정답셋으로 사용한다.
"""
import pandas as pd

RAW = "data/raw"
OUT = "data/reference"

rows = []
pattern_id = 0
current_type = None

with open(f"{RAW}/HI-Small_Patterns.txt", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        if line.startswith("BEGIN LAUNDERING ATTEMPT"):
            pattern_id += 1
            body = line.split("-", 1)[1] if "-" in line else line
            current_type = body.split(":")[0].strip()
            continue

        if line.startswith("END LAUNDERING ATTEMPT"):
            current_type = None
            continue

        if current_type is None:
            continue

        p = line.split(",")
        if len(p) < 11:
            continue
        rows.append({
            "pattern_id": pattern_id,
            "pattern_type": current_type,
            "ts": p[0],
            "from_bank": p[1],
            "from_account": p[2],
            "to_bank": p[3],
            "to_account": p[4],
            "amount": p[7],        # Amount Paid
            "currency": p[8],
            "fmt": p[9],
        })

pat = pd.DataFrame(rows)
pat["ts"] = pd.to_datetime(pat["ts"], format="%Y/%m/%d %H:%M")
pat["from_bank"] = pat["from_bank"].astype(int)
pat["to_bank"] = pat["to_bank"].astype(int)
pat["amount_key"] = pat["amount"].astype(float).round(2)

print(f"패턴 블록 {pattern_id}개 / 거래 {len(pat):,}건\n")
print("유형별 거래 수:")
print(pat.groupby("pattern_type").agg(
    blocks=("pattern_id", "nunique"),
    txns=("pattern_id", "size")).to_string())

# ===== 거래 원장과 매칭 =====
tx = pd.read_parquet(f"{OUT}/transactions.parquet")
tx["amount_key"] = tx["amount"].round(2)

KEY = ["ts", "from_bank", "from_account", "to_bank", "to_account",
       "amount_key", "currency", "fmt"]

# 패턴 쪽 중복 제거 (동일 거래가 여러 블록에 등장 가능)
pat_u = pat.drop_duplicates(subset=KEY, keep="first")
dropped = len(pat) - len(pat_u)
if dropped:
    print(f"\n패턴 내 동일 거래 중복 {dropped}건 제거")

merged = tx.merge(pat_u[KEY + ["pattern_id", "pattern_type"]],
                  on=KEY, how="inner")

print(f"\n원장과 매칭: {len(merged):,}건 / 패턴 거래 {len(pat_u):,}건 "
      f"(매칭률 {len(merged)/len(pat_u):.1%})")

bad = int((merged["is_laundering"] == 0).sum())
if bad:
    raise SystemExit(f"조인 오류: 라벨 0인 행 {bad}건 — 키 재검토 필요")
print("검증 통과: 매칭된 거래 전부 is_laundering=1")

dup = merged["txn_id"].duplicated().sum()
if dup:
    raise SystemExit(f"조인 오류: txn_id 중복 {dup}건")
print("검증 통과: txn_id 중복 없음")

# ===== 계좌 단위 정답셋 =====
acc_rows = []
for pt, g in merged.groupby("pattern_type"):
    for a in set(g["from_account"]) | set(g["to_account"]):
        acc_rows.append({"account_id": a, "pattern_type": pt})

pat_acc = pd.DataFrame(acc_rows).drop_duplicates()

print(f"\n패턴 관여 계좌: {pat_acc['account_id'].nunique():,}개")
print(pat_acc.groupby("pattern_type").size().to_string())

# R-02 목표 유형
R02 = ["STACK", "FAN-IN", "GATHER-SCATTER", "SCATTER-GATHER"]
r02_acc = pat_acc[pat_acc["pattern_type"].isin(R02)]["account_id"].nunique()
r03_acc = pat_acc[pat_acc["pattern_type"] == "CYCLE"]["account_id"].nunique()
print(f"\nR-02 정답 계좌(4개 유형): {r02_acc:,}개")
print(f"R-03 정답 계좌(CYCLE)   : {r03_acc:,}개")

merged[["txn_id", "pattern_id", "pattern_type"]].to_parquet(
    f"{OUT}/pattern_txns.parquet", index=False)
pat_acc.to_parquet(f"{OUT}/pattern_accounts.parquet", index=False)
print(f"\n→ {OUT}/pattern_txns.parquet, pattern_accounts.parquet 저장")