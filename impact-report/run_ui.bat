@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    echo [안내] .venv 가 없어 시스템 파이썬으로 실행합니다. openpyxl 이 없으면 엑셀 저장이 안 됩니다.
    set "PY=python"
)

echo 영향도 분석 UI 시작 - 종료하려면 이 창을 닫거나 Ctrl+C
"%PY%" egov_impact_ui.py

if errorlevel 1 (
    echo.
    echo [오류] 실행에 실패했습니다. 위 메시지를 확인하세요.
    pause
)