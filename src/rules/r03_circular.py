"""R-03 순환거래 (Cycle)

자금이 여러 계좌를 거쳐 최초 출발 계좌로 되돌아오는 패턴.
자금세탁 3단계 중 반복(layering)의 전형적 형태로, 자금 출처를
추적 불가능하게 만드는 것이 목적이다.

근거: 업무규정상 의심거래 유형 (자금 출처 은닉)
대응 패턴: CYCLE (정답 계좌 271개)

성능 설계
  전체 거래 그래프(448만 간선)에 순환 탐지를 그대로 적용하면
  탐색 공간이 폭발한다. 3단계로 후보를 축소한다.
    1) 금액 하한으로 간선 필터
    2) 순환에 속할 수 없는 노드 제거 (진입 또는 진출 차수 0)
    3) 강한 연결 요소(SCC) 단위로 분할 — 순환은 SCC 안에만 존재
"""
import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alerts import make_alert, finalize, summarize   # noqa: E402

REF = "data/reference"


def build_graph(tx, min_amount):
    """계좌 간 거래를 방향 그래프로 변환

    같은 계좌쌍에 여러 거래가 있으면 대표값 하나로 축약한다
    (금액 최대 건). 순환 구조 탐지가 목적이므로 중복 간선은 불필요.
    """
    sub = tx[tx["amount"] >= min_amount].copy()
    print(f"금액 {min_amount:,} 이상 거래: {len(sub):,}건")

    # 계좌쌍별 대표 거래
    idx = sub.groupby(["from_account", "to_account"])["amount"].idxmax()
    edges = sub.loc[idx]
    print(f"축약 후 간선: {len(edges):,}개")

    G = nx.DiGraph()
    for r in edges.itertuples():
        G.add_edge(r.from_account, r.to_account,
                   amount=r.amount, ts=r.ts, txn_id=r.txn_id)
    print(f"그래프: 노드 {G.number_of_nodes():,} / 간선 {G.number_of_edges():,}")
    return G


def prune(G):
    """순환에 속할 수 없는 노드를 반복 제거

    진입 차수 0 또는 진출 차수 0인 노드는 어떤 순환에도 속하지 못한다.
    제거하면 이웃의 차수가 줄어 연쇄적으로 더 제거된다.
    """
    n0 = G.number_of_nodes()
    while True:
        dead = [n for n in G.nodes
                if G.in_degree(n) == 0 or G.out_degree(n) == 0]
        if not dead:
            break
        G.remove_nodes_from(dead)
    print(f"가지치기: {n0:,} → {G.number_of_nodes():,} 노드")
    return G


def find_cycles(G, p):
    """SCC 단위로 순환 탐색

    순환은 반드시 하나의 강한 연결 요소(SCC) 안에 존재한다.
    SCC로 쪼개면 탐색 공간이 크게 줄어든다.
    """
    sccs = [c for c in nx.strongly_connected_components(G) if len(c) >= p["min_len"]]
    sccs.sort(key=len, reverse=True)
    print(f"SCC {len(sccs):,}개 (최대 크기 {len(sccs[0]) if sccs else 0:,})")

    cycles = []
    for i, comp in enumerate(sccs, 1):
        sub = G.subgraph(comp)
        for cyc in nx.simple_cycles(sub, length_bound=p["max_len"]):
            if len(cyc) < p["min_len"]:
                continue
            cycles.append(cyc)
            if len(cycles) >= p["max_cycles"]:
                print(f"  탐색 상한 {p['max_cycles']:,} 도달 — 중단")
                return cycles
        if i % 200 == 0:
            print(f"  SCC {i:,}/{len(sccs):,} 처리, 순환 {len(cycles):,}개",
                  end="\r")
    print(f"\n원시 순환: {len(cycles):,}개")
    return cycles


def validate(G, cycles, p):
    """순환의 금액 일관성·소요 기간 검증

    자금세탁 순환은 같은 자금이 돌기 때문에 경로상 금액이 비슷하고,
    일정 기간 안에 완료된다. 우연히 형성된 순환을 걸러낸다.
    """
    tol = p["amount_tolerance"]
    max_dur = pd.Timedelta(days=p["max_duration_days"])

    valid = []
    for cyc in cycles:
        edges = [(cyc[i], cyc[(i + 1) % len(cyc)]) for i in range(len(cyc))]
        data = [G.edges[e] for e in edges]

        amts = [d["amount"] for d in data]
        if min(amts) < max(amts) * (1 - tol):      # 금액 편차
            continue

        tss = [d["ts"] for d in data]
        if max(tss) - min(tss) > max_dur:          # 소요 기간
            continue

        valid.append({
            "cycle": cyc,
            "txn_ids": [d["txn_id"] for d in data],
            "amounts": amts,
            "ts_min": min(tss),
            "ts_max": max(tss),
        })
    print(f"검증 통과 순환: {len(valid):,}개")
    return valid


def to_alerts(tx, valid):
    """순환에 관여한 계좌마다 알림 생성"""
    by_id = tx.set_index("txn_id")

    # 계좌별로 관여한 순환을 모음
    acc_cycles = {}
    for v in valid:
        for a in v["cycle"]:
            acc_cycles.setdefault(a, []).append(v)

    alerts = []
    for acct, cycs in acc_cycles.items():
        best = max(cycs, key=lambda c: len(c["cycle"]))
        g = by_id.loc[best["txn_ids"]].reset_index()
        alerts.append(make_alert(
            "R-03", acct, g,
            {"cycle_length": len(best["cycle"]),
             "n_cycles": len(cycs),
             "path": " → ".join(best["cycle"][:6]) +
                     ("..." if len(best["cycle"]) > 6 else ""),
             "amount_min": round(min(best["amounts"]), 2),
             "amount_max": round(max(best["amounts"]), 2),
             "duration_days": round(
                 (best["ts_max"] - best["ts_min"]).total_seconds() / 86400, 1)},
        ))
    return finalize(alerts)


def evaluate(alerts, truth_accounts, label):
    if not len(alerts):
        print(f"[{label}] 알림 0건")
        return
    got = set(alerts["account_id"])
    truth = set(truth_accounts)
    tp = len(got & truth)
    print(f"[{label}] 알림 {len(got):,}계좌 / 정답 {len(truth):,}계좌")
    print(f"  재현율 {tp/len(truth):.1%}  ({tp:,}/{len(truth):,})")
    print(f"  정밀도 {tp/len(got):.1%}  ({tp:,}/{len(got):,})")


if __name__ == "__main__":
    cfg = yaml.safe_load(open("config/thresholds.yaml"))
    p = cfg["r03_circular"]

    tx = pd.read_parquet(f"{REF}/transactions.parquet")
    print(f"거래 {len(tx):,}건\n")

    G = build_graph(tx, p["min_amount"])
    G = prune(G.copy())

    if G.number_of_nodes() == 0:
        raise SystemExit("가지치기 후 노드 0개 — min_amount를 낮추십시오")

    cycles = find_cycles(G, p)
    valid = validate(G, cycles, p)

    r03 = to_alerts(tx, valid)
    print()
    summarize(r03, "R-03")

    pat_acc = pd.read_parquet(f"{REF}/pattern_accounts.parquet")
    truth = pat_acc[pat_acc["pattern_type"] == "CYCLE"]["account_id"]
    print()
    evaluate(r03, truth, "R-03")

    Path("data/alerts").mkdir(parents=True, exist_ok=True)
    r03.to_parquet("data/alerts/r03.parquet", index=False)
    print("\n→ data/alerts/r03.parquet 저장")