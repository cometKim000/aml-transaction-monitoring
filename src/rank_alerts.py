"""7단계: ML 알림 정렬

4개 룰의 알림을 하나의 풀로 모아 진성 확률을 예측하고,
상위 N%만 심사할 때 진성을 얼마나 잡는지 측정한다.

원칙: 룰은 탐지, 모델은 정렬만 한다. 새 계좌를 찾지 않고
이미 알림이 발생한 계좌의 우선순위만 매긴다 — 규제상
설명가능성 요건 때문에 탐지 자체를 모델에 맡기지 않는다.
"""
import json
from pathlib import Path

import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score

REF = "data/reference"
ALERTS = "data/alerts"

RULE_KEYS = {
    "r01": ["near_ratio", "near_count", "sum_amount", "max_single"],
    "r02": ["pass_ratio", "in_parties", "out_parties", "in_cnt", "out_cnt",
            "in_amount", "out_amount"],
    "r03": ["cycle_length", "n_cycles", "amount_min", "amount_max",
            "duration_days"],
    "r04": ["n_countries", "txn_count", "total_amount", "avg_amount"],
}
FILES = {"r01": "r01.parquet", "r02": "r02.parquet",
         "r03": "r03.parquet", "r04": "r04.parquet"}


def load_rule_features(tag, path, keys):
    """룰 알림을 계좌 단위로 집계해 피처화

    한 계좌가 같은 룰에서 여러 창(시간대)에 걸쳐 알림을 낼 수 있으므로
    (예: R-04는 계좌×7일창 단위), 계좌당 하나의 행으로 집계한다.
    """
    df = pd.read_parquet(f"{ALERTS}/{path}")
    if len(df) == 0:
        return pd.DataFrame(columns=["account_id", f"{tag}_flag"])

    ev = df["evidence"].apply(json.loads)
    for k in keys:
        df[f"{tag}_{k}"] = ev.apply(lambda e: e.get(k))
    df = df.rename(columns={"total_amount": f"{tag}_alert_amount",
                            "txn_count": f"{tag}_alert_txns"})

    num_cols = [c for c in df.columns if c.startswith(f"{tag}_")]
    g = df.groupby("account_id")[num_cols].max().reset_index()
    g[f"{tag}_flag"] = 1
    return g


def build_account_stats(tx, accounts):
    """계좌 전체 원장 통계 — 룰이 보지 않는 계좌 전반의 맥락"""
    sub = tx[tx["from_account"].isin(accounts) | tx["to_account"].isin(accounts)]

    rows = []
    for acct in accounts:
        m = (sub["from_account"] == acct) | (sub["to_account"] == acct)
        g = sub[m]
        if len(g) == 0:
            rows.append({"account_id": acct, "acct_total_txn": 0,
                        "acct_unique_cp": 0, "acct_total_amount": 0,
                        "acct_cross_border_ratio": 0, "acct_currency_count": 0})
            continue
        cp = pd.concat([
            g.loc[g["from_account"] == acct, "to_account"],
            g.loc[g["to_account"] == acct, "from_account"],
        ])
        rows.append({
            "account_id": acct,
            "acct_total_txn": len(g),
            "acct_unique_cp": cp.nunique(),
            "acct_total_amount": g["amount"].sum(),
            "acct_cross_border_ratio": g["is_cross_border"].mean(),
            "acct_currency_count": g["currency"].nunique(),
        })
    return pd.DataFrame(rows)


print("데이터 로딩...")
tx = pd.read_parquet(f"{REF}/transactions.parquet")
pat_acc = pd.read_parquet(f"{REF}/pattern_accounts.parquet")
truth_all = set(pat_acc["account_id"])   # 8개 유형 전체

# ===== 1. 룰 알림 피처 결합 =====
feat = None
for tag, fname in FILES.items():
    f = load_rule_features(tag, fname, RULE_KEYS[tag])
    feat = f if feat is None else feat.merge(f, on="account_id", how="outer")

flag_cols = [f"{t}_flag" for t in FILES]
feat[flag_cols] = feat[flag_cols].fillna(0)
feat["n_rules_fired"] = feat[flag_cols].sum(axis=1)

print(f"알림 계좌 {len(feat):,}개 (룰 4종 통합)")

# ===== 2. 계좌 전체 통계 =====
print("계좌 통계 계산 중...")
acct_stats = build_account_stats(tx, set(feat["account_id"]))
feat = feat.merge(acct_stats, on="account_id", how="left")

# ===== 3. 라벨 =====
feat["label"] = feat["account_id"].isin(truth_all).astype(int)
print(f"양성(진성) 비율: {feat['label'].mean():.2%} "
      f"({feat['label'].sum():,}/{len(feat):,})")

# ===== 4. 학습 =====
X = feat.drop(columns=["account_id", "label"])
y = feat["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=42, stratify=y)

model = lgb.LGBMClassifier(
    n_estimators=200, max_depth=4, learning_rate=0.05,
    random_state=42, verbose=-1,
)

# 5-fold 교차검증으로 안정성 확인 (작은 데이터셋이라 필수)
cv_auc = cross_val_score(model, X_train, y_train, cv=5, scoring="roc_auc")
print(f"\n교차검증 AUC: {cv_auc.mean():.3f} (±{cv_auc.std():.3f})")

model.fit(X_train, y_train)
proba = model.predict_proba(X_test)[:, 1]

# ===== 5. Precision@K / Recall@K =====
test = X_test.copy()
test["label"] = y_test.values
test["score"] = proba
test = test.sort_values("score", ascending=False).reset_index(drop=True)

base_precision = test["label"].mean()
print(f"\n테스트셋 기본 정밀도(정렬 안 함): {base_precision:.2%}")

print("\n상위 K% 심사 시 성능")
print(f"{'K%':>5} {'건수':>8} {'정밀도':>8} {'재현율':>8} {'기본 대비':>10}")
for k in [5, 10, 20, 30, 50, 100]:
    n = max(1, int(len(test) * k / 100))
    top = test.iloc[:n]
    prec = top["label"].mean()
    rec = top["label"].sum() / test["label"].sum()
    lift = prec / base_precision if base_precision else 0
    print(f"{k:>4}% {n:>8,} {prec:>7.1%} {rec:>7.1%} {lift:>9.1f}x")

# ===== 6. Feature Importance =====
imp = pd.DataFrame({
    "feature": X.columns,
    "importance": model.feature_importances_,
}).sort_values("importance", ascending=False).head(15)

plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False
plt.figure(figsize=(7, 5))
plt.barh(imp["feature"][::-1], imp["importance"][::-1], color="steelblue")
plt.title("알림 정렬 모델 — Feature Importance (상위 15)")
plt.xlabel("importance")
plt.tight_layout()
Path("docs/img").mkdir(parents=True, exist_ok=True)
plt.savefig("docs/img/ml_feature_importance.png", dpi=150)
print("\n→ docs/img/ml_feature_importance.png 저장")

print("\n상위 15개 피처:")
print(imp.to_string(index=False))

# ===== 7. 결과 저장 =====
result = feat[["account_id", "label"]].copy()
full_proba = model.predict_proba(X)[:, 1]
result["score"] = full_proba
result = result.sort_values("score", ascending=False)
result.to_parquet("data/alerts/ml_ranked.parquet", index=False)
print(f"\n→ data/alerts/ml_ranked.parquet 저장 ({len(result):,}건)")