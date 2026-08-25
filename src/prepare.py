"""1단계: 거래 원장 정제 + 계좌 국가 매핑 생성"""
import pandas as pd

RAW = "data/raw"
OUT = "data/reference"
CHUNK = 500_000

COUNTRIES = ["Portugal", "Canada", "UK", "Japan", "China", "France",
             "Germany", "Italy", "Spain", "India", "Russia", "Brazil",
             "Mexico", "Australia", "Switzerland", "Netherlands",
             "Belgium", "Austria"]

# ========== 1. 계좌 → 국가 매핑 ==========
acc = pd.read_csv(f"{RAW}/HI-Small_accounts.csv")


def to_country(name):
    for c in COUNTRIES:
        if name.startswith(c + " Bank"):
            return c
    return "US"          # 국가 접두어 없음 = 미국 지명 은행


def src_flag(name):
    return ("explicit" if any(name.startswith(c + " Bank") for c in COUNTRIES)
            else "inferred")


acc["country"] = acc["Bank Name"].apply(to_country)
acc["country_source"] = acc["Bank Name"].apply(src_flag)

print("국가 판정 근거:")
print(acc["country_source"].value_counts(normalize=True).round(4).to_string())

dup = len(acc) - acc["Account Number"].nunique()
USE_COMPOSITE = dup > 0
print(f"\n계좌 {len(acc):,}건 / 계좌번호 중복 {dup:,}건 "
      f"→ {'복합키(은행+계좌)' if USE_COMPOSITE else '단일키(계좌)'} 사용")

if USE_COMPOSITE:
    acc_map = acc.set_index(["Bank ID", "Account Number"])["country"].to_dict()
else:
    acc_map = acc.set_index("Account Number")["country"].to_dict()

acc[["Account Number", "Bank ID", "Bank Name",
     "country", "country_source"]].to_csv(f"{OUT}/account_country.csv",
                                          index=False)

# ========== 2. 거래 원장 정제 ==========
keep = []
n_raw = 0
n_self = 0

for i, ch in enumerate(pd.read_csv(f"{RAW}/HI-Small_Trans.csv",
                                   chunksize=CHUNK)):
    n_raw += len(ch)

    before = len(ch)
    ch = ch[ch["Account"] != ch["Account.1"]]      # 자기계좌 거래 제외
    n_self += before - len(ch)

    ch = ch.rename(columns={
        "Account": "from_account",
        "Account.1": "to_account",
        "From Bank": "from_bank",
        "To Bank": "to_bank",
        "Amount Paid": "amount",
        "Payment Currency": "currency",
        "Payment Format": "fmt",
        "Is Laundering": "is_laundering",
    })
    ch["ts"] = pd.to_datetime(ch["Timestamp"])

    keep.append(ch[["ts", "from_account", "to_account", "from_bank",
                    "to_bank", "amount", "currency", "fmt", "is_laundering"]])
    print(f"  청크 {i+1} 처리... 누적 {n_raw:,}행", end="\r")

tx = pd.concat(keep, ignore_index=True)
tx = tx.sort_values("ts").reset_index(drop=True)
tx["txn_id"] = range(1, len(tx) + 1)

# ========== 3. 국가 부착 ==========
if USE_COMPOSITE:
    tx["from_country"] = [acc_map.get((b, a)) for b, a
                          in zip(tx["from_bank"], tx["from_account"])]
    tx["to_country"] = [acc_map.get((b, a)) for b, a
                        in zip(tx["to_bank"], tx["to_account"])]
else:
    tx["from_country"] = tx["from_account"].map(acc_map)
    tx["to_country"] = tx["to_account"].map(acc_map)

miss_from = tx["from_country"].isna().sum()
miss_to = tx["to_country"].isna().sum()

# 국경 간 거래 여부 (R-04용)
tx["is_cross_border"] = (
    tx["from_country"].notna() & tx["to_country"].notna()
    & (tx["from_country"] != tx["to_country"])
)

# ========== 4. 결과 ==========
print(f"\n\n원본 {n_raw:,}행")
print(f"  자기계좌 제외 {n_self:,}건 ({n_self/n_raw:.2%})")
print(f"  정제 후 {len(tx):,}행")
print(f"  진성(is_laundering=1): {tx['is_laundering'].sum():,} "
      f"({tx['is_laundering'].mean():.4%})")
print(f"  기간: {tx['ts'].min()} ~ {tx['ts'].max()}")

print(f"\n국가 매핑 실패: 송신 {miss_from:,} / 수신 {miss_to:,}")

cb = tx["is_cross_border"]
print(f"\n국경 간 거래: {cb.sum():,} ({cb.mean():.2%})")
print(f"  그중 진성: {tx.loc[cb, 'is_laundering'].sum():,}")
print(f"  국내 거래 중 진성: {tx.loc[~cb, 'is_laundering'].sum():,}")

print("\n송신 국가 상위 10")
print(tx["from_country"].value_counts().head(10).to_string())

tx.to_parquet(f"{OUT}/transactions.parquet", index=False)
print(f"\n→ {OUT}/transactions.parquet ({len(tx):,}행)")

cash_usd = tx[(tx["fmt"] == "Cash") & (tx["currency"] == "US Dollar")]
cash_usd.to_parquet(f"{OUT}/cash_usd.parquet", index=False)
print(f"→ {OUT}/cash_usd.parquet ({len(cash_usd):,}행) — R-01용")
