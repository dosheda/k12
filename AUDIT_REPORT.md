# 安全与质量审计报告

审计日期：2026-06-13（Asia/Shanghai）

审计范围：审计时工作区 `D:\k12 helper codex` 的源码、文档、依赖声明、运行时数据文件和可见目录状态。审计过程未修改业务代码，仅生成本报告。

审计限制：
- 审计时当前目录不是 git 仓库，`git status` 报 `fatal: not a git repository`，且递归未发现 `.git` 目录。用户确认当时项目尚未初始化 git，因此当时没有可审计的 git 历史。
- `requirements.txt` 未锁定版本，依赖漏洞结论只能基于“当前 Python 环境中已安装的直接依赖版本”作为参考。
- `python -m pip_audit` 未安装；`uvx pip-audit -r requirements.txt` 在 124 秒超时。已补充使用 OSV.dev API 查询当前环境版本。
- 未启动 Streamlit 应用做动态渗透测试；以下结论以静态审计和只读命令结果为准。

已运行的检查：
- `rg` 扫描密钥、token、危险 API、文件读写、SQL、异常处理。
- `bandit -r .`：未发现 Bandit 规则命中的安全问题。
- OSV.dev API：当前环境的直接依赖中，`chromadb==1.5.9` 命中 `GHSA-f4j7-r4q5-qw2c / CVE-2026-45829`。
- SQLite 只读检查：`learning_records.db` 当前有 3 条学习记录。

用户确认更新（2026-06-13）：
- 项目可以给同一局域网用户访问，因此“无鉴权 + API 调用/学习记录写入”是已确认使用场景下的风险。
- 当前还没有初始化 git，因此“凭证是否进过 git 历史”在当前项目中不适用；重点转为初始化 git 前的预防。
- 用户确认 Chroma 只使用本地 `PersistentClient`，数据在本地 `chroma_db/` 文件夹，程序直接读写；没有以 HTTP server 方式运行，也不开任何网络端口。因此 Chroma CVE 当前没有对应远程 HTTP 攻击面，但仍应作为依赖治理风险处理。
- 当前学习记录是模拟数据，不是真实学生数据；但如后续接入真实学生，隐私和数据保留风险需要重新升档处理。
- API key 已写入系统环境变量，使用手册中的 `.bat` 明文写 key 示例与当前做法冲突，属于多余且不推荐的文档内容。

发布状态更新（2026-06-13）：
- 审计后已新增 `.gitignore`，过滤 `learning_records.db`、`chroma_db/`、`__pycache__/`、`.env*`、真实启动脚本和凭证类文件。
- 审计后已初始化 git，提交初始项目快照，并推送到私有仓库 `dosheda/k12` 的 `main` 分支。
- 审计后已创建初始 GitHub Release `v0.1.0`。

## ① 项目概览

项目用途：
- 一个面向 K12 的学习助手，核心是“古诗词 RAG 讲解助手”，并保留了一个命令行数学/错题讲解助手。
- 网页主入口是 Streamlit 应用，用户提问后从本地 Chroma 向量库检索古诗，再调用 DeepSeek API 生成讲解。
- 学习行为记录保存在本地 SQLite，用于生成学情报告。

技术栈：
- Python 3.14（当前环境）。
- Streamlit：网页聊天界面，见 `app.py:16`、`app.py:37`。
- ChromaDB + SentenceTransformer BGE 中文 embedding：本地向量检索，见 `app.py:29-31`、`app.py:77-81`。
- DeepSeek API，通过 OpenAI SDK 兼容接口调用，见 `app.py:121-124`、`app.py:433-437`。
- SQLite：学习记录，见 `learning_db.py:32`、`learning_db.py:50`。
- Tesseract OCR + Pillow：命令行图片题识别，见 `k12_helper.py:32-37`、`k12_helper.py:141-147`。

整体结构：
- `app.py`：Streamlit 主应用，包含 RAG 检索、多轮对话、TTS、学情报告。
- `learning_db.py`：SQLite 记录与统计。
- `rag_chat.py`、`search_rag.py`：命令行 RAG 讲解/检索脚本。
- `k12_helper.py`：命令行错题讲解与 OCR。
- `build_rag_db.py`、`update_chroma_tags.py`、`tag_poems.py`、`merge_*.py`、`reformat_poems.py`：数据处理、建库和标签脚本。
- `chroma_db/`、`learning_records.db`：运行时数据。
- `使用手册.html`：用户使用说明。
- `README.md`、`.gitignore`、测试目录目前缺失。

