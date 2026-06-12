# 项目进展记录

> 本文件是项目的“当前状态快照”。开新对话时，AI 先读 `AGENTS.md`、本文件和 `AUDIT_REPORT.md`，再动手。
> 每完成一个任务、或结束一次工作时，更新本文件。保持它反映“现在”的真实情况。

最后更新：2026-06-13

---

## 当前整体状态

核心功能已有可运行代码：Streamlit 古诗词 RAG 讲解助手、本地 Chroma 向量库、本地 SQLite 学习记录、DeepSeek API 讲解/学情报告，以及若干命令行数据处理脚本。

本轮已完成审计后的 P0/P1/P2 集中整改：局域网访问增加口令保护，API 调用增加输入长度和冷却限制，硬编码路径集中到 `config.py`，破坏性脚本改为备份/原子写入，DB/Chroma/API/OCR 的主要崩溃点增加保护，文档移除明文 key 启动脚本建议，直接依赖已固定版本。整改版已提交、推送并发布为 `v0.2.0`。随后已优化访问口令体验：登录成功后当前浏览器可记住 7 天，侧边栏可退出登录清除记住状态；学习记录已改成长远版口径，候选诗、真正讲解/复习诗、仅提及诗、未命中分开存储；已补充 GitHub README 运行说明；聊天正文已按浏览器会话保存到本地 SQLite，可恢复最近 5 轮对话，并发布为 `v0.4.0`。

---

## 已完成

- 【2026-06-13】完成 `AUDIT_REPORT.md` 安全与质量审计报告，覆盖安全、稳定性、可维护性、测试/文档缺口和修复优先级。
- 【2026-06-13】确认 Chroma 只使用本地 `PersistentClient`，数据在本地 `chroma_db/`，没有以 HTTP server 运行，也不开网络端口；原疑似 P0 降级为 P2 依赖治理风险。
- 【2026-06-13】确认项目可以给同一局域网用户访问，因此 Streamlit 无鉴权按 P1 风险处理。
- 【2026-06-13】确认当前学习记录是模拟数据；真实学生数据接入前必须补隐私提示和数据管理策略。
- 【2026-06-13】补全 `AGENTS.md` 和 `PROGRESS.md`，沉淀长期规则、安全红线和当前进展。
- 【2026-06-13】新增 `.gitignore`，过滤 `learning_records.db`、`chroma_db/`、`__pycache__/`、`.env*`、真实启动脚本、备份文件和凭证类文件。
- 【2026-06-13】初始化 git 仓库，提交初始项目快照，并推送到私有仓库 `dosheda/k12` 的 `main` 分支。
- 【2026-06-13】创建 GitHub Release `v0.1.0`。
- 【2026-06-13】完成审计后 P0/P1/P2 整改，推送到 `main` 并发布 GitHub Release `v0.2.0`。
- 【2026-06-13】优化访问口令体验：新增 7 天“记住此设备”签名 cookie，不保存真实口令；新增侧边栏“退出登录”清除当前浏览器记住状态。
- 【2026-06-13】学习记录改成长远版：新增 `explained_poems`、`reviewed_poems`、`mentioned_poems`、`candidate_poems`、`record_type`，候选诗不再计入已学习，旧记录兼容读取。
- 【2026-06-13】优化学情报告交互：从页面顶部 expander 改为弹窗显示，点击侧边栏生成后不需要回到页面顶部查看。
- 【2026-06-13】新增 GitHub `README.md`：基于原项目说明重写，补充项目特点、技术栈、运行步骤、环境变量、建库/标签脚本、局域网访问和安全说明。
- 【2026-06-13】提交、推送并发布新版 `v0.3.0`，包含访问体验、长远版学习统计、学情报告弹窗和 README 整理。
- 【2026-06-13】优化学情报告查看交互：关闭弹窗后可在侧边栏“查看上次报告”，需要最新数据时再点“重新生成学情报告”，避免重复 API 调用。
- 【2026-06-13】新增聊天正文持久化：`learning_records.db` 增加 `chat_messages` 表，浏览器通过随机会话 cookie 恢复最近 5 轮对话；“开始新对话”会新建会话，不删除学情统计。
- 【2026-06-13】提交、推送并发布新版 `v0.4.0`，包含学情报告复看入口和聊天历史持久化。

---

