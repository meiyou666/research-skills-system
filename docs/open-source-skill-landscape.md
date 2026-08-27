# 科研 Agent Skills 系统：开源景观与出版图形要求调研

> 核验日期：2026-08-27
> 核验口径：出版要求只采信出版社或期刊官方页面；开源项目只依据其官方仓库、项目文档和许可证。本文记录的是该日期可复核的事实，不把第三方预设、社区经验或同一出版机构旗下其他期刊的要求外推为目标期刊规则。

## 结论摘要

1. **出版合规必须按“出版社—具体期刊—文章类型—投稿阶段”解析。** Nature Portfolio、AAAS、IEEE 和 ACM 都不能用一个跨期刊的静态参数表替代实时投稿说明。
2. **官方模板与社区样式是两类资产。** Nature 的官方 Illustrator 模板、IEEE Template Selector 和 ACM Primary Article Template 可称为官方模板；SciencePlots 中名为 `nature`、`ieee` 的 `.mplstyle` 只能称社区预设，不能称官方模板或合规证明。
3. **规则引擎要保留来源、适用范围和核验日期。** 对存在冲突或阶段差异的要求，输出警告并回到目标期刊页面，而不是自动选择一个数字。
4. **系统采用 11 个可组合能力，而不是建立一条唯一流程。** `collect-research-sources`、`search-primary-evidence`、`audit-research-evidence`、`formulate-research-hypotheses`、`design-research-experiments`、`supervise-experiment-runs`、`inspect-gpu-environment`、`analyze-experiment-results`、`create-publication-figures`、`revise-evidence-report`、`no-negative-echo` 各自拥有清晰的交接物；README 应分别描述能力和交接契约，不把示例顺序写成强制状态机。
5. **开源项目最值得复用的是工作流与验证契约。** 图表契约、证据追踪、作用域受控的样式、最终成品检查、独立完成判定和带哈希的交付清单，比复制某套期刊外观更稳健。确定性 schema 只检查结构、声明和文件事实，不能代替领域判断、科学真伪、伦理审批或发表决定。
6. **Agent 自主探索和领域适配需要被保留。** 技能应给出目标、证据边界、停止条件和安全护栏，让 agent 自主选择查询、候选假设、设计分支和工具；按领域加载参考资料，不用固定来源数量、统一评分或万能实验模板制造伪确定性。
7. **两组已纳入材料的上游与许可证仍未确定。** 当前私有交付保留并改造 7 个监督 scripts，并迁移、泛化一份报告 CSS；该使用事实不产生或推定开源许可证，也不证明可公开分发。它们在第五、六节与 MIT 上游材料分开披露。
8. **调研候选中仅引入了已固定版本的 LB623 `no-negative-echo` MIT 上游材料。** 其余候选的“采用”表示采纳规范或设计原则，“只借鉴”表示不复制实现，“不采用”表示不进入核心设计。任何未来的其他外部依赖安装、源码复制或模板纳入都要另做固定版本、许可证、NOTICE、依赖和资产审计。
9. **GPU 验收必须区分“观测到、工具不支持、权限不足、工具缺失、未检查”。** 容器可见性不等于宿主机事实，镜像 digest 也不固定宿主机驱动、内核、GPU、MIG/分区、拓扑、功耗或热状态；没有真实硬件探测证据时不得把文档支持范围写成当前环境已验证。
10. **深度采集不是证据判断。** 大规模研究需要多个可降级的发现、元数据、RSS、代码仓库和页面入口，以及有限预算、缓存、断点、内容哈希和失败报告；采集命中仍可能只是 snippet、摘要或未核验页面。系统因此把 `collect-research-sources` 与检索策略、全文证据审计分开，并以实际查询、来源、时间窗、错误和访问缺口量化覆盖。

## 核验方法与边界

- 官方出版页面用于确定尺寸、格式、分辨率、可访问性、图像完整性和模板身份。投稿规则本身不是开源软件，表中的“许可证”因此标为不适用。
- 开源项目只有在仓库内存在明确许可证时才列出许可证；项目使用的字体、数据、模板、图片和依赖仍需逐项核验。
- “可复用经验”描述设计思想，不等于复制代码或内容的法律意见。
- 页面不可访问或规则存在歧义时，本文明确记录不确定性，不用搜索摘要、博客、缓存副本或其他期刊页面补数字。
- 本文不检查登录后才显示的投稿系统表单，也不替代编辑部的个案指示。
- 对 Agent Skills 的“官方来源”指项目维护者自己的仓库、源码和许可证；仓库热度、模型宣传指标和第三方聚合页不作为采纳依据。
- 处置含义：**采用**＝纳入本系统的接口或行为原则；**只借鉴**＝不复制候选项目实现，只吸收可验证的设计经验；**不采用**＝不作为核心依赖或规范来源。所有项目的代码引入状态均按核验日工作树的事实记录；来源或许可证不明的材料不据此获得开源身份。

## 系统设计结论：11 个可组合能力

### 能力边界

| Skill | 独立职责与主要交接物 | 自主性、领域适配与 schema 边界 |
|---|---|---|
| `collect-research-sources` | 运行有界的多源互联网采集 campaign：发现、规范化、跨源去重、版本聚类、合法抓取、快照/哈希、缓存、失败隔离和断点恢复；输出 candidate inventory、campaign state 与覆盖/缺口报告 | agent 可按领域选择、替换或扩展 connector，小任务可只用一个来源；硬门只检查 URL/路径安全、schema、状态、哈希、预算和凭据泄漏。候选记录及其排名、snippet 或提取文本都不是科学纳入结论或 claim 证据 |
| `search-primary-evidence` | 围绕问题探索一手来源，保存查询、候选来源、稳定标识、访问日期、版本/撤回状态、访问级别与覆盖边界；输出可追溯 `search-package` | agent 可改写查询、追踪引文和补搜反例，不强制固定数据库、查询轮数或来源数量；结构只校验标识与溯源字段，不把检索排名、snippet 或摘要当作已审计证据 |
| `audit-research-evidence` | 阅读可获得的原始内容并独立核对 claim 与来源是否身份一致、语境相符，标注支持、冲突、缺证、撤回/更正与不确定性；输出 `evidence-dossier` 和争议清单 | 可按风险抽样或全量深审；领域量表按需加载。不得用总分取代逐条证据判断，也不代替同行评审、编辑决定或事实真值判定 |
| `formulate-research-hypotheses` | 把观察与已有证据转成多个候选解释、竞争假设、可区分预测、测量定义和可证伪条件 | 保留少数意见、反例与 agent 生成候选的空间，不自动选“赢家”；schema 可验证候选是否有预测与来源，不能判定假设为真或按统一分数淘汰 |
| `design-research-experiments` | 在目标领域约束下比较设计、控制、随机化/分层、测量、分析、停止、缺失与偏差方案；可产出预注册草案和偏离记录 | 设计分支由科学问题、可用单位、伦理和资源决定；不硬编码通用样本量、显著性阈值或单一 DOE。伦理、监管和领域专家审批始终在外部 |
| `supervise-experiment-runs` | 拥有 `local` 与 `ssh` 两种 transport 和共享运行生命周期：通过浅适配器执行同一 runner 协议，固定运行记录，启动、低成本监控、取消、恢复/续跑、完成判定，并以 manifest/哈希收集产物 | 不自行解释 GPU 健康或科学结果；它执行经批准的 inspector/analyzer 计划并回传原始证据。高成本、凭证、数据删除和资源销毁遵从用户授权边界；调度器或云后端不是核心 transport |
| `inspect-gpu-environment` | 只读探测宿主机与容器边界、设备身份/可见性、驱动与运行时、物理 GPU/MIG/AMD 分区、拓扑、温度、功耗、时钟、ECC/Xid、工具与 profiler 能力；输出带状态的 environment snapshot | 依据现场 capability probe 选择 NVIDIA、AMD 或无 GPU 分支；不假定厂商对称，不执行功耗/时钟/ECC/MIG/分区修改、reset 或压力诊断。无法从当前权限观察的字段必须为 unknown/permission-denied |
| `analyze-experiment-results` | 验证输出正确性和测量边界，分析延迟、吞吐、带宽、能耗、roofline、稳定性及强/弱扩展；输出原始样本、定义、统计摘要、比较边界和逐项 acceptance finding | 可按领域选择指标、统计与 profiler，不把一个 GPU 总分或固定阈值硬编码为科学判断；区分 device/host 时间、payload/bus bandwidth、板卡/整机能耗和经验/理论 roof。侵入式 profiler/benchmark 需显式授权 |
| `create-publication-figures` | 建立 Figure Contract，从数据生成图，按目标 venue 当日官方要求配置并检查最终成品；输出图、源数据映射、render manifest 和 QA 报告 | agent 自主选最能忠实表达数据的图型；期刊 profile 是带来源的可更新提示，不是限制科学表达的硬模板。schema 不判断图是否科学上“好” |
| `revise-evidence-report` | 用 issue ledger 统筹修订、逐条关联证据，维护 disputed/accepted/deferred 状态，生成请求的 Markdown/HTML/PDF 等交付物并做视觉与证据 QA | 输出载体由用户和环境决定，不规定唯一表面或固定章节；报告结构适配受众和领域，不能用 IMRAD 或某个业务模板覆盖所有报告 |
| `no-negative-echo` | 在任何最终化界面检查被放弃提案、纠正历史和负向约束是否泄漏到名称、文案、代码、元数据或交接；输出命中与人工判定 | 可独立作为最后一道 gate，也可在中途审阅；扫描器只给候选，语义判断由 agent/人完成，不承诺零漏报或零误报 |

### 组合原则

- 这些名称是能力所有权，不是强制时间线。11 个能力均可单独、并行、回退或重复调用。例如已有候选清单可跳过互联网采集，本地已有结果可以直接分析，CPU 实验可跳过 GPU 检查，运行监督也可只调用 `local` 或 `ssh` transport；两种 transport 共用 runner、完成判定、恢复/续跑和 manifest 契约。
- 每个 `SKILL.md` 只保留触发条件、核心契约、安全边界和导航；详细领域规范、工具说明、模板放入 `references/`、`scripts/`、`assets/` 并按需读取。该结构符合 [Agent Skills 规范的渐进披露模型](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx)。
- 所有确定性工具都应报告“检查了什么”和“没有证明什么”。允许硬门的对象是可机械确认且稳定的事实，例如 JSON 可解析、DOI 格式、文件存在、哈希相符、字体嵌入；科学价值、因果识别、偏差严重度和结论可信度必须保留可解释判断。
- README 用“可组合能力”和示例交接说明系统，不宣称一条适用于所有学科的端到端研究流水线。

### 基础规范采纳决策

