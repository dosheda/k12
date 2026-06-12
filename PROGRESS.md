# 项目进展记录

> 本文件是项目的“当前状态快照”。开新对话时，AI 先读 `AGENTS.md`、本文件和 `AUDIT_REPORT.md`，再动手。
> 每完成一个任务、或结束一次工作时，更新本文件。保持它反映“现在”的真实情况。

最后更新：2026-06-13

---

## 当前整体状态
核心功能已经有可运行代码：Streamlit 古诗词 RAG 讲解助手、本地 Chroma 向量库、本地 SQLite 学习记录、DeepSeek API 讲解/学情报告，以及若干命令行数据处理脚本。

当前阶段是安全与质量整改前的整理阶段：已完成全面审计、文档规则补全、git 初始化、首个远端推送和初始 release；代码层面的 P1/P2 问题还没有修复。

---

## 已完成
- 【2026-06-13】完成 `AUDIT_REPORT.md` 安全与质量审计报告，覆盖安全、稳定性、可维护性、测试/文档缺口和修复优先级。
- 【2026-06-13】确认 Chroma 只使用本地 `PersistentClient`，数据在本地 `chroma_db/`，没有以 HTTP server 运行，也不开网络端口；原先疑似 P0 的 Chroma 远程攻击面降级为 P2 依赖治理风险。
- 【2026-06-13】确认项目可以给同一局域网用户访问，因此 Streamlit 无鉴权按 P1 风险处理。
- 【2026-06-13】确认当前项目尚未初始化 git；当前无 git 历史可审计，初始化 git 前必须先补 `.gitignore`。
- 【2026-06-13】确认学习记录当前为模拟数据；真实学生数据接入前必须补隐私提示和数据管理策略。
- 【2026-06-13】确认 API key 已写入系统环境变量；`.bat` 明文写 key 的文档示例属于多余且不推荐。
- 【2026-06-13】补全 `AGENTS.md`：项目概述、技术栈、长期约定和安全红线。
- 【2026-06-13】补全 `PROGRESS.md`：当前状态、已完成事项、未修问题和下一步计划。
- 【2026-06-13】新增 `.gitignore`，过滤 `learning_records.db`、`chroma_db/`、`__pycache__/`、`.env*`、真实启动脚本和凭证类文件。
- 【2026-06-13】初始化 git 仓库，提交初始项目快照，并推送到私有仓库 `dosheda/k12` 的 `main` 分支。
- 【2026-06-13】创建 GitHub Release `v0.1.0`。

---

## 刚才修复 / 确认的 P0/P1
- P0：没有修复代码层 P0。经用户确认，Chroma 不以 HTTP server 方式运行、不开放端口，因此原疑似 P0 不再作为当前暴露风险，已在审计报告中降级为 P2 依赖治理风险。
- P1：没有修复代码层 P1。本次只完成文档补全和风险确认；P1 代码问题仍列在“已知问题 / 技术债”中。

---

## 正在做（当前任务）
- 任务：安全审计后的项目长期规则和进展文档补全。
- 进展到哪：`AGENTS.md` 和 `PROGRESS.md` 已按当前代码和 `AUDIT_REPORT.md` 填好。
- 相关文件：`AGENTS.md`、`PROGRESS.md`、`AUDIT_REPORT.md`。
- 卡点/待决定：下一步先修哪个 P1 需要用户决定。

---

## 下一步计划
1. 先修 P1：给局域网访问增加最小鉴权、API 调用限流和输入长度限制。
2. 先修 P1：把硬编码绝对路径改成项目根目录相对路径或统一配置。
3. 继续修 P1：给会删除/覆盖数据的脚本加备份、确认或 `--force`。
4. 修 P2：升级并锁定 `chromadb` 和直接依赖版本，清理疑似未使用依赖。
5. 补基础工程：README、测试目录、运行说明、隐私说明和配置示例。

---

## 已知问题 / 技术债

### P0
- 当前没有已知未修 P0。Chroma CVE 已确认当前无 HTTP server 攻击面，但依赖仍需按 P2 处理。

### P1
- 【P1】Streamlit 无鉴权，且项目确认会给同一局域网用户访问；同网用户可能调用 DeepSeek API、产生成本并写入学习记录。位置：`app.py:803-817`、`使用手册.html:718-719`。
- 【P1】当前工作区 `D:\k12 helper codex` 与代码硬编码路径 `D:\k12 helper\...` 不一致，可能读取或写入错误目录。位置：`app.py:88`、`app.py:195`、`learning_db.py:38`、`rag_chat.py:42`、`rag_chat.py:134`。
- 【P1】多个脚本会删除或覆盖数据，没有确认、备份或原子写入。位置：`build_rag_db.py:66-71`、`reformat_poems.py:197-217`、`merge_all_poems.py:109-114`、`merge_80_poems.py:140-145`、`tag_poems.py:187-203`、`update_chroma_tags.py:88-93`。
- 【P1】SQLite 中 `poem_data` JSON 损坏或旧格式不兼容时，统计/学情报告可能崩溃。位置：`learning_db.py:141-154`、`learning_db.py:193-199`、`app.py:523-524`。
- 【P1】Chroma 查询结果和 metadata 结构被假定永远完整，空结果、缺字段、记录数不足时可能崩溃或错配标签。位置：`app.py:202-212`、`app.py:326-343`、`rag_chat.py:141-151`、`rag_chat.py:216-230`、`search_rag.py:82-90`、`update_chroma_tags.py:102-106`。

