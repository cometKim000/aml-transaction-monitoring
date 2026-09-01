"""AML 거래모니터링 심사 화면

실행: streamlit run app.py
"""
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, "src")
from generate_str import (format_evidence, generate_str,   # noqa: E402
                          load_profile)

REF = "data/reference"
ALERTS = "data/alerts"

RULE_LABELS = {
    "R-01": "분할입금 (Structuring)",
    "R-02": "자금통과계좌 (Mule Account)",
    "R-03": "순환거래 (Cycle)",
    "R-04": "국경간 고액거래",
}

# 처음 보는 사람이 룰 이름만으로는 무엇을 잡는지 알 수 없다.
# 무엇을 탐지하는지 / 왜 의심스러운지 / 어떤 조문에 근거하는지를 함께 보여준다.
RULE_DESC = {
    "R-01": {
        "what": "하루 동안 여러 번에 나눠 입금해, 합치면 기준액을 넘지만 "
                "한 건씩은 기준액($10,000) 아래가 되도록 맞춘 계좌입니다.",
        "why": "금융회사는 기준액 이상 현금거래를 의무적으로 보고(CTR)해야 "
               "합니다. 기준액 바로 아래로 쪼개 넣으면 이 보고를 피할 수 있어, "
               "쪼갠 행위 자체가 의심 신호가 됩니다.",
        "basis": "특금법 제4조의2 / 시행령 제8조의2 제1항",
    },
    "R-02": {
        "what": "짧은 시간 안에 여러 계좌에서 돈이 몰려 들어온 직후, "
                "다시 여러 계좌로 흩어져 빠져나간 계좌입니다.",
        "why": "돈이 머무르지 않고 스쳐 지나갔다는 뜻으로, 계좌 주인이 실제 "
               "주인이 아니라 자금이 거쳐 가는 통로일 가능성이 큽니다. "
               "흔히 말하는 대포통장의 전형적인 형태입니다.",
        "basis": "업무규정상 의심거래 유형 (자금 이동 경로 은닉)",
    },
    "R-03": {
        "what": "A → B → C → ... → 다시 A 순으로 자금이 여러 계좌를 돌아 "
                "출발한 계좌로 되돌아온 경우입니다.",
        "why": "돈을 굳이 여러 계좌에 돌린 뒤 자기에게 되돌리는 것은 정상 "
               "거래에서 드뭅니다. 거쳐 간 계좌가 많을수록 자금의 출처를 "
               "추적하기 어려워지며, 자금세탁의 반복(layering) 단계에 해당합니다.",
        "basis": "업무규정상 의심거래 유형 (자금 출처 은닉)",
    },
    "R-04": {
        "what": "국경을 넘는 거래 중 금액이 기준액($10,000) 이상인 경우입니다.",
        "why": "자금이 국외로 나가면 국내 수사·조사 권한이 미치지 않아 추적이 "
               "어려워집니다. 이 때문에 강화된 고객확인(EDD) 대상으로 "
               "분류해 자금 원천과 거래 목적을 확인해야 합니다.",
        "basis": "특금법 제5조의2 제1항 제2호 (강화된 고객확인)",
    },
}


def rule_help(rule_id, expanded=False):
    """룰 하나의 설명 블록"""
    d = RULE_DESC.get(rule_id)
    if not d:
        return
    with st.expander(f"{rule_id} {RULE_LABELS.get(rule_id, '')} — 어떤 룰인가요?",
                     expanded=expanded):
        st.markdown(f"**무엇을 탐지하나요**  \n{d['what']}")
        st.markdown(f"**왜 의심스러운가요**  \n{d['why']}")
        st.caption(f"근거: {d['basis']}")

st.set_page_config(page_title="AML 거래모니터링", layout="wide")


@st.cache_data
def load_all_alerts():
    frames = []
    for rid, fname in [("R-01", "r01.parquet"), ("R-02", "r02.parquet"),
                       ("R-03", "r03.parquet"), ("R-04", "r04.parquet")]:
        p = Path(f"{ALERTS}/{fname}")
        if p.exists():
            df = pd.read_parquet(p)
            df["rule_id"] = rid
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


@st.cache_data
def load_ml_scores():
    p = Path(f"{ALERTS}/ml_ranked.parquet")
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_transactions():
    """배포 환경(전체 원장 없음)에서는 알림 연루 거래 샘플로 대체"""
    full_path = Path(f"{REF}/transactions.parquet")
    if full_path.exists():
        return pd.read_parquet(full_path)
    sample_path = Path(f"{ALERTS}/tx_sample.parquet")
    if sample_path.exists():
        return pd.read_parquet(sample_path)
    st.error("거래 원장 데이터를 찾을 수 없습니다.")
    st.stop()


