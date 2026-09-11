# egov_impact_report.py 사용법

전자정부 프레임워크(Spring MVC + MyBatis + JSP + jQuery) 프로젝트에서
`JSP/JS → Controller → Service/DAO → Mapper → 테이블` 체인을 추적해서
영향도 분석서(xlsx)와 공수·일정을 뽑아주는 스크립트.

## 1. 설치

```powershell
C:\Python314\python.exe -m pip install openpyxl
```

`pip install`만 치면 다른 파이썬에 깔릴 수 있으니 반드시 `python.exe -m pip`로.

**폐쇄망일 때**

```powershell
# 인터넷 되는 PC
pip download openpyxl -d .\wheels

# 폐쇄망 PC (wheels 폴더 복사 후)
C:\Python314\python.exe -m pip install openpyxl --no-index --find-links .\wheels
```

## 2. 실행

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
| `<검색어>` | 테이블명 / mapper id / 컨트롤러 URL 일부 / JS 함수명(`fn_xxx`). 대소문자 무시, 부분 일치 | 필수 |
| `--start` | 작업 시작일 (YYYY-MM-DD). 주말이면 다음 영업일로 보정 | 오늘 |
| `--people` | 투입 인원 (소수 가능, 0.5 = 반 투입) | 1 |
| `--out` | 출력 파일명 | 영향도분석서.xlsx |

검색어 예:

```powershell
... D:\workspace\dWorks\src TB_USER          # 테이블 기준
... D:\workspace\dWorks\src selectUserList   # mapper id 기준
... D:\workspace\dWorks\src /user/list       # URL 기준
... D:\workspace\dWorks\src fn_search        # JS 함수 기준
```

실행하면 콘솔에 요약이 찍히고, 실행한 폴더에 엑셀이 생김:

```
영향도분석서.xlsx 저장 — 영향 23건, 총 14.2 MD, 2026-09-14~2026-09-24 (9 영업일 / 2.0명)
```

## 3. 결과 파일 구성

### 요약 시트
변경 대상, 영향 항목 수(직접/간접), 개발·테스트·버퍼 공수, 총 MD, 투입 인원, 예상 영업일, 시작일~종료일.

### 영향목록 시트
| 컬럼 | 내용 |
|---|---|
| 구분 | Table / Mapper / DAO / Service / Controller / JSP / JS |
| 항목 | 테이블명, statement id, 클래스.메서드 (URL), 파일명 등 |
| 파일 | 실제 경로 |
| 영향 | 직접 / 간접 |
| 경유 | 어떤 경로로 잡혔는지 (예: `selectUserList` → 이 DAO) |
| 공수(MD) | 자동 산정 |
| 시작일 / 종료일 | 항목별 순차 배분 |
| 담당자 / 조치내용 / 비고 | 빈 칸 — 직접 채움 |

필터가 걸려 있으니 구분/영향 기준으로 걸러서 보면 됨.

### 공수기준 시트
산정 근거표. 분석서에 그대로 첨부하면 "공수 어떻게 나왔냐"에 대한 답이 됨.

## 4. 공수 산정 방식

```
항목 공수 = 기본 MD × 파일크기 가중 × 영향 가중
총 공수   = 개발 공수 + 테스트(개발 × 30%) + 버퍼((개발+테스트) × 15%)
예상 기간 = 총 공수 / 투입 인원 (영업일, 주말만 제외)
```

- 기본 MD: Table 0.5 / Mapper 0.5 / DAO 0.3 / Service 0.5 / Controller 0.5 / JSP 0.7 / JS 0.5
- 파일크기 가중: 300라인 미만 1.0 / 1000라인 미만 1.3 / 그 이상 1.6
- 영향 가중: 직접 1.0 / 간접 0.5

팀 기준과 다르면 스크립트 상단의 `BASE_MD`, `TEST_RATIO`, `BUFFER_RATIO`를 수정하고 다시 실행.
기본값은 임의로 넣은 것이니 실제 수정 건 1~2개와 대조해서 맞추는 걸 권장.

## 5. 한계 (누락 가능 항목)

아래는 자동으로 못 잡으니 영향목록 시트에 행을 직접 추가할 것:

- `<include refid>`, `<sql>` 조각 안의 테이블
- `${}`로 동적 조립되는 테이블명
- `<c:url>`이나 JS 문자열 concat으로 만든 URL
- 프로시저 / 함수 내부 참조 → DB에서 `ALL_DEPENDENCIES`(Oracle), `pg_depend`(PostgreSQL)로 확인
- Controller ↔ Service 연결은 클래스명 관례(`UserController` ↔ `UserServiceImpl`)로 매칭하므로 이름 규칙이 깨진 곳은 IntelliJ `Find Usages`로 재확인
- 공휴일은 안 뺌 → 연휴 낀 기간이면 종료일 수동 보정

## 6. 결과가 0건일 때

- 검색어 오타 확인
- 소스루트를 너무 좁게 잡았는지 확인 (JSP 폴더가 `src` 밖 `WebContent`에 있는 경우 프로젝트 루트로)
- 프로젝트가 `@RequestMapping` 대신 XML 빈 매핑을 쓰면 정규식 수정 필요
