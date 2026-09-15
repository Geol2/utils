# 스프링 영향도 분석 도구 사용법

Spring MVC + MyBatis + JSP + jQuery 프로젝트에서
`JSP/JS → Controller → Service/DAO → Mapper → 테이블` 체인을 추적해서
영향도 분석서(xlsx)와 공수·일정을 뽑아주는 도구.

| 파일 | 용도 |
|---|---|
| `egov_impact_ui.py` | 브라우저 UI. 평소엔 이걸 쓰면 됨 |
| `egov_impact_report.py` | 커맨드라인 버전. 배치나 자동화용 |

둘 다 분석 로직과 공수 기준은 동일.

## 1. 설치 (venv + 오프라인)

venv 자체는 표준 라이브러리라 인터넷 없이 만들어지고, 넣어야 할 패키지는 `openpyxl` 하나뿐(엑셀 저장용).

**인터넷 되는 PC에서 whl 받기**

```powershell
mkdir wheels
C:\Python314\python.exe -m pip download openpyxl -d .\wheels
```

`openpyxl`, `et_xmlfile` 두 개가 떨어짐. 순수 파이썬 패키지라 `py3-none-any` whl로 받히니 파이썬 버전이 조금 달라도 됨.
`wheels` 폴더를 스크립트와 함께 폐쇄망 PC로 복사.

**폐쇄망 PC**

```powershell
cd C:\work\impact
C:\Python314\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --no-index --find-links .\wheels openpyxl
```

- `Activate.ps1` 실행 정책 에러 → `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 한 번, 또는 활성화 없이 `.\.venv\Scripts\python.exe`로 직접 호출
- venv 생성 시 pip 부트스트랩 실패 → `python -m venv .venv --without-pip` 후 `python -m ensurepip`
- `pip install`만 치면 다른 파이썬에 깔릴 수 있으니 항상 `python -m pip`

## 2. UI로 실행 (권장)

`run_ui.bat` 더블클릭. (`.venv`가 있으면 그걸로, 없으면 시스템 `python`으로 실행)

터미널에서 직접 실행할 때:

```powershell
.\.venv\Scripts\python.exe egov_impact_ui.py
```

브라우저가 `http://127.0.0.1:8765`로 자동으로 열림. 안 열리면 주소를 직접 입력. 127.0.0.1에만 바인딩되어 있어 외부에서는 접속 불가. 종료는 콘솔에서 Ctrl+C.

분석을 실행하면 오른쪽 상단에 진행 상황이 실시간으로 표시됨 — 단계(파일 수집 → Controller URL 매핑 → Mapper XML 파싱 → Java→Mapper 추적 → JSP/JS 스캔 → 영향 항목 수집 → 공수 산정), 지금 처리 중인 파일(n/전체), 단계별로 찾은 개수, 경과 시간. 콘솔에도 같은 로그가 찍힘. 완료되면 접히고 제목을 클릭하면 다시 펼쳐짐.

**화면**

1. 왼쪽 패널에 소스 루트 폴더(`…` 버튼으로 폴더 선택창), 검색어, 작업 시작일, 투입 인원 입력
2. **분석 실행** (검색어 칸에서 Enter도 됨) — 진행 로그가 뜨고 끝나면 표가 채워짐
3. 오른쪽 상단에 영향 항목 수, 개발/테스트·버퍼/총 공수, 예상 기간이 표시됨
4. 표에서 구분·영향 드롭다운과 텍스트 필터로 좁혀 보기
4-1. **관계도** 탭 — JSP → JS 함수 → Controller → Service → DAO → Mapper → 테이블 순으로 열을 세워 누가 누구를 부르는지 선으로 연결. 노드에 마우스를 올리면 그 노드와 위아래로 이어진 경로만 남고 나머지는 흐려짐 (클릭하면 고정, 빈 곳 클릭으로 해제). 빨간 테두리 직접, 노란 테두리 간접. 점선은 `<script src>` include. 노드 위에 마우스를 올리면 전체 이름과 파일 경로가 툴팁으로 뜸
5. 담당자·조치내용·비고는 표에서 바로 입력
6. **엑셀로 저장** → 입력값까지 포함된 `영향도분석서_<검색어>_<시작일>.xlsx` 다운로드 (관계도 내용은 `연결관계` 시트로 들어감)

**최근 분석**

한 번 실행한 소스 루트·검색어·투입 인원은 왼쪽 패널 아래 "최근 분석" 목록에 쌓임(최대 30개). 클릭하면 입력칸에 채워지고, × 로 삭제. 소스 루트와 검색어 입력칸에서도 이전 값이 자동완성으로 뜸. 기록은 스크립트 옆 `impact_history.json`에 저장되므로 브라우저를 바꿔도 유지됨.

폴더 선택창은 tkinter를 쓰는데, 파이썬 설치 시 빠져 있으면 경로를 직접 입력하면 됨.

## 3. 커맨드라인으로 실행

```powershell
C:\Python314\python.exe egov_impact_report.py <소스루트> <검색어> [옵션]
```

