# 神农农牧助手：本地演示网页

## 当前使用方式

当前版本为本机免登录模式：打开网页无需账号或密码。问答历史保存在本机 `data/conversations.sqlite3`，刷新页面或重启服务后仍可查看；此前数据库中的历史记录也会显示。网页只监听本机 `127.0.0.1:8767`，没有公网链接，电脑关机时无法访问。

首次使用时配置神农和腾讯 TokenHub 环境变量；需要维语语音时安装本地 ONNX 模型，需要维语朗读时配置讯飞环境变量。之后双击项目根目录的 `start.cmd`，在浏览器打开 `http://127.0.0.1:8767/`。这是本机演示页面，不需要登录、账号或密码。

当前支持中文文字、中文语音、阿拉伯维文文字、维语语音和图片识别。维文先由腾讯 TokenHub `hy-mt2-plus` 翻成中文，神农 `sn` 只生成中文回答，完成后再由腾讯翻译成阿拉伯维文。中文回答流式显示；回答只在点击对应喇叭时朗读。

界面语言选择保存在当前浏览器。历史问答保存在这台电脑，不会自动同步到其他电脑。换一台电脑需要在那台电脑单独准备项目和 API 环境变量。

项目里保留了此前的云部署和账号管理文件，但当前本地启动流程不会使用它们。

## 维语识别模型：安装、推理

