"""STR(의심거래보고서) 초안 자동생성

FIU 「특정 금융거래정보 보고 및 감독규정」 별지 제1호 서식 항목에 맞춰
알림 하나를 STR 초안으로 변환한다.

근거: 특금법 제4조 / 시행령 제7조
보고 기한: 의심거래 결정 시점부터 3영업일 이내 (2021.3.25 개정 반영)

종합의견 작성 원칙 (FIU 심사분석 사례 기준)
  육하원칙에 따라 기재하고, 명확한 보고 이유·창구 정황·명확한 고객 정보·
  관련인·송금자 정보·자금 출처·변동된 차이점·특이점을 포함한다.

주의: 이 초안은 시스템이 자동 생성한 것으로, 최종 제출 전 반드시
보고책임자의 검토·보완을 거쳐야 한다. 시스템이 채울 수 있는 것은 거래
원장에서 확인되는 사실뿐이며, 탐지 조건과 임계값을 옮겨 적은 서술만으로는
미흡 보고로 분류된다. 계좌주 정보·창구 정황·자금 출처·평소 거래유형과의
차이는 담당자가 기재해야 심사분석에 쓸 수 있는 보고서가 된다.
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


RULE_WHY = {
    "R-01": "고액현금거래보고(CTR) 기준액 미만으로 거래를 분할해 보고 의무를 "
            "회피한 정황으로, 자금세탁 3단계 중 예치(placement)에 해당한다.",
    "R-02": "단기간 집중 유입 직후 분산 유출되어 계좌가 자금의 실질 귀속처가 "
            "아닌 경유지로 이용된 정황으로, 자금 이동 경로 추적을 어렵게 한다.",
    "R-03": "자금이 여러 계좌를 순환해 최초 계좌로 회귀하여 자금의 출처를 "
            "가린 정황으로, 자금세탁 3단계 중 반복(layering)에 해당한다.",
    "R-04": "국경 간 고액거래로 강화된 고객확인(EDD) 대상에 해당하며, "
            "자금의 국외 이전을 통한 추적 회피 가능성을 검토해야 한다.",
}


def format_5w1h(rule_id, account_id, evidence, txns):
    """육하원칙 기재사항 표

    STR 종합의견은 육하원칙에 따라 기재하는 것이 원칙이다. 시스템은
    거래 원장에서 확인되는 사실(누가·언제·어디서·무엇을·어떻게)까지만
    채우고, 고객 진술과 정성적 판단이 필요한 부분은 담당자 몫으로 비워 둔다.
    """
    ts_min, ts_max = txns["ts"].min(), txns["ts"].max()
    span_days = (ts_max - ts_min).total_seconds() / 86400

    channels = ", ".join(f"{k}({v}건)" for k, v in
                        txns["fmt"].value_counts().items())

    where = f"거래채널 {channels}"
    if "from_bank" in txns.columns and "to_bank" in txns.columns:
        banks = pd.unique(pd.concat([txns["from_bank"], txns["to_bank"]]))
        where += f" / 관련 금융기관 {len(banks):,}개"
    if "is_cross_border" in txns.columns and txns["is_cross_border"].any():
        countries = pd.unique(pd.concat([txns["from_country"],
                                        txns["to_country"]]))
        where += f" / 관련국 {', '.join(map(str, countries))}"

    cur = txns["currency"].unique()
    cur_label = cur[0] if len(cur) == 1 else f"{len(cur)}종 혼재"

    rows = [
        ("누가 (Who)", f"계좌 {account_id} / 명의인 [원장 계좌정보 연동 후 기입]"),
        ("언제 (When)", f"{ts_min:%Y-%m-%d %H:%M} ~ {ts_max:%Y-%m-%d %H:%M} "
                       f"({span_days:.1f}일간)"),
        ("어디서 (Where)", where),
        ("무엇을 (What)", f"{len(txns):,}건 / 합산 {txns['amount'].sum():,.2f} "
                         f"{cur_label}"),
        ("어떻게 (How)", format_evidence(rule_id, evidence)),
        ("왜 (Why)", RULE_WHY.get(rule_id, "") +
                    " — 이는 시스템의 탐지 근거이며, 실제 보고 사유는 아래 "
                    "담당자 기재사항의 '명확한 보고 이유'에 서술해야 한다."),
    ]

    out = ["| 구분 | 내용 |", "|---|---|"]
    out += [f"| **{k}** | {v} |" for k, v in rows]
    return out


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

    lines.append("## ⑤ 의심스러운 합당한 근거 (종합의견)")
    lines.append("")
    lines.append(f"**적용 규정**: {RULE_BASIS.get(rule_id, '')}")
    lines.append("")
    lines.append("### 육하원칙 기재사항")
    lines.append("")
    lines += format_5w1h(rule_id, account_id, evidence, txns)
    lines.append("")
    lines.append("### 담당자 기재사항")
    lines.append("")
    lines.append("> 위 표는 거래 원장에서 확인되는 사실만 담고 있습니다. "
                "**탐지 조건과 임계값을 옮겨 적은 서술만으로는 미흡 보고**로 "
                "분류됩니다(예: \"다수 계좌를 통한 분할입금 및 지급이어서 "
                "보고함\" — 계좌주 정보와 창구 현장정보가 없어 심사분석에 "
                "도움이 되지 않은 사례). 아래 항목을 채워 "
                "심사분석관이 전제범죄 유형을 파악할 수 있게 하십시오.")
    lines.append("")
    lines.append("| 항목 | 기재사항 |")
    lines.append("|---|---|")
    for item, guide in [
        ("명확한 보고 이유",
         "이 거래를 의심하는 이유를 전제범죄 유형(횡령·조세포탈·사기 등)을 "
         "가늠할 수 있게 서술"),
        ("창구 정황",
         "내점 여부, 응대 시 고객 진술, 질문 회피·진술 번복·대리인 개입 등. "
         "창구 접촉이 없는 비대면 거래는 그 사실을 명시"),
        ("명확한 고객 정보",
         "명의인 성명·실명번호·직업·업종. 법인계좌면 대표자·실제 지시자와의 관계"),
        ("관련인",
         "거래상대방 중 가족·법인 임직원 등 관계인 및 그 관계"),
        ("송금자 정보",
         "전신송금이 포함된 경우 송금인·수취인 정보와 송금 목적"),
        ("자금 출처",
         "유입 자금의 원천(급여·매출·대출·타인 이체 등)과 확인 근거"),
        ("변동된 차이점",
         "알림 기간 전후의 거래내역 및 평소 거래유형과 비교해 무엇이 달라졌는지. "
         "알림 구간만 떼어 기술하면 미흡 보고로 분류됨"),
        ("특이점",
         "직업·소득 대비 거래규모 불일치, 과거 STR 보고 이력, 언론보도 등 "
         "분석에 유용한 정보"),
    ]:
        lines.append(f"| **{item}** | [{guide}] |")
    lines.append("")
    lines.append("### 담당자 종합의견")
    lines.append("")
    lines.append("[위 사실관계를 종합해 보고책임자가 의심 사유를 서술]")
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