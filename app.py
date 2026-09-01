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
from generate_str import generate_str   # noqa: E402

REF = "data/reference"
ALERTS = "data/alerts"

RULE_LABELS = {
    "R-01": "분할입금 (Structuring)",
    "R-02": "자금통과계좌 (Mule Account)",
    "R-03": "순환거래 (Cycle)",
    "R-04": "국경간 고액거래",
}

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

# =====================================================================
# ① 대시보드
# =====================================================================
if page == "① 대시보드":
    st.title("탐지 현황 대시보드")

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

    for _, row in acc_alerts.iterrows():
        with st.expander(f"{RULE_LABELS.get(row['rule_id'], row['rule_id'])} "
                        f"— 탐지 {row['detected_ts']}"):
            ev = json.loads(row["evidence"])
            st.json(ev)

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

    row = alerts[(alerts["rule_id"] == rule_id) &
                (alerts["account_id"] == account_id)].iloc[0]
    st.caption(f"근거 거래 {row['txn_count']:,}건 / "
              f"합산 {row['total_amount']:,.2f}")

    if st.button("STR 초안 생성", type="primary"):
        with st.spinner("초안 생성 중..."):
            st.session_state["str_doc"] = generate_str(
                account_id, rule_id, row, tx)
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