## 刚才修复 / 确认的 P0/P1

- P0：当前没有已确认未修 P0。Chroma 未以 HTTP server 方式运行、不开放端口，当前无对应远程 HTTP 攻击面；风险保留为 P2 依赖治理。
- P1：已给局域网访问增加最小口令保护，口令来自 `K12_HELPER_ACCESS_CODE`，未配置时 Streamlit 会停止继续使用。位置：`app.py:73`、`config.py:25`。
- P1：已给聊天 API 调用增加输入长度限制和单会话冷却限制，降低局域网滥用和成本风险。位置：`app.py:540`、`config.py:28-29`。
- P1：已把硬编码项目路径集中到 `config.py`，默认使用项目根目录，可通过环境变量覆盖数据路径。位置：`config.py:7-21`。
- P1：已把会删除/覆盖数据的脚本改为先备份或原子替换。位置：`safe_io.py:29`、`safe_io.py:38`、`build_rag_db.py:70`、`reformat_poems.py:216`、`merge_all_poems.py:119`、`merge_80_poems.py:150`、`tag_poems.py:206`。
- P1：已给学习记录 JSON 解析增加容错，坏记录不会直接拖垮统计/报告。位置：`learning_db.py:58`、`learning_db.py:138`、`learning_db.py:200`。
- P1：已给 Chroma 查询空结果、缺字段、记录数不足等情况增加保护。位置：`app.py:140`、`rag_chat.py:51`、`search_rag.py:38`、`update_chroma_tags.py:60`。

---

## 本轮已修复的 P2

- 【P2】API 响应结构不稳定导致崩溃：新增 `api_utils.extract_chat_content()` 统一校验。位置：`api_utils.py:4`。
- 【P2】原始错误信息暴露给用户：新增 `api_utils.classify_api_error()`，UI/CLI 输出安全文案。位置：`api_utils.py:16`、`app.py:955`、`k12_helper.py:248`、`rag_chat.py:357`。
- 【P2】用户输入、报告 prompt 和 API 成本无上限：增加单次问题长度、冷却时间、报告记录数和 prompt 长度限制。位置：`config.py:28-32`、`app.py:540`、`app.py:599`。
- 【P2】使用手册建议 `.bat` 明文保存 API key：已改为系统环境变量和不含密钥的启动脚本建议。位置：`使用手册.html:371-405`。
- 【P2】模型学习标记解析脆弱：已改为隐藏 JSON learning 标记，并兼容旧 taught 标记。位置：`learning_record_utils.py:14`。
- 【P2】OCR 图片无大小/像素限制：已增加文件大小和像素上限。位置：`k12_helper.py:139`、`k12_helper.py:156`。
- 【P2】依赖未固定且含疑似未用 LangChain 依赖：已固定直接依赖版本，并移除未发现 import 的 `langchain*` 依赖。位置：`requirements.txt:1-6`。
- 【P2】学习数据第三方 API 流向说明不足：使用手册已改为说明普通提问和学情报告会把问题/必要摘要发送给 DeepSeek。位置：`使用手册.html:701`。

---

## 正在做（当前任务）

- 任务：无。学情报告查看交互和聊天历史恢复已优化，并纳入新版 `v0.4.0`。
- 进展到哪：生成过报告后，关闭弹窗不会丢失当前会话里的报告；侧边栏可查看上次报告或重新生成。成功问答会写入 `chat_messages`，刷新/重开浏览器可恢复最近 5 轮对话。
- 相关文件：`app.py`、`learning_db.py`、`README.md`、`使用手册.html`、`PROGRESS.md`。
- 卡点/待决定：无阻塞。`chromadb==1.5.9` 截至 2026-06-13 未查到更高修复版，只能先保留本地-only 红线并持续关注升级。

---

## 下一步计划

1. 补 `.env.example` 或更细的配置示例，把可选环境变量集中列清楚。
2. 补自动化测试目录，优先覆盖 `api_utils.py`、`learning_db.py`、`safe_io.py` 和输入校验。
3. 抽出共享 RAG 模块，减少 `app.py` 与 `rag_chat.py` 的重复逻辑。
4. 继续关注 `chromadb` 修复版；一旦有高于 `1.5.9` 的安全版本，优先升级并回归验证。

---

## 已知问题 / 技术债

### P0

- 当前没有已知未修 P0。