예시:

```powershell
C:\Python314\python.exe egov_impact_report.py D:\workspace\dWorks\src TB_USER --start 2026-09-14 --people 2
```

| 인자 | 설명 | 기본값 |
|---|---|---|
| `<소스루트>` | Controller.java, mapper XML, JSP, JS가 모두 포함되는 상위 폴더. 하위 폴더 전부 재귀 탐색 | 필수 |
| `<검색어>` | 테이블명 / mapper id / 컨트롤러 URL 일부 / JS 함수명. 대소문자 무시, 부분 일치 | 필수 |
| `--start` | 작업 시작일 (YYYY-MM-DD). 주말이면 다음 영업일로 보정 | 오늘 |
| `--people` | 투입 인원 (소수 가능, 0.5 = 반 투입) | 1 |
| `--out` | 출력 파일명 | 영향도분석서.xlsx |

UI 없이 여러 검색어를 배치로 돌리거나 Jenkins 등에서 자동화할 때 사용.

검색어 예:

```powershell
... D:\workspace\dWorks\src TB_USER          # 테이블 기준
... D:\workspace\dWorks\src selectUserList   # mapper id 기준
... D:\workspace\dWorks\src /user/list       # URL 기준
... D:\workspace\dWorks\src fn_search        # JS 함수 기준
```

실행하면 콘솔에 UI와 같은 진행 로그가 찍히고, 실행한 폴더에 엑셀이 생김:

```
▶ 파일 목록 수집
   ✔ Java 530개 (Controller 41) · XML 88개 · JSP/JS 305개
▶ Controller URL 매핑
   ✔ URL 412개
...
▶ 영향 항목 수집
   ✔ 테이블/Mapper 기준 14건
   ✔ URL 기준 +0건
   ✔ JS 함수 기준 +3건
   ✔ JS 를 include 하는 JSP +6건
▶ 공수·일정 산정
   ✔ 영향도분석서.xlsx 저장 — 영향 23건, 총 14.2 MD, 2026-09-14~2026-09-24 (9 영업일 / 2.0명), 3.2초
```

## 4. 결과 파일 구성

### 요약 시트
변경 대상, 영향 항목 수(직접/간접), 개발·테스트·버퍼 공수, 총 MD, 투입 인원, 예상 영업일, 시작일~종료일.

### 영향목록 시트
| 컬럼 | 내용 |
|---|---|
| 구분 | Table / Mapper / DAO / Service / Controller / JSP / JS |
| 항목 | 테이블명, statement id, 클래스.메서드 (URL), 파일명 등 |
| 파일 | 실제 경로 |
| 영향 | 직접 / 간접 |
| 경유 | 어떤 경로로 잡혔는지 (예: `selectUserList` → 이 DAO, `/user/list` → 이 JS, `user.js include` → 이 JSP) |
| 공수(MD) | 자동 산정 |
| 시작일 / 종료일 | 항목별 순차 배분 |
| 담당자 / 조치내용 / 비고 | 빈 칸 — 직접 채움 |

필터가 걸려 있으니 구분/영향 기준으로 걸러서 보면 됨.

### 연결관계 시트
관계도의 선 목록. From 구분 / From / To 구분 / To / 관계(호출·참조·include). JS 쪽은 `user.js › fn_userSearch()` 처럼 함수 단위로 나옴.

### 공수기준 시트
산정 근거표. 분석서에 그대로 첨부하면 "공수 어떻게 나왔냐"에 대한 답이 됨.

## 5. 공수 산정 방식

```
항목 공수 = 기본 MD × 파일크기 가중 × 영향 가중
총 공수   = 개발 공수 + 테스트(개발 × 30%) + 버퍼((개발+테스트) × 15%)
예상 기간 = 총 공수 / 투입 인원 (영업일, 주말만 제외)
```

- 기본 MD: Table 0.5 / Mapper 0.5 / DAO 0.3 / Service 0.5 / Controller 0.5 / JSP 0.7 / JS 0.5
- 파일크기 가중: 300라인 미만 1.0 / 1000라인 미만 1.3 / 그 이상 1.6
- 영향 가중: 직접 1.0 / 간접 0.5

팀 기준과 다르면 두 스크립트 상단의 `BASE_MD`, `TEST_RATIO`, `BUFFER_RATIO`를 수정하고 다시 실행 (UI는 서버 재시작 필요).
기본값은 임의로 넣은 것이니 실제 수정 건 1~2개와 대조해서 맞추는 걸 권장.

## 6. JSP/JS 는 어떻게 잡나

Java 쪽은 mapper id 문자열로, 화면 쪽은 아래 세 가지로 연결함.

**컨트롤러 URL 호출** — JSP/JS 안의 슬래시가 든 문자열 리터럴(`"…/…"`)을 전부 모아 컨트롤러 URL과 *뒤에서부터* 맞춰봄. 그래서 `$.ajax({url:…})`, `$.post(…)`, `fetch(…)`, `location.href=…`, `<form action=…>`, `<c:url value=…>` 등 어떤 형태든 상관없고, 아래도 다 같은 URL로 인식:

