$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --onefile --windowed --name '口琴助手录音版' --distpath '.' --workpath build --specpath build --add-data "$PSScriptRoot/models/basic_pitch.onnx;models" --hidden-import scipy.signal --collect-submodules scipy._external --collect-all onnxruntime app.py
if ($LASTEXITCODE -ne 0) { throw '打包失败，请查看上方错误。' }
