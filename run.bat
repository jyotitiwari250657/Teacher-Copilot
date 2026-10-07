@echo off
REM ==========================================================================
REM  TeacherCopilot - one-command start for Windows.
REM
REM    run.bat            start the app on http://127.0.0.1:5173
REM    run.bat build      produce a production build in frontend\dist
REM
REM  The app runs entirely in your browser. No backend, no API key, no
REM  database and no Python are needed.
REM ==========================================================================

setlocal
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
set "FRONTEND=%ROOT%frontend"
if "%PORT%"=="" set "PORT=5173"

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js / npm was not found.
    echo         Install Node.js 18 or newer from https://nodejs.org
    echo         and re-open this terminal so PATH picks it up.
    exit /b 1
)

if not exist "%FRONTEND%" (
    echo [ERROR] Could not find the "frontend" folder next to this script.
    exit /b 1
)

if not exist "%FRONTEND%\node_modules" (
    echo [1/2] Installing dependencies ^(first run takes a minute^)
    pushd "%FRONTEND%"
    call npm install
    if errorlevel 1 (
        popd
        exit /b 1
    )
    popd
)

if /i "%~1"=="build" goto :build

REM --- run -------------------------------------------------------------------
echo [2/2] Starting TeacherCopilot on http://127.0.0.1:%PORT%
echo.
echo   Sign in with    demo@teachercopilot.app / demo1234
echo   Press Ctrl+C to stop.
echo.
pushd "%FRONTEND%"
call npm run dev -- --port %PORT%
popd
exit /b %errorlevel%

:build
echo [2/2] Building for production into frontend\dist
pushd "%FRONTEND%"
call npm run build
popd
echo.
echo To preview the production build:  cd frontend ^&^& npx vite preview
exit /b %errorlevel%