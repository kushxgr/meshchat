param(
    [string]$Python = "C:\Users\Manas Mishra\AppData\Local\Programs\Python\Python312\python.exe"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not (Test-Path "$Python")) {
    throw "Python executable not found: $Python"
}

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