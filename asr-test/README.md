# 独立维语语音识别测试页

测试对象：[gheyret/uyghurasr_python](https://github.com/gheyret/uyghurasr_python) 的 ONNX 模型。此目录不调用神农，不改主网页，也不上传录音到第三方服务。模型本地推理的输出是**拉丁维文**；本页不做翻译。

首次使用：双击 `install-model.cmd`。安装脚本仅给主项目已有的 `.venv` 增加 `onnxruntime`，并从原仓库 GitHub Release 下载约 279 MB 的模型至本目录 `model`。网络无法下载时，手动打开[模型下载页](https://github.com/gheyret/uyghurasr_python/releases/tag/tunji)，将 `uyghur_asr.onnx` 放入本目录的 `model` 文件夹。

然后双击 `start.cmd`，保持黑色启动窗口打开，在普通浏览器访问 **http://127.0.0.1:8766/**。允许浏览器使用麦克风，按住页面上的按钮说话，松开后页面会自动用本机模型识别并显示拉丁维文。最长 45 秒；录音发送到本机服务进行识别，不会发送给神农或第三方。

原仓库未标明明确的开源许可证。此页仅作个人本地评估；决定纳入公开产品前，需确认模型与代码的使用授权。
