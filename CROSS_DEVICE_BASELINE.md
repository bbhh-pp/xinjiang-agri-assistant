# 跨设备改造前基线（2026-10-19）

本记录只描述当前代码和本机数据；没有读取或记录任何 API 密钥。此阶段没有修改数据库结构或草原主页。

## 页面与缓存

- `server.py` 的 `/` 只返回 `web/index.html`。`design-previews/` 中的方案页和 `asr-test/` 中的识别测试页不是正式主页。
- 正式主页加载 `web/grassland.css`、`web/ui_locale.js`、`web/app.js`，三者使用相同版本参数 `responsive-home-2026-10-19-1`；`server.py` 的 `BUILD_ID` 也为该值。
- HTML 响应使用 `Cache-Control: no-store`，静态资源使用 `no-cache`。CSS 在 700px 和 400px 设置窄屏布局，项目没有按设备返回不同 HTML 的分支。
- 浏览器 `localStorage` 保存当前对话 ID 和界面语言；这些选择不会自动跨设备同步。

## 服务、接口与数据

- `start.cmd` 调用 `start.ps1`，将端口设为 8767 并运行 `server.py`。`server.py` 监听 `127.0.0.1`；手机上的 `127.0.0.1` 指手机自己，不能访问这台电脑的本地服务。
- 现有文字、语音、图片与对话历史接口都由该本地服务提供。当前没有账号登录、用户所有权检查或跨设备同步机制。
- `conversation_store.py` 默认使用 `data/conversations.sqlite3`。数据库含 `conversations` 和 `turns` 两张表，后者通过 `conversation_id` 关联前者；没有用户表或 `user_id`。
- 检查时数据库有 2 段对话、5 轮记录。原始输入、中文问题、图片文字观察结果及中维回答属于待迁移的现有数据；数据库不存图片和录音二进制。
- 本次使用 SQLite 在线备份 API 保存到 `data/backups/conversations-20261019-175417.sqlite3`，备份 `PRAGMA quick_check` 为 `ok`。没有执行任何 schema migration。
- 检查时本机 8767 端口没有监听进程，因此只能确认源码版本，不能确认用户之前手机和电脑实际访问的是哪个运行版本。

## 手机与电脑差异的已确认边界

同一服务的正式主页是同一份 HTML，窄屏通过响应式 CSS 改变布局。若两端看到完全不同的主页，需要对照各自的完整 URL、`/api/health` 的 `build`、资源请求状态和浏览器缓存来定位；目前没有手机端实际 URL，不能据此断定具体是哪一个原因。公网开放前，需要先实现账号隔离与服务端会话安全。

## 下一步迁移会影响的部分

增加账号和跨设备历史时，需要给已有 `conversations` 记录确定归属，同时保持 `turns` 外键和已有回答完整；更新对话创建、列表、读取、删除、追问和翻译补全接口的授权范围；把浏览器当前对话选择与已登录用户关联。迁移前应再次生成并校验数据库备份，不能把现有 2 段对话混入其他用户账号。