## ② 安全问题

### S1. P2：当前环境的 `chromadb==1.5.9` 命中漏洞，但当前本地 PersistentClient 用法未暴露对应 HTTP 攻击面

位置：
- `requirements.txt:7`
- `app.py:96-100`
- `rag_chat.py:49-52`
- `search_rag.py:37-40`
- `build_rag_db.py:73-80`
- `update_chroma_tags.py:59-60`

说明：
- OSV.dev 显示当前环境 `chromadb==1.5.9` 受 `GHSA-f4j7-r4q5-qw2c / CVE-2026-45829` 影响，摘要为 ChromaDB Python project pre-authentication code injection vulnerability。
- OSV 影响范围显示 `introduced: 1.0.0`，`last_affected: 1.5.9`。
- 用户确认当前只使用本地 `PersistentClient`，数据存在本地 `chroma_db/`，没有以 HTTP server 方式运行，也不开任何网络端口。因此该 CVE 的预认证 HTTP 攻击面在当前部署中不暴露。
- 风险仍需保留为 P2：依赖版本处于已知受影响范围，未来如果启用 Chroma server、升级部署方式或复用依赖，可能重新引入高危风险。

建议：
- 将 `chromadb` 升级到不受影响版本，并在 `requirements.txt` 中固定版本。
- 在 README/运行说明中写明当前只支持本地 `PersistentClient`，不启动 Chroma HTTP server。
- 如果未来要启用 Chroma server，必须先完成依赖升级、鉴权和端口暴露审查。

### S2. P1：Streamlit 应用无鉴权，局域网访问场景已确认，可能导致 API 成本被滥用

位置：
- `app.py:803-817`
- `app.py:837-852`
- `learning_db.py:80-104`
- `使用手册.html:718-719`

说明：
- 应用没有登录、口令、访问控制或 CSRF/来源限制。
- 使用手册说明手机可通过同一 WiFi 访问 `http://电脑的IP地址:8501`。
- 用户已确认项目可以给同一局域网用户访问；因此任何同网用户都可能提问、触发 DeepSeek API 成本，并写入共享的 `learning_records.db`。

建议：
- 仅本机使用时，文档明确要求绑定 localhost。
- 需要局域网使用时，增加最小鉴权，如访问口令、反向代理 Basic Auth、Streamlit secrets 中的本地密码。
- 对生成报告、调用 API 的动作加速率限制和输入长度限制。

### S3. P2（真实数据前升 P1）：学习记录数据库位于项目目录且没有 `.gitignore`

位置：
- `learning_db.py:38`
- `learning_db.py:94-100`
- `learning_records.db`（工作区根目录，当前 3 条记录）

说明：
- `learning_records.db` 保存用户问题和检索到的诗/标签，属于学习行为数据。
- 用户确认当前记录是模拟数据，因此当前泄露影响较低；如果后续接入真实学生数据，本项应提升为 P1。
- 用户确认当前尚未初始化 git，因此没有当前项目 git 历史可泄露；但当前目录没有 `.gitignore`，如果后续初始化 git，数据库、`chroma_db/`、`__pycache__/` 都可能被误提交。
- 当前代码还把数据库路径硬编码到 `D:\k12 helper\learning_records.db`，与当前工作区 `D:\k12 helper codex` 不一致，容易出现“代码读写另一个目录的数据”的问题。

建议：
- 增加 `.gitignore`：至少排除 `*.db`、`chroma_db/`、`__pycache__/`、`.env`、密钥文件。
- 把学习记录移到用户数据目录或可配置路径。
- README/使用手册中说明学习记录包含提问数据，提供清空和备份方式。

### S4. P2：学习数据会发送给 DeepSeek，真实数据使用前需要隐私提示

位置：
- `app.py:414-425`
- `app.py:433-437`
- `app.py:550-583`
- `使用手册.html:703-704`

