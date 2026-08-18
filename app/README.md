# YouTube Download Manager

A no-code Windows command-line downloader for YouTube videos and playlists that you are permitted to save.

## Start it

1. Install [Python 3.10+](https://www.python.org/downloads/) once, selecting **Add Python to PATH** in its installer.
2. Double-click `run.bat`. It displays every startup step, installs Python, the required packages, FFmpeg, and Deno automatically when they are missing.
3. Paste a YouTube link, choose from the displayed qualities and estimates, then select a save folder in the Windows dialog.

The app resumes partial downloads where possible and shows a live percentage, download size, speed, and time remaining.

## FFmpeg

Most high-quality YouTube formats provide video and audio separately. FFmpeg combines them into one playable MP4. The launcher installs it automatically on first use and passes its location directly to the app, so downloading can start in the same window.

Playlist quality is selected as a maximum resolution: each video downloads at that resolution or the best available below it. Reported sizes are for the first playlist video because each item may have different formats.
