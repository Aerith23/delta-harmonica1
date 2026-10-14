# Delta Harmonica · 口琴助手

第一阶段：录制电脑正在播放的声音，为后续音源分离、音频转谱提供 WAV 素材。

## 使用

1. 双击 `口琴助手录音版.exe`，不需要安装 Python，也不需要原软件的激活密钥。
2. 在“录音来源”选择音乐实际播放的耳机或扬声器。系统默认输出已标注。
3. 点击“开始录制”。此时显示“等待声音”，不创建空白录音。
4. 在音乐软件或网页中播放音乐。有声音时开始计时、写入文件。
5. 点击“停止并保存”，文件保存到 EXE 同目录的 `recordings`，也可更改目录。
6. 在素材列表选择录音，点击“试听 / 停止”；点击“打开保存目录”查看 WAV。

这里只跳过开头静音；开始录制后，乐句之间以及结尾的静音均保留。关闭窗口也会请求停止并保存。

## 起录灵敏度

默认阈值 -60 dBFS，依据所有声道的采样峰值判断起录。低于阈值的开头被视作静音。
数值越低越灵敏：很轻的音乐未触发时，可调整到 -70 或 -80 dBFS；背景底噪导致误触发时可调高。
从首次达到阈值的完整采样帧开始保存，不按整块粗略裁剪。首次触发后不再应用静音门限。
所有电脑声音（包括通知声）都可能触发录音；此版本不判断声音是否是音乐。

## 音频与运行

- Windows 64 位，WASAPI 回环录音，不录麦克风。
- 16-bit PCM WAV，保留所选设备原始采样率和声道数。
- 采用流式写盘，不将整首歌曲缓存在内存中。
- 录制中禁止切换设备／目录，避免文件格式和来源中途变化。
- 蓝牙耳机断开、录音溢出或磁盘写入失败会报错；尽可能保留已录部分。
- 录音先写 `.partial.wav`，正常完成后改为 `.wav`。进程被强制终止时可能留下临时文件。
- 达到约 3.5 GB 自动停止，避免超过标准 WAV 的大小限制。
- 输出设备变动后点击“刷新设备”。本版不自动跟随 Windows 中途切换的输出。
- 此阶段不包含人声分离、音频转谱、游戏演奏或 LangChain。

## 代码结构

```text
app.py                       Tkinter 界面与主线程事件处理
recorder.py                  WASAPI 回环、起录门限、WAV 写入
tests/test_recorder.py       静音门限、声道对齐、音符停顿测试
tests/loopback_check.py      本机音频集成检查（会播放两段短测试音）
requirements.txt            运行依赖
requirements-build.txt      打包依赖
requirements-lock.txt       本次构建环境的完整依赖版本
build.ps1                   打包命令
recordings/                 用户录音，不提交到 Git
```

## 开发

在本目录打开 PowerShell，建议 Python 3.13 x64。已提供的 `.venv` 是本机开发环境，移动项目或换电脑后请重新创建。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

手动音频验证（先暂停其他音源；测试录音放在临时目录并在测试结束后清理）：

```powershell
.\.venv\Scripts\python.exe tests/loopback_check.py
```

重新构建前关闭正在运行的录音版 EXE：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1
```

此版本使用 Windows 音频设备，因此桌面录音组件直接运行在 Windows；后续音频处理服务可以单独部署到 Docker。

## 已验证

7 项静音门限单元测试通过。本机 48 kHz 双声道 WASAPI 测试通过：等待声音、跳过开头静音、保留两个测试音之间的停顿、保存可读 WAV、连续第二次录音无声不生成文件。
测试设备：Monitor (NVIDIA High Definition Audio)。HyperX 耳机已成功枚举，未进行该设备的播放实测。

## 第三方

录音库：[PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch)，基于 PyAudio / PortAudio。
打包器：[PyInstaller](https://pyinstaller.org/)。第三方许可见 `第三方许可/`。


## 项目目录与 Git

后续开发以 `C:/Users/Administrator/Desktop/delta-harmonica` 为唯一工作目录。
本仓库已迁入录音功能的源码、测试、构建文件、独立 EXE、现有录音和原曲库。
原目录保留作备份；原商业软件的 EXE、授权数据和打包运行库不属于新软件。
`曲库/` 为迁入的参考素材，目前录音页面尚未接入曲谱播放。

Git 跟踪源码、依赖版本、文档和测试；EXE、录音、曲库、模型、虚拟环境、构建缓存不提交。
修改后先运行测试，再用 `git diff` 检查，并仅暂存本次改动。不要将 API 密钥写入代码。
提交使用 `feat:`、`fix:`、`test:`、`docs:`、`chore:` 等前缀，推送远端前核对差异。

后续计划：音源分离 → 音频转谱 → JSON/MIDI 曲库与演奏 → 独立 LangChain 参数解析服务。
桌面录音留在 Windows，后续模型服务用于练习 FastAPI 和 Docker 部署。