说明：
- 普通提问会把用户问题和检索上下文发送给 DeepSeek。
- 学情报告会把历史提问、接触过的诗和标签摘要发送给 DeepSeek。
- 用户确认当前数据是模拟数据；如果后续输入真实学生问题或学习记录，需按真实学习数据处理。
- 使用手册写“DeepSeek API 默认不记录请求内容”，该说法需要以服务商当前政策为准。此处标为疑似，因为我没有在项目内看到政策链接或用户同意流程。

建议：
- 文档改为可验证表述：说明哪些数据会发给第三方 API，并链接服务商隐私/数据政策。
- 学情报告前增加确认提示。
- 对问题文本做必要最小化，避免把无关个人信息发给模型。

### S5. P2：未知错误直接展示原始错误信息，可能暴露路径、请求细节或内部状态

位置：
- `app.py:591-603`
- `app.py:858-880`
- `k12_helper.py:186-187`
- `k12_helper.py:230-264`
- `rag_chat.py:345-369`

说明：
- 未知异常会把 `str(e)` 直接显示到 UI 或终端。
- 对本地工具影响较小；如果给学生/家长或局域网用户使用，错误信息可能包含本机路径、库内部信息、API 响应细节等。

建议：
- 用户侧只显示通用错误文案和错误编号。
- 详细错误写入本地日志，日志中注意脱敏。
- API 错误按异常类型处理，避免字符串匹配和原文透出。

### S6. P2：没有输入长度、频率和成本控制

位置：
- `app.py:803-817`
- `app.py:409-425`
- `app.py:550-569`
- `k12_helper.py:275-299`
- `rag_chat.py:280-317`

说明：
- 用户输入没有长度限制。
- 多轮历史和 RAG 上下文会一起进入 API 请求。
- 学情报告会把全部历史记录拼入 prompt，记录变多后可能超长、超时或产生高额 token 成本。

建议：
- 对单次问题、历史条数、报告记录数设上限。
- 对 API 调用加 cooldown、重试退避和预算提示。
- 报告生成改为分页/摘要后再发送。

### S7. P2：使用手册建议在 `.bat` 中写 API Key，容易形成明文凭证文件

位置：
- `使用手册.html:402-407`

说明：
- 文档示例建议创建 `启动.bat` 并写入 `set DEEPSEEK_API_KEY=sk-你的key`。
- 用户确认 API key 已写入系统环境变量，因此该 `.bat` 写 key 示例多余，且会诱导用户把密钥保存成明文文件，后续可能被误提交、截图或共享。

建议：
- 改为说明系统级用户环境变量、PowerShell profile、Windows Credential Manager，或明确要求 `启动.bat` 不得提交。
- 如果保留脚本方案，应提供 `启动.example.bat`，其中只放占位符，并在 `.gitignore` 排除真实脚本。

### S8. P2：硬编码绝对路径暴露本机结构并造成安全/运维边界混乱

位置：
- `app.py:88`
- `app.py:195`
- `learning_db.py:38`
- `build_rag_db.py:25`
- `build_rag_db.py:66`
- `merge_all_poems.py:87-99`
- `merge_80_poems.py:115-118`
- `使用手册.html:383`
- `使用手册.html:403-406`

说明：
- 多处路径写死为 `D:\k12 helper\...` 或 `C:\Users\aa\Music\shi\...`，与当前项目目录不一致。
- 这会导致程序从另一个目录读写数据，也可能在错误信息或文档中暴露本机用户名/目录结构。

建议：
- 使用项目根目录相对路径或统一配置文件。
- 所有数据路径从环境变量或 Streamlit secrets/config 读取。

### S9. 已确认未发现：硬编码真实密钥、命令注入、SQL 拼接注入

位置：
- 环境变量读取：`app.py:110-123`、`k12_helper.py:47-65`、`rag_chat.py:61-71`、`tag_poems.py:29-34`
- SQL 参数化写入：`learning_db.py:94-101`
- 固定 SQL 查询：`learning_db.py:132-137`、`learning_db.py:187-188`

说明：
- 当前源码没有发现真实 `sk-...`、AWS key、Google API key、私钥块等明文凭证。
- 没有发现 `subprocess`、`os.system`、`shell=True`、`eval`、`exec` 等命令执行入口。
- SQLite 写入使用参数化查询，没有看到 SQL 字符串拼接。

