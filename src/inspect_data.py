"""0단계: 원본 데이터 구조 확인"""
import pandas as pd

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 60)

RAW = "data/raw"

# ============ 1. 거래 원장 ============
print("=" * 70)
print("HI-Small_Trans.csv")
print("=" * 70)

df = pd.read_csv(f"{RAW}/HI-Small_Trans.csv", nrows=300_000)
print(f"(상위 30만행 기준)\n")

print("[1] 컬럼과 타입")
print(df.dtypes)

print("\n[2] 샘플 3행")
print(df.head(3).to_string())

print("\n[3] 결측치")
print(df.isnull().sum())

print("\n[4] 컬럼별 고유값 수")
for c in df.columns:
    print(f"  {c}: {df[c].nunique()}")


def find(keys, frame=df):
    return [c for c in frame.columns if any(k in c.lower() for k in keys)]


print("\n[5] 핵심 컬럼 후보")
print("  시각:", find(["time", "date"]))
print("  계좌:", find(["account", "acct"]))
print("  은행:", find(["bank"]))
print("  금액:", find(["amount", "paid", "received"]))
print("  통화:", find(["currency"]))
print("  결제형식:", find(["format", "payment"]))
print("  라벨:", find(["launder", "label"]))

# 라벨 분포
lab = find(["launder", "label"])
if lab:
    c = lab[0]
    print(f"\n[6] 라벨 '{c}'")
    print(df[c].value_counts())
    print("비율:", df[c].value_counts(normalize=True).round(6).to_dict())

# 결제형식 — CTR 적용의 전제 (현금 구분 가능한가)
fmt = [c for c in df.columns if "format" in c.lower()]
if fmt:
    c = fmt[0]
    print(f"\n[7] 결제형식 '{c}' 값 분포  ★ 현금 구분 가능 여부")
    print(df[c].value_counts())

# 시각
ts = find(["time", "date"])
if ts:
    c = ts[0]
    print(f"\n[8] 시각 '{c}'")
    print("  원본 예시:", df[c].head(3).tolist())
    p = pd.to_datetime(df[c], errors="coerce")
    print("  파싱 성공률:", round(p.notna().mean(), 4))
    print("  범위:", p.min(), "~", p.max())
    print("  시(hour) 분포:")
    print(p.dt.hour.value_counts().sort_index().to_string())

# 금액
amt = find(["amount", "paid"])
if amt:
    c = amt[0]
    print(f"\n[9] 금액 '{c}' 분포")
    print(df[c].describe())

# 통화
cur = find(["currency"])
if cur:
    c = cur[0]
    print(f"\n[10] 통화 '{c}' 분포")
    print(df[c].value_counts().head(10))

# ============ 2. 계좌 정보 ============
print("\n" + "=" * 70)
print("HI-Small_accounts.csv")
print("=" * 70)

acc = pd.read_csv(f"{RAW}/HI-Small_accounts.csv", nrows=100_000)
print("[1] 컬럼과 타입")
print(acc.dtypes)
print("\n[2] 샘플 3행")
print(acc.head(3).to_string())
print("\n[3] 고유값 수")
for c in acc.columns:
    print(f"  {c}: {acc[c].nunique()}")

# ★ 국가 정보 유무 — 있으면 합성 불필요
geo = [c for c in acc.columns if any(k in c.lower()
       for k in ["country", "region", "nation", "location", "bank"])]
print("\n[4] 국가/은행 관련 컬럼:", geo)
for c in geo:
    print(f"\n  {c} 상위 10개:")
    print(acc[c].value_counts().head(10).to_string())

# ============ 3. 패턴 파일 ============
print("\n" + "=" * 70)
print("HI-Small_Patterns.txt — 자금세탁 유형")
print("=" * 70)

with open(f"{RAW}/HI-Small_Patterns.txt", encoding="utf-8") as f:
    lines = f.readlines()

print("총 라인 수:", len(lines))
begins = [l.strip() for l in lines if l.startswith("BEGIN LAUNDERING")]
print("패턴 블록 수:", len(begins))

from collections import Counter
types = Counter(b.replace("BEGIN LAUNDERING ATTEMPT - ", "").split(":")[0].strip()
                for b in begins)
print("\n유형별 개수:")
for k, v in types.most_common():
    print(f"  {k}: {v}")