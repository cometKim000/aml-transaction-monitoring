import pandas as pd

tx = pd.read_parquet("data/reference/transactions.parquet")
key = ["ts", "from_bank", "from_account", "to_bank", "to_account"]

d = tx.duplicated(subset=key, keep=False)
print(f"원장에서 키 중복 거래: {d.sum():,}건")
print(f"영향받는 키 조합: {tx[d].groupby(key).ngroups:,}개\n")

if d.sum():
    g = tx[d].groupby(key).size().sort_values(ascending=False)
    print("중복 상위 5:")
    print(g.head().to_string())
    sample = g.index[0]
    m = (tx["ts"] == sample[0]) & (tx["from_account"] == sample[2]) & \
        (tx["to_account"] == sample[4])
    print("\n샘플 상세:")
    print(tx[m][["txn_id", "ts", "from_account", "to_account",
                 "amount", "currency", "fmt", "is_laundering"]].to_string())
                 