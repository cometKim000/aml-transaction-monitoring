"""0단계-2: 전체 데이터 기준 재확인 (청크 처리)"""
import pandas as pd
from collections import Counter

PATH = "data/raw/HI-Small_Trans.csv"
CHUNK = 500_000

n_rows = 0
label_cnt = Counter()
fmt_cnt = Counter()
cur_cnt = Counter()
hour_cnt = Counter()
self_loop = 0
ts_min, ts_max = None, None

# Cash 거래만 별도 집계
cash_rows = []

for i, ch in enumerate(pd.read_csv(PATH, chunksize=CHUNK)):
    n_rows += len(ch)
    label_cnt.update(ch["Is Laundering"].value_counts().to_dict())
    fmt_cnt.update(ch["Payment Format"].value_counts().to_dict())
    cur_cnt.update(ch["Payment Currency"].value_counts().to_dict())

    ts = pd.to_datetime(ch["Timestamp"], errors="coerce")
    hour_cnt.update(ts.dt.hour.value_counts().to_dict())
    ts_min = ts.min() if ts_min is None else min(ts_min, ts.min())
    ts_max = ts.max() if ts_max is None else max(ts_max, ts.max())

    self_loop += (ch["Account"] == ch["Account.1"]).sum()

    c = ch[ch["Payment Format"] == "Cash"]
    if len(c):
        cash_rows.append(c)

    print(f"  chunk {i+1} 처리... 누적 {n_rows:,}행", end="\r")

print(f"\n\n총 행수: {n_rows:,}")
print(f"기간: {ts_min} ~ {ts_max}")

print("\n[라벨]")
tot = sum(label_cnt.values())
for k, v in sorted(label_cnt.items()):
    print(f"  {k}: {v:,} ({v/tot:.4%})")

print("\n[결제형식]")
for k, v in fmt_cnt.most_common():
    print(f"  {k}: {v:,} ({v/tot:.2%})")

print(f"\n[자기계좌 거래] {self_loop:,} ({self_loop/tot:.2%})")

print("\n[통화 상위 8]")
for k, v in cur_cnt.most_common(8):
    print(f"  {k}: {v:,} ({v/tot:.2%})")

print("\n[시간대 분포]  ★ R-05 성립 여부")
for h in range(24):
    v = hour_cnt.get(h, 0)
    bar = "█" * int(v / max(hour_cnt.values()) * 40)
    print(f"  {h:02d}시 {v:>9,} {bar}")

# ===== Cash 거래 상세 =====
cash = pd.concat(cash_rows, ignore_index=True)
print(f"\n\n===== Cash 거래 {len(cash):,}건 =====")
print("통화 분포:")
print(cash["Payment Currency"].value_counts().head(8).to_string())
print("\n라벨:", cash["Is Laundering"].value_counts().to_dict())

usd = cash[cash["Payment Currency"] == "US Dollar"]
print(f"\nUSD 현금거래 {len(usd):,}건 금액 분포:")
print(usd["Amount Paid"].describe())
print("\n1만 USD 이상:", (usd["Amount Paid"] >= 10_000).sum())
print("5천~1만 USD:", ((usd["Amount Paid"] >= 5_000) &
                        (usd["Amount Paid"] < 10_000)).sum())

cash.to_csv("data/reference/cash_transactions.csv", index=False)
print("\n→ data/reference/cash_transactions.csv 저장")

# ===== 은행명에서 국가 추출 가능성 =====
acc = pd.read_csv("data/raw/HI-Small_accounts.csv")
print(f"\n\n===== 계좌 {len(acc):,}건 =====")

COUNTRIES = ["Portugal", "Canada", "UK", "Japan", "China", "France",
             "Germany", "Italy", "Spain", "India", "Russia", "Brazil",
             "Mexico", "Australia", "Switzerland", "Netherlands",
             "Sweden", "Norway", "Denmark", "Korea", "Singapore",
             "Nigeria", "Saudi", "Turkey", "Poland", "Austria", "Belgium"]

def to_country(name):
    for c in COUNTRIES:
        if name.startswith(c + " Bank"):
            return c
    return "US(추정)"

acc["country"] = acc["Bank Name"].apply(to_country)
print("\n국가 추출 결과:")
print(acc["country"].value_counts().to_string())
print(f"\n미분류(US 추정) 비율: {(acc['country']=='US(추정)').mean():.2%}")