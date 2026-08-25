"""알림 스키마 및 생성 인터페이스 — 모든 룰이 이 형식으로 출력"""
import json
import pandas as pd

ALERT_COLUMNS = [
    "alert_id",        # 전역 유일 (룰별 생성 후 부여)
    "rule_id",         # R-01 ~ R-04
    "account_id",      # 알림 대상 계좌
    "detected_ts",     # 탐지 기준 시각 (관련 거래 중 최종)
    "txn_ids",         # 근거 거래 ID 리스트 (JSON 문자열)
    "txn_count",       # 근거 거래 건수
    "total_amount",    # 근거 거래 금액 합
    "currency",        # 통화 (혼재 시 'MIXED')
    "evidence",        # 룰별 상세 근거 (JSON 문자열)
    "is_true_positive",  # 근거 거래에 진성 포함 여부 (평가용)
]


def make_alert(rule_id, account_id, txns, evidence):
    """
    txns : 근거 거래 DataFrame (transactions.parquet의 부분집합)
    evidence : dict — 룰이 판단한 근거 (임계값, 계산값 등)
    """
    cur = txns["currency"].unique()
    return {
        "alert_id": None,
        "rule_id": rule_id,
        "account_id": account_id,
        "detected_ts": txns["ts"].max(),
        "txn_ids": json.dumps(txns["txn_id"].tolist()),
        "txn_count": len(txns),
        "total_amount": float(txns["amount"].sum()),
        "currency": cur[0] if len(cur) == 1 else "MIXED",
        "evidence": json.dumps(evidence, default=str),
        "is_true_positive": bool(txns["is_laundering"].any()),
    }


def finalize(alerts, start_id=1):
    """알림 리스트 → DataFrame + alert_id 부여"""
    if not alerts:
        return pd.DataFrame(columns=ALERT_COLUMNS)
    df = pd.DataFrame(alerts)
    df["alert_id"] = range(start_id, start_id + len(df))
    return df[ALERT_COLUMNS]


def summarize(df, rule_id=None):
    """룰 성과 요약 출력"""
    tag = rule_id or "ALL"
    n = len(df)
    if n == 0:
        print(f"[{tag}] 알림 0건")
        return
    tp = df["is_true_positive"].sum()
    print(f"[{tag}] 알림 {n:,}건 / 진성포함 {tp:,}건 "
          f"/ 정밀도 {tp/n:.2%}")
