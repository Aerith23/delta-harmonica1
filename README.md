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
- 此阶段包含音频转谱，不包含人声分离、游戏演奏或 LangChain。

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

## 启动时报缺少 pyaudiowpatch

双击 `启动源码.cmd`。该入口固定使用本项目 `.venv/Scripts/python.exe`，无需手动激活环境。
也可以在本目录执行 `.\.venv\Scripts\python.exe app.py`。
不要依赖系统默认的 `python` 或直接双击 `.py` 文件，它们可能指向未安装依赖的 Anaconda 环境。
依赖包名称为 `PyAudioWPatch`，代码导入名称为 `pyaudiowpatch`。
需要补装时执行 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`。


## 录音转 JSON

在“已录制文件”列表选择 WAV，点击“转换为 JSON”。后台使用本地 Basic Pitch ONNX 音符模型，界面显示进度，可取消。
默认“单音简化”根据力度、音区和连续性选择一条声部并截断重叠；“保留所有音符”保留识别出的多音。
单音简化是启发式处理，不等同于人声分离或保证识别主旋律。复杂完整歌曲可能出现伴奏、错音和漏音，优先使用清晰独奏或器乐录音。
默认保存到 `曲库/曲谱/录音名称.json`；同名时添加唯一后缀，不覆盖已有曲谱。原 WAV 保留。
格式与原有 110 首曲谱一致：`harmonica-score-v1`，`pitch` 为 MIDI 整数，`start` / `duration` 为秒，`velocity` 为 1–127，`track` / `channel` 为 0。
输出保留录音的休止时间和原音高；`studio.auto_adapt` 开启，供后续口琴编排模块适配音域。
模型随 EXE 打包，本机离线运行，无需登录和上传录音。
源码开发首次准备模型：`.venv/Scripts/python.exe scripts/setup_model.py`；模型来源和 SHA-256 在 `model-manifest.json`，下载需联网。
单文件最长 12 分钟。空录音或未识别到音符会给出提示，不保存空曲谱。

模型端到端检查（合成 C4/E4/G4，不播放声音）：`.venv/Scripts/python.exe tests/transcription_smoke.py`。
模型：[Spotify Basic Pitch](https://github.com/spotify/basic-pitch)，Apache-2.0，许可见 `第三方许可/Spotify-Basic-Pitch-LICENSE.txt`。
推理、重采样和音符解码封装在 `transcription.py`，后台只通过消息队列更新界面。

## 转谱验证记录

本次版本已通过 16 项单元测试，其中读取并校验全部 110 首已有 JSON。
界面测试覆盖列表可见、转换期间按钮禁用、完成恢复和取消流程。
实际 ONNX 模型已将合成的 C4 / E4 / G4 识别为 MIDI 音高 60 / 64 / 67；独立 EXE 同样通过此测试。
空音频、取消任务不生成曲谱；重复转换不会覆盖此前生成的 JSON。
合成音测试用于验证端到端链路，不能代表复杂真实混音的识别精度。