限制：
- 因无 git 历史，无法证明历史提交中从未出现过凭证。

## ③ Bug 与稳定性风险

### B1. P1：当前工作区与硬编码路径不一致，主应用可能读取/写入错误目录

位置：
- `app.py:88`
- `app.py:195`
- `learning_db.py:38`
- `rag_chat.py:42`
- `rag_chat.py:134`

说明：
- 当前项目在 `D:\k12 helper codex`，但代码读写 `D:\k12 helper\...`。
- 如果旧目录不存在，应用会找不到向量库或诗词文件；如果旧目录存在，则当前项目的 `chroma_db/` 和 `learning_records.db` 可能不会被使用。

建议：
- 统一用 `Path(__file__).resolve().parent` 拼接项目内数据路径。
- 允许通过环境变量覆盖数据目录。

### B2. P1：多个脚本会覆盖或删除数据，没有确认、备份或原子写入

位置：
- `build_rag_db.py:66-71`
- `reformat_poems.py:197-217`
- `merge_all_poems.py:109-114`
- `merge_80_poems.py:140-145`
- `tag_poems.py:187-203`
- `update_chroma_tags.py:88-93`

说明：
- 建库脚本发现目标 Chroma 目录存在就直接 `shutil.rmtree`。
- 格式化和合并脚本直接覆盖源/目标文本文件。
- 标签更新脚本直接修改 Chroma metadata。

建议：
- 写入前创建时间戳备份。
- 改为先写临时文件，校验成功后原子替换。
- 对删除/覆盖动作增加确认参数，如 `--force`。

### B3. P1：SQLite 中 JSON 损坏或旧格式不兼容会导致统计/报告崩溃

位置：
- `learning_db.py:141-154`
- `learning_db.py:193-199`
- `app.py:523-524`

说明：
- `json.loads(row["poem_data"])` 没有异常处理。
- 侧边栏统计处有宽泛 `except`，但学情报告生成在进入 API try 块前就读取 records/stats，数据库一旦损坏会直接中断报告流程。

建议：
- 对每条记录独立容错，坏记录隔离并提示。
- 增加 schema version 和迁移逻辑。
- 提供数据库健康检查/修复工具。

### B4. P1：Chroma 查询结果和 metadata 结构被假定永远完整

位置：
- `app.py:202-212`
- `app.py:326-343`
- `rag_chat.py:141-151`
- `rag_chat.py:216-230`
- `search_rag.py:82-90`
- `update_chroma_tags.py:102-106`

说明：
- 代码直接访问 `results["ids"][0]`、`metas_list[i]["title"]`。
- `update_chroma_tags.py` 固定抽查第 0、19、76 条，数据少于 77 条会崩溃。
- `load_poem_data()` 默认 Chroma metadata 顺序与文本文件顺序一致；如果顺序变化，标签可能匹配到错误诗。

建议：
- 对空结果、缺字段、数量不足做保护。
- 按稳定 id 或诗名关联文本和 metadata，不依赖列表顺序。
- 启动时校验 Chroma 记录数和文本诗数量一致。

### B5. P2：API 响应结构被假定一定有 `choices[0].message.content`

位置：
- `app.py:438`
- `app.py:586`
- `k12_helper.py:214`
- `rag_chat.py:326`
- `tag_poems.py:126`

说明：
- API 超时、内容过滤、空响应或 SDK 返回结构变化时，可能出现 `IndexError` 或 `AttributeError`。

建议：
- 检查 `response.choices` 是否存在。
- 对空内容给用户可恢复提示。
- 对 API 调用统一封装。

### B6. P2：模型标记解析脆弱，可能导致学习记录漏记

位置：
- `app.py:421-423`
- `app.py:455-467`
- `app.py:837-852`

说明：
- 依赖模型在回答末尾输出 `<!-- taught: ... -->`。
- 正则 `([^-]+?)` 遇到连字符可能截断，诗名分隔只按英文逗号，不支持中文逗号。
- 如果模型未按格式输出，学习记录静默跳过。

建议：
- 使用结构化输出或单独 JSON 字段。
- 至少支持中文逗号、顿号和多行格式。
- 记录解析失败指标，便于发现漏记。

