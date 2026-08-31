# 데이터 라이선스

이 저장소는 **코드와 데이터에 서로 다른 라이선스가 적용됩니다.**

| 대상 | 라이선스 | 파일 |
|---|---|---|
| 소스 코드, 문서 (`src/`, `config/`, `docs/*.md`, `README.md`) | MIT | [`LICENSE`](LICENSE) |
| 파생 데이터 (`data/alerts/*.parquet`) | CDLA-Sharing-1.0 | [`CDLA-Sharing-1.0.txt`](CDLA-Sharing-1.0.txt) |

---

## 원본 데이터 출처

- **데이터셋**: IBM Transactions for Anti Money Laundering (AML) — HI-Small 분할본
- **Data Provider**: IBM Corporation (Erik Altman 외)
- **배포처**: https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
- **라이선스**: Community Data License Agreement – Sharing – Version 1.0 (CDLA-Sharing-1.0)
- **원문**: https://cdla.dev/sharing-1-0/ (전문 사본: [`CDLA-Sharing-1.0.txt`](CDLA-Sharing-1.0.txt))

원본 데이터 파일(`HI-Small_Trans.csv`, `HI-Small_accounts.csv`,
`HI-Small_Patterns.txt`)은 이 저장소에 포함되어 있지 않습니다.
위 Kaggle 페이지에서 직접 내려받아 `data/raw/`에 배치하십시오.

---

## 변경 고지 (CDLA-Sharing-1.0 §3.1(b))

`data/alerts/` 디렉터리의 parquet 파일은 **원본 데이터를 변경·가공하여
생성한 파생 데이터입니다.** 원본 그대로가 아닙니다.

가한 변경은 다음과 같습니다.

- 송신·수신 계좌가 동일한 거래 591,212건 제외 (전체의 11.64%)
- 은행명 접두어에서 국가(`country`) 컬럼 파생 — 49.16%는 미국 지명 기반 추정
- 탐지 룰 R-01~R-04 적용 결과를 계좌 단위 알림 레코드로 재구성
- 각 알림에 원본 거래 식별자(`txn_ids`), 집계 금액(`total_amount`),
  탐지 근거(`evidence` JSON), 정답 라벨(`is_true_positive`) 부여

상세 가공 내역과 판단 근거는 [`docs/data_prep.md`](docs/data_prep.md) 참조.

---

## 재배포 조건

`data/alerts/`의 파일에는 원본 데이터에서 유래한 계좌 식별자·거래
식별자·거래 시각·금액이 포함되어 있습니다. 따라서 CDLA-Sharing-1.0의
Results 예외(§3.5)에 해당한다고 단정하지 않고, **보수적으로 Enhanced Data로
간주하여 동일 라이선스로 배포합니다.**

이 데이터를 재배포하려는 경우 CDLA-Sharing-1.0 §3의 조건을 따라야 합니다.

- 동일하게 CDLA-Sharing-1.0으로 배포 (§3.1(a), §3.3)
- 변경 사실을 명시 (§3.1(b))
- Data Provider(IBM) 귀속 표시 유지 (§3.1(c))
- 계약 전문 또는 그 사본에 대한 링크 포함 (§3.3)

코드(MIT)는 이 조건과 무관하게 자유롭게 사용할 수 있습니다.

---

## 개인정보

원본은 IBM 리서치가 다중 에이전트 시뮬레이터로 생성한 **합성 데이터**입니다.
실존 인물·계좌·거래가 아니며 개인정보를 포함하지 않습니다.
