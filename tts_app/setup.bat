@echo off
rem Windows: double-click this file. Installs Git Bash if it is missing, then runs setup.sh.
setlocal
cd /d "%~dp0"

call :find_bash
if not defined GITBASH (
    echo Git Bash not found - installing Git for Windows...
    where winget >nul 2>nul || goto :no_winget
    winget install -e --id Git.Git --silent --accept-package-agreements --accept-source-agreements
    call :find_bash
)
if not defined GITBASH goto :no_winget

"%GITBASH%" setup.sh
if errorlevel 1 (echo. & echo Setup failed - see the messages above.) else (echo. & echo To start the app later: double-click start.bat)
pause
exit /b

:find_bash
rem Git's own bash, not C:\Windows\System32\bash.exe, which is WSL
set "GITBASH="
for %%P in ("%ProgramFiles%\Git\bin\bash.exe" "%LOCALAPPDATA%\Programs\Git\bin\bash.exe") do (
    if not defined GITBASH if exist "%%~P" set "GITBASH=%%~P"
)
exit /b

:no_winget
echo Could not install Git automatically.
echo Install it from https://git-scm.com/download/win and double-click setup.bat again.
pause
exit /b 1
