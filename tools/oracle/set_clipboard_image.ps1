# set_clipboard_image.ps1 — poe uma imagem no clipboard (STA) pra colar (Ctrl+V) no ChatGPT.
# Metodo provado (file_upload falha p/ paths do repo; clipboard+Ctrl+V funciona).
# Uso:  powershell -STA -NoProfile -ExecutionPolicy Bypass -File set_clipboard_image.ps1 -Path "C:\...\img.png"
param([Parameter(Mandatory = $true)][string]$Path)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$b = [System.Drawing.Image]::FromFile($Path)
[System.Windows.Forms.Clipboard]::SetImage($b)
$b.Dispose()
Write-Output "clipboard <- $Path"
