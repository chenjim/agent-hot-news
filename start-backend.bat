@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d %~dp0

:: Load .env file if exists
if exist ".env" (
    for /f "usebackq tokens=*" %%i in (".env") do (
        set "line=%%i"
        if not "!line!"=="" (
            set "firstchar=!line:~0,1!"
            if not "!firstchar!"=="#" (
                for /f "tokens=1,* delims==" %%a in ("%%i") do (
                    if not "%%a"=="" set "%%a=%%b"
                )
            )
        )
    )
) else (
    echo [WARN] .env file not found, using defaults
)

cd /d %~dp0backend
set PYTHONPATH=%CD%

echo [CONFIG] DATABASE_URL=%DATABASE_URL%
echo [CONFIG] REDIS_URL=%REDIS_URL%
echo [CONFIG] OPENAI_BASE_URL=%OPENAI_BASE_URL%
echo [CONFIG] PYTHONPATH=%PYTHONPATH%
echo.

python -m uvicorn app.main:app --host 0.0.0.0 --port 51180
echo.
echo Backend stopped.
pause
