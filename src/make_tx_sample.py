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

ROOT = Path(__file__).resolve().parents[1]
ALERTS = str(ROOT / "data" / "alerts")
REF = str(ROOT / "data" / "reference")

FILES = ["r01.parquet", "r02.parquet", "r03.parquet", "r04.parquet"]
OUT = f"{ALERTS}/tx_sample.parquet"
OUT_PROFILE = f"{ALERTS}/account_profile.parquet"


def collect_targets():
    """알림의 근거 거래 ID와 대상 계좌 수집"""
    txn_ids, accounts = set(), set()
    for fname in FILES:
        p = Path(f"{ALERTS}/{fname}")
        if not p.exists():
            print(f"  건너뜀 (없음): {fname}")
            continue
        df = pd.read_parquet(p)
        for ids in df["txn_ids"]:
            txn_ids.update(json.loads(ids))
        accounts.update(df["account_id"])
        print(f"  {fname}: 알림 {len(df):,}건 → 누적 거래 ID {len(txn_ids):,}개 "
              f"/ 계좌 {len(accounts):,}개")
    return txn_ids, accounts


def build_profile(tx, accounts):
    """알림 계좌의 평소 거래 프로파일

    STR 종합의견의 '변동된 차이점'은 알림 구간을 평소 거래유형과 비교해
    기술해야 한다. 비교에 필요한 것은 집계값뿐이므로 원본 거래를 싣지 않고
    계좌별 요약만 만든다 — 전체 이력을 담으면 20MB지만 요약은 280KB다.

    계좌는 송신·수신 양쪽에 나타나므로 두 방향을 각각 한 행으로 펼친 뒤
    집계한다.
    """
    cols = ["from_account", "to_account", "amount", "ts"]
    sent = tx[cols].rename(columns={"from_account": "account_id",
                                    "to_account": "cp"})
    recv = tx[["to_account", "from_account", "amount", "ts"]].rename(
        columns={"to_account": "account_id", "from_account": "cp"})
    long = pd.concat([sent, recv], ignore_index=True)
    long = long[long["account_id"].isin(accounts)]

    prof = long.groupby("account_id").agg(
        txn_total=("amount", "size"),
        amount_total=("amount", "sum"),
        cp_total=("cp", "nunique"),
        first_ts=("ts", "min"),
        last_ts=("ts", "max"),
    ).reset_index()
    print(f"계좌 프로파일: {len(prof):,}개 계좌")
    return prof


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
    txn_ids, accounts = collect_targets()
    if not txn_ids:
        raise SystemExit("알림이 없습니다 — src/rules/ 실행이 선행돼야 합니다")

    tx = pd.read_parquet(full_path)
    print(f"\n전체 원장: {len(tx):,}건")

    sample = tx[tx["txn_id"].isin(txn_ids)]
    print(f"추출: {len(sample):,}건 ({len(sample)/len(tx):.1%})")

    verify(sample, txn_ids)

    profile = build_profile(tx, accounts)
    profile.to_parquet(OUT_PROFILE, index=False, compression="zstd")
    prof_kb = Path(OUT_PROFILE).stat().st_size / 1024
    print(f"→ {OUT_PROFILE} ({prof_kb:.0f} KB)")

    # zstd — 전체 컬럼을 유지하면서 snappy 대비 약 27% 작다
    sample.to_parquet(OUT, index=False, compression="zstd")
    size_mb = Path(OUT).stat().st_size / 1_048_576
    print(f"\n→ {OUT} ({size_mb:.2f} MB)")
