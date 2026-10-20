param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not $Python -or -not (Test-Path $Python)) {
    $candidates = @(
        $env:PYTHON,
        (Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:SystemDrive\Python\python.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

    if (-not $candidates) {
        throw "Python executable not found. Pass -Python to build_app.ps1 or install Python first."
    }

    $Python = $candidates
}

& $Python -m pip install --upgrade PyInstaller
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --name MeshChatStudio `
    --windowed `
    --onefile `
    --icon "assets\mesh_chat.ico" `
    --add-data "topology_chain3.json;." `
    --add-data "topology_demo.json;." `
    --add-data "assets\mesh_chat.ico;assets" `
    app.py