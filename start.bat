@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 run.py %*
  goto done
)
where python >nul 2>nul
if not errorlevel 1 (
  python run.py %*
  goto done
)
echo Нужен Python 3.10 или новее: https://www.python.org/downloads/
echo При установке отметьте Add Python to PATH.
:done
pause
