$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --onefile --windowed --name '口琴助手录音版' --distpath '.' --workpath build --specpath build app.py
if ($LASTEXITCODE -ne 0) { throw '打包失败，请查看上方错误。' }
