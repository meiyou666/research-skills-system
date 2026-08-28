# 第三方搜索运行时核验

核验日期：2026-08-28

范围：在没有 Docker/Podman 的主机上，为深度检索能力选择可审查、可恢复的外部运行时。本文同时记录官方资料、环境探测和本次隔离安装验证；第三方源码、依赖、临时配置与 smoke-test 产物位于 Git 忽略的 `.runtime/`，不进入仓库提交。

## 结论

| 组件 | 本次定位 | 当前环境判断 | 最短可行路径 |
|---|---|---|---|
| GitHub CLI (`gh`) | 默认启用的代码、仓库、issue、PR、release 与 commit 连接器 | 官方 `2.98.0` 发行资产已校验并隔离安装；认证 API 与仓库连接器 smoke test 通过 | 将已校验 binary 置于调用方控制的 `PATH`，按 campaign 限额调用 |
| RSSHub | 可选的 RSS 生产服务；已有 RSS/Atom 源无需部署它 | 固定 commit 已按 lockfile 构建；回环监听、内存缓存、健康检查及通用 RSS connector 前向测试通过 | 只启动任务需要的路由；浏览器、Redis 与账号型路由另行授权和预算 |
| SearXNG | 可选的自托管元搜索发现入口 | 固定 commit 的用户态开发实例可启动，健康、JSON API 和连接器路径通过；当前网络无法访问所试上游引擎 | 本地研究可按受限开发路径使用；公开或长期服务仍需按官方系统部署完成 |

这三项均是采集连接器，不承担全文证据判定。搜索命中、snippet、README、issue 和评论仍是未核验证据。

## 环境与执行边界

| 项目 | 探测结果 |
|---|---|
| 操作系统 | Ubuntu 24.04，x86_64 |
| 容器运行时 | Docker、Podman 均不可用 |
| 基础工具 | Git `2.43.0`、curl `8.5.0` |
| Python | `3.13.12` |
| Node.js 工具链 | Node `24.18.0`、npm `11.16.0`、Corepack `0.35.0`；Corepack 按项目元数据提供 `pnpm 10.34.5` |
| 缓存/服务组件 | Redis、Valkey、uWSGI、nginx、`systemctl` 均不可用 |
| GitHub CLI | 宿主已有 `2.96.0`；另行校验并安装 `2.98.0`，认证调用成功，未读取或记录账号、scope、token |
| 权限与容量 | 非交互 sudo 不可用；约 66 GiB 可用磁盘 |

探测与本次 smoke test 只证明下文列明的版本、监听面和有界请求，不代表公开部署安全、全部路由/引擎兼容或负载容量。

## SearXNG

### 官方状态与固定版本