### B7. P2：学情报告 prompt 随历史无界增长

位置：
- `app.py:550-569`

说明：
- 报告生成会拼接全部记录和所有接触过的诗，记录增加后可能触发 token 超限、慢请求或高成本。

建议：
- 先在本地聚合摘要，限制问题样本数量。
- 对报告生成设置最大记录数和最大 prompt 字符数。

### B8. P2：OCR 接收本地图片路径但没有大小/像素限制

位置：
- `k12_helper.py:119-147`

说明：
- 只校验文件存在和扩展名，未限制文件大小、像素数量或格式解析风险。
- Pillow/Tesseract 处理超大或恶意图片可能造成内存/CPU 占用过高。

建议：
- 检查文件大小和像素上限。
- 打开图片后调用 `img.verify()` 或受控转换。
- 对 OCR 设置超时。

## ④ 可维护性问题

### M1. P2：RAG 检索逻辑在 `app.py` 和 `rag_chat.py` 中重复

位置：
- `app.py:216-389`
- `rag_chat.py:155-260`

说明：
- 关键词提取、关键词检索、混合检索基本重复。
- 后续修 bug 容易只改一处。

建议：
- 抽到共享模块，如 `rag_service.py`。

### M2. P2：错误处理逻辑重复且靠字符串匹配

位置：
- `app.py:858-880`
- `k12_helper.py:230-268`
- `rag_chat.py:345-371`

说明：
- 三处维护同一套错误分类。
- 依赖 `str(e)` 中包含 `401`、`429` 等字符串，SDK 或服务端文案变化时容易误判。

建议：
- 封装统一 API 调用与异常分类。
- 优先使用 SDK 异常类型和 HTTP 状态码。

### M3. P2：主应用文件过长，多个长函数承担过多职责

位置：
- `app.py:287-389`
- `app.py:515-603`
- `app.py:624-700`
- `app.py:708-880`

说明：
- `app.py` 共 880 行，混合了配置、检索、API、报告、TTS、UI 渲染和状态管理。
- 长函数包括 `rag_search`、`generate_learning_report`、`render_tts_button`。

建议：
- 按模块拆分：配置、RAG、API、学习记录、UI 组件。

### M4. P2：依赖声明未固定版本且包含疑似未使用依赖

位置：
- `requirements.txt:1-8`

说明：
- 没有版本号和 hash，无法复现环境，也影响漏洞审计。
- `langchain`、`langchain-chroma`、`langchain-community` 在源码中未发现 import，可能是历史遗留。

建议：
- 固定直接依赖版本，必要时生成 lock 文件。
- 移除未使用依赖，降低安装体积和漏洞面。

### M5. P3：项目还没有清晰包结构，脚本与数据混在根目录

位置：
- 工作区根目录整体结构。

说明：
- 主程序、实验脚本、生成脚本、数据库、向量库、图片样例、文档都在根目录。
- 新人或后续 AI 很难区分“生产入口”和“一次性脚本”。

建议：
- 建议结构：`src/`、`scripts/`、`data/`、`docs/`、`tests/`。
- 在 README 中标明主入口和脚本用途。

### M6. P3：`AGENTS.md` 与 `PROGRESS.md` 仍是模板状态

位置：
- `AGENTS.md:9-16`
- `AGENTS.md:19-25`
- `PROGRESS.md:6-28`
- `PROGRESS.md:32-58`

说明：
- 项目概述、技术栈、当前进展、已知问题都未填。
- 长期协作规则要求“新增或修改功能后同步更新 README/PROGRESS”，但当前状态没有沉淀。

建议：
- 在你确认后补全项目一句话目标、技术栈选择、当前功能和已知问题。

## ⑤ 缺失项

- 缺 `README.md`：当前只有 `使用手册.html`，没有面向开发者的安装、运行、配置、数据目录、隐私说明。
- 缺 `.gitignore`：运行时 DB、向量库、缓存、密钥文件没有保护。
- 缺测试目录和自动化测试：没有 pytest/unittest 测试；`test_question.png`、`test_triangle.png` 只是样例图片。
- 缺依赖锁定：`requirements.txt` 无版本号，无法稳定复现和审计。
- 缺配置示例：没有 `.env.example` 或配置说明来替代硬编码路径。
- 缺 CI/格式化/静态检查配置。
- 缺数据库备份、迁移、清空学习记录的正式机制。
- 缺隐私说明：需要明确哪些数据会留本地、哪些会发给 DeepSeek。

