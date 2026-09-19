@echo off
setlocal enabledelayedexpansion
title Enhance Audio - DJI Mic

if "%~1"=="" (
  echo.
  echo   Drag one or more video or audio files onto this file.
  echo.
  echo   Each one gets written back out next to the original as
  echo   NAME_audio-enhanced.mp4 -- video untouched, audio rebuilt
  echo   with the "voice" preset.
  echo.
  pause
  exit /b 1
)

:loop
echo.
echo ============================================================
echo   %~nx1
echo ============================================================
python "%~dp0src\enhance_audio.py" "%~1"
if errorlevel 1 (
  echo.
  echo   FAILED on %~nx1
)
shift
if not "%~1"=="" goto loop

echo.
echo   All done.
pause