### P1

- 当前没有已知未修 P1。若后续接入真实学生/家长数据、开放公网访问、或把 Chroma 改成 HTTP server，必须重新审计并可能产生新的 P1/P0。

### P2

- 【P2】`chromadb==1.5.9` 命中 `CVE-2026-45829`；截至 2026-06-13 `pip index versions chromadb` 未查到高于 `1.5.9` 的修复版。当前缓解措施是只允许本地 `PersistentClient`，不运行 Chroma HTTP server、不开放端口。位置：`requirements.txt:5`、`AGENTS.md:51`。
- 【P2，真实数据前升 P1】`learning_records.db` 默认仍在项目数据目录，且现在包含学习记录和聊天正文；已通过 `.gitignore` 排除并可用 `K12_LEARNING_DB_PATH` 覆盖，但真实学生数据接入前仍需要正式的数据位置、清空、备份和保留策略。位置：`config.py:15`、`learning_db.py:53`。
- 【P2，真实数据前升 P1】学习数据会发送给 DeepSeek；使用手册已有基本提示，但真实使用前还缺正式隐私说明、第三方 API 数据流确认和用户同意流程。位置：`app.py:599`、`使用手册.html:701`。
- 【P2】RAG 检索逻辑仍在 `app.py` 和 `rag_chat.py` 两处存在重复，后续应抽到共享模块。位置：`app.py:250-477`、`rag_chat.py:155-282`。
- 【P2】`app.py` 仍偏长，检索、API、报告、TTS、UI 和状态管理混在一个文件；本轮为控制风险未做大拆分。位置：`app.py:250-955`。
- 【P2】错误分类已集中到 `api_utils.py`，但仍主要依赖错误文本/状态码字符串判断；后续可按 OpenAI SDK 异常类型细化。位置：`api_utils.py:16`。
- 【P2】依赖已固定直接版本，但还没有 lock 文件、hash 校验或自动漏洞扫描流程。位置：`requirements.txt:1-6`。

### P3

- 【P3】缺少 `.env.example` 或集中配置示例；README 已补基础运行说明。
- 【P3】缺少自动化测试目录和 pytest/unittest 用例；本轮只做了语法、静态扫描和轻量 smoke test。
- 【P3】缺少 CI、格式化、静态检查配置和 `.env.example` 或配置示例。
- 【P3】项目根目录仍混放源码、一次性脚本、数据文件、运行时数据库、向量库和样例图片；后续可整理为 `src/`、`scripts/`、`data/`、`docs/`、`tests/`。
- 【P3】缺少数据库备份、迁移、清空学习记录的正式工具和 README 说明。

---

## 重要决策记录

- 【2026-06-13】决定当前技术栈继续沿用 Python + Streamlit + Chroma 本地 `PersistentClient` + SQLite + DeepSeek API；原因是代码已按该方式实现，且适合本地/局域网学习助手。
- 【2026-06-13】决定 Chroma 不以 HTTP server 方式运行，不开放网络端口；如未来要启用 Chroma server，必须先做安全审查和依赖升级。
- 【2026-06-13】决定 API key 只使用系统环境变量 `DEEPSEEK_API_KEY`；不再推荐 `.bat` 明文写 key。
- 【2026-06-13】决定局域网访问必须配置 `K12_HELPER_ACCESS_CODE`，不能默认裸奔。
- 【2026-06-13】确认当前学习记录是模拟数据；如果以后接入真实学生数据，隐私提示和数据管理策略必须先补齐。
- 【2026-06-13】已初始化 git 并推送到私有仓库 `dosheda/k12`；初始化前已补 `.gitignore`，避免运行时数据和密钥误提交。

---

## 给下一个对话的备注

- 开始任务前先读 `AGENTS.md`、`PROGRESS.md`、`AUDIT_REPORT.md`。
- 不要把 Chroma 改成 HTTP server；当前只允许本地 `PersistentClient`。
- 不要把 API key 或访问口令写入 `.bat`、`.env`、说明文档真实示例或任何会提交的文件。
- 新增路径请放进 `config.py` 或环境变量，不要重新写本机绝对路径。
- 当前仓库远端是 `https://github.com/dosheda/k12.git`，默认分支 `main`，已有 release `v0.1.0`、`v0.2.0`、`v0.3.0` 和 `v0.4.0`。
