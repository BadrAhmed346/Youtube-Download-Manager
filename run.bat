@echo off
setlocal
set "APP_DIR=%~dp0app"
cd /d "%APP_DIR%"
echo.
echo ======================================
echo   YouTube Download Manager - Startup
echo ======================================
echo Checking the required software...

where py >nul 2>nul
if errorlevel 1 (
  echo Python is needed for the first run. Installing it now...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo Windows Package Manager was not found.
    echo Install Python 3.10 or later from https://www.python.org/downloads/ then run this file again.
    pause
    exit /b 1
  )
  echo Downloading and installing Python. This may take a minute...
  winget install --id Python.Python.3.13 -e --source winget --accept-package-agreements --accept-source-agreements
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python was installed, but Windows needs a new Command Prompt to find it.
    echo Close this window and double-click run.bat again.
    pause
    exit /b 0
  )
)

if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe --version >nul 2>nul
  if errorlevel 1 (
    echo Repairing the moved app environment...
    rmdir /s /q .venv
  )
)

if not exist .venv\Scripts\python.exe (
  echo Creating the app's private Python environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :setup_failed
)

echo Checking and updating required libraries (yt-dlp, its YouTube challenge support, and Rich)...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check --upgrade -r requirements.txt
if errorlevel 1 goto :setup_failed
set "YTDL_FFMPEG_LOCATION="
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*") do (
  if exist "%%~fD\ffmpeg.exe" set "YTDL_FFMPEG_LOCATION=%%~fD"
  if exist "%%~fD\bin\ffmpeg.exe" set "YTDL_FFMPEG_LOCATION=%%~fD\bin"
)
if defined YTDL_FFMPEG_LOCATION goto :ffmpeg_ready
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo FFmpeg is needed to combine high-quality video and audio.
  echo Downloading and installing FFmpeg for first use...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo Windows Package Manager was not found, so FFmpeg could not be installed automatically.
    echo Install it with: winget install Gyan.FFmpeg
    pause
    exit /b 1
  )
  winget install --id Gyan.FFmpeg -e --source winget --accept-package-agreements --accept-source-agreements
  if errorlevel 1 goto :setup_failed
  for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*") do (
    if exist "%%~fD\ffmpeg.exe" set "YTDL_FFMPEG_LOCATION=%%~fD"
    if exist "%%~fD\bin\ffmpeg.exe" set "YTDL_FFMPEG_LOCATION=%%~fD\bin"
  )
  if not defined YTDL_FFMPEG_LOCATION (
    echo FFmpeg was installed but its location could not be found in this window.
    echo Close this window and double-click run.bat again.
    pause
    exit /b 0
  )
)
:ffmpeg_ready
where deno >nul 2>nul
if errorlevel 1 (
  if exist "%USERPROFILE%\.deno\bin\deno.exe" (
    set "PATH=%USERPROFILE%\.deno\bin;%PATH%"
  ) else (
    echo Installing Deno. YouTube needs it to solve current playback checks...
    where winget >nul 2>nul
    if errorlevel 1 (
      echo Windows Package Manager was not found, so Deno could not be installed automatically.
      goto :setup_failed
    )
    winget install --id DenoLand.Deno -e --source winget --accept-package-agreements --accept-source-agreements
    if errorlevel 1 goto :setup_failed
    if exist "%USERPROFILE%\.deno\bin\deno.exe" set "PATH=%USERPROFILE%\.deno\bin;%PATH%"
  )
)
echo.
echo Setup complete. Opening the download manager...
timeout /t 1 /nobreak >nul
cls
.venv\Scripts\python.exe youtube_download_manager.py
pause
exit /b %errorlevel%

:setup_failed
echo.
echo Setup failed. Check that Python and an internet connection are available, then try again.
pause
exit /b 1
