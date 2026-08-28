"""6단계-5: 민감도 곡선 시각화

CSV 3개를 읽어 파라미터별 (알림 수, 재현율, 정밀도) 곡선을 그린다.
산출물은 docs/img/ 아래 PNG — threshold_tuning.md에서 참조한다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams["font.family"] = "AppleGothic"      # macOS 한글
plt.rcParams["axes.unicode_minus"] = False

OUT = Path("docs/img")
OUT.mkdir(parents=True, exist_ok=True)


def plot_param(df, param, title, fname, xlabel=None):
    """한 파라미터의 알림 수 + 재현율/정밀도 이중축 곡선"""
    g = df[df["param"] == param].sort_values("value") if "param" in df.columns else df
    if len(g) == 0:
        return

    fig, ax1 = plt.subplots(figsize=(7, 4.2))

    ax1.bar(range(len(g)), g["alerts"], width=0.5, alpha=0.3,
            color="steelblue", label="알림 수")
    ax1.set_xticks(range(len(g)))
    ax1.set_xticklabels([f"{v:g}" for v in g["value"]])
    ax1.set_xlabel(xlabel or param)
    ax1.set_ylabel("알림 수")

    ax2 = ax1.twinx()
    if "recall" in g.columns:
        ax2.plot(range(len(g)), g["recall"] * 100, "o-",
                 color="firebrick", label="재현율 (%)")
    ax2.plot(range(len(g)), g["precision"] * 100, "s--",
             color="darkgreen", label="정밀도 (%)")
    ax2.set_ylabel("비율 (%)")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)

    plt.title(title)
    plt.tight_layout()
    plt.savefig(OUT / fname, dpi=150)
    plt.close()
    print(f"  → {OUT/fname}")


# ===== R-02 =====
r02 = pd.read_csv("docs/r02_tuning.csv")
print("R-02 곡선")
plot_param(r02, "window_hours", "R-02: 관찰 창 크기", "r02_window.png", "창 크기 (시간)")
plot_param(r02, "min_in_parties", "R-02: 최소 유입 상대방 수", "r02_parties.png", "유입 상대방 수")
plot_param(r02, "pass_ratio", "R-02: 통과 비율", "r02_ratio.png", "유출/유입 비율")

# ===== R-03 =====
r03 = pd.read_csv("docs/r03_tuning.csv")
print("R-03 곡선")
plot_param(r03, "amount_tolerance", "R-03: 금액 편차 허용치", "r03_tolerance.png", "허용 편차")
plot_param(r03, "max_len", "R-03: 최대 순환 길이", "r03_maxlen.png", "순환 길이 (hop)")
plot_param(r03, "max_duration_days", "R-03: 순환 완료 기간 상한", "r03_duration.png", "기간 (일)")

# ===== R-04 (구조가 달라 직접 처리) =====
r04 = pd.read_csv("docs/r04_tuning.csv")
print("R-04 곡선")
d = r04[r04["window_days"] == 7].copy()
d = d.rename(columns={"threshold": "value"})
d["param"] = "threshold"
plot_param(d, "threshold", "R-04: 기준액 (7일 창)", "r04_threshold.png", "기준액 (USD)")

print("\n완료 — docs/img/ 확인")