@st.cache_data
def load_account_profile():
    """평소 거래 프로파일 (STR '변동된 차이점' 산출용)"""
    return load_profile()


@st.cache_data
def load_baselines():
    out = {}
    for tag, fname in [("BASE-01", "baseline_r01.parquet"),
                       ("BASE-04", "baseline_r04.parquet")]:
        p = Path(f"{ALERTS}/{fname}")
        if p.exists():
            out[tag] = pd.read_parquet(p)
    return out


alerts = load_all_alerts()
ml = load_ml_scores()
tx = load_transactions()
baselines = load_baselines()

if not ml.empty:
    alerts = alerts.merge(ml[["account_id", "score"]], on="account_id", how="left")
else:
    alerts["score"] = 0.0

st.sidebar.title("AML 거래모니터링")
page = st.sidebar.radio("화면", ["① 대시보드", "② 알림 리스트", "③ 알림 상세", "④ STR 생성"])

st.sidebar.divider()
with st.sidebar.expander("처음 오셨나요?"):
    st.markdown(
        "자금세탁이 의심되는 거래를 찾아내는 시스템입니다.\n\n"
        "**용어**\n"
        "- **알림**: 탐지 룰에 걸린 계좌 한 건\n"
        "- **진성**: 실제 자금세탁으로 확인된 건\n"
        "- **정밀도**: 알림 중 진성의 비율 (높을수록 헛수고가 적음)\n"
        "- **STR**: 의심거래보고서. 금융회사가 FIU에 제출하는 법정 서식\n\n"
        "**보는 순서**\n"
        "① 전체 현황 → ② 우선순위 높은 알림 고르기 → "
        "③ 근거 확인 → ④ 보고서 초안 만들기"
    )
with st.sidebar.expander("탐지 룰 4종"):
    for rid, d in RULE_DESC.items():
        st.markdown(f"**{rid} {RULE_LABELS[rid]}**  \n{d['what']}")

# =====================================================================
# ① 대시보드
# =====================================================================
if page == "① 대시보드":
    st.title("탐지 현황 대시보드")
    st.caption("탐지 룰 4종이 낸 알림의 전체 현황입니다. "
              "정밀도가 높을수록 심사 인력이 헛도는 일이 적습니다.")

    total_alerts = alerts["account_id"].nunique()
    total_tp = alerts.groupby("account_id")["is_true_positive"].any().sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("전체 알림 계좌", f"{total_alerts:,}")
    c2.metric("진성 포함", f"{int(total_tp):,}")
    c3.metric("전체 정밀도", f"{total_tp/total_alerts:.2%}" if total_alerts else "-")
    if "BASE-01" in baselines:
        base_n = len(baselines["BASE-01"])
        c4.metric("CTR 베이스라인 대비 감축", f"{1 - total_alerts/base_n:.1%}")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("룰별 알림 점유율")
        by_rule = alerts.groupby("rule_id")["account_id"].nunique().reset_index()
        by_rule["rule_label"] = by_rule["rule_id"].map(RULE_LABELS)
        fig = px.pie(by_rule, values="account_id", names="rule_label", hole=0.4)
        st.plotly_chart(fig, width="stretch")

    with col2:
        st.subheader("룰별 정밀도")
        prec = alerts.groupby("rule_id").agg(
            alerts=("account_id", "nunique"),
            tp=("is_true_positive", "sum"),
        ).reset_index()
        prec["precision"] = prec["tp"] / prec["alerts"]
        prec["rule_label"] = prec["rule_id"].map(RULE_LABELS)
        fig = px.bar(prec, x="rule_label", y="precision",
                    text=prec["precision"].apply(lambda x: f"{x:.1%}"))
        fig.update_layout(yaxis_tickformat=".0%")
        st.plotly_chart(fig, width="stretch")

    st.divider()
    st.subheader("베이스라인 대비 감축 효과")
    if "BASE-01" in baselines:
        r01 = alerts[alerts["rule_id"] == "R-01"]
        b1 = baselines["BASE-01"]
        comp = pd.DataFrame({
            "구분": ["베이스라인 (CTR)", "R-01 적용"],
            "알림": [len(b1), len(r01)],
            "진성": [int(b1["is_true_positive"].sum()),
                    int(r01["is_true_positive"].sum())],
        })
        st.dataframe(comp, width="stretch", hide_index=True)

