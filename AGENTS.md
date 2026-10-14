# 开发约定

- 本项目的工作根目录是 `C:/Users/Administrator/Desktop/delta-harmonica`。
- 使用此目录的虚拟环境，禁止再往原口琴工坊发行版目录添加功能。
- 用户希望通过本项目学习 Git、Docker 和 LangChain；修改时说明用途和验证方式。
- 当前已实现系统回环录音。录音前仅过滤开头静音，起录后必须保留音乐内部停顿。
- `app.py` 负责界面；`recorder.py` 负责音频捕获和保存，保持两者解耦。
- 测试：`.venv/Scripts/python.exe -m unittest discover -s tests -v`。
- 硬件集成测试会播放测试音，不要自动重复执行或提交录音文件。
- 不提交 EXE、模型、录音、曲库、虚拟环境、缓存或密钥。
- 保留用户已有的修改与暂存区操作，只提交当前任务相关文件；不自动推送远端。
- LangChain 阶段先使用固定流程，不引入 Agent；音频转谱由音乐模型处理。