SearXNG 的 Python 包要求 `Python >=3.10`，许可证字段为 `AGPL-3.0-or-later`；这些信息可在核验 commit 的官方 [`setup.py`](https://github.com/searxng/searxng/blob/9fea41204fdfa7a5cfa15b0ebd12904c520478ce/setup.py) 核验。项目采用 rolling release，维护文档将 `master` 的每个 commit 视作一次 release，见官方 [update 指南](https://docs.searxng.org/admin/update-searxng.html)；GitHub Releases 页面没有另发 tagged release。本次审查固定到 2026-08-22 的 commit [`9fea41204fdfa7a5cfa15b0ebd12904c520478ce`](https://github.com/searxng/searxng/commit/9fea41204fdfa7a5cfa15b0ebd12904c520478ce)，提交历史见官方 [`master` commits](https://github.com/searxng/searxng/commits/master)，GitHub 发行状态见官方 [Releases](https://github.com/searxng/searxng/releases)。

项目许可证为 [`AGPL-3.0-or-later`](https://github.com/searxng/searxng/blob/9fea41204fdfa7a5cfa15b0ebd12904c520478ce/LICENSE)。作为外部服务使用或分发修改版前，应由采用方复核 AGPL 的网络交互与源代码提供义务。

### 无容器的官方安装路径

官方原生安装文档要求 Python venv、Git、编译工具及 Python/XML/SSL/FFI 开发包；Debian/Ubuntu 示例包含 `python3-dev`、`python3-babel`、`python3-venv`、`python-is-python3`、`uwsgi`、`uwsgi-plugin-python3`、`git`、`build-essential`、`libxslt-dev`、`zlib1g-dev`、`libffi-dev` 和 `libssl-dev`。完整、可随项目更新的清单以 [Step by step installation](https://docs.searxng.org/admin/installation-searxng.html) 为准。

官方自动化入口是：

```bash
git clone https://github.com/searxng/searxng.git
cd searxng
git checkout --detach 9fea41204fdfa7a5cfa15b0ebd12904c520478ce
sudo -H ./utils/searxng.sh install all
```

脚本会创建服务用户、Python 环境、设置和 uWSGI 集成；其组件还包括 Valkey、nginx 或 Apache，详见官方 [`searxng.sh` 参考](https://docs.searxng.org/utils/searxng.sh.html)和[安装脚本说明](https://docs.searxng.org/admin/installation-scripts.html)。`instance update` 会更新并重置源码状态，因此生产自动化应固定、审查并显式切换 commit，而不是无人值守地跟随分支。

当前主机没有非交互 sudo、uWSGI 或系统服务管理器，故上述官方系统安装路径不可直接完成。Python 版本达标不等于用户空间生产部署已成立；本次隔离开发实例仅用于验证 API 和 connector 边界，不作为公开服务的生产证明。

### 启动、健康与接口

官方开发检查使用 `python -m searx.webapp`，默认监听 `127.0.0.1:8888`；官方安装文档给出的 HEAD 检查应返回 HTTP 200，见 [Step by step installation](https://docs.searxng.org/admin/installation-searxng.html)。核验 commit 还注册了返回 `OK` 的 `GET /healthz`，见官方 [`searx/webapp.py`](https://github.com/searxng/searxng/blob/9fea41204fdfa7a5cfa15b0ebd12904c520478ce/searx/webapp.py#L597-L599)。生产部署使用 uWSGI，由系统服务托管；worker/thread 数应按 CPU 和负载调整，见官方 [uWSGI 部署文档](https://docs.searxng.org/admin/installation-uwsgi.html)。

可机械检查分两层：

```bash
curl --fail http://127.0.0.1:8888/healthz
curl --fail 'http://127.0.0.1:8888/search?q=health&format=json'
```

`/healthz` 只证明 Web 进程可应答。第二项只有在设置中显式启用 JSON 输出后才成立；`/search` 的参数和 JSON/CSV/RSS 格式开关以官方 [Search API](https://docs.searxng.org/dev/search_api.html) 为准。应先检查进程/HTTP 活性，再检查实际出站查询，避免把进程存活误认为所有引擎可用。

### 本次实际核验

- 从官方固定 commit 归档安装 Python 依赖和 SearXNG；归档 SHA-256 为 `4065d39a15d33f717c002d7196d39694902943f95f75f6970d78365856cd5cf7`，安装面约 `144 MiB`。
- 使用运行时随机 `SEARXNG_SECRET`、`127.0.0.1:18888`、关闭 limiter，并在本地设置中启用 HTML/JSON 输出。`ss` 观察到仅回环监听；`GET /healthz` 返回 `200 OK`。
- `/search?...&format=json` 返回结构化 JSON；随后以同一端点运行 `collect-research-sources` 的 `searxng` connector，campaign 和哈希验证均通过。
- 所试 Brave、DuckDuckGo、Google CSE、Startpage 和 Wikipedia 引擎在当前执行网络中超时或连接失败，因此该次 campaign 为零候选。启动日志还记录 Ahmia、Torch 注册失败和 Wikidata 初始化超时；这些引擎没有被视为可用。connector 完成了零候选 package 与哈希验证，但 campaign 没有保存逐引擎失败或 access gap；这些故障只在服务日志中可见。因此本次测试不证明引擎级失败记录，也不构成有效搜索覆盖证明。
- smoke test 后服务已停止；长期运行需调用方自己的服务管理、网络出口、代理信任与资源策略。

### 安全、缓存与资源

直接应用的默认端口是 `8888`、默认绑定地址是 `127.0.0.1`；`server.secret_key` 必须替换为随机值。`debug` 只用于本地开发。相关设置见 [`server` settings](https://docs.searxng.org/admin/settings/settings_server.html)和 [`general` settings](https://docs.searxng.org/admin/settings/settings_general.html)。对外提供服务时，应使用调用方控制的 TLS 反向代理、主机防火墙和访问边界；官方 [private instance 指南](https://docs.searxng.org/own-instance.html)说明了自有实例与公共实例的信任差异。

Valkey 不是最小本地查询路径的硬依赖，但启用 SearXNG limiter 时必须有 Valkey；连接格式和 socket/URL 配置见 [`valkey` settings](https://docs.searxng.org/admin/settings/settings_valkey.html)，限流、代理 IP 识别和机器人防护见 [`searx.limiter`](https://docs.searxng.org/admin/searx.limiter.html)。对外实例应同时校准 trusted proxy，不应只开启缓存服务就视为完成防护。

官方没有给出可泛化的内存、CPU 或吞吐基准。最低运行面是 Python Web 应用；生产面通常再加入 uWSGI，公开实例还可能加入 Valkey 与反向代理。资源预算应按启用引擎、并发、超时、worker 数和缓存负载实测，不能用固定数字冒充容量证明。

## RSSHub

### 官方状态与固定版本

RSSHub 当前 `package.json` 要求 Node `^22.22.2 || ^24.15.0`，锁定 `pnpm 10.34.5`，构建脚本生成 `dist/index.mjs`，生产启动脚本运行该入口；以核验 commit 的官方 [`package.json`](https://github.com/DIYgod/RSSHub/blob/c2ca45493bdb/package.json)为准。项目没有 GitHub Release，本次审查固定到 2026-08-27 的 commit `c2ca45493bdb`；更新状态可核验官方 [`master` commits](https://github.com/DIYgod/RSSHub/commits/master)，发行状态见 [Releases](https://github.com/DIYgod/RSSHub/releases)。

项目许可证为 [`AGPL-3.0`](https://github.com/DIYgod/RSSHub/blob/c2ca45493bdb/LICENSE)。运行或修改服务前，应复核网络服务场景中的源码提供义务；各路由所访问内容还受来源站点条款、版权、隐私和账号授权约束。

### 无容器的最短路径

RSSHub 没有与 SearXNG 系统脚本等价的裸机安装器。官方部署文档源码给出 clone、`pnpm i`、build/start 与可选 PM2 托管，见 [`rsshub-docs/src/deploy/index.md`](https://github.com/RSSNext/rsshub-docs/blob/main/src/deploy/index.md)；以下可复现路径再结合核验 commit 的官方 [`Dockerfile`](https://github.com/DIYgod/RSSHub/blob/c2ca45493bdb/Dockerfile)和 [`package.json`](https://github.com/DIYgod/RSSHub/blob/c2ca45493bdb/package.json)，不代表项目承诺特定的生产服务管理器：

```bash
git clone https://github.com/DIYgod/RSSHub.git
cd RSSHub
git checkout --detach c2ca45493bdb
corepack enable pnpm
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=true pnpm install --frozen-lockfile
pnpm build
LISTEN_INADDR_ANY=false CACHE_TYPE=memory pnpm start
```

当前 Node `24.18.0` 满足项目约束，Corepack 可提供项目锁定的 pnpm。本次按 lockfile 完成安装与生产构建；依赖浏览器的路由仍需另行预算浏览器、字体、共享内存和隔离运行面。

### 启动、健康与接口

服务默认端口为 `1200`。官方 compose 使用 `/healthz` 作为健康检查，因此最小存活检查为：

```bash
curl --fail http://127.0.0.1:1200/healthz
```

端口、健康路径、Redis 和 browserless 的官方组合可在核验 commit 的 [`docker-compose.yml`](https://github.com/DIYgod/RSSHub/blob/c2ca45493bdb/docker-compose.yml)核验。健康检查通过后，还应对实际计划使用的一个公开、无需凭据的 feed 做有界 smoke test，并确认 MIME、状态码和缓存行为；`/healthz` 不证明所有路由或上游站点可用。若配置了 `ACCESS_KEY`，访问控制中间件也会保护 `/healthz`；探针不得把 key 写入共享日志或 manifest，具体行为见核验 commit 的 [`access-control.ts`](https://github.com/DIYgod/RSSHub/blob/c2ca45493bdb/lib/middleware/access-control.ts)。

### 本次实际核验

- 从官方固定 commit 归档安装；归档 SHA-256 为 `b45318bae59a378b2e348bd438548479f3c649c7b10c1e3de59fb8d22f658a6a`。`pnpm --frozen-lockfile` 安装 `1,077` 个包，`pnpm build` 成功生成约 `26 MiB` 的 `dist/`；完整源码、依赖和构建面约 `1.2 GiB`。
- 两个旧可选 WebSocket native addon 在 Node 24 上编译失败，但 pnpm 将其视为可降级组件，整体安装与 RSSHub build 均以退出码 `0` 完成。实际启动和测试路由未加载这两个 addon。
- 以 `LISTEN_INADDR_ANY=0`、`PORT=12001`、`CACHE_TYPE=memory` 启动生产构建。`ss` 观察到仅 `127.0.0.1:12001` 监听；`GET /healthz` 返回 `200 ok`。
- 官方内置 `/test/1` route 返回 XML，通用 `rss` connector 在配置的五候选上限处停止，产出 `5` 个 metadata-only 候选；campaign 与哈希验证通过，同时按预期标记为 `limited` / `candidates_with_gaps` 并给出 limit warning。一次 GitHub issue route 成功返回 XML；后续请求因当前网络的 GitHub API `504` 失败，说明 route 可用性仍取决于上游网络。
- smoke test 后服务已停止；浏览器路由、Redis、账号型路由、长期重启恢复和生产负载尚未验证。

### 安全、缓存与资源

当前配置的 `LISTEN_INADDR_ANY` 默认为 `true`，因此最短本地路径必须显式设为 `false`，并让受控代理或调用方决定是否暴露网络。默认 `PORT=1200`、`CACHE_TYPE=memory`、`MEMORY_MAX=256`；缓存还支持 Redis 和 HTTP，具体默认值与环境变量以核验 commit 的官方 [`lib/config.ts`](https://github.com/DIYgod/RSSHub/blob/c2ca45493bdb/lib/config.ts)为准。

Redis 不是单进程轻量路径的最低依赖。多进程共享或需要跨重启缓存时可选择 Redis，但应独立配置持久性、访问边界和容量。RSSHub 当前配置名称和文档语义是 Redis；不应未经兼容性测试就把 Valkey 声明为已支持替代。

`ACCESS_KEY` 可限制 RSSHub 访问，但不替代 TLS、主机防火墙或上游账号授权。路由所需的 cookie、token 和账号状态只能由调用方的 secret/env/受控文件注入，不得进入命令参数、日志、快照、campaign state 或仓库。项目的漏洞报告渠道见核验 commit 的官方 [`SECURITY.md`](https://github.com/DIYgod/RSSHub/blob/c2ca45493bdb/SECURITY.md)。

官方没有给出通用资源基准。轻量面包括 Node 进程和有上限条目数的内存缓存；依赖树与 TypeScript 构建需要额外磁盘和内存，浏览器/Playwright 路径显著扩大磁盘、内存和攻击面，Redis 又增加一个服务。当前约 66 GiB 可用磁盘只说明构建有候选空间，不构成浏览器路由或长期缓存的容量保证。

自动化应固定 commit、使用 `--frozen-lockfile`、记录构建日志，并由调用方已有的服务管理器托管 `pnpm start`。升级必须重新安装锁定依赖、重建、运行 `/healthz` 与代表性 feed 检查；单次后端失败不应阻断其他采集连接器。

## GitHub CLI

### 官方状态、安装与升级

GitHub CLI 是 MIT 许可的软件，许可证见官方 [`LICENSE`](https://github.com/cli/cli/blob/trunk/LICENSE)。官方 Linux 安装支持 apt、dnf、Homebrew 和预编译的 `386`/`amd64`/`arm64`/`armv6` 发行资产；没有管理员权限时，可下载匹配架构的预编译 archive、核验官方 checksum 后把 `gh` 放入调用方控制的 `PATH`，详见官方 [Linux installation](https://github.com/cli/cli/blob/trunk/docs/install_linux.md)。它不需要 Node、Python、Redis/Valkey，也不运行常驻端口。

宿主原有 `gh 2.96.0`。官方最新版本是 [`v2.98.0`](https://github.com/cli/cli/releases/tag/v2.98.0)，发布于 2026-08-20；该版本将 Codespaces port forward 默认绑定改为 localhost，并在发行说明中建议受影响用户升级。本次已在隔离运行目录安装并使用 `2.98.0`，未覆盖宿主 binary。

### 认证、健康与自动化

交互环境可使用浏览器认证；无头自动化应从标准输入或受控环境注入凭据。官方 `gh auth login` 文档说明了系统凭据存储和无法使用安全存储时退回明文文件的风险；`--with-token` 从标准输入读取，见 [`gh auth login`](https://cli.github.com/manual/gh_auth_login)。环境变量优先级和 `GH_TOKEN`/`GITHUB_TOKEN` 用法见官方 [environment reference](https://cli.github.com/manual/gh_help_environment)。不得把 token 放入命令参数、日志、manifest 或仓库，也不得在审计输出中使用 `gh auth status --show-token`。

无常驻服务时，完成门是版本、认证和最小 API 调用：

```bash
gh --version
gh auth status
gh api rate_limit
```

本次从官方 release 下载 `gh_2.98.0_linux_amd64.tar.gz` 与 checksum 清单，SHA-256 `3b8ac6b30336802fc1a858d7c084e11cdf24ac1a761ca90b68022d7d729208de` 校验通过。该 binary 报告 `gh 2.98.0 (2026-08-20)`；认证 `rate_limit` 请求成功。将其置于本次进程 `PATH` 后，`github-gh` connector 对 `CUDA kernel language:C++` 做一页、三条仓库查询，campaign 生成 `3` 个候选并通过哈希验证；第二页被配置的页数上限明确标为 `limited`。安装面约 `55 MiB`，不运行常驻端口。

`gh api` 可调用 REST/GraphQL 并支持分页，见官方 [`gh api`](https://cli.github.com/manual/gh_api)。认证成功的常规 REST 请求通常有每小时 5,000 次主限额，未认证请求通常为每小时 60 次，搜索和部分端点另有限额；应读取响应头、尊重 `Retry-After`/reset，避免并发洪泛，详见官方 [REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)和 [REST API best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)。

`gh` 是按调用启动的单进程 CLI，主机资源成本通常低于常驻爬取服务；真正的约束是 API 配额、结果字节、分页数量和缓存。每次 campaign 都应设置最大页数/记录数/字节、指数退避与恢复检查点，不应把认证成功等同于无限抓取权限。

## 本次不默认安装的候选

| 候选 | 官方状态与许可 | 决策 |
|---|---|---|
| MediaCrawler | 官方仓库说明其通过 Playwright 保存浏览器登录状态，并需要 Python/uv、Node 和平台账号；见官方 [README](https://github.com/NanmiCoder/MediaCrawler)。其 [NON-COMMERCIAL LEARNING LICENSE 1.1](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE)限制为非商业学习/研究，且明确禁止大规模爬取；官方 [Releases](https://github.com/NanmiCoder/MediaCrawler/releases)为空。 | 不作为默认或大规模采集依赖。只有许可证、账号授权和目标平台规则均允许时，才可在隔离环境显式 opt-in。 |
| WeWe RSS | 官方仓库 [cooderl/wewe-rss](https://github.com/cooderl/wewe-rss) 已于 2026-05-11 归档为只读；许可证为 [MIT](https://github.com/cooderl/wewe-rss/blob/main/LICENSE)，历史发行见官方 [Releases](https://github.com/cooderl/wewe-rss/releases)。 | 不新增部署。对调用方已合法运行、已授权的 feed，可继续通过通用 RSS connector 消费。 |
| Crawl4AI | 官方仓库提供 Python/Docker 抓取运行时，当前发行状态见 [Releases](https://github.com/unclecode/crawl4ai/releases)。其 [`LICENSE`](https://github.com/unclecode/crawl4ai/blob/main/LICENSE)包含 Apache License 2.0 文本及项目归属要求。浏览器执行和复杂抽取扩大资源、SSRF、重定向、文件与不可信内容处理面。 | 不进入最短发现路径。未来可作为隔离的可选全文抽取器，但须先完成许可证复核、网络出口策略、MIME/大小限制、沙箱与恶意 fixture 测试。 |

上述排除不影响使用官方 API、站点自有导出、RSS/Atom、机构仓储和 source-owned 页面。采集器不得绕过访问控制、robots、站点条款或账号授权。

## 推荐执行顺序与完成门

1. **GitHub CLI**：核验 `v2.98.0` 或更新稳定版的官方 checksum，升级后确认版本、认证和一个有界 API 请求；记录请求数、分页、失败和 rate-limit 状态。
2. **RSSHub（按需）**：只在通用 RSS connector 无法直接消费现有 feed 时部署。固定 commit，按 lockfile 构建，以回环地址和内存缓存启动；完成 `/healthz`、一个代表性公开 feed 和重启恢复检查。浏览器路由、Redis 和任何账号型路由分别授权、预算和测试。
3. **SearXNG（按需）**：在具备管理员授权、系统包和服务管理器的受控主机执行官方脚本。完成随机 secret、回环绑定、uWSGI 服务、HTTP/JSON 查询、引擎失败隔离和必要的 Valkey limiter 检查后，才接入 campaign。

任何组件未通过自己的完成门时，其 connector 应报告结构化错误并降级，不能阻断其他数据源。覆盖报告必须量化已查询的源、查询、时间窗、记录数、失败和访问缺口，不得宣称穷尽互联网或穷尽文献。
