"""배포용 거래 샘플 추출

전체 거래 원장(448만 건 / 119MB)은 용량 때문에 리포지토리에 포함하지
않으므로, Streamlit Cloud 등 원격 배포 환경에는 존재하지 않는다.
알림 evidence의 txn_ids에 등장하는 거래만 추출해 경량 샘플을 만든다.

app.py의 load_transactions()는 전체 원장이 없으면 이 파일로 대체하며,
알림 근거 거래가 전량 포함되므로 ③ 알림 상세·④ STR 생성은 동일하게
작동한다.

주의: 룰을 재실행해 알림이 바뀌면 이 스크립트도 다시 돌려야 한다.
      샘플이 낡으면 배포 환경에서만 근거 거래가 비어 보인다.
"""
import json
from pathlib import Path

import pandas as pd

ALERTS = "data/alerts"
REF = "data/reference"

FILES = ["r01.parquet", "r02.parquet", "r03.parquet", "r04.parquet"]
OUT = f"{ALERTS}/tx_sample.parquet"


def collect_txn_ids():
    """알림에 근거로 쓰인 고유 거래 ID 수집"""
    txn_ids = set()
    for fname in FILES:
        p = Path(f"{ALERTS}/{fname}")
        if not p.exists():
            print(f"  건너뜀 (없음): {fname}")
            continue
        df = pd.read_parquet(p)
        for ids in df["txn_ids"]:
            txn_ids.update(json.loads(ids))
        print(f"  {fname}: 알림 {len(df):,}건 → 누적 거래 ID {len(txn_ids):,}개")
    return txn_ids


def verify(sample, txn_ids):
    """모든 알림의 근거 거래가 샘플에 포함됐는지 확인

    하나라도 빠지면 배포 환경의 ③번 화면에서 해당 알림의 거래 내역이
    비어 보이므로, 저장 전에 막는다.
    """
    missing = txn_ids - set(sample["txn_id"])
    if missing:
        raise SystemExit(
            f"근거 거래 {len(missing):,}건이 원장에 없습니다. "
            f"원장과 알림의 생성 시점이 어긋났는지 확인하십시오."
        )
    print(f"검증: 알림 근거 거래 {len(txn_ids):,}건 전량 포함")


if __name__ == "__main__":
    full_path = Path(f"{REF}/transactions.parquet")
    if not full_path.exists():
        raise SystemExit(
            f"{full_path} 없음 — 이 스크립트는 전체 원장이 있는 로컬에서만 "
            f"실행할 수 있습니다. src/prepare.py를 먼저 수행하십시오."
        )

    print("알림 근거 거래 ID 수집")
    txn_ids = collect_txn_ids()
    if not txn_ids:
        raise SystemExit("알림이 없습니다 — src/rules/ 실행이 선행돼야 합니다")

    tx = pd.read_parquet(full_path)
    print(f"\n전체 원장: {len(tx):,}건")

    sample = tx[tx["txn_id"].isin(txn_ids)]
    print(f"추출: {len(sample):,}건 ({len(sample)/len(tx):.1%})")

    verify(sample, txn_ids)

    # zstd — 전체 컬럼을 유지하면서 snappy 대비 약 27% 작다
    sample.to_parquet(OUT, index=False, compression="zstd")
    size_mb = Path(OUT).stat().st_size / 1_048_576
    print(f"\n→ {OUT} ({size_mb:.2f} MB)")
