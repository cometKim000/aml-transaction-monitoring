"""STR(의심거래보고서) 초안 자동생성

FIU 「특정 금융거래정보 보고 및 감독규정」 별지 제1호 서식 항목에 맞춰
알림 하나를 STR 초안으로 변환한다.

근거: 특금법 제4조 / 시행령 제7조
보고 기한: 의심거래 결정 시점부터 3영업일 이내 (2021.3.25 개정 반영)

주의: 이 초안은 시스템이 자동 생성한 것으로, 최종 제출 전 반드시
보고책임자의 검토·보완을 거쳐야 한다. 특히 "의심스러운 합당한 근거"는
시스템이 채운 정량적 근거에 담당자의 정성적 판단을 추가해야 한다.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

REF = "data/reference"
ALERTS = "data/alerts"

# ④항 거래 표에 싣는 최대 행 수 (초과분은 건수만 표기하고 생략)
MAX_TABLE_ROWS = 100

RULE_LABELS = {
    "R-01": "분할입금(Structuring) — 고액현금거래보고 회피 의심",
    "R-02": "자금통과계좌(Mule Account) — 자금이동경로 은닉 의심",
    "R-03": "순환거래(Cycle) — 자금출처 은닉 의심",
    "R-04": "국경간 고액거래 — 강화된 고객확인(EDD) 대상",
}

RULE_BASIS = {
    "R-01": "특정금융정보법 제4조의2 / 동법 시행령 제8조의2 제1항",
    "R-02": "특정 금융거래정보 보고 및 감독규정 (의심거래 유형 - 자금이동경로 은닉)",
    "R-03": "특정 금융거래정보 보고 및 감독규정 (의심거래 유형 - 자금출처 은닉)",
    "R-04": "특정금융정보법 제5조의2 제1항 제2호 (강화된 고객확인)",
}


def load_account_txns(tx, account_id, txn_ids):
    """알림 근거 거래 상세 조회"""
    return tx[tx["txn_id"].isin(txn_ids)].sort_values("ts")


def format_evidence(rule_id, evidence):
    """룰별 evidence를 사람이 읽는 문장으로 변환"""
    if rule_id == "R-01":
        return (
            f"관찰 기간({evidence.get('window_days')}일) 내 개별 거래는 전부 "
            f"기준액(${evidence.get('threshold'):,}) 미만이었으나, 근접거래"
            f"(기준액의 {evidence.get('near_ratio', 0)*100:.0f}% 이상) "
            f"{evidence.get('near_count')}건이 발생하여 합산액이 기준액을 "
            f"초과함(합산 ${evidence.get('sum_amount', 0):,.2f})."
        )
    if rule_id == "R-02":
        return (
            f"{evidence.get('window_hours')}시간 이내 서로 다른 "
            f"{evidence.get('in_parties')}개 계좌로부터 자금이 집중 유입"
            f"(${evidence.get('in_amount', 0):,.2f})된 직후, 서로 다른 "
            f"{evidence.get('out_parties')}개 계좌로 자금이 분산 유출"
            f"(${evidence.get('out_amount', 0):,.2f})됨. "
            f"유출/유입 비율 {evidence.get('pass_ratio', 0):.2f}."
        )
    if rule_id == "R-03":
        path = evidence.get("path", "")
        return (
            f"자금이 {evidence.get('cycle_length')}개 계좌를 거쳐 "
            f"최초 계좌로 회귀하는 순환 경로가 확인됨 (경로: {path}). "
            f"경로상 거래금액은 ${evidence.get('amount_min', 0):,.2f}~"
            f"${evidence.get('amount_max', 0):,.2f} 범위로 유사하며, "
            f"{evidence.get('duration_days', 0):.1f}일 이내 완료됨. "
            f"동일 계좌가 관여한 유사 순환 {evidence.get('n_cycles', 1)}건 확인."
        )
    if rule_id == "R-04":
        countries = ", ".join(evidence.get("countries", []))
        return (
            f"관찰 기간({evidence.get('window_days')}일) 내 국경 간 고액거래 "
            f"{evidence.get('txn_count')}건 발생 (합산 "
            f"${evidence.get('total_amount', 0):,.2f}, 평균 "
            f"${evidence.get('avg_amount', 0):,.2f}). 거래 상대국: {countries}."
        )
    return json.dumps(evidence, ensure_ascii=False)


def generate_str(account_id, rule_id, alert_row, tx):
    """단일 알림 → STR 초안 (마크다운)"""
    evidence = json.loads(alert_row["evidence"])
    txn_ids = json.loads(alert_row["txn_ids"])
    txns = load_account_txns(tx, account_id, txn_ids)

    decided_at = datetime.now()
    deadline = decided_at + timedelta(days=3)  # 3영업일 근사(주말 미반영)

    lines = []
    lines.append(f"# 의심거래보고서(STR) 초안")
    lines.append(f"")
    lines.append(f"> **자동생성 초안 — 보고책임자 검토 전 제출 금지**")
    lines.append(f"> 생성 시각: {decided_at:%Y-%m-%d %H:%M} "
                f"/ 보고기한: {deadline:%Y-%m-%d} (결정일로부터 3영업일 이내)")
    lines.append(f"")
    lines.append(f"근거 법령: 특정금융정보법 제4조 / 동법 시행령 제7조")
    lines.append(f"")

    lines.append("## ① 보고기관")
    lines.append("")
    lines.append("| 항목 | 내용 |")
    lines.append("|---|---|")
    lines.append("| 보고기관 | [기관명 기입] |")
    lines.append("| 보고책임자 | [담당자 기입] |")
    lines.append("| 탐지 시스템 | AML Transaction Monitoring System |")
    lines.append("")

    lines.append("## ② 거래자")
    lines.append("")
    lines.append("| 항목 | 내용 |")
    lines.append("|---|---|")
    lines.append(f"| 계좌번호 | {account_id} |")
    lines.append("| 성명/상호 | [명의인 정보 기입 — 원장 계좌정보 연동 필요] |")
    lines.append("")

    lines.append("## ③ 거래채널")
    lines.append("")
    fmts = txns["fmt"].value_counts()
    lines.append("| 결제형식 | 건수 |")
    lines.append("|---|---:|")
    for fmt, cnt in fmts.items():
        lines.append(f"| {fmt} | {cnt} |")
    lines.append("")

    lines.append("## ④ 의심스러운 거래내용")
    lines.append("")
    lines.append(f"탐지 유형: **{RULE_LABELS.get(rule_id, rule_id)}**")
    lines.append("")
    # R-03(순환거래)은 경로 순서로, 그 외 룰은 시간순으로 정렬
    ordered_txns = txns
    if rule_id == "R-03":
        cycle = evidence.get("cycle_path_full") or []
        if cycle:
            pos = {acct: i for i, acct in enumerate(cycle)}
            ordered_txns = txns.copy()
            ordered_txns["_hop"] = ordered_txns["from_account"].map(pos)
            ordered_txns = ordered_txns.sort_values(
                "_hop", na_position="last").drop(columns="_hop")
            lines.append(f"*아래 거래는 시간순이 아닌 순환 경로 순서로 "
                        f"정렬되어 있습니다 ({len(cycle)}개 계좌 순환).*")
            lines.append("")

    # 자금통과계좌는 근거 거래가 수만 건에 이르는 경우가 있다(최대 82,841건).
    # 전량을 표로 펼치면 문서가 수 MB로 불어나 사람이 읽을 수 없고 화면도
    # 멈추므로, 표는 상한까지만 싣고 누락 사실을 명시한다. 전체 내역은
    # ⑥항의 알림 판정 로그(evidence)에 보존된다.
    shown = ordered_txns.head(MAX_TABLE_ROWS)
    omitted = len(ordered_txns) - len(shown)
    if omitted > 0:
        lines.append(f"*근거 거래 {len(ordered_txns):,}건 중 {len(shown):,}건만 "
                    f"표로 싣습니다 (나머지 {omitted:,}건은 ⑥항 판정 로그 참조). "
                    f"아래 합계는 생략분을 포함한 전체 기준입니다.*")
        lines.append("")

    lines.append("| 순번 | 일시 | 송신계좌 | 수신계좌 | 금액 | 통화 | 형식 |")
    lines.append("|---:|---|---|---|---:|---|---|")
    for i, r in enumerate(shown.itertuples(), 1):
        lines.append(f"| {i} | {r.ts:%Y-%m-%d %H:%M} | {r.from_account} | "
                    f"{r.to_account} | {r.amount:,.2f} | "
                    f"{r.currency} | {r.fmt} |")
    if omitted > 0:
        lines.append(f"| … | *이하 {omitted:,}건 생략* | | | | | |")
    lines.append("")
    lines.append(f"거래 건수: {len(txns):,}건 / "
                f"합산 금액: {txns['amount'].sum():,.2f}")
    lines.append("")

    lines.append("## ⑤ 의심스러운 합당한 근거")
    lines.append("")
    lines.append(f"**적용 규정**: {RULE_BASIS.get(rule_id, '')}")
    lines.append("")
    lines.append(f"**시스템 판정 근거**: {format_evidence(rule_id, evidence)}")
    lines.append("")
    lines.append("**담당자 검토 의견**: [보고책임자가 정성적 판단을 추가 기입]")
    lines.append("")

    lines.append("## ⑥ 보존자료의 종류")
    lines.append("")
    lines.append(f"- 거래 원장 상세 내역 전체 {len(txns):,}건 "
                f"(본 문서 ④항에는 최대 {MAX_TABLE_ROWS}건까지 발췌)")
    lines.append("- 탐지 룰 판정 로그 (`data/alerts/` evidence — 근거 거래 ID 전량)")
    lines.append("- 계좌 실명확인 자료 [금융회사 보유분 별도 첨부]")
    lines.append("")

    lines.append("---")
    lines.append(f"*본 초안은 {rule_id} 탐지 결과를 기반으로 자동 생성되었으며, "
                f"실제 제출 전 보고책임자의 검토·서명이 필요합니다.*")

    return "\n".join(lines)


if __name__ == "__main__":
    rule_id = sys.argv[1] if len(sys.argv) > 1 else "R-03"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    fname = {"R-01": "r01.parquet", "R-02": "r02.parquet",
            "R-03": "r03.parquet", "R-04": "r04.parquet"}[rule_id]

    alerts = pd.read_parquet(f"{ALERTS}/{fname}")
    alerts = alerts[alerts["is_true_positive"]].sort_values(
        "total_amount", ascending=False).head(n)

    tx = pd.read_parquet(f"{REF}/transactions.parquet")

    out_dir = Path("data/str_drafts")
    out_dir.mkdir(parents=True, exist_ok=True)

    for _, row in alerts.iterrows():
        doc = generate_str(row["account_id"], rule_id, row, tx)
        fpath = out_dir / f"STR_{rule_id}_{row['account_id']}.md"
        fpath.write_text(doc, encoding="utf-8")
        print(f"→ {fpath}")

    print(f"\n{len(alerts)}건 생성 완료 (rule={rule_id})")