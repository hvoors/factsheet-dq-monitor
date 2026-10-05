$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$projectRoot\.venv\Scripts\python.exe" -m uvicorn app:app --app-dir "$projectRoot\backend" --host 127.0.0.1 --port 80 --reload
