# Oracle Always Free + Tailscale Funnel 演示部署

本指南仅为比赛演示准备；它不会自动创建 Oracle 或 Tailscale 资源，也不保证账号能申请到免费实例。只在 Oracle 控制台明确显示 **Always Free Eligible** 时创建资源；若提示升级、试用额度或可能收费，停止操作。

## 方案和边界

- 使用 Oracle Cloud VM.Standard.A1.Flex 的 Always Free 配额（官方当前列为合计最多 2 OCPU、12 GB 内存，需在 home region 创建）。这比 1 GB 的 AMD Micro 更适合当前包含约 279 MB 维语模型的服务，但要在目标机实际跑模型确认性能。
- 使用 Ubuntu ARM64。容器安装系统 FFmpeg，避免依赖打包了平台专用 FFmpeg 二进制的 Python wheel。ONNX Runtime 官方支持 Python CPU 安装，但是否能在当前 ARM 镜像上成功取得兼容 wheel、加载项目模型并完成推理，必须用目标 ARM 构建和实机发布检查确认。
- Tailscale Funnel 为 Tailscale 官方所称的 beta 功能；公开生成的 `*.ts.net` HTTPS 地址。老师只用浏览器，不需要 Tailscale 客户端。它有不可配置的带宽限制；Oracle Always Free 实例可能因连续低利用率被回收，区域也可能暂时无免费容量，所以不能视为有 SLA 的长期服务。
- 数据库放在 Docker 持久卷。容器更新和 VM 重启不会自行清空历史；删除 VM 或 Docker 卷仍可能丢数据，必须先备份。
- 共享 `admin` 账号的现有 SQLite 配额默认 3 次/分钟、20 次/日，适用于全体共享账号使用者。Funnel 的普通 HTTP 反向代理不会把访问者真实 IP 交给应用，因此这套准备采用账号级共享总限额，不信任用户可伪造的转发头；如比赛期间需要 IP 级限额，需另行部署支持受信代理地址的 IP 透传方案。
- 项目当前使用的维语 ONNX 文件来源仓库没有找到明确许可证。部署前应取得该模型的使用/托管许可；哈希校验只验证文件版本，不能证明授权。

## 本地准备文件

- `Dockerfile`：Python 3.12、CPU ONNX Runtime，构建时下载并校验固定 SHA-256 模型；系统安装 FFmpeg。
- `compose.oracle.yaml`：只将应用端口绑定到服务器 `127.0.0.1:8000`，不启用 Caddy，也不把应用端口暴露到公网；SQLite 使用持久卷。
- `.env.oracle.example`：无真实密钥的服务器配置模板。部署时在服务器复制为 `.env.oracle`，并收紧文件权限。

## 你在控制台需要完成的事

1. 注册/登录 Oracle Cloud Free Tier。创建实例时选 home region 中明确标记 **Always Free Eligible** 的 Ubuntu ARM64 VM.Standard.A1.Flex；总资源不要超过 Always Free 额度。不要升级账号，不要继续任何付费或不明确的确认页。
2. 记录实例的公网 IP、SSH 用户名和 SSH 登录方式。公网安全列表仅允许你管理用的 SSH 来源；不要开放 TCP 8000、80 或 443。Funnel 通过 Tailscale 建立出站隧道。
3. 注册/登录 Tailscale 免费账号，启用 MagicDNS、HTTPS 证书及 Funnel 策略。在服务器安装 Tailscale 并 `tailscale up`。不要把 Tailscale auth key 贴到聊天或写进仓库。
4. 安装 Docker Engine 与 Compose 插件，把本项目部署文件传到服务器。复制模板并在服务器安全终端自行填入神农、腾讯 TokenHub、讯飞服务密钥：

   ```bash
   cp .env.oracle.example .env.oracle
   chmod 600 .env.oracle
   nano .env.oracle
   ```

   编辑器里输入密钥，不要在命令参数、终端回显、截图或日志里输入密钥。

5. 先构建 ARM64 镜像并运行本地发布检查。若 Docker 构建、ONNX Runtime ARM wheel 安装、模型加载、FFmpeg 或本地识别任何一步失败，先停止，不改买收费服务器：

   ```bash
   docker compose -f compose.oracle.yaml build
   ```

   真实部署时还需要服务器环境中的密钥、数据库和 HTTPS 源地址，所以 `scripts/release_check.py` 应在配置完成后运行；它只显示配置项名称，不打印密钥值。

6. 先启动本机回环应用并检查 `http://127.0.0.1:8000/api/health`，再在服务器运行 Funnel：

   ```bash
   tailscale funnel --bg --https=443 http://127.0.0.1:8000
   tailscale funnel status
   ```

   Funnel 会给出 `https://<服务器名>.<tailnet>.ts.net`。把该 HTTPS 源地址写入服务器 `.env.oracle` 的 `SHENNONG_PUBLIC_ORIGIN`，然后重启容器。应用端口仍然只绑定回环地址。

7. 从另一台设备打开最终 HTTPS 地址，完成登录、历史读取、中文文字短问、维语翻译链路和 SSE 验证。首次上线只做一次短真实 API 问答；这些模型/翻译/合成调用可能产生 API 费用，与免费服务器费用分开。

## 现有演示账号和历史

当前本机数据库已有一个启用的 `admin` 账号、2 段对话和 5 轮历史。账号密码只以 scrypt 哈希保存，本地数据库文件为 `data/conversations.sqlite3`。部署前应把它复制到服务器并先在服务器上备份目标数据库，然后通过 `scripts/migrate_sqlite.py` 迁移；不要初始化空库、不要运行 `init-admin` 覆盖现有账号。登录用户名为 `admin`，密码使用你当前已有的管理员密码。若忘记密码，在服务器 Compose 服务中交互式重置（隐藏输入）：

```bash
docker compose -f compose.oracle.yaml exec app python manage_users.py reset-password admin
```

不要把密码放进命令行参数。共享登录意味着老师共同看到并续写同一份历史；比赛结束后可重置密码或关闭 Funnel。

迁移数据库前，在服务器 `/var/lib/shennong/` 做 SQLite 一致性备份并确认剩余空间；停掉应用后再迁移。迁移完成用只读统计比对账号数、对话数、轮次数，并运行 `PRAGMA quick_check`。完成公网测试后保留该备份，不能删除本机原数据库。

## 服务控制和关闭公网

应用：

```bash
docker compose -f compose.oracle.yaml stop
docker compose -f compose.oracle.yaml start
docker compose -f compose.oracle.yaml logs --tail=100 app
```

关闭公网 Funnel（HTTPS 443）：

```bash
tailscale funnel --https=443 off
```

也可在 Tailscale 管理控制台撤销 Funnel 的 node attribute。VM 重启时 Docker `restart: unless-stopped` 会启动服务；Tailscale Linux 守护进程随系统运行，使用 `--bg` 创建的 Funnel 会在重启后恢复。老师访问不依赖你的个人电脑。

## 当前状态

此配置尚未发布。当前工作站没有 Docker 或 Tailscale CLI，也未检测到 `.env.production`；没有 Oracle/Tailscale 服务器账号信息。真实 ARM64 镜像构建、模型实机推理、数据库上传迁移、公网 HTTPS、麦克风、图片和远程 SSE 都尚待账号与实例可用后测试。不要把未执行的步骤当成已验证。