| 来源 | 精确官方来源 | 许可证 | 核验日期 | 处置 | 代码是否引入 | 理由 |
|---|---|---|---|---|---|---|
| Agent Skills specification | [规范源码](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx)、[仓库](https://github.com/agentskills/agentskills)、[LICENSE](https://github.com/agentskills/agentskills/blob/main/LICENSE) | 代码 Apache-2.0；文档 CC-BY-4.0 | 2026-08-27 | **采用** | 否，仅采用格式与组织原则 | 原生支持 `SKILL.md` + `scripts/references/assets` 和三级渐进披露；规范也明确 frontmatter 的 `license` 是可选字段，因此仍须检查仓库级与逐文件许可 |
| RO-Crate | [规范仓库](https://github.com/ResearchObject/ro-crate)、[快速参考](https://www.researchobject.org/ro-crate/quick-reference) | Apache-2.0 | 2026-08-27 | **只借鉴** | 否 | 借鉴研究对象、输入/输出、软件、人员和许可的 JSON-LD 溯源模型；完整 RO-Crate 对当前轻量交接可能过重，先保持可映射字段 |
| PRISMA 2020 | [官方 checklist](https://www.prisma-statement.org/prisma-2020-checklist)、[官方说明](https://www.prisma-statement.org/prisma-2020) | checklist CC-BY-4.0 | 2026-08-27 | **只借鉴** | 否 | 用作系统综述任务的按需 reporting reference，不外推为普通检索或所有研究报告的强制流程 |
| OSF Registrations / API | [COS 官方仓库](https://github.com/CenterForOpenScience/osf.io)、[注册说明源码](https://github.com/CenterForOpenScience/OSFDocs/blob/master/registrations.rst)、[API v2 规范](https://github.com/CenterForOpenScience/developer.osf.io/blob/master/swagger-spec/swagger.yaml)、[COS Terms](https://github.com/CenterForOpenScience/cos.io/blob/master/TERMS_OF_USE.md) | OSF 软件 Apache-2.0；用户注册内容依各项目所选许可 | 2026-08-27 | **只借鉴** | 否，未来可做可选适配器 | 借鉴冻结、时间戳、公开/embargo 和偏离可追溯；预注册模板应按领域选择，不能让 OSF 表单 schema 代替实验设计 |

## 一、出版图形要求

### 范围与来源总表

| 对象 | 已核验的官方范围 | 官方入口 | 许可证 | 核验日期 | 关键边界 |
|---|---|---|---|---|---|
| Nature Portfolio / `Nature` | Portfolio 总入口、旗舰期刊 `Nature` 的 Research Figure Guide、图像完整性政策 | [Nature Portfolio 写作入口](https://www.nature.com/nature-portfolio/for-authors/write)、[`Nature` Research Figure Guide](https://research-figure-guide.nature.com/) | 不适用；投稿规则不是开源许可 | 2026-08-27 | Research Figure Guide 自述适用于旗舰期刊 `Nature`，不能自动外推到全部 Nature Portfolio 期刊 |
| Science / AAAS | 旗舰 `Science` 官方入口可定位，但本次访问被 403 拒绝；另核验了 AAAS 的 Science Partner Journals（SPJ）及其中 `Research` 期刊 | [`Science` 初投稿说明](https://www.science.org/content/page/instructions-preparing-initial-manuscript)、[SPJ 项目说明](https://spj.science.org/program-overview)、[`Research` 作者指南](https://spj.science.org/page/research/for-authors/) | 不适用 | 2026-08-27 | SPJ 与 Science family 编辑独立；`Research` 的数值不能写成旗舰 `Science` 要求 |
| IEEE Journals | IEEE Author Center 的期刊图形、尺寸、格式、可访问性和模板入口 | [Create Graphics for Your Article](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/) | 不适用 | 2026-08-27 | 具体 publication 仍可能有附加要求，应由目标刊物页面和模板覆盖通用指南 |
| ACM | ACM TAPS 投稿模板、Primary Article Template 说明 | [ACM Submission Template](https://authors.acm.org/binaries/content/assets/publications/taps/acm_layout_submission_template.pdf)、[Primary Article Template Instructions](https://www.acm.org/binaries/content/assets/publications/taps/acm_primary_article_template_instructions.pdf) | 不适用 | 2026-08-27 | 全 ACM 的统一 DPI/栏宽数值未在已核验通用来源中确认；会议或期刊局部要求不可外推 |

### 1. Nature Portfolio 与旗舰期刊 `Nature`

#### 可验证要求

- Nature Portfolio 的[作者写作入口](https://www.nature.com/nature-portfolio/for-authors/write)要求先选择具体期刊；各刊有自己的文章类型、图形要求和投稿细节。
- 旗舰期刊 `Nature` 的[图板构建与导出指南](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/)给出主文图宽：单栏 89 mm、双栏 183 mm，最大高度 170 mm。
- 同一指南要求正文图文字通常为 5–7 pt，使用 Arial 或 Helvetica 等标准字体，保持文字可编辑，不把文字转轮廓，并嵌入 TrueType type 2 或 type 42 字体。
- 主文图要求可编辑的矢量文件，优先 AI、EPS、PDF；指南还列出分层 PSD、PPT 导出 PDF、普通 SVG、Excel 和 PS 等可接受情况。该指南明确不把 JPEG、TIFF、PNG 作为主文图文件格式；文件尽可能不超过 50 MB，并应嵌入组成元素。
- Extended Data 使用另一组约束：RGB、最高 300 dpi、单文件不超过 10 MB，优先 JPEG，也接受 TIFF/EPS。自动检查不能把它与主文图规则合并。
- [图形规格页](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/)要求坐标轴、刻度和单位清楚；panel 标签为 8 pt 加粗小写字母，其他文字为 5–7 pt；显微或空间图像应使用可编辑比例尺，而不是只给放大倍数。
- 颜色应有足够对比度，避免红绿组合和彩虹色图，并避免仅靠颜色区分类别。指南给出大于 4.5 的对比度目标，同时建议不要使用彩色文字或图标。
- 对 Matplotlib PDF 字体，官方示例设置 `Matplotlib.rcParams['pdf.fonttype'] = 42`。
- [Nature Portfolio 图像完整性政策](https://www.nature.com/nature-portfolio/editorial-policies/image-integrity)要求最小化处理、保留原始数据与元数据，明确分隔并说明拼接图像，并披露处理软件和操作；出版社可要求提交未处理数据。
- 旗舰指南的[图像完整性页](https://research-figure-guide.nature.com/figures/image-integrity/)进一步要求整幅图像一致调整，禁止克隆、修复、选择性编辑和生成式 AI 或内容感知编辑。

#### 需要保留为冲突而不是自动归一的要求

[图形规格页](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/)一处写摄影图像最低 300 dpi、在线校样最高 450 dpi，并称提交至少 450 dpi 可获得最高质量；同页导出摘要又写图像最低 450 dpi。旗舰期刊的[最终投稿页](https://www.nature.com/nature/for-authors/final-submission)还保留摄影图像 PSD/TIFF 300–600 dpi 的表述。它们可能反映图像类型、文件阶段或新旧流程差异。系统应显示原文来源和适用阶段，要求作者在最终提交前向目标刊物或编辑确认，不应把任一数字编码为全局硬门槛。

#### 可复用的自动检查

- 检查最终版面尺寸、字体大小、字体嵌入、panel 标签、坐标单位、比例尺和文件体积。
- 对每个图层区分矢量、摄影、显微和 Extended Data，按类型运行不同规则。
- 做灰度辨识和对比度检查，并检查类别是否还有形状、线型或直接标注等非颜色编码。
- 生成处理记录并关联原始数据；把拼接、裁剪和任何非线性处理列为人工复核项。

#### 模板边界

Nature Guide 的[官方资源页](https://research-figure-guide.nature.com/resources/templates/)提供官方 Adobe Illustrator 模板。只有这类由出版社发布的文件可称为官方模板。任何 `nature.mplstyle`、复刻 CSS、Illustrator 社区文件或“Nature 风格”配色都不是出版社模板，也不能证明投稿合规。

### 2. Science、AAAS 与 Science Partner Journals

#### 本次能够与不能够核验的范围

- 已定位旗舰 `Science` 的[初投稿说明](https://www.science.org/content/page/instructions-preparing-initial-manuscript)、[修订研究论文说明](https://www.science.org/content/page/instructions-authors-revised-research-articles)和[Science Journals 编辑政策](https://www.science.org/content/page/science-journals-editorial-policies)，但本次审计访问这些页面时均收到 HTTP 403。因此本文不转述旗舰 `Science` 的 DPI、栏宽、字体或格式数字。
- [SPJ 项目说明](https://spj.science.org/program-overview)和[SPJ FAQ](https://spj.science.org/frequently-asked-questions)说明这些期刊由 AAAS 运营和出版，但与 Science family 在编辑上独立且分开。因而 SPJ 页面只能证明对应 SPJ 期刊的规则。

#### SPJ 期刊 `Research` 的官方要求（仅限该刊）

根据 [`Research` 作者指南](https://spj.science.org/page/research/for-authors/)：

- 修订阶段应单独提交可编辑图文件，优先矢量；图示用 PDF/EPS。照片和显微图可用 TIFF、JPEG、PNG、PSD、EPS、PDF，页面优先 PDF，最低 300 dpi。
- 不接受 PowerPoint 文件、嵌入 Word 的图，或由 PowerPoint/Word 转换出的图。
- 符号至少 6 pt、线宽至少 0.5 pt；显微图应有比例尺。
- 避免红绿组合、过于接近的色相和灰度下无法分辨的编码。
- 线性调整应施于整幅图像；非线性调整需要披露；不接受选择性增强。
- 页面还建议尽可能使用 serif 字体。该建议只属于此处核验的 `Research`，不能与旗舰 `Science` 或其他 SPJ 期刊合并。

#### 可复用的自动检查与边界

可以复用“源文件可编辑、图像处理可追溯、比例尺存在、线宽/符号大小、灰度辨识、复用许可附件”等检查结构。不能把 `Research` 的 300 dpi、6 pt、0.5 pt 或 serif 字体写入 `Science` 通用配置；在旗舰页面可人工访问并重新核验前，相关字段应保持 `unknown`，而不是用第三方摘要补齐。此次也未核验到可称为旗舰 `Science` 官方图形模板的文件。

### 3. IEEE Journals

#### 可验证要求

- IEEE 的[分辨率与尺寸页](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/resolution-and-size/)优先以 PS、EPS、PDF 保存矢量图；非矢量彩色与灰度图要求高于 300 dpi，黑白线稿要求高于 600 dpi。
- 同页给出单栏宽 3.5 in（88.9 mm、21 pica），双栏宽 7.16 in（182 mm、43 pica），并建议图不要小于单栏宽。
- [文件格式页](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/file-formatting/)列出 PS、EPS、PDF、PNG、TIFF；只有图原本在 Microsoft Office 中绘制时才使用对应 Office 文件。JPEG 仅用于作者照片，VSD、GIF、BMP 不能处理。
- 同页建议 Helvetica、Times New Roman、Arial、Cambria 或 Symbol；EPS、PS、PDF 应嵌入字体或转轮廓；图按最终尺寸显示时文字约 9–10 pt。
- 图形压缩后不应超过 7.16 × 8.8 in（182 × 220 mm）。
- IEEE 的[图形总页](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/)要求不要只用颜色传义：同时使用形状、独特符号或线型，保证色彩与明度对比，尽可能直接标注，并做灰度测试。页面还说明不再接受 Lena 图像。

#### 可复用的自动检查

- 在目标物理尺寸下读取有效 DPI，而不是仅检查像素总量。
- 区分连续色调图、灰度图和一位线稿，再应用不同阈值。
- 检查文件后缀与内容类型、字体嵌入、最终文字大小、栏宽和最大画布。
- 对类别编码运行灰度、线型和标记冗余检查。

#### 模板边界

IEEE 的[Authoring Tools and Templates](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/authoring-tools-and-templates/)及 Template Selector 才是官方模板入口；具体 publication 可能有自己的模板与说明。SciencePlots 的 `ieee` 样式不是 IEEE 发布或认证的模板。

### 4. ACM

#### 可验证要求

- ACM 的[投稿模板 PDF](https://authors.acm.org/binaries/content/assets/publications/taps/acm_layout_submission_template.pdf)接受 TIFF/JPEG，并强烈偏好可缩放的 SVG/EPS/PS；不建议提交 Corel、Word、Excel、PowerPoint 等应用程序源文件。
- 所有字体需要嵌入，图像方向应正确。
- 每个非装饰性图都需要与 caption 分离的描述；描述不应重复 caption。复杂图可以在附录中提供更长说明或数据表。官方模板给出的图描述长度上限为 2,000 个字符。
- [Primary Article Template Instructions](https://www.acm.org/binaries/content/assets/publications/taps/acm_primary_article_template_instructions.pdf)是已接收 ACM 投稿进入生产流程时的官方模板说明。

#### 可访问性与数值边界

ACM 的 LaTeX 流程可通过 `\Description{...}`承载图描述；描述需要传达读者无法从 caption 获取的视觉信息和数据关系。ACM DIS 2023 的[无障碍图表指南](https://dis.acm.org/2023/creating-accessible-figures-and-tables/)提出至少 300 dpi 等建议，但它是具体会议页面，不能作为全 ACM 的统一门槛。

本次核验的 ACM 通用来源没有确认一个适用于所有刊物、会议和轨道的 DPI 或栏宽数字。因此合规配置应从具体 venue 的 call、模板和 TAPS 指示解析；未知时保持未知。

#### 可复用的自动检查与模板边界

- 检查字体嵌入、图像方向、矢量优先以及每个非装饰性图是否有图描述。
- 对图描述做“非空、长度、是否机械重复 caption”的初筛，但语义充分性仍需人工审查。
- ACM Primary Article Template 是官方模板；社区 LaTeX 类封装、绘图样式或某会议往年的尺寸表都不能替代当前目标 venue 的官方文件。

## 二、基础绘图库与社区样式

### 5. Matplotlib

| 项目 | 官方来源 | 许可证 | 核验日期 | 定位 |
|---|---|---|---|---|
| Matplotlib | [官方文档](https://matplotlib.org/stable/)、[源码仓库](https://github.com/matplotlib/matplotlib) | [Matplotlib License](https://github.com/matplotlib/matplotlib/blob/main/LICENSE/LICENSE)，基于 PSF License、BSD-compatible；不是 SPDX `BSD-3-Clause` | 2026-08-27 | 通用绘图库和可复现导出基础设施，不是出版商模板 |

[自定义指南](https://matplotlib.org/stable/users/explain/customizing.html)说明配置优先级为运行时 `rcParams` 高于 style sheets，高于 `matplotlibrc`；`rc_context` 和 style context 可限制临时设置的作用域，多个样式按从左到右组合且右侧覆盖左侧。包可以分发自己的 `.mplstyle`。这为科研技能提供了几个稳健设计点：

- 用局部 context 应用期刊或项目样式，避免污染进程全局状态。
- 在运行记录中保存 Matplotlib 版本、样式列表及顺序、关键 `rcParams`、物理尺寸和导出参数。
- 将“视觉预设”与“合规验证”分开：样式负责默认值，验证器检查最终 PDF/SVG/位图成品。
- 根据数据语义选择 colormap。官方的[colormap 指南](https://matplotlib.org/stable/users/explain/colors/colormaps.html)强调数据类别与感知亮度，而不是承诺某个配色天然满足所有无障碍或出版要求。
- 使用 [`savefig`](https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.savefig.html)明确记录格式、DPI、bbox、元数据等导出选项。

许可证边界：Matplotlib 自身许可证要求随分发保留许可证和版权信息，并对衍生分发总结修改；仓库还包含可能适用其他许可的资产、字体或第三方软件，需查看对应文件。不能把整个生态简单标成 `BSD-3-Clause`。

### 6. SciencePlots

| 项目 | 官方来源 | 许可证 | 核验日期 | 定位 |
|---|---|---|---|---|
| SciencePlots | [仓库](https://github.com/garrettj403/SciencePlots)、[README](https://github.com/garrettj403/SciencePlots/blob/master/README.md) | [MIT](https://github.com/garrettj403/SciencePlots/blob/master/LICENSE)，Copyright 2018 John Garrett | 2026-08-27 | Matplotlib 科研论文、演示和学位论文的社区样式集合 |

可复用经验：通过 `import scienceplots` 注册样式；用 `plt.style.context(...)` 做局部应用；用列表组合基础 `science` 与其他预设；为无 LaTeX 和 CJK 场景显式选择兼容配置。默认 `science` 样式依赖 LaTeX，环境探测和字体检查应成为运行前置条件。

边界：仓库包含名为 `ieee`、`nature` 等样式，但未发现出版社认证或隶属证明。名称表示作者设计的社区预设，不是 IEEE、Nature 或其他出版商的官方模板，也不是对当前投稿规则的合规证书。最终稿仍需用目标期刊当日官方说明校验。

## 三、Agent Skills、研究工作流与基础设施候选

以下只依据维护者官方仓库、源码、规范或许可证。许可证覆盖范围按项目自己的声明记录，不自动覆盖论文全文、训练数据、集成数据、字体、图片、模型、API 服务或引用的第三方资产。**本节所有行在核验日的代码引入状态均为“否”。**

### 3.1 深度互联网搜索与采集

`collect-research-sources` 是后端中立的采集层：它接收有界 query plan 或等价的 seed inventory，输出可恢复的 candidate inventory、原始观察记录、版本/重复关系、快照哈希和逐 connector 覆盖/失败报告。它不决定科学纳入、不把搜索排序解释为质量，也不把 README、issue、评论、snippet、摘要或页面提取文本提升为 agent 指令。核心实现独立编写，没有复制下列项目的源码、Compose、模板或 fixture。

#### 通用发现、页面、RSS 与代码仓库候选

| 候选 | 精确官方来源与维护证据 | 许可证 | 核验日期 | 运行、认证、资源与自动化 | 处置与主要风险 |
|---|---|---|---|---|---|
| MediaCrawler | [仓库/README](https://github.com/NanmiCoder/MediaCrawler)、[pyproject](https://github.com/NanmiCoder/MediaCrawler/blob/main/pyproject.toml)、[issues](https://github.com/NanmiCoder/MediaCrawler/issues)、[releases](https://github.com/NanmiCoder/MediaCrawler/releases)；2026 年 7 月仍有 issue 活动，仓库没有可供固定的正式 release | [NON-COMMERCIAL LEARNING LICENSE 1.1](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE)，限制非商业学习/研究，并明确禁止大规模抓取或干扰平台；不按通用开源许可证处理 | 2026-08-27 | Python 3.11、Playwright/Chrome，部分路径还需 Node；以二维码登录和缓存浏览器状态访问多个社交平台，可接代理与多种数据库，浏览器、账号、代理和存储成本高，不是无凭据服务 | **不采用、不注册 connector。** 许可证与大规模 campaign 冲突；登录态、cookie、代理和降低风控检测的浏览器路径带来账号授权、隐私、平台条款和封控风险。若调用方另行研究某个窄范围用途，必须重新核验当日许可、账号所有权、目标平台规则和保存范围，且该动作留在本 skill 外 |
| SearXNG | [仓库](https://github.com/searxng/searxng)、[Search API](https://docs.searxng.org/dev/search_api.html)、[容器部署](https://docs.searxng.org/admin/installation-docker.html)、[limiter](https://docs.searxng.org/admin/searx.limiter.html)、[commits](https://github.com/searxng/searxng/commits/master)；官方文档构建于 2026-08-22，源码仍持续更新 | [AGPL-3.0-or-later](https://github.com/searxng/searxng/blob/master/LICENSE) | 2026-08-27 | 自托管 Python Web 服务；官方推荐 Docker/Podman Compose，limiter 需要 Valkey。HTTP `/search` 可给 JSON/CSV/RSS，但实例必须启用对应格式，许多公共实例会关闭；查询会转发给选定搜索引擎。成本是容器、缓存、出口流量和后端封控处理；访问控制由实例运营者配置 | **采用为可选外部 discovery connector，不打包服务。** 只连接调用方运营或明确获准的端点，限制页数/并发并记录返回 engine；一个实例失败时结构化来源继续。SearXNG 聚合不转移下游引擎条款，也不证明覆盖率；不依赖不受控公共实例 |
| Crawl4AI | [仓库](https://github.com/unclecode/crawl4ai)、[LICENSE](https://github.com/unclecode/crawl4ai/blob/main/LICENSE)、[releases](https://github.com/unclecode/crawl4ai/releases)、[v0.9.0 安全默认](https://github.com/unclecode/crawl4ai/blob/main/docs/blog/release-v0.9.0.md)、[Security](https://github.com/unclecode/crawl4ai/security)；v0.9.2 于 2026-07-15 发布，2026 年有连续安全修复 | 文件包含 Apache License 2.0 正文及其后的项目特定显著归属要求；引入或公开使用前需同时审查该附加要求，本文不把它简化为无附加条件的 `Apache-2.0` | 2026-08-27 | 可 `pip` 安装并下载 Playwright 浏览器，也可运行带 Redis/浏览器的 Docker API；浏览器与 `shm`、内存、CPU 开销显著。v0.9.0 的远程服务默认回环绑定，外部暴露需 `CRAWL4AI_API_TOKEN` 和 TLS 反向代理；可做异步抓取、缓存、深度遍历和恢复 | **只作为未来可选、隔离的页面 extractor；当前仓库未提供 bundled adapter。** 固定已审版本、做健康/认证/出口检查，只传已验证 HTTP(S) URL，禁用任意 hook、JavaScript、local-file 和调用方路径能力。2026 年官方 advisories 覆盖 RCE、SSRF、任意写入、认证绕过和凭据外泄，故不能把其自身检查替代本系统 SSRF/MIME/大小/重定向门 |
| RSSHub | [仓库/README](https://github.com/DIYgod/RSSHub)、[LICENSE](https://github.com/DIYgod/RSSHub/blob/master/LICENSE)、[package.json](https://github.com/DIYgod/RSSHub/blob/master/package.json)、[Compose](https://github.com/DIYgod/RSSHub/blob/master/docker-compose.yml)、[commits](https://github.com/DIYgod/RSSHub/commits/master)；主分支持续活跃并有大量 route 更新 | AGPL-3.0 | 2026-08-27 | Node 服务，可本机或 Docker/Compose 运行；规模化部署通常需要缓存/持久层、网络出口和 route-specific 凭据。自动定时生成 RSS 很适合增量发现，但各 route 访问的是不同第三方平台 | **采用通用 RSS/Atom consumer；RSSHub 仅作调用方运营的可选 feed producer。** 不打包 RSSHub、route 或部署栈。逐 feed 记录来源所有者、抓取方式和保留范围；route credential、目标平台条款、反爬限制和自托管 AGPL 义务由运营者核验 |
| WeWe RSS | [仓库/README](https://github.com/cooderl/wewe-rss)、[LICENSE](https://github.com/cooderl/wewe-rss/blob/main/LICENSE)、[Dockerfile](https://github.com/cooderl/wewe-rss/blob/main/Dockerfile)、[releases](https://github.com/cooderl/wewe-rss/releases)；仓库由所有者于 2026-05-11 archive，当前只读，最后一批正式 release 停在 2024 年 | MIT | 2026-08-27 | Node 20，可用 MySQL 或 SQLite、Docker 和定时任务；需要微信读书二维码登录并保存账号状态，官方 README 明示过高添加频率会触发账号封控，部分接口还经项目指定转发服务 | **不作为部署依赖或专用 connector。** 已由调用方合法运营、授权并审查保留范围的 RSS/Atom 可以进入通用 consumer；archive 状态、账号会话、第三方转发、平台封控和全文版权使它不适合可复用核心 |
| GitHub `gh` CLI | [官方仓库](https://github.com/cli/cli)、[MIT LICENSE](https://github.com/cli/cli/blob/trunk/LICENSE)、[releases](https://github.com/cli/cli/releases)、[`gh api`](https://cli.github.com/manual/gh_api)、[`gh auth login`](https://cli.github.com/manual/gh_auth_login)、[REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)、[REST best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)；v2.97.0 于 2026-07-31 发布，官方 release 持续更新 | MIT | 2026-08-27 | 调用方安装一个本地二进制；`gh api` 支持 REST/GraphQL、分页和缓存，适合仓库、代码、issue/PR、commit 与 release。多数 API 数据需要认证或认证后限额更高；自动化可从 `GH_TOKEN`/`GITHUB_TOKEN` 或既有凭据读取。GitHub 对未认证、已认证和 search endpoint 分别限流，并可能施加 secondary limits | **采用为可选外部 CLI adapter，不复制 CLI。** adapter 只做只读、有界请求，不调用 `gh auth login`、`gh auth token` 或 `--show-token`，不把 token 放入 argv/log/snapshot；遵循 `Retry-After`/rate headers。私有仓库需显式权限，仓库文件、issue 与评论仍按各自许可、隐私和不可信文本处理 |

#### 一手学术元数据与全文定位入口

| 来源 | 精确官方接口、条款与维护证据 | 数据权利 | 核验日期 | 运行、认证、成本与自动化 | 处置与证据边界 |
|---|---|---|---|---|---|
| Crossref REST API | [REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)、[访问/认证/当前限额](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)、[2025-12 限额变更](https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/)、[元数据来源与许可](https://www.crossref.org/documentation/retrieve-metadata/)、[官方文档仓库](https://github.com/CrossRef/rest-api-doc)；访问与许可页更新于 2025-10-16，当前服务继续发布状态和文档更新 | 书目事实通常不受版权限制；Crossref 生成内容、Open Funder Registry 与 Retraction Watch 数据为 CC0；摘要版权仍归作者或出版社；站点文档为 CC-BY-4.0 | 2026-08-27 | 免费 public 无注册；polite pool 用 `mailto`/agent；付费 Metadata Plus 用 header token。通用表列 public 5 requests/interval 且并发 1、polite 10 且并发 3、Plus 150；2025-12 起 list/search 请求另按 public 1/s、polite 3/s 管理。client 必须以实际 `x-rate-limit-*`/`x-concurrency-limit` 为准，缓存并对 `429` 退避；年度 public data file 适合真正 bulk | **采用标准库 connector**，用于 DOI、出版元数据、关系、许可链接和更新信号；不保存摘要。成员提交元数据可能缺失或错误，DOI 命中仍需到 source-owned artifact 核实，Plus 与 bulk 下载不是默认依赖 |
| OpenAlex | [当前 API](https://help.openalex.org/api/)、[认证与限额](https://help.openalex.org/api/authentication/)、[价格](https://help.openalex.org/access/pricing/)、[数据模型](https://help.openalex.org/data/)、[历史文档仓库及 CC0 声明](https://github.com/ourresearch/openalex-docs/blob/main/license.md)；新 Help Center 的认证页更新于 2026-08-19，旧 `openalex-docs` 仓库于 2026-07-23 archive，维护已迁至新站 | OpenAlex 数据为 CC0；location 指向的论文/PDF 仍需按相应内容许可决定保存和再分发 | 2026-08-27 | 基础查询无需 key；免费账户 key 将日预算提高 10 倍并暴露用量，超过免费日预算可 pay-as-you-go/年度计划。官方同时限制 100 requests/s、单页 100、普通分页 10,000，较大集合应 cursor page，并根据 `meta.cost_usd` 与 rate headers 估算/停止 | **采用预算感知的标准库 connector**，用于作品、作者、机构、DOI、引用、相关作品、版本与语言关系；key 只从调用方 env/header 注入。它是持续修订的知识图谱，ID 合并、消歧、主题、引用数和 OA locator 不是全文真实性或科学质量证明 |
| arXiv API | [API 入口](https://info.arxiv.org/help/api/index.html)、[User Manual](https://info.arxiv.org/help/api/user-manual.html)、[API Terms](https://info.arxiv.org/help/api/tou.html)、[投稿许可](https://info.arxiv.org/help/license/index.html)、[S3 bulk](https://info.arxiv.org/help/bulk_data_s3.html)；官方继续提供 legacy Atom/OAI/RSS 与 bulk 服务并公布变更责任 | 描述性 metadata 为 CC0；绝大多数 e-print 使用 arXiv 非独占分发许可，arXiv 无权替其他人授权再分发；少量论文另有 Creative Commons 等许可，必须逐件读取 | 2026-08-27 | legacy API 无登录，Atom 自动化成熟；所有受控机器合计每 3 秒最多 1 request 且仅 1 connection。全文 S3 是 requester-pays，官方记录的整体规模为 TB 级；大规模成本和版权均不适合默认短路径 | **采用 metadata-only connector**，保留 arXiv ID 与版本并链接 abstract/source-owned 页面，不下载或重新发布 e-print。请求节流不得通过多机规避；需要全文时由上层按论文许可和研究用途另行取得 |
| PubMed / NCBI E-utilities | [NCBI API hub](https://www.ncbi.nlm.nih.gov/home/develop/api/)、[E-utilities usage](https://www.ncbi.nlm.nih.gov/books/NBK25497/)、[参数参考](https://www.ncbi.nlm.nih.gov/books/NBK25499/)、[NCBI policies](https://www.ncbi.nlm.nih.gov/home/about/policies/)；参数参考更新于 2026-03-04，NCBI 仍维护 E-utilities/EDirect | 美国政府自产页面可能为 public domain，但 NCBI 混合第三方内容；PubMed abstract 可能受作者或出版社版权，NCBI 不授予其再分发权；使用软件须向用户显示 NCBI disclaimer/copyright notice | 2026-08-27 | 免费、无 key 最多 3 requests/s；调用方 NCBI account key 默认最多 10 requests/s，更高需联系 NCBI。应携带注册的 `tool`/`email`，超过 100 次的序列安排在周末或美东非高峰；用 Entrez History、EPost/EFetch batch 减少请求 | **采用有界 ESearch→ESummary connector**，保存 PMID/DOI 与摘要以外的 summary metadata；不收集 abstract。大量结果使用 History/batch 或官方 dump，不逐 ID 洪泛；医学命中不等于医疗建议或证据支持 |
| Europe PMC | [Developer resources](https://europepmc.org/developers)、[REST API](https://europepmc.org/RestfulWebService)、[copyright](https://europepmc.org/Copyright)、[REST release notes](https://europepmc.org/docs/Europe_PMC_RESTful_Release_Notes.pdf)；当前 REST API 标示 v6.9，官方持续发布 release notes | metadata、abstract、全文和补充文件不是一项统一许可；仅 Open Access subset 可通过指定 API/OAI/FTP 批量取得，仍须读取每篇文章的 Creative Commons 或相似许可；其他全文不得自动 bulk 下载 | 2026-08-27 | public REST search 可返回 XML/JSON/DC，支持 cursor、引用、reference、状态、数据库关系和 OA locator；已核验官方页未公布统一数值 rate 或付费认证要求，因此 client 应保守限流、缓存、对 `429/5xx` 退避并在大规模前向运营方确认 | **采用标准库 connector**，用于生命科学 metadata、PMID/PMCID/DOI、版本/状态与 OA 定位；abstract 保存需调用方明确 retention basis，默认只记 locator/级别。`isOpenAccess` 只触发逐件许可检查，不能自动授予全文保存或再分发 |

#### 采集层实现结论

- connector 只负责 `discover`/规范化和可选的合法 fetch；统一记录保留 query、connector、原始排名、发现/抓取时间、canonical URL/ID、来源所有者、语言、MIME/status、内容级别、SHA256、快照或外部 locator、提取器版本、访问级别、错误和重试状态。原始观察与派生候选分开，SQLite state 有 schema version，JSONL 可导出。
- campaign 从有限 query/seed 开始，经并发 fan-out、canonicalization、跨源去重、版本聚类、受权全文定位、引用/作者/仓库关系扩展、反向查询和增量刷新；每一步都有 connector/host 限速、指数退避、timeout、深度、item、page、byte、wall-time 与 retry 上限。覆盖报告按 connector、query、语言、时间窗、content level、成功/失败和未访问范围量化，不宣称穷尽互联网或文献。
- generic fetch 只允许经 host policy 批准的 HTTP(S)，每次重定向重验 DNS/address；默认拒绝 loopback、private/link-local/reserved address、URL credential、危险 MIME、非 identity 压缩、超限响应与由 locator 派生的文件路径。页面内容按不可信数据存储，不能触发命令、工具、配置、凭据读取或新的 agent 指令。
- 最短路径只需一个结构化 source 与一个有限 query；大规模 stack 是按需 profile。SearXNG、RSSHub 与 Crawl4AI 都保持为外部服务，`gh` 保持调用方已有 CLI；核心不要求 Docker。一个 connector 失败只形成带状态缺口，其余任务继续，恢复时以 campaign/idempotency state 跳过已完成工作。
- `status` 只描述有界任务是否仍可恢复或已经全部终态；独立的 `collection_outcome` 区分已有候选、候选伴随缺口、零候选和全部 connector 失败/受限。这样不会把“所有失败都已记录”误读成采集成功，也不会把零结果伪装成科学排除结论。
- 2026-08-27 的 fresh 离线前向测试覆盖 606 条双语候选、跨查询 DOI 去重、arXiv 版本聚类、中断恢复、关系扩展、六类模拟 `gh` 资源、loopback Atom 增量、单 connector 故障与全失败结果状态；这证明接口与状态行为，不代表百万级性能或任一线上服务可用。
- 对 GPU/CUDA 调研，组合可覆盖论文与 preprint、厂商 source-owned 文档、GitHub 仓库、代码、issue/PR、release/commit 和 RSS 更新；社交平台帖子最多是待审候选，不能替代驱动 release notes、硬件文档、源码或经过全文审计的论文。

### 3.2 一手证据检索与证据审计

| 候选 | 精确官方来源 | 许可证 | 核验日期 | 处置 | 代码是否引入 | 采用判断 |
|---|---|---|---|---|---|---|
| FutureHouse PaperQA2 | [仓库与算法说明](https://github.com/Future-House/paper-qa)、[LICENSE](https://github.com/Future-House/paper-qa/blob/main/LICENSE) | Apache-2.0 | 2026-08-27 | **只借鉴** | 否 | 借鉴 agent 可自由重排“搜索—取证—回答”、本地全文索引、页级证据和带引文回答；不引入其重型 RAG/LLM/embedding 运行时。默认模型和外部元数据服务需凭证，项目也说明内部评测条件与公开版本并不完全相同；全文许可必须另审 |
| K-Dense `research-lookup` | [技能源码](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/research-lookup/SKILL.md)、[LICENSE](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/LICENSE.md) | MIT | 2026-08-27 | **只借鉴** | 否 | 借鉴 manuscript research packet、claim-to-source map 和后端路由；不采用默认“60 篇”目标或 Parallel/OpenRouter 绑定。来源数量不能成为质量硬门，查询可能向第三方 API 发送，需在权限与隐私边界内显式选择 |
| K-Dense `literature-review` | [技能源码](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/literature-review/SKILL.md)、[LICENSE](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/LICENSE.md) | MIT | 2026-08-27 | **只借鉴** | 否 | 借鉴查询日志、筛选理由、去重、citation verification、PRISMA 路由；不复制七阶段固定流程、外部 key 依赖或超长主 skill。系统综述与快速一手证据检索必须是不同模式 |
| K-Dense `peer-review` | [技能源码](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/peer-review/SKILL.md)、[LICENSE](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/LICENSE.md) | MIT | 2026-08-27 | **只借鉴** | 否 | 借鉴授权/保密 intake、claim–evidence 检查、方法/统计/复现审阅和“验证声明而非真值”的本地工具边界；不把证据审计伪装成匿名同行评审，也不生成编辑决定 |
| AllenAI SciFact | [仓库](https://github.com/allenai/scifact)、[分层 LICENSE](https://github.com/allenai/scifact/blob/master/LICENSE.md) | 代码 Apache-2.0；claims/evidence annotations CC-BY-4.0；abstract corpus ODC-By-1.0 | 2026-08-27 | **只借鉴**为测试语料模型 | 否 | claim、evidence span、support/refute 的拆分适合构造回归测试；SciFact 是限定语料的事实核验数据集，不是生产审计规范，摘要也不足以代替全文语境 |
| FutureHouse Aviary | [仓库](https://github.com/Future-House/aviary)、[LICENSE](https://github.com/Future-House/aviary/blob/main/LICENSE) | Apache-2.0 | 2026-08-27 | **只借鉴**为评测框架 | 否 | 可借鉴把 agent、环境、工具与轨迹分离，测试查询探索能力；它是训练/评测 gym，不提供本系统的来源权威性或审计规则 |

建议：`search-primary-evidence` 可直接接收 `collect-research-sources` 的 candidate inventory，也可使用用户给出的等价清单或自主做少量检索；它负责围绕研究问题制定纳入/排除、反向证据和覆盖停止判断，而不拥有采集系统。最终 evidence item 必须指向实际原始论文、官方数据、标准、源码或来源所有者页面。`audit-research-evidence` 应在独立上下文重开全文，核对身份、版本、页码/段落、许可和 claim，不信任采集或筛选阶段的 snippet 与摘要性结论。

### 3.3 假设形成、实验设计与预注册

| 候选 | 精确官方来源 | 许可证 | 核验日期 | 处置 | 代码是否引入 | 采用判断 |
|---|---|---|---|---|---|---|
| K-Dense `hypothesis-generation` v2.1 | [技能源码](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/hypothesis-generation/SKILL.md)、[LICENSE](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/LICENSE.md) | MIT | 2026-08-27 | **采用原则、独立实现** | 否 | 与目标边界最吻合：候选与竞争解释、可区分预测、因果/关联区分、预注册与偏离记录；明确 validator 只检声明和内部一致性，不验证科学真理或选择假设，也拒绝统一样本量门槛 |
| K-Dense `experimental-design` v1.1 | [技能源码](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/experimental-design/SKILL.md)、[LICENSE](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/LICENSE.md) | MIT | 2026-08-27 | **只借鉴** | 否 | 借鉴随机化、独立重复、blocking、pseudoreplication、factorial/response-surface 等模式库；不复制依赖 numpy/pandas/pyDOE3 的生成器或把通用教科书语句做成领域硬门。因果结论仍需要 estimand、执行、缺失和假设共同支持 |
| Anthropic `scientific-problem-selection` | [技能源码](https://github.com/anthropics/knowledge-work-plugins/blob/main/bio-research/skills/scientific-problem-selection/SKILL.md)、[LICENSE](https://github.com/anthropics/knowledge-work-plugins/blob/main/LICENSE) | Apache-2.0 | 2026-08-27 | **只借鉴** | 否 | 借鉴候选问题、风险、成功标准、参数策略和决策树的对话式展开；它面向生命科学早研，不是通用假设验证器，也不能替代领域专家、伦理或实验设计 |
| FutureHouse Robin | [仓库](https://github.com/Future-House/robin)、[LICENSE](https://github.com/Future-House/robin/blob/main/LICENSE) | Apache-2.0 | 2026-08-27 | **只借鉴** | 否 | 借鉴多 agent 生成文献查询、候选 assay/治疗候选、保存中间输出和允许实验数据反馈；当前示例限定疾病输入、依赖付费 Edison 与模型 API，并用 pairwise ranking 收敛候选，不适合作为跨领域核心流程 |
| Sakana AI Scientist | [仓库](https://github.com/SakanaAI/AI-Scientist)、[当前 LICENSE](https://github.com/SakanaAI/AI-Scientist/blob/main/LICENSE) | 自定义 AI Scientist Source Code License 1.0，含用途限制；**不按通用开源许可证处理** | 2026-08-27 | **不采用** | 否 | 端到端自动生成 idea、实验、论文和 review 的固定模板与本系统“保留人类科学责任、可组合能力”不符；当前许可限制科学文稿使用并要求披露，模板还混合第三方代码，不能作为可自由复用的开源来源 |

预注册的系统定位：OSF 的冻结/时间戳和 PRISMA 等报告规范可按领域启用，但 `design-research-experiments` 应先让 agent 与研究者形成问题、estimand、测量、排除、停止和分析方案，再映射到所选注册表。预注册提高透明度，不禁止合理适应；数据后产生的修改要作为 dated deviation 或 exploratory analysis 保留，不能把观察到的结果回写成事前预测。

### 3.4 远程实验监督、复现与产物追踪

| 候选 | 精确官方来源 | 许可证 | 核验日期 | 处置 | 代码是否引入 | 采用判断 |
|---|---|---|---|---|---|---|
| Anthropic `cwc-long-running-agents` | [仓库与 README](https://github.com/anthropics/cwc-long-running-agents)、[LICENSE](https://github.com/anthropics/cwc-long-running-agents/blob/main/LICENSE) | Apache-2.0 | 2026-08-27 | **采用原则、独立实现** | 否 | 借鉴默认失败的 evidence contract、新上下文只读 evaluator、磁盘交接和 kill switch；仓库明确是活动演示、未维护、提供构件而非 turnkey 系统，也不是 SSH/GPU 监督实现 |
| SkyPilot Agent Skill | [官方 skill](https://github.com/skypilot-org/skypilot/blob/master/agent/skills/skypilot/SKILL.md)、[仓库](https://github.com/skypilot-org/skypilot)、[LICENSE](https://github.com/skypilot-org/skypilot/blob/master/LICENSE) | Apache-2.0 | 2026-08-27 | **只借鉴；保留可选适配器位** | 否 | 借鉴结构化 JSON 状态、managed job 恢复、checkpoint 责任拆分、阻塞日志等待、autostop 和成本意识；不把 25+ 云/Slurm/Kubernetes 的 provider schema 变成核心接口。其清理示例含破坏性命令，实际技能必须先解析并确认精确目标与授权 |
| Snakemake | [仓库](https://github.com/snakemake/snakemake)、[部署与复现说明](https://github.com/snakemake/snakemake/blob/main/docs/snakefiles/deployment.rst)、[LICENSE](https://github.com/snakemake/snakemake/blob/main/LICENSE.md) | MIT | 2026-08-27 | **只借鉴；可选后端** | 否 | 借鉴代码/配置/环境分离、DAG、dry run、按变化重跑和自包含 archive；它管理声明式分析 workflow，不负责 agent 授权、进程外科学验收或通用 SSH 环境引导 |
| Nextflow | [仓库](https://github.com/nextflow-io/nextflow)、[LICENSE](https://github.com/nextflow-io/nextflow/blob/master/COPYING) | Apache-2.0 | 2026-08-27 | **只借鉴；可选后端** | 否 | 借鉴可移植数据流、HPC/云/Kubernetes executor 和依赖环境；不将 DSL 或生物信息学惯例设为通用实验接口 |
| DVC | [仓库](https://github.com/iterative/dvc)、[LICENSE](https://github.com/iterative/dvc/blob/main/LICENSE) | Apache-2.0 | 2026-08-27 | **只借鉴；可选集成** | 否 | 借鉴数据/模型/参数/指标版本与 pipeline lineage；不要求所有领域采用 Git+DVC，也不把实验指标比较当科学完成判定 |
| MLflow | [仓库](https://github.com/mlflow/mlflow)、[LICENSE](https://github.com/mlflow/mlflow/blob/master/LICENSE.txt) | Apache-2.0 | 2026-08-27 | **只借鉴；可选集成** | 否 | run ID、参数、指标、artifact 和状态可映射到 supervision manifest；平台重点是 ML/agent 工程，tracking server 的认证、数据驻留和运维超出核心 skill |
| Weights & Biases SDK | [仓库](https://github.com/wandb/wandb)、[LICENSE](https://github.com/wandb/wandb/blob/main/LICENSE) | MIT | 2026-08-27 | **不采用为核心依赖** | 否 | 运行、config、metrics、artifacts 的关联值得借鉴，但默认云账户/API key 和平台数据流与本地优先、后端中立的核心不符；用户显式选择时才考虑外部集成 |

核心 skill 应拥有“授权—环境事实—固定运行记录—低成本监控—独立完成判定—校验收集”语义，让 SkyPilot、Snakemake、Nextflow、DVC、MLflow 等成为可选适配器。适配器状态只能提供运行证据；`SUCCEEDED`、进程退出码 0 或指标被记录都不能单独证明科学目标完成。

### 3.5 多个 scientific visualization skills 的直接比较

| 候选 | 精确官方来源 | 许可证 | 核验日期 | 渐进披露 / 自主性 | 出版真实性与 QA | 处置 | 代码是否引入 |
|---|---|---|---|---|---|---|---|
| K-Dense `scientific-visualization` | [技能源码](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-visualization/SKILL.md)、[LICENSE](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/LICENSE.md) | MIT | 2026-08-27 | 有 references/scripts/assets 分层；允许按问题选图，但仍有较多通用指南 | 明确要求实时核验目标期刊、不声称 palette/DPI 自动合规；强调数据诚实、局部 style、导出/provenance 和最终成品检查 | **采用原则、独立实现** | 否 |
| SciToolsmith `sci-plot` | [仓库](https://github.com/SciToolsmith/sci-plot)、[技能源码](https://github.com/SciToolsmith/sci-plot/blob/main/skills/sci-plot/SKILL.md)、[LICENSE](https://github.com/SciToolsmith/sci-plot/blob/main/LICENSE) | Apache-2.0 | 2026-08-27 | Figure Contract 先固定语义，render manifest 与 QA 分开，给 agent 较大图型空间 | 明确无 Nature 隶属关系，“Nature-style”不是官方；强调 evidence architecture、科学语义和不静默改数据 | **只借鉴** | 否 |
| Harvard Zitnik Lab OptimusKG skill | [技能源码](https://github.com/mims-harvard/OptimusKG/blob/main/.agents/skills/scientific-visualization/SKILL.md)、[LICENSE](https://github.com/mims-harvard/OptimusKG/blob/main/LICENSE) | MIT | 2026-08-27 | `SKILL.md` + references + scripts/styles 三层清楚，适配生物医学 KG 场景 | 提供导出/检查工具，但硬编码 journal 表和 `nature`/`science` preset；存在“总要加显著性标记”等过宽规则 | **只借鉴目录与工具分层；不采用规则/profile** | 否 |
| OpenAI `visualize-data` | [技能源码](https://github.com/openai/role-specific-plugins/blob/main/plugins/data-analytics/skills/visualize-data/SKILL.md)、[LICENSE](https://github.com/openai/role-specific-plugins/blob/main/LICENSE) | MIT | 2026-08-27 | chart contract、最简单可辩护图型、按最终表面检查，保留一定选择空间 | 强调非颜色编码、takeaway 和 final-context QA；没有科研 venue 规则，部分实现耦合 MCP/Recharts | **只借鉴 chart contract 与成品 QA** | 否 |
| SciencePlots | [仓库](https://github.com/garrettj403/SciencePlots)、[README](https://github.com/garrettj403/SciencePlots/blob/master/README.md)、[LICENSE](https://github.com/garrettj403/SciencePlots/blob/master/LICENSE) | MIT | 2026-08-27 | 可组合 Matplotlib styles 与 context，图型选择仍由调用者负责 | 只有视觉 defaults，没有来源绑定的合规验证；`nature`/`ieee` 名称不是出版社认证 | **不采用为合规层；仅允许用户显式选择为可选样式** | 否 |
| Matplotlib | [官方文档](https://matplotlib.org/stable/)、[仓库](https://github.com/matplotlib/matplotlib)、[LICENSE](https://github.com/matplotlib/matplotlib/blob/main/LICENSE/LICENSE) | Matplotlib License（PSF-based、BSD-compatible） | 2026-08-27 | style/context、对象 API 与导出参数让 agent 按领域生成多种图，不规定论文工作流 | 提供渲染能力，不验证期刊规则或科学语义；最终 PDF/SVG/位图仍需独立检查 | **采用为绘图接口基线** | 否；作为运行时依赖调用，不随仓库分发 |

`create-publication-figures` 的建议是吸收 K-Dense 的实时核验边界、SciPlot 的 Figure Contract/manifest、OpenAI 的 final-context QA 和 OptimusKG 的资源分层，独立实现轻量工具；不复制任何 journal profile，也不把 SciencePlots 引入为合规依赖。图型、统计表达和领域惯例由 agent 在 Figure Contract 与证据约束内探索。

### 3.6 报告交付与最终化 gate

| 候选 | 精确官方来源 | 许可证 | 核验日期 | 处置 | 代码是否引入 | 采用判断 |
|---|---|---|---|---|---|---|
| K-Dense `scientific-writing` v2.0 | [技能源码](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-writing/SKILL.md)、[LICENSE](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/LICENSE.md) | MIT | 2026-08-27 | **采用原则、独立实现** | 否 | 借鉴证据 provenance、reporting-guideline 路由、作者责任、保密和本地一致性检查；不把 IMRAD 或投稿准备扩成所有分析报告的固定结构 |
| OpenAI `build-report` | [技能源码](https://github.com/openai/role-specific-plugins/blob/main/plugins/data-analytics/skills/build-report/SKILL.md)、[LICENSE](https://github.com/openai/role-specific-plugins/blob/main/LICENSE) | MIT | 2026-08-27 | **只借鉴** | 否 | 借鉴 answer-first report spine、受众、evidence/caveat/source metadata、最终表面检查；不采用 Codex desktop/MCP/Recharts 的表面路由，也不强制“exactly one”业务报告模式 |
| Quarto CLI | [仓库](https://github.com/quarto-dev/quarto-cli)、[LICENSE](https://github.com/quarto-dev/quarto-cli/blob/main/COPYING.md) | MIT | 2026-08-27 | **只借鉴；未来可选渲染后端** | 否 | 科学/技术 Markdown、交叉引用、引用文献、代码输出和多格式项目能力成熟；运行时包含/调用的 Pandoc、LaTeX、浏览器与扩展各有许可证和供应链成本，不应成为 skill 接口本身 |
| WeasyPrint | [仓库](https://github.com/Kozea/WeasyPrint)、[LICENSE](https://github.com/Kozea/WeasyPrint/blob/main/LICENSE) | BSD-3-Clause | 2026-08-27 | **只借鉴；未来可选 PDF 后端** | 否 | 适合 HTML/CSS → PDF 和分页预览；处理不可信 HTML/CSS 有安全风险，PDF 生成成功也不证明链接、字体、分页或证据正确 |
| Pandoc | [仓库](https://github.com/jgm/pandoc)、[COPYING](https://github.com/jgm/pandoc/blob/main/COPYING.md) | GPL-2.0-or-later | 2026-08-27 | **不直接引入** | 否 | 格式转换能力广，但若分发/嵌入需单独评估 GPL 和二进制供应链；可由用户已有 Quarto/Pandoc 环境间接调用，不复制源码 |
| LB623 `no-negative-echo` | [固定上游 revision `c771b7e`](https://github.com/LB623/no-negative-echo/tree/c771b7e6b0bd908c7690e401007a5044cbaf47e0)、[skill v2 baseline `9e78138`](https://github.com/LB623/no-negative-echo/tree/9e78138504905bd7c967ce3e2d9ae7cfa2aacdbf/no-negative-echo)、[固定 revision 的 LICENSE](https://github.com/LB623/no-negative-echo/blob/c771b7e6b0bd908c7690e401007a5044cbaf47e0/LICENSE) | MIT | 2026-08-27 | **固定版本采用并改造；保留 LICENSE/NOTICE/PROVENANCE** | **是** | `SKILL.md` 与 high-assurance reference 基于上游流程改造；`scripts/check_surface.py` 原样保留；另加离线自测与 host metadata。未引入上游二进制界面图片或 installer integrity manifest；最终化 gate 降低而不消除迭代残留泄漏 |
| `pre-commit` | [仓库](https://github.com/pre-commit/pre-commit)、[LICENSE](https://github.com/pre-commit/pre-commit/blob/main/LICENSE) | MIT | 2026-08-27 | **只借鉴 gate 编排** | 否 | 适合统一运行多语言确定性检查；Git hook 不是交付物语义审查，也不能保证没有被跳过，因此最终化 skill 仍需显式执行和报告 |
| in-toto | [实现仓库](https://github.com/in-toto/in-toto)、[规范](https://github.com/in-toto/docs/blob/master/in-toto-spec.md) | 实现 Apache-2.0；当前社区说明中规范/文档许可另有分层 | 2026-08-27 | **只借鉴** | 否 | 借鉴 materials/products/byproducts、签名 link metadata 和独立 inspection；完整软件供应链密钥/布局对研究报告过重，SHA-256 manifest 与可选签名即可先满足需求 |

`revise-evidence-report` 应拥有 issue ledger、claim/source 状态和跨全稿一致性，而渲染后端可替换；`no-negative-echo` 是独立可调用的最终表面检查，不要求产物必须先经过任何其他 skill。构建完成的 gate 至少检查目标文件存在、可打开、链接/字体/页面视觉、证据覆盖、未解决争议和哈希；任何“通过”都应列出检查范围与遗留人工项。

## 四、GPU 环境、计时与结果验收专项

本节只依据 NVIDIA、AMD、PyTorch、OCI 的官方文档、官方源码仓库和仓库内许可证。**本次没有 NVIDIA 或 AMD 物理 GPU 供现场执行，也没有安装、调用或复制下列工具。** 因而本节证明的是“哪些探测和分析路径有一手依据、系统应如何判断”，不是对当前机器或任一 GPU 型号的实测认证。

### 4.1 Skill 所有权与 supervisor transport 边界

| 所有者 | 拥有的动作与事实 | 明确不拥有 | 交接契约 |
|---|---|---|---|
| `supervise-experiment-runs` | `local` 与 `ssh` transport；认证材料的瞬时使用；本地或远端命令/文件准备；共享 runner、完成判定、恢复/续跑与 manifest；进程/session/run ID、退出状态、取消、重连、日志游标、产物收集与哈希 | GPU 健康解释、计时方法选择、指标科学意义、性能通过/失败结论；核心能力不拥有调度器或云后端 | 通过浅 transport adapter 执行 inspector 的只读探测或已批准的实验执行契约；两种 transport 都回传命令、stdout/stderr、退出码、起止时间、host/container context ID 与原始文件，不把 transport 成功改写成验收成功 |
| `inspect-gpu-environment` | 默认只读的 preflight/start/end/error snapshot；物理设备与逻辑实例身份、可见性、驱动/运行时、拓扑、健康遥测、MIG/AMD 分区、工具版本、权限与 profiler capability | 启动、监控、取消或恢复任何实验任务；修改时钟、功耗、ECC、MIG/分区、持久化或 compute mode；GPU reset；默认运行压力测试或 profiler | 每个字段返回 `observed`、`unsupported`、`permission-denied`、`tool-missing` 或 `not-checked`，并附采集位置（host/container）、时间、命令/API、设备 UUID/BDF/MIG UUID 与原始值 |
| `analyze-experiment-results` | 消费可追溯原始结果，复核正确性记录与测量边界，派生吞吐/带宽/能耗/roofline/扩展性指标，评估基线可比性、稳定性并形成有边界的 finding | `local`/`ssh` transport、主动 benchmark/profiler、资源销毁、把 profiler 输出自动升级为因果解释或科学真值 | 分析输出保留细粒度观测、公式、单位、分母、数据/精度/设备上下文、失败与污染状态，以及 `accepted/rejected/inconclusive` 理由；需要补跑时返回可追溯缺口，由设计者更新测量方案和执行契约 |

采用判断：**采用并独立实现** `inspect-gpu-environment` 与 `analyze-experiment-results`。两者有各自复杂的能力探测、证据状态和安全边界，继续塞进 supervisor 会让 transport adapter 同时承担硬件判断与科学判断，接口过浅。能力仍可组合：inspector 定义只读探测，实验设计者给出测量与执行契约，`supervise-experiment-runs` 通过 `local` 或 `ssh` adapter 在目标执行环境运行获批计划，analyzer 消费 snapshot 与运行产物；本地结果分析或 CPU 实验不必经过完整链条。

默认安全策略是 read-only allowlist。`nvidia-smi` 和 `amd-smi` 同时提供查询与修改命令，技能不能因为二进制已安装就允许 setter。NVIDIA 的 persistence/ECC/compute mode、power/clock lock、reset、MIG create/destroy，以及 AMD 的 power/clock/overdrive/reset/partition setter 都不属于 inspector；主动 DCGM diagnostics、Nsight、CUPTI、`rocprofv3`、ROCm Compute Profiler、`nvbandwidth`、`nccl-tests` 也不是“环境查看”，只能先写入实验方案或补充诊断方案，并在费用、独占性、重跑语义、权限和输出位置明确后交给 supervisor 执行。

### 4.2 CUDA、HIP 与 PyTorch 的计时/异步错误契约

GPU kernel launch 通常异步返回。主机 wall clock 包住 launch 而不等待设备，只会量到提交开销；同理，“launch API 返回成功”不证明 kernel 已执行成功。系统采用以下契约：

1. 正确性检查先于性能结论。CUDA launch 后检查即时 launch/configuration error，并在预定同步点检查执行错误；错误可能在后续 CUDA API 才浮现，因此记录“哪个同步/API 报错”和先前异步工作范围，不能把报错机械归因于当前调用。
2. device elapsed time 使用同一目标 stream 上的成对 CUDA/HIP events，等待 stop event 完成后再取时间；跨 stream、默认 stream 或混合 context 时保存依赖关系。需要 end-to-end latency 时另用明确同步的 host timer，并把 host/device 两种时间分栏。
3. 先 warm-up，再采集多次原始样本；记录重复数、聚合方式、线程数、同步方式和异常值处置。PyTorch 工作负载优先借鉴 `torch.utils.benchmark.Timer` 的 warm-up、异步 accelerator 同步、replicate 与 `blocked_autorange`，不把一次 `timeit` 当 GPU 时间。
4. profiler 期间的 wall time 不可直接替代普通运行时间。Nsight Compute 会序列化/重放 kernel、保存与恢复内存并引入 metric-dependent overhead；ROCm profiler 也可能多 pass 重跑应用。profiling run 与 acceptance timing run 必须是不同 run class。

| 一手来源 | 精确官方来源 | 许可证 | 核验日期 | 处置 | 代码是否引入 | 采用边界 |
|---|---|---|---|---|---|---|
| CUDA events / async execution / errors | [CUDA Runtime Event API](https://docs.nvidia.com/cuda/cuda-runtime-api/group__CUDART__EVENT.html)、[Asynchronous Execution](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/asynchronous-execution.html)、[CUDA C++ 错误检查示例](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/intro-to-cuda-cpp.html)、[CUDA EULA](https://docs.nvidia.com/cuda/eula/index.html) | NVIDIA Software License Agreement / CUDA Supplement，非 OSI 开源许可证 | 2026-08-27 | **采用行为契约** | 否 | `cudaEventElapsedTime` 只用于已完成 events 的 elapsed-time 计算；API 明示可能返回先前异步 launch 的错误，且非空 stream 间可能插入其他工作。只依据文档独立实现适配器，不复制 SDK 代码 |
| PyTorch benchmark utilities | [官方 benchmark recipe](https://docs.pytorch.org/tutorials/recipes/recipes/benchmark)、[`torch.utils.benchmark` API](https://docs.pytorch.org/docs/stable/benchmark_utils.html)、[root LICENSE](https://github.com/pytorch/pytorch/blob/main/LICENSE) | PyTorch root code BSD-3-Clause；发行包所含第三方组件仍按各自许可 | 2026-08-27 | **只借鉴；已有 PyTorch 时可选调用** | 否 | 官方 recipe 明确普通 `timeit` 未同步 CUDA 时只量 launch；`Timer` 负责 warm-up 与同步。核心系统不强制安装 PyTorch，其他 accelerator/framework 仍可实现同一 measurement contract |
| HIP events | [HIP Event Management](https://rocm.docs.amd.com/projects/HIP/en/latest/reference/hip_runtime_api/modules/event_management.html)、[HIP 当前源码](https://github.com/ROCm/rocm-systems/tree/develop/projects/hip)、[LICENSE](https://github.com/ROCm/rocm-systems/blob/develop/projects/hip/LICENSE.md) | MIT | 2026-08-27 | **采用行为契约** | 否 | 使用 `hipEventRecord`、`hipEventQuery`/`hipEventSynchronize`、`hipEventElapsedTime` 的真实返回状态；不因 API 形状近似 CUDA 就假定精度、错误传播、支持设备或 fence 行为完全相同 |

### 4.3 NVIDIA 工具、健康信号与 profiler 决策

| 工具/信号 | 精确官方来源 | 许可证 | 核验日期 | 处置 | 代码是否引入 | 可证明的事实与限制 |
|---|---|---|---|---|---|---|
| `nvidia-smi` / NVML | [`nvidia-smi` 官方文档](https://docs.nvidia.com/deploy/nvidia-smi/index.html)、[NVML API](https://docs.nvidia.com/deploy/nvml-api/index.html)、[device query API](https://docs.nvidia.com/deploy/nvml-api/group__nvmlDeviceQueries.html)、[CUDA/driver EULA](https://docs.nvidia.com/cuda/eula/index.html) | NVIDIA SDK/driver 专有条款，非 OSI 开源许可证 | 2026-08-27 | **采用为 NVIDIA 首选只读 probe** | 否 | 可读设备 UUID/BDF、driver、显存/进程、利用率、温度、功耗、时钟及 clock-event reasons、ECC、PCIe/NVLink 与拓扑；NVML 还提供总能耗计数器。各 API 可返回 `NOT_SUPPORTED`，某些 topology/sysfs 字段需要 host/root；只允许 query/list/topo，不允许任何 setter/reset |
| NVIDIA DCGM / `dcgmi` | [当前文档](https://docs.nvidia.com/datacenter/dcgm/latest/)、[Feature Overview](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/feature-overview.html)、[process/job statistics](https://docs.nvidia.com/datacenter/dcgm/latest/learn/core-services/process-and-job-statistics.html)、[profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)、[源码 LICENSE](https://github.com/NVIDIA/DCGM/blob/master/LICENSE)、[官方贡献说明](https://github.com/NVIDIA/DCGM/blob/master/docs/contributing.md) | 开源仓库 Apache-2.0；官方说明 profiling module 不属于开源 DCGM，安装包/闭源模块另受 NVIDIA 条款 | 2026-08-27 | **采用可选被动遥测；主动 diagnostics 需批准** | 否 | job stats 必须在 workload 前启用 watch 才可靠；profile fields 是 interval average，不是 kernel trace，counter 资源还可能与 developer profiler 冲突。`dcgmi diag` 是侵入式且要求独占 GPU：level 1 约数秒、level 2 约 2 分钟、level 3 约 15 分钟，支持级别随产品而异，不能作为默认 preflight |
| Xid / ECC | [Xid Introduction](https://docs.nvidia.com/deploy/xid-errors/introduction.html)、[Working with Xid Errors](https://docs.nvidia.com/deploy/xid-errors/working-with-xid-errors.html)、[`nvidia-smi` ECC 定义](https://docs.nvidia.com/deploy/nvidia-smi/index.html)、[GPU Debug Guidelines](https://docs.nvidia.com/deploy/gpu-debug-guidelines/) | NVIDIA 文档/driver 条款，非开源代码许可 | 2026-08-27 | **采用为带上下文的健康证据** | 否 | Xid 来自 host kernel/event log，容器或普通用户可能不可见；它可能源于硬件、NVIDIA 软件或用户应用，只是调查起点。ECC 要区分 enabled/current/pending、corrected/uncorrected、volatile/aggregate 及采集窗口；历史累计值不能自动归因于当前 run |
| MIG | [Introduction](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/introduction.html)、[Supported GPUs](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/supported-gpus.html)、[Getting Started](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/getting-started-with-mig.html)、[Deployment Considerations](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/latest/deployment-considerations.html) | NVIDIA driver/文档条款，非 OSI 开源许可证 | 2026-08-27 | **采用只读枚举；不管理分区** | 否 | snapshot 同时记录 physical GPU UUID、GI/CI/MIG UUID、profile、可见实例与 driver 版本；不能把 MIG instance 当整卡。支持 GPU、P2P、profiling 与实例持久性随架构/driver 而变；toggle/create/destroy 需要 `CAP_SYS_ADMIN`/root，可能 reset 或改变其他用户资源，inspector 永不执行 |
| Nsight Systems | [User Guide](https://docs.nvidia.com/nsight-systems/UserGuide/index.html)、[Copyright and Licenses](https://docs.nvidia.com/nsight-systems/CopyrightAndLicenses/index.html) | NVIDIA Software License Agreement；所带第三方组件各自许可 | 2026-08-27 | **只借鉴；显式授权后的可选 timeline profiler** | 否 | 可关联 CPU/GPU timeline、CUDA API、kernel 和 memory movement；配置可能插入同步，API/backtrace/page-fault/memory tracking 可显著增加 overhead。用于定位阶段与空洞，不作为无 profiler 运行的 timing acceptance |
| Nsight Compute | [Profiling Guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html)、[Roofline Charts](https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html#roofline-charts)、[Copyright and Licenses](https://docs.nvidia.com/nsight-compute/CopyrightAndLicenses/index.html) | NVIDIA Software License Agreement；所带第三方组件各自许可 | 2026-08-27 | **只借鉴；可选 kernel/roofline profiler** | 否 | 官方 roofline 以 achieved FLOP/s、arithmetic intensity、memory-bandwidth 与 peak-compute boundaries 解释 kernel；metric 数可能触发多 pass replay、序列化、内存保存/恢复或软件 patch。只分析选定 kernel，报告 profiler/replay mode、data type 与 overhead，不把图上接近 roof 当正确性证明 |
| CUPTI | [官方概览](https://docs.nvidia.com/cupti/index.html)、[Usage](https://docs.nvidia.com/cupti/main/main.html)、[CUDA EULA](https://docs.nvidia.com/cuda/eula/index.html) | CUDA Toolkit 专有条款；个别 samples/components 以随附许可为准 | 2026-08-27 | **不作为核心依赖；只预留 adapter** | 否 | 能构建 trace/profile 工具；Auto Range 会在每个 kernel 后 context synchronize，官方警告可能使有跨-kernel 依赖的程序挂起，decode/finalize 也可同步。只有明确需要自定义 collector 时才考虑，先检查 driver/CUPTI compatibility |
| `nvbandwidth` | [官方仓库与测量方法](https://github.com/NVIDIA/nvbandwidth)、[LICENSE](https://github.com/NVIDIA/nvbandwidth/blob/main/LICENSE) | Apache-2.0 | 2026-08-27 | **采用为可选、主动带宽基线** | 否 | 支持 H2D/D2H/D2D、CE/SM、单/双向与部分多节点测量，官方说明用 events、多次 sample 与 median；必须记录方向、buffer、copy engine、并发和 topology。它会占用互连/设备，不是默认 inspector，也不代表应用实际带宽 |
| `nccl-tests` | [官方仓库](https://github.com/NVIDIA/nccl-tests)、[Performance definitions](https://github.com/NVIDIA/nccl-tests/blob/master/doc/PERFORMANCE.md)、[LICENSE](https://github.com/NVIDIA/nccl-tests/blob/master/LICENSE.txt) | BSD-3-Clause | 2026-08-27 | **采用为可选 collective correctness/通信基线** | 否 | 可变 rank/GPU/node 并有 warm-up、iterations 与 correctness check；必须原样区分 `algbw=S/t` 和经 collective 公式校正的 `busbw`，后者不是应用吞吐或逐链路实测。只用于通信子系统，不替代端到端 scaling |
| CUDA Samples `bandwidthTest` | [Utilities README](https://github.com/NVIDIA/cuda-samples/blob/master/cpp/1_Utilities/README.md)、[LICENSE](https://github.com/NVIDIA/cuda-samples/blob/master/LICENSE) | BSD-3-Clause 风格；LICENSE 另指 CUDA EULA | 2026-08-27 | **不采用** | 否 | 官方仓库已说明该 sample 自 CUDA Samples 12.9 起因过时被移除，并指向 `nvbandwidth`；不能继续把旧 `bandwidthTest` 作为当前官方验收工具。`deviceQuery`/`topologyQuery` 的概念可借鉴，但 inspector 优先用已安装的管理接口 |
| NVBench | [官方仓库](https://github.com/NVIDIA/nvbench)、[benchmark/throughput 文档](https://github.com/NVIDIA/nvbench/blob/main/docs/benchmarks.md)、[LICENSE](https://github.com/NVIDIA/nvbench/blob/main/LICENSE) | Apache-2.0 WITH LLVM-exception | 2026-08-27 | **只借鉴；未来可选 CUDA C++ backend** | 否 | 借鉴 cold/batch samples、噪声控制、manual timing、items/s、bytes/s 与 peak-memory-bandwidth percentage 的显式工作量声明；它是 CUDA kernel benchmark library，不应成为所有语言和 accelerator 的核心依赖 |

NVIDIA snapshot 的最低建议字段是：host/container 位置、timestamp、driver/NVML/tool version、physical GPU UUID/BDF/name/compute capability、visible device/MIG mapping、memory、process occupancy、PCIe/NVLink/topology/NUMA、current clocks 与 event reasons、temperature/threshold、power draw/limit、energy counter 支持、ECC mode/counters、run 窗口内 Xid、DCGM watch/health 状态以及每项 query 的返回状态。任何阈值均应来自目标硬件/实验要求；“temperature 可读”不等于“没有热节流”，“utilization 100%”也不等于计算单元有效饱和。

### 4.4 AMD ROCm 能力探测与未验证边界

| 工具/能力 | 精确官方来源 | 许可证 | 核验日期 | 处置 | 代码是否引入 | 可证明的事实与限制 |
|---|---|---|---|---|---|---|
| AMD SMI / `amd-smi` | [CLI 文档](https://rocm.docs.amd.com/projects/amdsmi/en/latest/how-to/amdsmi-cli-tool.html)、[Python API 与 status](https://rocm.docs.amd.com/projects/amdsmi/en/latest/reference/amdsmi-py-api.html)、[当前 source-of-truth](https://github.com/ROCm/rocm-systems/tree/develop/projects/amdsmi)、[LICENSE](https://github.com/ROCm/rocm-systems/blob/develop/projects/amdsmi/LICENSE) | MIT | 2026-08-27 | **采用为 AMD 首选只读 probe** | 否 | 可列设备/driver/ROCm、BDF/HIP ID/UUID、进程、显存、温度、功耗/能耗、clock/activity/ECC、throttle/violation、partition 与 topology，并支持 JSON/CSV。driver 与 SMI 版本错配可使 `gpu_metrics` 字段为 N/A；API 明确返回 `NOT_SUPPORTED`、`NOT_YET_IMPLEMENTED`、`NO_PERM` 等，必须保留而非填零 |
| legacy ROCm-SMI / `rocm-smi` | [退役仓库与 maintenance notice](https://github.com/ROCm/rocm_smi_lib)、[LICENSE](https://github.com/ROCm/rocm_smi_lib/blob/amd-staging_deprecated/License.txt)、[`amd-smi --rocm-smi` 兼容说明](https://rocm.docs.amd.com/projects/amdsmi/en/latest/how-to/amdsmi-cli-tool.html) | 当前退役分支 LICENSE 为 MIT | 2026-08-27 | **不作为新核心 backend；只做兼容探测** | 否 | 官方要求 ROCm 7.0 起迁移到 AMD SMI，旧仓库只收 critical fixes/已 retired。若现场只有 `rocm-smi`，可回传原始输出并标为 legacy；不要依赖旧文本格式建立新的稳定 schema，优先尝试 AMD SMI compatibility mode |
| HIP events | [Event Management](https://rocm.docs.amd.com/projects/HIP/en/latest/reference/hip_runtime_api/modules/event_management.html)、[LICENSE](https://github.com/ROCm/rocm-systems/blob/develop/projects/hip/LICENSE.md) | MIT | 2026-08-27 | **采用为 AMD device-time primitive** | 否 | `hipEventQuery`/`hipEventSynchronize` 确认完成，`hipEventElapsedTime` 计算时间；事件 flags 会改变 timing/fence/sync 行为。现场必须验证 HIP runtime、设备和 event 返回码，不把文档存在等同当前 GPU 已支持 |
| ROCprofiler-SDK / `rocprofv3` | [官方文档](https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/latest/)、[`rocprofv3-avail` 能力查询](https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/docs-7.14.0/how-to/using-rocprofv3-avail.html)、[profiling/tracing 说明](https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/develop/how-to/using-rocprofv3.html)、[当前源码](https://github.com/ROCm/rocm-systems/tree/develop/projects/rocprofiler-sdk)、[LICENSE](https://github.com/ROCm/rocm-systems/blob/develop/projects/rocprofiler-sdk/LICENSE.md) | MIT | 2026-08-27 | **采用 capability probe；profiling 仅按需** | 否 | 先运行 `rocprofv3-avail list/info` 与 `pmc-check`，因为 counters 随 GPU 且组合受硬件限制；多组 counter 会多 pass 从头重跑应用，trace/counter 采集会改变运行环境。`--list-avail` 属 capability，实际 attach/trace/PMC 属 analyzer 的主动测量 |
| ROCm Compute Profiler | [What is ROCm Compute Profiler](https://rocm.docs.amd.com/projects/rocprofiler-compute/en/latest/what-is-rocprof-compute.html)、[兼容 accelerator 表](https://rocm.docs.amd.com/projects/rocprofiler-compute/en/develop/reference/compatible-accelerators.html)、[profile/roofline mode](https://rocm.docs.amd.com/projects/rocprofiler-compute/en/develop/how-to/profile/mode.html)、[当前源码](https://github.com/ROCm/rocm-systems/tree/develop/projects/rocprofiler-compute)、[LICENSE](https://github.com/ROCm/rocm-systems/blob/develop/projects/rocprofiler-compute/LICENSE.md) | 主项目 MIT；LICENSE 另列 bundled dependencies 的各自许可 | 2026-08-27 | **只借鉴；支持设备上的可选 roofline/backend** | 否 | kernel-level counters、baseline、memory chart 和 empirical roofline 很有用；profile 默认多阶段/多次运行并执行 accelerator-specific microbenchmarks，支持范围按官方 compatibility table。必须先匹配 SoC/ROCm/OS，不支持或未列设备输出 `unsupported/unverified`，不尝试“尽量跑”后宣称可比 |

AMD 的最低 snapshot 与 NVIDIA 同构到“概念层”即可，不能强行同字段：设备 UUID/BDF/HIP ID、driver/ROCm/AMD SMI version、physical/partition mapping、可见 render nodes、memory/process、activity、temperature、power/energy、clock、ECC/XGMI/topology、throttle/violation 和 profiler capabilities。不同 ASIC、APU、VM guest、driver/SMI 版本和权限会让部分字段不可用；例如官方 release notes 明示某些 APU 不适用 PCIe/ECC/energy 项。跨厂商比较时保留原始字段和采样语义，只在单位与覆盖范围真正一致时生成归一化视图。

### 4.5 `analyze-experiment-results` 的 GPU 验收合同

| 维度 | 必须保存与计算 | 可以得出的结论 | 禁止的捷径 |
|---|---|---|---|
| 正确性/完整性 | test oracle、退出码、expected/actual、NaN/Inf、校验和、失败样本、异步同步点、run 前后 Xid/ECC delta 及时间窗 | 本次输入和已声明 oracle 下是否通过；硬件信号是否要求隔离/复测 | 用“kernel launch 成功”“GPU utilization 高”或 profiler 有输出代替结果正确性；把历史 ECC/Xid 全归因当前 run |
| latency/time | warm-up；同步的 host end-to-end 与 device event 时间分栏；全部 repeats、median/quantiles/dispersion；计时区间所含 setup/I/O/transfer | 指定边界的延迟分布和不稳定性 | 单次最好值；未同步 wall clock；把 profiler run 的 wall time与普通运行混用 |
| throughput | 明确 work numerator（samples/tokens/items/FLOPs/iterations）和 elapsed denominator；batch、precision、correctness、并发与 steady-state window | 指定 workload definition 下的 achieved throughput | 只写“x/s”不定义 x；把理论峰值、SM activity 或 kernel 局部 throughput 写成端到端吞吐 |
| memory/interconnect bandwidth | bytes 定义（payload、reads+writes、per direction 或 aggregate）、方向、buffer size、CE/SM、拓扑、rank/node、warm-up/repeats；NCCL 原样保存 `algbw`/`busbw` | 某一 transfer/collective 与配置下的 achieved bandwidth | 混用 GB/s 与 GiB/s；把公式校正的 `busbw` 当链路逐字节实测；用 `nvbandwidth` 替代应用 profile |
| energy/power | 优先使用 run 前后累计能耗 counter 差值；不支持时按带 timestamp 的 power samples 数值积分，并报告 cadence、coverage、缺样与误差；同时给 duration、work/energy | 在相同边界下的 board/GPU energy、平均功耗和 energy per work | 把瞬时 power × 总时长当精确能耗；把 GPU board 能耗写成 node/datacenter 能耗；未声明 idle subtraction |
| roofline | profiler/tool/version、kernel、data type、work 与 bytes 定义、memory hierarchy level、empirical/theoretical ceilings、replay mode、设备/clock/power context | 该定义下 achieved point 更接近 memory-bound 或 compute-bound 区域，并提出待验证优化假设 | 跨工具/厂商直接比较不同 counter 定义；把“接近 roof”当数值正确或端到端最优；隐藏 profiler replay |
| strong scaling | 固定全局问题/数据、算法、精度与收敛标准；保存每个 resource point 的 time/throughput 与拓扑。若有一设备基线，报告 `S_n=T_1/T_n`、`E_n=S_n/n`；否则明确以最小可行 `n0` 为基线 | 在声明范围内的 speedup、parallel efficiency、拐点和通信占比候选 | 因单卡装不下仍伪造 `T_1`；把不同 batch/数据/收敛目标点连成 strong-scaling 曲线 |
| weak scaling | 固定每设备问题规模与质量标准；记录总规模、设备数、时间/每资源吞吐、placement/topology | 随资源增长的时间保持程度与系统吞吐扩展 | 与 strong scaling 混称“线性扩展”；只给 aggregate throughput 而不披露每设备工作增长 |
| 稳态与热/功耗限制 | warm-up/steady-state 定义；clock、temperature、power limit/draw、clock-event/throttle/violation 随时间；background processes 与 MIG/partition | 性能漂移是否与可观测热、功耗或共享资源信号同期 | 用单个起始温度证明全程无 throttling；把相关的 clock event 自动判成唯一根因 |

工具对应关系：CUDA/HIP events 或 `torch.utils.benchmark` 负责普通计时；`nvbandwidth` 与 `nccl-tests` 只提供 transfer/collective 基线；Nsight Systems/Compute、CUPTI、`rocprofv3` 和 ROCm Compute Profiler属于诊断性运行；NVML/DCGM/AMD SMI 为环境与 run-window telemetry。NVIDIA [NVML device queries](https://docs.nvidia.com/deploy/nvml-api/group__nvmlDeviceQueries.html)说明总能耗为 driver reload 以来的 mJ counter，且 power reading 的 averaging 语义随架构不同；AMD SMI 的 [GPU metrics struct](https://rocm.docs.amd.com/projects/amdsmi/en/develop/doxygen/docBin/html/structamdsmi__gpu__metrics__t.html)同时暴露 energy accumulator、driver timestamp、功耗、温度和 clock 字段。实验设计必须按现场 support status 选择采集方法；分析时再核对所用方法，并把累计 counter 的 wrap/reset、采样区间及 background load 纳入不确定性。

验收不是单一 GPU 分数。每个用户声明的 success criterion 单独输出 `accepted`、`rejected` 或 `inconclusive`，关联原始 evidence、比较基线和未检查项；正确性失败不能被性能优势抵消，环境异常也不自动证明算法失败。若指标定义、同步、支持状态、宿主机边界或原始样本缺失，默认结论是 `inconclusive`。

### 4.6 容器 digest 与宿主机边界

| 来源 | 精确官方来源 | 许可证 | 核验日期 | 处置 | 代码是否引入 | 采用判断 |
|---|---|---|---|---|---|---|
| OCI Image Specification | [Content Descriptor 与 digest](https://github.com/opencontainers/image-spec/blob/main/descriptor.md)、[仓库与 LICENSE](https://github.com/opencontainers/image-spec) | Apache-2.0 | 2026-08-27 | **采用镜像身份原则** | 否 | 保存解析后的 platform manifest digest，并在取得内容时验证 digest/size；tag 可变，digest 是内容标识。但它只固定 OCI image graph，不固定 runtime flags、挂载、secret、外部数据或 host |
| NVIDIA Container Toolkit | [Architecture Overview](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/arch-overview.html)、[Troubleshooting 的 device/driver injection 说明](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/troubleshooting.html)、[官方 license 说明](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/overview.html)、[源码](https://github.com/NVIDIA/nvidia-container-toolkit) | Apache-2.0 | 2026-08-27 | **采用 host-injection 边界** | 否 | runtime/hook 会向容器提供 host GPU device、cgroup access 和 driver libraries；因此容器内 `nvidia-smi`/NVML 读到的许多事实来自 host，镜像 digest 不能证明 host driver、GPU、MIG、firmware、kernel 或 topology |
| ROCm containers | [官方 Docker 说明](https://rocm.docs.amd.com/projects/install-on-linux/en/develop/how-to/docker.html) | AMD 官方文档；页面未提供可用于复制代码的单一 OSI 许可，本次不引入内容/代码 | 2026-08-27 | **采用 host-device 边界** | 否 | 容器共享 host kernel，GPU 通过 `/dev/kfd`、`/dev/dri` 或 AMD Container Toolkit 暴露；host 需要合适 kernel-mode driver。容器中的 `rocminfo`/`amd-smi` 只枚举传入设备，不能证明 host 上没有其他 GPU |

每次容器化 run 至少生成两个关联但不合并的记录：

- **Host record：** host/cluster ID，OS/kernel，container runtime 与启动参数，GPU driver，physical GPU UUID/BDF、MIG/AMD partition 与 topology，scheduler placement，device nodes/cgroup/capabilities，clock/power/thermal/ECC/Xid 采集范围，以及 host 侧 inspector 权限。
- **Container record：** image reference 和不可变 digest/平台，容器 OS 与关键 package/runtime/tool version，visible devices 到 host identity 的映射，mount/volume、环境变量的非敏感摘要、工作树 commit/diff、数据与配置哈希、执行命令及 artifact manifest。secret 只记录“由何种机制提供”，不写值。

若只能进入容器而无 host 权限，host driver/GPU 的可见读数仍可作为 `observed-from-container`，但 host kernel logs、完整 topology、未映射设备、MIG/partition 管理状态和其他租户干扰应标为 `not-observable`。镜像 digest 相同但 host、runtime flags、外部数据或 GPU placement 不同的运行不能自动判为环境等价。

### 4.7 专项采用结论

- **采用并独立实现：** `inspect-gpu-environment` 与 `analyze-experiment-results` 的接口和证据状态；CUDA/HIP event-aware timing；`nvidia-smi`/NVML 与 AMD SMI 的只读 capability probes；host/container 双记录；逐指标 acceptance findings。
- **作为现场已有工具的可选集成：** DCGM 被动 watch/job stats、`torch.utils.benchmark`、`nvbandwidth`、`nccl-tests`、`rocprofv3-avail`，以及明确批准后的 Nsight、CUPTI、ROCprofiler/ROCm Compute Profiler。核心 skill 不安装、不 vendoring，也不把这些工具设为所有实验的必备依赖。
- **默认不运行：** DCGM active diagnostics、压力/带宽 microbenchmark、profiler attach/replay、任何 root/CAP_SYS_ADMIN 操作，以及所有 clock/power/ECC/MIG/partition/reset setter。
- **不采用：** 已从官方 CUDA Samples 移除的 `bandwidthTest` 作为当前基线；legacy ROCm-SMI 作为新 schema；容器 digest 作为完整硬件复现证明；跨厂商字段强制对称或单分数 GPU pass/fail。

## 五、已纳入材料的来源边界

| 当前文件范围 | 上游与许可证核验 | 核验日期 | 处置 | 边界 |
|---|---|---|---|---|
| `supervise-experiment-runs/scripts/` 中 7 个既有监督 scripts | 未提供上游，材料中未发现 `LICENSE` 或许可证声明；状态为 **upstream/license unknown** | 2026-08-27 | **仅用于当前私有交付；不推定开源许可证** | 保留并改造 `build_result_manifest.py`、`fetch_results.sh`、`inspect_server.sh`、`remote_runner.sh`、`self_test.py`、`ssh_session.sh`、`verify_result_manifest.py`。当前使用不证明公开复制或分发权限，也不能把功能相似项目的许可证作为其来源 |
| `revise-evidence-report/assets/report.css` | 未提供上游，材料中未发现许可证声明；状态为 **upstream/license unknown** | 2026-08-27 | **机械迁移并泛化，仅用于当前私有交付** | 当前使用不产生开源许可，也不证明对外复制或分发权限 |
| `no-negative-echo` | [LB623/no-negative-echo](https://github.com/LB623/no-negative-echo)，固定 revision 与 baseline 见该 skill 的 NOTICE/PROVENANCE；[MIT](https://github.com/LB623/no-negative-echo/blob/main/LICENSE) | 2026-08-27 | **按固定官方上游引入并修改** | 保留 LICENSE、NOTICE 与逐文件 PROVENANCE；改造 workflow/reference，原样保留 scanner，新增离线自测与可选 host metadata |

## 六、实施处置与未决事项

### 建议落地方式

- 11 个 skills 共享少量稳定的 evidence/manifest 字段。源码/资产例外只有两类：第五节披露的 7 个 supervisor scripts 与一份报告 CSS，以及按 MIT 固定版本引入并记录 LICENSE/NOTICE/PROVENANCE 的 `no-negative-echo` 上游材料；其他候选项目只提供接口/行为原则，不是源码来源。
- 采用 Agent Skills 的渐进披露目录约定。主 skill 只持有目标、边界、交接物和资源导航；出版社规则、领域设计模式、API 说明和渲染细节按需加载。
- 由 `collect-research-sources` 提供后端中立的 connector interface 与可恢复 campaign state；标准库实现覆盖 Crossref、OpenAlex、arXiv、PubMed、Europe PMC、RSS 和安全 seed/fetch，SearXNG 与调用方已有 `gh` 是可选 adapter。`search-primary-evidence` 消费其 candidate inventory 或任何等价输入，保存问题驱动的筛选、反证查询和停止理由。
- 为 `audit-research-evidence`、运行完成判定和最终交付使用独立只读上下文及默认失败的证据契约；失败表示证据不足或检查未完成，不等于科学结论为假。
- 为 hypothesis/design schemas 只设置结构门，例如候选、预测、测量、偏离和来源字段。候选优先级、领域合理性、因果识别、样本量与伦理判断保持可解释、可覆写并交由合适的人类责任主体。
- `supervise-experiment-runs` 只提供 `local` 与 `ssh` 两个浅 transport adapter，并让两者共用 runner、完成判定、恢复/续跑和 manifest；调度器/云集成若未来出现，应作为另行核验的外部 adapter，不改变核心运行协议。
- `inspect-gpu-environment` 只拥有带支持状态的只读 snapshot；`design-research-experiments` 拥有 measurement plan；`analyze-experiment-results` 拥有正确性/性能派生分析和逐项 acceptance finding。主动 benchmark/profiler 先进入获批设计或补充诊断方案，再交给 supervisor 按授权执行。
- `create-publication-figures` 采用 Figure Contract、数据不静默改写、Matplotlib 局部 style、render manifest 和最终成品检查；期刊参数始终附 `source_url`、scope、`verified_at` 和 conflict status。
- `revise-evidence-report` 支持用户需要的任一耐久交付面；Markdown/HTML/PDF 是实现选项，不是固定顺序。`no-negative-echo` 可独立应用于任意最终产物。

### 第三方代码与资产决定

- **调研候选开源项目引入：仅 LB623 `no-negative-echo`。** 发行物固定 upstream revision `c771b7e6b0bd908c7690e401007a5044cbaf47e0` 与 skill v2 baseline `9e78138504905bd7c967ce3e2d9ae7cfa2aacdbf`，保留 MIT LICENSE、NOTICE 和逐文件 PROVENANCE；其余候选项目的许可证只用于决策记录，没有复制其源码或资产。
- **来源受限材料：两组。** `supervise-experiment-runs` 的 7 个既有 scripts 与 `revise-evidence-report/assets/report.css` 均为 `upstream/license unknown`，只用于当前私有交付，不能借用任何相似开源项目的许可证，也不构成公开分发授权。
- **采集 connector 是独立协议实现。** 仓库没有复制 SearXNG、Crawl4AI、RSSHub、WeWe RSS、MediaCrawler 或 `gh` 的代码、容器定义、route、示例全文或品牌资产。标准库 client 只按公开 HTTP/Atom/API 契约互操作；外部服务和 CLI 仍由调用方安装、运营、授权并承担其许可证/条款。
- 如未来引入：必须固定 commit/tag 或发布版本，保存 LICENSE/NOTICE，列出修改，审计 transitive dependencies、字体、示例数据、论文全文、图标和模板，并确认商标/隶属表述。
- 优先使用协议适配或用户已有可执行程序，而不是 vendoring 大型平台。SearXNG、Crawl4AI、RSSHub、`gh`、PaperQA、SkyPilot、Snakemake、Nextflow、DVC、MLflow、Quarto、WeasyPrint 均是可选外部集成或未来候选，不是 11-skill 设计的必备依赖。
- SciencePlots、K-Dense profiles、OptimusKG presets 和 SciPlot reference packs 不进入官方合规规则库；Sakana AI Scientist 因当前自定义用途限制和端到端科学责任边界，不进入核心设计。

### 只能作为带日期的参考配置

- 任一期刊的宽度、字体、DPI、文件格式和面板规则。
- SciencePlots、K-Dense、OptimusKG 或 SciPlot 中的期刊命名样式与 profile。
- 具体会议、合作期刊、旧投稿阶段页面、API 价格/限额和云平台支持列表。

### 采纳前必须补证

- 旗舰 `Science` 当前图形数值与官方模板：需在可人工访问官方页面的环境重新核验。
- Nature 图像 300/450 dpi 表述：需按图像类型和投稿阶段向目标期刊确认。
- ACM 具体 venue 的 DPI、栏宽和生产规则：需读取该 venue 当期 call、模板和 TAPS 指示。
- 两组来源/许可证不明材料在当前私有交付之外的复制、修改和公开分发权限：需由权利人或明确许可证确认；当前使用事实不能外推为开源或再分发授权。
- `no-negative-echo` 的未来上游更新：必须重新固定 revision、复核许可证与逐文件差异，并同步 NOTICE/PROVENANCE；当前固定记录只覆盖本次列明版本。
- 任何 API 的隐私、数据驻留、全文抓取权利、速率与费用：在实际启用适配器时重新核验，不以本报告替代服务条款。

## 七、来源清单

### 出版机构

- Nature Portfolio：[写作入口](https://www.nature.com/nature-portfolio/for-authors/write)、[`Nature` Research Figure Guide](https://research-figure-guide.nature.com/)、[图板构建与导出](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/)、[图形规格](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/)、[图像完整性](https://research-figure-guide.nature.com/figures/image-integrity/)、[Portfolio 图像完整性政策](https://www.nature.com/nature-portfolio/editorial-policies/image-integrity)、[模板资源](https://research-figure-guide.nature.com/resources/templates/)、[`Nature` 最终投稿](https://www.nature.com/nature/for-authors/final-submission)。
- AAAS / Science：[旗舰初投稿说明](https://www.science.org/content/page/instructions-preparing-initial-manuscript)、[旗舰修订说明](https://www.science.org/content/page/instructions-authors-revised-research-articles)、[编辑政策](https://www.science.org/content/page/science-journals-editorial-policies)、[SPJ 项目说明](https://spj.science.org/program-overview)、[SPJ FAQ](https://spj.science.org/frequently-asked-questions)、[SPJ `Research` 作者指南](https://spj.science.org/page/research/for-authors/)。
- IEEE：[图形总页](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/)、[分辨率与尺寸](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/resolution-and-size/)、[文件格式](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/file-formatting/)、[工具与模板](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/authoring-tools-and-templates/)。
- ACM：[Submission Template](https://authors.acm.org/binaries/content/assets/publications/taps/acm_layout_submission_template.pdf)、[Primary Article Template Instructions](https://www.acm.org/binaries/content/assets/publications/taps/acm_primary_article_template_instructions.pdf)、[DIS 2023 无障碍图表指南](https://dis.acm.org/2023/creating-accessible-figures-and-tables/)。

### Skill 规范、开放科学与证据基础设施

- Agent Skills：[规范仓库](https://github.com/agentskills/agentskills)、[格式规范](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx)、[LICENSE](https://github.com/agentskills/agentskills/blob/main/LICENSE)。
- RO-Crate：[规范仓库](https://github.com/ResearchObject/ro-crate)、[快速参考](https://www.researchobject.org/ro-crate/quick-reference)、[Apache-2.0 说明](https://github.com/ResearchObject/ro-crate#license)。
- PRISMA：[PRISMA 2020](https://www.prisma-statement.org/prisma-2020)、[CC-BY-4.0 checklist](https://www.prisma-statement.org/prisma-2020-checklist)。
- Center for Open Science / OSF：[OSF 源码](https://github.com/CenterForOpenScience/osf.io)、[registration 文档](https://github.com/CenterForOpenScience/OSFDocs/blob/master/registrations.rst)、[API v2 规范](https://github.com/CenterForOpenScience/developer.osf.io/blob/master/swagger-spec/swagger.yaml)、[服务与开源许可说明](https://github.com/CenterForOpenScience/cos.io/blob/master/TERMS_OF_USE.md)。
- FutureHouse PaperQA2：[仓库](https://github.com/Future-House/paper-qa)、[Apache-2.0](https://github.com/Future-House/paper-qa/blob/main/LICENSE)。
- AllenAI SciFact：[仓库](https://github.com/allenai/scifact)、[代码/claims/abstract 分层许可](https://github.com/allenai/scifact/blob/master/LICENSE.md)。
- FutureHouse Aviary：[仓库](https://github.com/Future-House/aviary)、[Apache-2.0](https://github.com/Future-House/aviary/blob/main/LICENSE)。

### 深度采集组件与一手数据接口

- MediaCrawler：[仓库/README](https://github.com/NanmiCoder/MediaCrawler)、[pyproject](https://github.com/NanmiCoder/MediaCrawler/blob/main/pyproject.toml)、[LICENSE](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE)、[issues](https://github.com/NanmiCoder/MediaCrawler/issues)、[releases](https://github.com/NanmiCoder/MediaCrawler/releases)。
- SearXNG：[仓库](https://github.com/searxng/searxng)、[AGPL LICENSE](https://github.com/searxng/searxng/blob/master/LICENSE)、[Search API](https://docs.searxng.org/dev/search_api.html)、[容器部署](https://docs.searxng.org/admin/installation-docker.html)、[limiter](https://docs.searxng.org/admin/searx.limiter.html)、[commits](https://github.com/searxng/searxng/commits/master)。
- Crawl4AI：[仓库](https://github.com/unclecode/crawl4ai)、[LICENSE 与附加归属要求](https://github.com/unclecode/crawl4ai/blob/main/LICENSE)、[releases](https://github.com/unclecode/crawl4ai/releases)、[v0.9.0 安全默认](https://github.com/unclecode/crawl4ai/blob/main/docs/blog/release-v0.9.0.md)、[Security/advisories](https://github.com/unclecode/crawl4ai/security)。
- RSSHub：[仓库/README](https://github.com/DIYgod/RSSHub)、[AGPL LICENSE](https://github.com/DIYgod/RSSHub/blob/master/LICENSE)、[package.json](https://github.com/DIYgod/RSSHub/blob/master/package.json)、[Compose](https://github.com/DIYgod/RSSHub/blob/master/docker-compose.yml)、[commits](https://github.com/DIYgod/RSSHub/commits/master)。
- WeWe RSS：[archive 仓库/README](https://github.com/cooderl/wewe-rss)、[MIT LICENSE](https://github.com/cooderl/wewe-rss/blob/main/LICENSE)、[Dockerfile](https://github.com/cooderl/wewe-rss/blob/main/Dockerfile)、[releases](https://github.com/cooderl/wewe-rss/releases)。
- GitHub CLI：[仓库](https://github.com/cli/cli)、[MIT LICENSE](https://github.com/cli/cli/blob/trunk/LICENSE)、[releases](https://github.com/cli/cli/releases)、[`gh api`](https://cli.github.com/manual/gh_api)、[`gh auth login`](https://cli.github.com/manual/gh_auth_login)、[环境变量](https://cli.github.com/manual/gh_help_environment)、[REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)、[REST best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)。
- Crossref：[REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)、[访问/认证/限额](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)、[元数据来源与许可](https://www.crossref.org/documentation/retrieve-metadata/)、[官方文档仓库](https://github.com/CrossRef/rest-api-doc)。
- OpenAlex：[当前 API](https://help.openalex.org/api/)、[认证与限额](https://help.openalex.org/api/authentication/)、[价格](https://help.openalex.org/access/pricing/)、[数据模型](https://help.openalex.org/data/)、[CC0 声明](https://github.com/ourresearch/openalex-docs/blob/main/license.md)。
- arXiv：[API 入口](https://info.arxiv.org/help/api/index.html)、[User Manual](https://info.arxiv.org/help/api/user-manual.html)、[API Terms](https://info.arxiv.org/help/api/tou.html)、[许可选择](https://info.arxiv.org/help/license/index.html)、[S3 bulk](https://info.arxiv.org/help/bulk_data_s3.html)。
- PubMed / NCBI：[API hub](https://www.ncbi.nlm.nih.gov/home/develop/api/)、[E-utilities usage](https://www.ncbi.nlm.nih.gov/books/NBK25497/)、[参数参考](https://www.ncbi.nlm.nih.gov/books/NBK25499/)、[数据使用与版权 policies](https://www.ncbi.nlm.nih.gov/home/about/policies/)。
- Europe PMC：[Developer resources](https://europepmc.org/developers)、[REST API](https://europepmc.org/RestfulWebService)、[copyright](https://europepmc.org/Copyright)、[REST release notes](https://europepmc.org/docs/Europe_PMC_RESTful_Release_Notes.pdf)。

### Agent skills 与自动科研系统

- K-Dense scientific-agent-skills：[仓库](https://github.com/K-Dense-AI/scientific-agent-skills)、[`research-lookup`](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/research-lookup/SKILL.md)、[`literature-review`](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/literature-review/SKILL.md)、[`peer-review`](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/peer-review/SKILL.md)、[`hypothesis-generation`](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/hypothesis-generation/SKILL.md)、[`experimental-design`](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/experimental-design/SKILL.md)、[`scientific-visualization`](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-visualization/SKILL.md)、[`scientific-writing`](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-writing/SKILL.md)、[MIT License](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/LICENSE.md)。
- Anthropic knowledge-work plugins：[仓库](https://github.com/anthropics/knowledge-work-plugins)、[`scientific-problem-selection`](https://github.com/anthropics/knowledge-work-plugins/blob/main/bio-research/skills/scientific-problem-selection/SKILL.md)、[Apache-2.0](https://github.com/anthropics/knowledge-work-plugins/blob/main/LICENSE)。
- FutureHouse Robin：[仓库](https://github.com/Future-House/robin)、[Apache-2.0](https://github.com/Future-House/robin/blob/main/LICENSE)。
- Sakana AI Scientist：[仓库](https://github.com/SakanaAI/AI-Scientist)、[当前自定义许可证](https://github.com/SakanaAI/AI-Scientist/blob/main/LICENSE)。

### 远程运行、复现与追踪

- Anthropic CWC：[仓库](https://github.com/anthropics/cwc-long-running-agents)、[Apache-2.0](https://github.com/anthropics/cwc-long-running-agents/blob/main/LICENSE)。
- SkyPilot：[仓库](https://github.com/skypilot-org/skypilot)、[Agent Skill](https://github.com/skypilot-org/skypilot/blob/master/agent/skills/skypilot/SKILL.md)、[YAML job recovery 规范](https://github.com/skypilot-org/skypilot/blob/master/docs/source/reference/yaml-spec.rst)、[Apache-2.0](https://github.com/skypilot-org/skypilot/blob/master/LICENSE)。
- Snakemake：[仓库](https://github.com/snakemake/snakemake)、[部署与复现](https://github.com/snakemake/snakemake/blob/main/docs/snakefiles/deployment.rst)、[MIT License](https://github.com/snakemake/snakemake/blob/main/LICENSE.md)。
- Nextflow：[仓库](https://github.com/nextflow-io/nextflow)、[Apache-2.0](https://github.com/nextflow-io/nextflow/blob/master/COPYING)。
- DVC：[仓库](https://github.com/iterative/dvc)、[Apache-2.0](https://github.com/iterative/dvc/blob/main/LICENSE)。
- MLflow：[仓库](https://github.com/mlflow/mlflow)、[Apache-2.0](https://github.com/mlflow/mlflow/blob/master/LICENSE.txt)。
- Weights & Biases SDK：[仓库](https://github.com/wandb/wandb)、[MIT License](https://github.com/wandb/wandb/blob/main/LICENSE)。

### GPU、性能分析与容器边界

- CUDA 行为与许可：[Runtime Event API](https://docs.nvidia.com/cuda/cuda-runtime-api/group__CUDART__EVENT.html)、[Asynchronous Execution](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/asynchronous-execution.html)、[CUDA C++ 错误检查示例](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/intro-to-cuda-cpp.html)、[CUDA EULA](https://docs.nvidia.com/cuda/eula/index.html)。
- PyTorch 计时：[benchmark recipe](https://docs.pytorch.org/tutorials/recipes/recipes/benchmark)、[`torch.utils.benchmark` API](https://docs.pytorch.org/docs/stable/benchmark_utils.html)、[BSD-3-Clause root LICENSE](https://github.com/pytorch/pytorch/blob/main/LICENSE)。
- NVIDIA 设备与健康：[`nvidia-smi`](https://docs.nvidia.com/deploy/nvidia-smi/index.html)、[NVML](https://docs.nvidia.com/deploy/nvml-api/index.html)、[device queries](https://docs.nvidia.com/deploy/nvml-api/group__nvmlDeviceQueries.html)、[Xid](https://docs.nvidia.com/deploy/xid-errors/introduction.html)、[GPU debug guidelines](https://docs.nvidia.com/deploy/gpu-debug-guidelines/)、[MIG User Guide](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/introduction.html)。
- NVIDIA DCGM：[文档](https://docs.nvidia.com/datacenter/dcgm/latest/)、[feature overview](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/feature-overview.html)、[process/job statistics](https://docs.nvidia.com/datacenter/dcgm/latest/learn/core-services/process-and-job-statistics.html)、[profiling](https://docs.nvidia.com/datacenter/dcgm/latest/learn/modules/profiling.html)、[Apache-2.0 LICENSE](https://github.com/NVIDIA/DCGM/blob/master/LICENSE)、[开源/闭源模块边界](https://github.com/NVIDIA/DCGM/blob/master/docs/contributing.md)。
- NVIDIA profiler：[Nsight Systems User Guide](https://docs.nvidia.com/nsight-systems/UserGuide/index.html) 与 [license](https://docs.nvidia.com/nsight-systems/CopyrightAndLicenses/index.html)、[Nsight Compute Profiling Guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html) 与 [license](https://docs.nvidia.com/nsight-compute/CopyrightAndLicenses/index.html)、[CUPTI overview](https://docs.nvidia.com/cupti/index.html) 与 [usage](https://docs.nvidia.com/cupti/main/main.html)。
- NVIDIA benchmark 工具：[`nvbandwidth`](https://github.com/NVIDIA/nvbandwidth) 与 [Apache-2.0](https://github.com/NVIDIA/nvbandwidth/blob/main/LICENSE)、[`nccl-tests`](https://github.com/NVIDIA/nccl-tests) 的 [performance definitions](https://github.com/NVIDIA/nccl-tests/blob/master/doc/PERFORMANCE.md) 与 [BSD-3-Clause](https://github.com/NVIDIA/nccl-tests/blob/master/LICENSE.txt)、[CUDA Samples Utilities README](https://github.com/NVIDIA/cuda-samples/blob/master/cpp/1_Utilities/README.md) 与 [LICENSE](https://github.com/NVIDIA/cuda-samples/blob/master/LICENSE)、[NVBench](https://github.com/NVIDIA/nvbench) 的 [benchmark 文档](https://github.com/NVIDIA/nvbench/blob/main/docs/benchmarks.md) 与 [LICENSE](https://github.com/NVIDIA/nvbench/blob/main/LICENSE)。
- AMD 管理接口：[AMD SMI CLI](https://rocm.docs.amd.com/projects/amdsmi/en/latest/how-to/amdsmi-cli-tool.html)、[Python API/status](https://rocm.docs.amd.com/projects/amdsmi/en/latest/reference/amdsmi-py-api.html)、[当前源码](https://github.com/ROCm/rocm-systems/tree/develop/projects/amdsmi) 与 [MIT LICENSE](https://github.com/ROCm/rocm-systems/blob/develop/projects/amdsmi/LICENSE)；[退役 ROCm-SMI 仓库](https://github.com/ROCm/rocm_smi_lib) 与 [退役分支 LICENSE](https://github.com/ROCm/rocm_smi_lib/blob/amd-staging_deprecated/License.txt)。
- AMD 计时与 profiler：[HIP events](https://rocm.docs.amd.com/projects/HIP/en/latest/reference/hip_runtime_api/modules/event_management.html) 与 [MIT LICENSE](https://github.com/ROCm/rocm-systems/blob/develop/projects/hip/LICENSE.md)、[ROCprofiler-SDK](https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/latest/)、[`rocprofv3-avail`](https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/docs-7.14.0/how-to/using-rocprofv3-avail.html)、[ROCprofiler-SDK 源码](https://github.com/ROCm/rocm-systems/tree/develop/projects/rocprofiler-sdk) 与 [MIT LICENSE](https://github.com/ROCm/rocm-systems/blob/develop/projects/rocprofiler-sdk/LICENSE.md)。
- AMD roofline：[ROCm Compute Profiler](https://rocm.docs.amd.com/projects/rocprofiler-compute/en/latest/what-is-rocprof-compute.html)、[兼容 accelerator 表](https://rocm.docs.amd.com/projects/rocprofiler-compute/en/develop/reference/compatible-accelerators.html)、[profile/roofline mode](https://rocm.docs.amd.com/projects/rocprofiler-compute/en/develop/how-to/profile/mode.html)、[当前源码](https://github.com/ROCm/rocm-systems/tree/develop/projects/rocprofiler-compute) 与 [MIT LICENSE](https://github.com/ROCm/rocm-systems/blob/develop/projects/rocprofiler-compute/LICENSE.md)。
- 容器身份与 host 边界：[OCI Image Specification descriptor](https://github.com/opencontainers/image-spec/blob/main/descriptor.md) 与 [Apache-2.0 仓库](https://github.com/opencontainers/image-spec)、[NVIDIA Container Toolkit 架构](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/arch-overview.html)、[device/driver injection troubleshooting](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/troubleshooting.html)、[Apache-2.0 源码](https://github.com/NVIDIA/nvidia-container-toolkit)、[ROCm Docker](https://rocm.docs.amd.com/projects/install-on-linux/en/develop/how-to/docker.html)。

### 图形、报告与最终化

- Matplotlib：[文档](https://matplotlib.org/stable/)、[自定义与样式](https://matplotlib.org/stable/users/explain/customizing.html)、[colormap](https://matplotlib.org/stable/users/explain/colors/colormaps.html)、[`savefig`](https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.savefig.html)、[许可证](https://github.com/matplotlib/matplotlib/blob/main/LICENSE/LICENSE)、[许可说明](https://github.com/matplotlib/matplotlib/blob/main/doc/project/license.rst)。
- SciencePlots：[仓库](https://github.com/garrettj403/SciencePlots)、[README](https://github.com/garrettj403/SciencePlots/blob/master/README.md)、[MIT License](https://github.com/garrettj403/SciencePlots/blob/master/LICENSE)。
- OpenAI role-specific plugins：[仓库](https://github.com/openai/role-specific-plugins)、[`visualize-data`](https://github.com/openai/role-specific-plugins/blob/main/plugins/data-analytics/skills/visualize-data/SKILL.md)、[`build-report`](https://github.com/openai/role-specific-plugins/blob/main/plugins/data-analytics/skills/build-report/SKILL.md)、[MIT License](https://github.com/openai/role-specific-plugins/blob/main/LICENSE)。
- Harvard Zitnik Lab OptimusKG：[仓库](https://github.com/mims-harvard/OptimusKG)、[visualization skill](https://github.com/mims-harvard/OptimusKG/blob/main/.agents/skills/scientific-visualization/SKILL.md)、[MIT License](https://github.com/mims-harvard/OptimusKG/blob/main/LICENSE)。
- SciToolsmith sci-plot：[仓库](https://github.com/SciToolsmith/sci-plot)、[skill](https://github.com/SciToolsmith/sci-plot/blob/main/skills/sci-plot/SKILL.md)、[Apache-2.0](https://github.com/SciToolsmith/sci-plot/blob/main/LICENSE)。
- Quarto CLI：[仓库](https://github.com/quarto-dev/quarto-cli)、[MIT License](https://github.com/quarto-dev/quarto-cli/blob/main/COPYING.md)。
- WeasyPrint：[仓库](https://github.com/Kozea/WeasyPrint)、[BSD-3-Clause](https://github.com/Kozea/WeasyPrint/blob/main/LICENSE)。
- Pandoc：[仓库](https://github.com/jgm/pandoc)、[GPL-2.0-or-later](https://github.com/jgm/pandoc/blob/main/COPYING.md)。
- `pre-commit`：[仓库](https://github.com/pre-commit/pre-commit)、[MIT License](https://github.com/pre-commit/pre-commit/blob/main/LICENSE)。
- in-toto：[实现仓库与 Apache-2.0](https://github.com/in-toto/in-toto/blob/develop/LICENSE)、[规范](https://github.com/in-toto/docs/blob/master/in-toto-spec.md)、[社区许可分层说明](https://github.com/in-toto/community/blob/main/GOVERNANCE.md)。
- LB623 no-negative-echo：[固定上游 revision](https://github.com/LB623/no-negative-echo/tree/c771b7e6b0bd908c7690e401007a5044cbaf47e0)、[skill v2 baseline](https://github.com/LB623/no-negative-echo/tree/9e78138504905bd7c967ce3e2d9ae7cfa2aacdbf/no-negative-echo)、[固定 revision 的 MIT License](https://github.com/LB623/no-negative-echo/blob/c771b7e6b0bd908c7690e401007a5044cbaf47e0/LICENSE)。