# =====================================================================
# ② 알림 리스트
# =====================================================================
elif page == "② 알림 리스트":
    st.title("알림 리스트")
    st.caption("ML 우선순위 점수 기준 정렬. 상위 20%만 심사해도 진성의 79.2%를 포착합니다.")

    col1, col2, col3 = st.columns(3)
    with col1:
        rule_filter = st.multiselect("룰", options=list(RULE_LABELS.keys()),
                                     default=list(RULE_LABELS.keys()))
    with col2:
        only_tp_hint = st.checkbox("고위험(상위 20% 점수)만 보기", value=False)
    with col3:
        sort_desc = st.checkbox("점수 높은 순", value=True)

    for rid in rule_filter:
        rule_help(rid)

    view = alerts[alerts["rule_id"].isin(rule_filter)].copy()
    view = view.sort_values("score", ascending=not sort_desc)

    if only_tp_hint and len(view):
        cutoff = view["score"].quantile(0.8)
        view = view[view["score"] >= cutoff]

    view["rule_label"] = view["rule_id"].map(RULE_LABELS)
    show = view[["account_id", "rule_label", "score", "detected_ts",
                "txn_count", "total_amount"]].rename(columns={
        "account_id": "계좌", "rule_label": "탐지 룰", "score": "우선순위 점수",
        "detected_ts": "탐지 시각", "txn_count": "거래건수", "total_amount": "합산금액",
    })
    show["우선순위 점수"] = show["우선순위 점수"].round(3)

    st.write(f"총 {len(show):,}건")
    st.dataframe(show, width="stretch", hide_index=True, height=500)

    st.session_state.setdefault("selected_account", None)
    picked = st.selectbox("상세보기로 이동할 계좌 선택",
                          options=[""] + view["account_id"].tolist())
    if picked:
        st.session_state["selected_account"] = picked
        st.info(f"'③ 알림 상세'에서 {picked} 확인 가능")

# =====================================================================
# ③ 알림 상세
# =====================================================================
elif page == "③ 알림 상세":
    st.title("알림 상세")
    st.caption("이 계좌가 왜 걸렸는지, 근거가 된 거래가 무엇인지 확인하는 화면입니다.")

    default_acc = st.session_state.get("selected_account", "")
    acc_options = sorted(alerts["account_id"].unique().tolist())
    idx = acc_options.index(default_acc) if default_acc in acc_options else 0
    account_id = st.selectbox("계좌 선택", options=acc_options, index=idx)

    acc_alerts = alerts[alerts["account_id"] == account_id]

    st.subheader(f"계좌: {account_id}")
    c1, c2, c3 = st.columns(3)
    c1.metric("걸린 룰 수", acc_alerts["rule_id"].nunique())
    c2.metric("우선순위 점수", f"{acc_alerts['score'].max():.3f}")
    c3.metric("실제 진성 여부", "예" if acc_alerts["is_true_positive"].any() else "미상")
    st.caption("'진성'은 데이터에 자금세탁으로 라벨된 거래가 근거에 포함됐다는 "
              "뜻입니다. 평가용 지표이며 실무에서는 알 수 없는 값입니다.")

    for _, row in acc_alerts.iterrows():
        rid = row["rule_id"]
        with st.expander(f"{RULE_LABELS.get(rid, rid)} "
                        f"— 탐지 {row['detected_ts']}", expanded=True):
            ev = json.loads(row["evidence"])

            d = RULE_DESC.get(rid)
            if d:
                st.markdown(f"**어떤 룰인가요**  \n{d['what']}")
                st.markdown(f"**왜 의심스러운가요**  \n{d['why']}")

            st.markdown("**이 계좌의 판정 근거**")
            st.info(format_evidence(rid, ev))

            with st.popover("판정에 쓰인 원시 수치 (JSON)"):
                st.json(ev)

            st.markdown(f"**근거가 된 거래 내역** ({row['txn_count']:,}건)")
            txn_ids = json.loads(row["txn_ids"])
            detail = tx[tx["txn_id"].isin(txn_ids)].sort_values("ts")
            st.dataframe(
                detail[["ts", "from_account", "to_account", "amount",
                       "currency", "fmt"]],
                width="stretch", hide_index=True,
            )

            if row["rule_id"] == "R-03" and "cycle_path_full" in ev:
                st.write("**순환 경로 시각화**")
                path = ev["cycle_path_full"]
                fig = go.Figure(go.Scatter(
                    x=list(range(len(path) + 1)),
                    y=[0] * (len(path) + 1),
                    mode="markers+lines+text",
                    text=path + [path[0]],
                    textposition="top center",
                    marker=dict(size=14, color="crimson"),
                ))
                fig.update_layout(height=200, showlegend=False,
                                 xaxis_visible=False, yaxis_visible=False)
                st.plotly_chart(fig, width="stretch")

    st.divider()
    if st.button("이 계좌로 STR 초안 생성하기"):
        st.session_state["str_target"] = account_id
        st.session_state["str_rule"] = acc_alerts.iloc[0]["rule_id"]
        st.success("'④ STR 생성'에서 초안을 확인하십시오.")

