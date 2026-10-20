# 腾讯 Hy-MT2-Plus 农牧业术语库

本目录由 `generate_tencent_glossary.py` 从根目录的 `维文标准对照表_更正版.txt` 生成，共 402 个去重术语对。

腾讯官方术语库管理接口不是 TokenHub Bearer Key 接口。创建和维护术语库需要腾讯云 API 3.0 的 TC3-HMAC-SHA256 鉴权（SecretId/SecretKey），请求域名为 `hunyuan.tencentcloudapi.com`，版本 `2023-09-01`。

1. 在腾讯云 API Explorer 选择 **腾讯混元大模型 → 混元翻译相关接口 → CreateGlossary**。
2. 创建 `Source=ug, Target=zh` 的术语库，并记录真实 `GlossaryId`。
3. 创建 `Source=zh, Target=ug` 的术语库，并记录真实 `GlossaryId`。
4. 选择 **CreateGlossaryEntry**，把对应方向的 `create-entries-01.json` 至 `create-entries-05.json` 逐批导入。官方单次限制 100 条；把文件中的占位 `GlossaryId` 替换成控制台返回的真实 ID。
5. 抽查 `terms.tsv` 中的标准词义；它是便于人工检查的 UTF-8 BOM 表格，不代表控制台一定支持直接上传文件。
6. 将两个真实 ID 分别保存为 Windows 用户环境变量 `TENCENT_GLOSSARY_UG_ZH_ID` 和 `TENCENT_GLOSSARY_ZH_UG_ID`，然后重启 `start.cmd`。

没有配置术语库 ID 时，网页仍会把当前文本中高置信命中的最多 10 个词对放入官方 `context` 字段，不会伪造 ID。