主网页使用 [gheyret/uyghurasr_python](https://github.com/gheyret/uyghurasr_python) ONNX 模型。录音只发送到本机 `127.0.0.1` 服务并通过 FFmpeg 解码、本地推理；录音文件不会发送给神农或腾讯。识别和校正后的文字会交给腾讯翻译，只有译成的中文问题会交给神农。

首次安装请先准备主项目 `.venv`，然后双击 `asr-test\install-model.cmd`。它会安装 `onnxruntime` 与 `imageio-ffmpeg`，并下载模型至 `asr-test\model\uyghur_asr.onnx`。主网页和独立测试页共用这份模型文件。

完成安装后双击项目根目录的 `start.cmd`，在普通浏览器打开 **http://127.0.0.1:8767/**。选择“中文语音”并允许麦克风后，按住按钮说普通话，松开后浏览器识别并把结果放入“文字提问”框，核对或修改后再点击“获取回答”。识别过程中可点击“停止识别”丢弃本次结果。选择“维语文字”可输入阿拉伯维文；选择“维语语音”时按住按钮说话，松开后等待本机识别和神农双语回答。识别或回答过程中可点击“停止识别与回答”取消页面本次请求并立即重新提问。页面显示维语识别稿及中维回答；点击各语言旁的喇叭按钮才会尝试朗读，不会自动播放。

项目原有 Whisper 训练脚本仍保留，但与网页当前使用的 ONNX 识别模型分开；训练所得模型不会自动替换网页识别器。

## 用标注语音继续训练，提高准确率

需要**录音和人工校对的维语原文**，仅有录音不能直接做有监督微调。建议先把录音切为每条 3–30 秒、一条对应一句或一段文字，统一维语文字规范、数字与标点。将不同说话人的语音分别分到训练集与验证集；如果有条件，再保留完全独立的测试集。农牧业术语、方言、噪声环境应在训练中有代表性。现有的五段 MP3 尚无对应标注清单，所以项目不会把它们当成训练标签。

准备 UTF-8 CSV，例如 `data/labels.csv`。`audio` 可以是相对 CSV 所在文件夹的路径，也可用绝对路径；`speaker_id` 建议填写，不同 split 不能有同一说话人：

```csv
audio,text,split,speaker_id
clips/001.wav,这里填写该录音人工校对的维语原文,train,person_01
clips/002.wav,这里填写另一段人工校对的维语原文,validation,person_02
```

上面的中文只说明格式，训练时必须换成真实的维语原文。先检查路径、空标签、重复音频和说话人泄漏：

```powershell
.\.venv\Scripts\python.exe .\train_uyghur_asr.py --manifest .\data\labels.csv --validate-only
```

然后训练。以下命令从 **Rekipjan 的合并模型**继续做 LoRA 微调，不会从零训练 Whisper：

```powershell
.\.venv\Scripts\python.exe .\train_uyghur_asr.py --manifest .\data\labels.csv --output .\training-output --epochs 5
```

每轮会输出训练 loss、验证集 WER（词错误率）和 CER（字错误率）。查看 `training-output/validation-results.txt` 中每条预测与参考文本，纠正常见的错标和术语。最佳 LoRA 适配器保存在 `training-output/best-adapter/`；默认还会导出完整模型到 `training-output/merged/`。在 PowerShell 中选用新模型：

```powershell
$env:UYGHUR_ASR_MODEL_DIR = (Resolve-Path .\training-output\merged).Path
.\start.ps1
```

训练前后请用**同一份未参与训练的测试集**比较 WER/CER。验证集用于挑选轮次，不能当作最终证明。数据太少时应优先补充并校对录音，单纯增加轮次可能过拟合。大致可从数小时不同说话人的标注语音开始实验；实际需要的数据量取决于口音、噪声与术语范围。

## 启动

维语识别首次安装时，先双击 `asr-test\install-model.cmd`。首次配置依次运行 `save-key.cmd` 保存神农密钥、运行 `save-tencent-key.cmd` 保存腾讯 TokenHub 密钥，并按需运行 `set-xfyun-tts-key.cmd` 配置维语朗读。之后双击项目根目录的 `start.cmd`，保持启动窗口打开，然后在普通浏览器打开 **http://127.0.0.1:8767/**。无需登录。结束时在启动窗口按 Ctrl+C。

如果习惯使用 PowerShell，也可以在本目录运行：

```powershell
.\start.ps1
```

`save-key.cmd` 会把神农密钥保存在当前 Windows 用户的环境变量中，不会写入网页或项目代码。以后启动脚本会自动读取，无须每次输入。未保存神农密钥时，网页仍可直接打开，问答功能需配置密钥后重启服务才能使用。不要把密钥发送给别人，也不要把它写入网页文件。Windows 用户环境变量适合本机开发；正式部署时应使用服务器的密钥管理功能。

`save-tencent-key.cmd` 同样把 `TENCENT_TOKENHUB_API_KEY` 保存在 Windows 用户环境变量，并设置大陆 TokenHub 地址与 `hy-mt2-plus`。可选的持久化术语库 ID 使用 `TENCENT_GLOSSARY_UG_ZH_ID` 和 `TENCENT_GLOSSARY_ZH_UG_ID`。没有配置术语库 ID 时，程序仍会把本次命中的最多 10 个标准词对通过翻译上下文传入。

`tencent-glossary\ug-zh` 与 `tencent-glossary\zh-ug` 中包含从更正版词表生成的双向 TSV 和每批最多 100 条的 `CreateGlossaryEntry` JSON。术语库管理接口位于 `hunyuan.tencentcloudapi.com`，使用腾讯云 API 3.0 的 TC3 鉴权；TokenHub Bearer Key 不能代替 SecretId/SecretKey。请先在腾讯混元术语库控制台/API Explorer 创建 `ug→zh` 和 `zh→ug` 两个术语库，再按批导入条目，把真实 ID 保存到上述两个环境变量。项目不会生成或猜测 ID。

维吾尔语朗读使用讯飞在线语音合成。首次配置时运行 `set-xfyun-tts-key.cmd`，按提示输入 TTS 服务的 APPID、APIKey 和 APISecret（输入时不会显示），发音人默认使用 `x2_ugsp_dilare`。凭据保存在当前 Windows 用户环境变量中；配置后重新运行 `start.cmd`。回答生成后，只有点击维吾尔语回答右上角喇叭才会请求讯飞并播放；中文喇叭仍使用电脑本地语音。维文合成要求该发音人在讯飞控制台已开通，试用或授权到期后需在讯飞控制台处理。

如果 PowerShell 阻止脚本运行，可以在项目目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

本服务默认只监听这台电脑的 `127.0.0.1`，尚未对公网开放。

## 图片提问

打开网页后点“图片识别”，选择一张清晰的 JPG 或 PNG 照片（最多 4 MB），可补充一句中文问题。页面会预览照片，回答区先显示图片初步观察，再显示神农建议。识别到空白、模糊或非农牧业图片时会提示重拍；模型识别仍可能出错，不能把照片建议当作确诊。为了让识别更可靠，建议分别拍异常部位近照和整株或牲畜全身照；当前页面每次只上传一张。

神农[官方开发文档](https://api.agent-tech.cc/docs)说明其同一接口支持 Base64 图片，也提供农作物病虫害和部分牲畜照片的相关能力。本实现直接使用现有神农密钥和接口，不新增视觉服务账户。每次图片提问会调用神农两次：先观察图片，再结合观察结果回答。官方文档当前标明按输入和输出 token 计费，`sn` 每次调用另计 ¥0.1；两次调用约产生 ¥0.2 的固定调用费，另有 token 费用，实际以账户账单为准。项目不会自动开通付费服务。

`tests/wheat-leaf-rust.jpg` 是公开测试照片，来源为[维基共享资源的美国农业部小麦叶锈病照片](https://commons.wikimedia.org/wiki/File:Wheat_leaf_rust_on_wheat.jpg)，可用于核对上传链路。真实照片识别结果需要结合田间情况复核。

## 开源许可证

本项目以 [MIT License](LICENSE) 开源。下载的第三方模型、测试素材和外部服务仍分别受其原始许可证与服务条款约束。