# =====================================================================
# ④ STR 생성
# =====================================================================
elif page == "④ STR 생성":
    st.title("STR 초안 생성")
    st.caption("FIU 별지 제1호 서식 기준. 자동생성 초안이며 보고책임자 검토가 필요합니다.")

    with st.expander("STR이 무엇인가요?"):
        st.markdown(
            "**STR(의심거래보고)** 은 금융회사가 자금세탁이 의심되는 거래를 "
            "발견했을 때 금융정보분석원(FIU)에 제출하는 법정 보고서입니다. "
            "금액과 무관하게 의심된다고 판단하면 보고 의무가 생기고, "
            "의심거래로 결정한 시점부터 **3영업일 이내**에 보고해야 합니다.\n\n"
            "종합의견은 **육하원칙(누가·언제·어디서·무엇을·어떻게·왜)** 에 따라 "
            "적는 것이 원칙이며, 명확한 보고 이유·창구 정황·명확한 고객 정보·"
            "관련인·송금자 정보·자금 출처·변동된 차이점·특이점을 포함해야 합니다.\n\n"
            "아래 초안에서 **시스템이 채우는 것은 거래 원장에서 확인되는 "
            "사실까지**입니다. 나머지는 `[  ]` 로 비워 두었으며, 보고책임자가 "
            "채우고 서명해야 제출할 수 있습니다.\n\n"
            ":warning: 탐지 조건과 임계값을 옮겨 적은 서술(\"다수 계좌를 통한 "
            "분할입금이어서 보고함\")만으로는 **미흡 보고**로 분류됩니다. "
            "계좌주 정보와 창구 정황이 없으면 심사분석에 쓸 수 없기 때문입니다."
        )

    target = st.session_state.get("str_target", "")
    rule_default = st.session_state.get("str_rule", "R-03")

    col1, col2 = st.columns(2)
    with col1:
        rule_id = st.selectbox("룰 선택", options=list(RULE_LABELS.keys()),
                              index=list(RULE_LABELS.keys()).index(rule_default))
    with col2:
        acc_options = sorted(
            alerts[alerts["rule_id"] == rule_id]["account_id"].unique().tolist())
        acc_idx = acc_options.index(target) if target in acc_options else 0
        account_id = st.selectbox("계좌 선택", options=acc_options,
                                 index=acc_idx if acc_options else 0)

    rule_help(rule_id)

    row = alerts[(alerts["rule_id"] == rule_id) &
                (alerts["account_id"] == account_id)].iloc[0]
    st.caption(f"근거 거래 {row['txn_count']:,}건 / "
              f"합산 {row['total_amount']:,.2f}")

    if st.button("STR 초안 생성", type="primary"):
        with st.spinner("초안 생성 중..."):
            st.session_state["str_doc"] = generate_str(
                account_id, rule_id, row, tx, load_account_profile())
        # 생성 시점의 대상을 함께 기록 — 룰·계좌를 바꾸면 이전 초안을 내린다
        st.session_state["str_doc_key"] = (rule_id, account_id)

    if st.session_state.get("str_doc_key") == (rule_id, account_id):
        st.divider()
        st.markdown(st.session_state["str_doc"])
        st.download_button(
            "STR 초안 다운로드 (.md)",
            data=st.session_state["str_doc"],
            file_name=f"STR_{rule_id}_{account_id}.md",
            mime="text/markdown",
        )
    elif "str_doc_key" in st.session_state:
        st.info("룰 또는 계좌가 변경되었습니다. 'STR 초안 생성'을 다시 누르십시오.")