### P2
- 【P2，真实数据前升 P1】`learning_records.db` 位于项目目录，当前是模拟数据；已通过 `.gitignore` 避免提交，但后续接入真实学生数据前仍必须迁移或明确保护。位置：`learning_db.py:38`、`learning_records.db`。
- 【P2】学习数据会发送给 DeepSeek；当前为模拟数据，真实使用前缺少隐私提示、第三方 API 数据流说明和政策链接。位置：`app.py:550-583`、`使用手册.html:703-704`。
- 【P2】未知错误会把原始错误信息展示给用户，可能暴露本机路径、请求细节或内部状态。位置：`app.py:591-603`、`app.py:858-880`、`k12_helper.py:186-187`、`rag_chat.py:345-369`。
- 【P2】用户输入、报告生成和 API 成本没有上限控制。位置：`app.py:803-817`、`app.py:409-425`、`app.py:550-569`。
- 【P2】当前环境 `chromadb==1.5.9` 命中 `CVE-2026-45829`；当前本地 `PersistentClient` 用法不暴露 HTTP 攻击面，但依赖仍应升级并锁版本。位置：`requirements.txt:7`。
- 【P2】使用手册建议在 `.bat` 中明文保存 API key，与当前系统环境变量做法冲突且不推荐。位置：`使用手册.html:402-407`。
- 【P2】API 响应结构被假定一定有 `choices[0].message.content`，空响应或 SDK 变化时可能崩溃。位置：`app.py:438`、`app.py:586`、`k12_helper.py:214`、`rag_chat.py:326`、`tag_poems.py:126`。
- 【P2】模型讲解诗名标记解析脆弱，可能导致学习记录漏记。位置：`app.py:421-423`、`app.py:455-467`、`app.py:837-852`。
- 【P2】学情报告 prompt 随历史记录无界增长，可能超 token、变慢或增加成本。位置：`app.py:550-569`。
- 【P2】OCR 图片路径输入缺少文件大小、像素数量和处理超时限制。位置：`k12_helper.py:119-147`。
- 【P2】RAG 检索逻辑在 `app.py` 和 `rag_chat.py` 重复，后续修 bug 容易漏改。位置：`app.py:216-389`、`rag_chat.py:155-260`。
- 【P2】错误处理逻辑重复且靠字符串匹配，SDK 或服务端文案变化时容易误判。位置：`app.py:858-880`、`k12_helper.py:230-268`、`rag_chat.py:345-371`。
- 【P2】`app.py` 过长且职责混杂，检索、API、报告、TTS、UI 和状态管理都在一个文件里。位置：`app.py:287-880`。
- 【P2】`requirements.txt` 未锁版本，且 `langchain`、`langchain-chroma`、`langchain-community` 在源码中未发现 import，疑似未使用依赖。位置：`requirements.txt:1-8`。

### P3
- 【P3】项目根目录混放源码、一次性脚本、数据文件、运行时数据库、向量库和样例图片，结构不清晰。
- 【P3】缺少 `README.md`，当前只有 `使用手册.html`，没有面向开发者的安装、运行、配置、数据目录和隐私说明。
- 【P3】缺少自动化测试目录和 pytest/unittest 用例；现有 `test_question.png`、`test_triangle.png` 只是样例图片。
- 【P3】缺少 CI、格式化、静态检查配置和 `.env.example` 或配置示例。
- 【P3】缺少数据库备份、迁移、清空学习记录的正式机制说明。

---

## 重要决策记录
- 【2026-06-13】决定当前技术栈继续沿用 Python + Streamlit + Chroma 本地 `PersistentClient` + SQLite + DeepSeek API；原因是代码已按该方式实现，且适合本地/局域网学习助手。
- 【2026-06-13】决定 Chroma 不以 HTTP server 方式运行，不开放网络端口；如未来要启用 Chroma server，必须先做安全审查和依赖升级。
- 【2026-06-13】决定 API key 只使用系统环境变量 `DEEPSEEK_API_KEY`；不再推荐 `.bat` 明文写 key。
- 【2026-06-13】确认当前学习记录是模拟数据；如果以后接入真实学生数据，隐私提示和数据管理策略必须先补齐。
- 【2026-06-13】已初始化 git 并推送到私有仓库 `dosheda/k12`；初始化前已补 `.gitignore`，避免运行时数据和密钥误提交。

---

## 给下一个对话的备注
- 开始任务前先读 `AGENTS.md`、`PROGRESS.md`、`AUDIT_REPORT.md`。
- 目前没有代码层 P1 已修复；优先从局域网访问鉴权、硬编码路径、数据覆盖保护开始。
- 不要把 Chroma 改成 HTTP server；当前只允许本地 `PersistentClient`。
- 不要把 API key 写入 `.bat`、`.env` 或文档真实示例。
- 当前仓库远端是 `https://github.com/dosheda/k12.git`，默认分支 `main`，初始 release 为 `v0.1.0`。
