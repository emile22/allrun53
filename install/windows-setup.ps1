$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    py -3.11 -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install -e ".[test]"
    & .\.venv\Scripts\python.exe --version
} finally {
    Pop-Location
}