## ⑥ 修复优先级清单

| 级别 | 问题 | 位置 | 建议 |
| --- | --- | --- | --- |
| P1 | Streamlit 无鉴权，且局域网访问已确认，可被同网用户调用 API 和写学习记录 | `app.py:803-817`、`使用手册.html:718-719` | 加访问口令；报告/API 调用加限流；不要无保护暴露到局域网 |
| P2（真实数据前升 P1） | 学习记录 DB 在项目目录且无 `.gitignore`，当前是模拟数据但未来易误提交 | `learning_db.py:38`、`learning_records.db` | 初始化 git 前增加 `.gitignore`；迁移到用户数据目录；提供清空/备份 |
| P1 | 硬编码路径与当前工作区不一致，可能读写错误目录 | `app.py:88`、`app.py:195`、`learning_db.py:38` | 改项目相对路径和统一配置 |
| P1 | 建库/整理脚本会删除或覆盖数据，无备份 | `build_rag_db.py:66-71`、`reformat_poems.py:197-217` | 加备份、原子写入和 `--force` |
| P1 | DB JSON 或 Chroma 数据异常会导致报告/检索崩溃 | `learning_db.py:142`、`app.py:326-343` | 加数据校验、坏记录隔离、空结果保护 |
| P2 | 学习数据会发给 DeepSeek；当前为模拟数据，真实使用前隐私说明不足 | `app.py:550-583`、`使用手册.html:703-704` | 增加隐私提示、用户确认、政策链接 |
| P2 | 原始错误信息展示给用户 | `app.py:591-603`、`app.py:858-880` | 用户侧通用错误，内部日志脱敏 |
| P2 | 输入、报告和 API 成本无上限 | `app.py:803-817`、`app.py:550-569` | 限制字符数、历史数、报告记录数和调用频率 |
| P2 | `chromadb==1.5.9` 命中 CVE-2026-45829；当前本地用法不暴露 HTTP 攻击面，但依赖仍应升级 | `requirements.txt:7`、`app.py:96` | 升级并固定 `chromadb`；未来启用 Chroma server 前先做安全审查 |
| P2 | 使用手册建议 `.bat` 明文保存 API key，与系统环境变量做法冲突且不推荐 | `使用手册.html:402-407` | 删除该示例或改为不含 key 的启动脚本 |
| P2 | RAG、错误处理等逻辑重复 | `app.py:216-389`、`rag_chat.py:155-260` | 抽共享模块 |
| P2 | 依赖未锁版本且存在疑似未使用依赖 | `requirements.txt:1-8` | 固定版本；移除未用依赖；定期漏洞扫描 |
| P3 | 主文件过长、职责混杂 | `app.py:287-880` | 拆模块 |
| P3 | README、测试、CI、配置样例缺失 | 项目根目录 | 补齐工程基础设施 |
| P3 | AGENTS/PROGRESS 仍是模板 | `AGENTS.md:9-25`、`PROGRESS.md:6-58` | 你确认后补全长期规则和项目状态 |

## 确认状态与遗留问题

1. 已确认：项目可以给同一局域网用户访问，所以无鉴权风险按真实使用场景处理。
2. 已确认：当前还没有初始化 git，因此当前项目无 git 历史可审计；初始化前应先补 `.gitignore`。
3. 已确认：Chroma 只使用本地 `PersistentClient`，数据存在本地 `chroma_db/`，没有以 HTTP server 方式运行，也不开任何网络端口；CVE 项已降级为依赖治理风险。
4. 已确认：当前学习记录是模拟数据，不是真实学生数据；真实使用前需要补隐私提示和数据管理策略。
5. 已确认：API key 已写入系统环境变量，使用手册里的 `.bat` 明文 key 示例多余且不推荐。
6. 待确认：是否同意把“不要把 API key 写进 bat 文件”和“运行时数据必须 gitignore”写进 `AGENTS.md` 作为长期规则。
