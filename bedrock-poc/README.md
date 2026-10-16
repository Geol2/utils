# Bedrock 서울 리전 Claude 호출 PoC

폐쇄망 도입 검토용. **인터넷망 PC**에서 돌려서 아래 세 가지를 확인하고, 그 결과를 품의·보안성 검토 자료에 그대로 붙이는 걸 목적으로 함.

1. 서울 리전(`ap-northeast-2`)으로 실제 호출이 되는가
2. 처리가 리전을 벗어나지 않는가 (= 데이터 국외 이전이 없는가)
3. 응답 시간·토큰·비용이 얼마인가

> **주의**: 업무망 소스코드를 개인 AWS 계정으로 올리지 말 것. PoC 는 더미 데이터나 공개 샘플로 할 것.

## 1. 설치

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install boto3
```

## 2. AWS 준비 (최초 1회)

1. AWS 콘솔에서 리전을 **아시아 태평양(서울) ap-northeast-2** 로 변경
2. **Bedrock > Model access** 에서 쓸 Claude 모델을 활성화 (승인까지 보통 즉시~몇 분)
3. IAM 사용자 하나 만들고 액세스 키 발급. 필요한 권한:
   - `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`
   - `bedrock:ListFoundationModels`, `bedrock:ListInferenceProfiles` (list 명령용)
4. 자격증명 등록

```powershell
$env:AWS_ACCESS_KEY_ID = "AKIA..."
$env:AWS_SECRET_ACCESS_KEY = "..."
```

또는 `aws configure`. 키를 스크립트에 적지 말 것.

## 3. 실행

### 연결 확인 (모델 호출 없음 = 과금 없음)

```powershell
.\.venv\Scripts\python.exe bedrock_poc.py check
```

```
■ 리전 · 엔드포인트
   리전      ap-northeast-2 (서울)
   엔드포인트 https://bedrock-runtime.ap-northeast-2.amazonaws.com
   판정      리전 전용 엔드포인트 — 호출이 이 리전으로 들어갑니다.
```

이 엔드포인트 줄이 **"서울 리전으로만 나간다"는 증빙**이 됨.

### 모델 ID 확인

```powershell
.\.venv\Scripts\python.exe bedrock_poc.py list
```

모델 ID 는 리전·시점마다 다르므로 **반드시 이 명령으로 확인**하고 쓸 것. 출력에서 봐야 할 것:

| 표시 | 의미 |
|---|---|
| `모델 ID 직접` | 온디맨드 호출 가능. 서울 리전에서 처리됨 |
| `추론 프로필 필요` | 모델 ID 로 직접 못 부름. 아래 추론 프로필 목록에서 골라야 함 |
| 추론 프로필 `리전 내` | 서울에서 처리 — **검토 자료에 쓸 건 이것** |
| 추론 프로필 `교차 리전` (`apac.`, `us.`, `global.` 등) | 처리가 다른 리전으로 넘어갈 수 있음. 국외 이전 이슈가 생기므로 주의 |

### 1회 호출

```powershell
.\.venv\Scripts\python.exe bedrock_poc.py ask -m <모델ID> "한국어로 한 문장만 답해줘"
```

`--stream` 을 붙이면 토큰이 오는 대로 출력되고 첫 글자까지 걸린 시간도 같이 나옴.

### 측정 (품의서용 숫자)

```powershell
.\.venv\Scripts\python.exe bedrock_poc.py bench -m <모델ID> -n 10 --price-in 3 --price-out 15 --save report.json
```

```
■ 결과 (10회)
   응답 시간  평균 1,840 ms · 중앙값 1,790 ms · 최소 1,210 · 최대 2,980
   토큰       입력 합계 1,260 · 출력 합계 5,110 (1회 평균 입력 126 · 출력 511)
   비용       $0.08043  (약 112.6원)   [입력 $3.0/1M · 출력 $15.0/1M 기준]
```

- `--price-in` / `--price-out` 은 **1M 토큰당 USD**. AWS Bedrock 요금 페이지에서 쓰는 모델·리전 값을 보고 직접 넣을 것 (요금이 바뀌므로 스크립트에 하드코딩하지 않음)
- `--krw` 로 환율 변경 (기본 1400)
- `--save` 로 JSON 보고서 저장 → 검토 자료 첨부용

월 비용은 `1회당 비용 × 예상 월 호출 건수`로 산정. 예상 건수는 "영향도 분석 1건당 N회 × 월 M건" 식으로 잡으면 설명하기 쉬움.

## 4. 오류가 날 때

스크립트가 원인과 조치를 같이 출력함. 자주 나는 것:

| 메시지 | 원인 |
|---|---|
| 자격증명이 없습니다 | `aws configure` 또는 환경변수 미설정 |
| 액세스 키가 유효하지 않습니다 | 키 오타 / 비활성 키 |
| IAM 권한이 없거나 모델 액세스가 승인되지 않았습니다 | Bedrock > Model access 에서 모델 미활성화가 대부분 |
| 그 리전에 없는 모델 ID 입니다 | `list` 로 ID 재확인 |
| 온디맨드를 지원하지 않습니다 | 모델 ID 대신 추론 프로필 ID 로 호출 |
| 엔드포인트에 연결하지 못했습니다 | 프록시 환경이면 `HTTPS_PROXY` 설정, 방화벽에서 `bedrock-runtime.ap-northeast-2.amazonaws.com` 허용 |

## 5. 검토 자료에 넣을 항목

이 PoC 로 뽑히는 것:

- **데이터 국외 이전 없음** — 서울 리전 엔드포인트 + 리전 내 추론 프로필 사용 (`check` 출력)
- **응답 시간** — `bench` 평균·중앙값
- **비용** — 1회당 비용과 월 환산
- **통제 구조** — 인터넷망 게이트웨이 1대만 외부 통신, 업무망은 기존 망분리 구조 유지

이 PoC 로는 **안 나오는** 것 (별도 검토 필요):

- 망분리 지침상 예외 적용 가능 여부
- 기관 보안성 검토 일정
- 공공기관 클라우드 이용 시 CSAP 인증 범위
- 전송 전 개인정보 마스킹 방안

## 6. 파일 구성

```
bedrock-poc\
├─ bedrock_poc.py      PoC 스크립트
├─ requirements.txt    boto3
├─ README.md
└─ .venv\              가상환경 (PC마다 새로 생성, 복사 금지)
```