- `"/dWorks/user/list.do"` (컨텍스트 경로 붙은 것), `ctx + "/user/list.do"`, `"${ctx}/user/list.do"`, `"<%=ctx%>/user/list.do"`
- `"/user/list.do?x=1"` (쿼리스트링), `"/user/detail/" + id` ↔ `@GetMapping("/user/detail/{id}")`
- `.do` 유무 무관. 클래스 레벨 `@RequestMapping("/user")` + 메서드 `@GetMapping("/list")` = `/user/list`

**JS 함수** — `function a()`, `a = function()`, `a: function()`, `a = () =>` 형태의 정의를 전부 수집하고, 중괄호 짝으로 함수 본문 범위를 잡아서 URL 호출이 *어느 함수 안에서* 일어나는지까지 기록함. 그래서 경유 컬럼에 `/user/list ← fn_userSearch()` 처럼 찍히고, 관계도에는 파일이 아니라 `user.js › fn_userSearch()` 노드로 나옴.

검색어가 함수명에 포함되면 정의한 파일은 직접, 그 함수를 호출하는 JSP/JS는 간접, 그 함수가 부르는 컨트롤러부터 아래(Service → DAO → Mapper → 테이블)는 간접으로 이어서 추적. 검색어에 `/`나 `.`이 있으면(URL/테이블 형태) 함수 매칭은 건너뜀.

**위에서 아래로 내려갈 때 (URL·함수 검색)** — Controller → Service/DAO 는 클래스명 관례(`UserController` ↔ `UserServiceImpl`, `UserDAO`)로 잇고, 그 클래스가 쓰는 mapper id 전부와 그 테이블을 간접으로 넣음. 메서드 단위가 아니라 클래스 단위 근사라서 실제보다 넓게 잡힐 수 있음 — 관계도에서 보고 관계없는 건 엑셀에서 지우면 됨.

**script include** — 어떤 JS 파일이 영향 목록에 들어가면 그 파일을 `<script src="…/x.js">`로 물고 있는 JSP를 간접으로 추가. src 가 `<c:url>`이나 `${ctx}`로 감싸져 있어도 파일명으로 맞추므로 상관없음.

## 7. 한계 (누락 가능 항목)

아래는 자동으로 못 잡으니 엑셀의 영향목록 시트에 행을 직접 추가할 것:

- `<include refid>`, `<sql>` 조각 안의 테이블
- `${}`로 동적 조립되는 테이블명
- URL 중간이 변수로 조립되는 것 (`"/user/" + type + "/list.do"`). 앞뒤만 붙는 건 잡힘
- JS 파일 안에서 다른 JS 함수를 거쳐 URL을 호출하는 2단계 이상 체인 (`a.js`의 함수가 `b.js`의 함수를 부르고 거기서 ajax) — b.js 는 잡히지만 a.js 는 함수명으로 따로 검색해야 함
- 프로시저 / 함수 내부 참조 → DB에서 `ALL_DEPENDENCIES`(Oracle), `pg_depend`(PostgreSQL)로 확인
- Controller ↔ Service 연결은 클래스명 관례(`UserController` ↔ `UserServiceImpl`)로 매칭하므로 이름 규칙이 깨진 곳은 IntelliJ `Find Usages`로 재확인
- 공휴일은 안 뺌 → 연휴 낀 기간이면 종료일 수동 보정
- JS 함수 본문 범위는 중괄호 개수로 잡으므로 문자열/정규식 안에 `{`가 홀로 들어 있으면 그 파일의 함수 경계가 어긋날 수 있음 (그 경우 파일 단위로만 잡힘)

## 8. 결과가 0건일 때

- 검색어 오타 확인
- UI에서 "폴더를 찾을 수 없습니다" → 경로 오타이거나 네트워크 드라이브 권한 문제
- 소스루트를 너무 좁게 잡았는지 확인 (JSP 폴더가 `src` 밖 `WebContent`에 있는 경우 프로젝트 루트로)
- 프로젝트가 `@RequestMapping` 대신 XML 빈 매핑을 쓰면 정규식 수정 필요
- JSP/JS 가 하나도 안 잡히면 진행 로그의 `URL 호출 n건`을 확인 — 0건이면 컨트롤러 URL 과 화면의 URL 문자열이 안 맞는 것 (예: 화면은 `.do` 를 붙이는데 컨트롤러는 `/*.do` 서블릿 매핑으로 처리)

## 9. 파일 구성

```
impact\
├─ run_ui.bat              UI 실행용 (더블클릭)
├─ egov_impact_ui.py       UI
├─ egov_impact_report.py   CLI
├─ README.md
├─ impact_history.json     최근 분석 기록 (UI가 자동 생성)
├─ wheels\                 오프라인 설치용 whl
└─ .venv\                  가상환경 (PC마다 새로 생성, 복사 금지)
```
