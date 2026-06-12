# K12 古诗词 RAG 讲解助手

一个面向中小学生的本地古诗词智能讲解助手：学生用自然语言提问，系统从本地古诗词知识库检索相关作品，再调用 DeepSeek 生成适合学生理解的内容讲解、情感分析和赏析。

## 项目特点

- 本地优先：古诗词知识库、Chroma 向量库和学习记录都保存在本机，适合个人或同一局域网内试用。
- RAG 闭环完整：从古诗文本整理、向量建库、标签生成、混合检索，到大模型讲解都有可运行脚本。
- 检索更稳：语义向量检索结合关键词与主题标签，缓解“问法不同就搜不到”的问题。
- 面向学生：Prompt 约束为温和、清楚、分板块的讲解方式，避免只给成人化赏析。
- 支持多轮对话：能理解“再讲一首”“它的作者是谁”等接续上文的追问。
- 带学情记录：按真正讲解、复习、仅提及、候选诗分开统计，并可生成学情报告。
- 局域网可用：Streamlit 网页入口支持本地访问口令，浏览器可选择记住 7 天。

## 项目概览

这个项目的目标是验证一套可迁移到教育辅导场景的 RAG 能力。古诗词内容天然按“一首一块”组织，且讲解高度依赖背景、注释和赏析，适合作为 RAG 技术路线的试验田。

当前知识库以 80 首小学必备古诗词为核心。用户提问后，系统会先检索本地 Chroma 知识库，再把检索结果、最近对话历史和讲解规则一起发给 DeepSeek。模型只基于检索到的内容回答；如果知识库里确实没有合适的诗，会明确说明找不到，而不是硬编。

主要入口：

- `app.py`：Streamlit 网页聊天入口。
- `build_rag_db.py`：读取古诗文本并构建本地 Chroma 向量库。
- `tag_poems.py`：调用 DeepSeek 为每首诗生成主题标签。
- `update_chroma_tags.py`：把标签写入 Chroma metadata，供混合检索使用。
- `rag_chat.py`：命令行 RAG 对话脚本。
- `search_rag.py`：命令行检索测试脚本。
- `k12_helper.py`：命令行错题讲解与 OCR 识别脚本。
- `learning_db.py`：本地 SQLite 学习记录与统计。

## 技术栈

| 模块 | 使用技术 | 作用 |
|---|---|---|
| Web 界面 | Python + Streamlit | 提供本地/局域网聊天界面 |
| 大模型 | DeepSeek API，OpenAI SDK 兼容接口 | 生成古诗词讲解与学情报告 |
| 模型名称 | `deepseek-v4-pro` | 当前代码使用的 DeepSeek 模型 |
| 向量数据库 | ChromaDB `PersistentClient` | 本地落盘保存古诗向量 |
| Embedding | `BAAI/bge-small-zh-v1.5` | 中文语义向量化，本地运行 |
| 检索策略 | 语义检索 + 关键词/标签匹配 | 提升主题、手法、意象类问题召回 |
| 学习记录 | SQLite | 保存本地学习行为与统计 |
| OCR | Tesseract + Pillow | 命令行图片题识别 |
| 依赖管理 | `requirements.txt` | 固定当前直接依赖版本 |

安全边界：本项目当前只使用本地 Chroma `PersistentClient`，直接读写 `chroma_db/`，不以 Chroma HTTP server 方式运行，也不开放 Chroma 网络端口。

## 如何运行

以下命令以 Windows PowerShell 为例。首次运行建议使用虚拟环境。

### 1. 克隆并进入项目

```powershell
git clone https://github.com/dosheda/k12.git
cd k12
```

如果你已经在本地项目目录中，可以直接进入该目录。

### 2. 创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

首次加载 `BAAI/bge-small-zh-v1.5` 时会下载约 100MB 的模型文件，之后会使用本地缓存。

### 3. 配置环境变量

项目需要两个关键环境变量：

- `DEEPSEEK_API_KEY`：DeepSeek API key，用于调用大模型。
- `K12_HELPER_ACCESS_CODE`：网页访问口令，用于本地或局域网访问保护。

只在当前 PowerShell 窗口临时生效：

```powershell
$env:DEEPSEEK_API_KEY = Read-Host "请输入 DeepSeek API Key"
$env:K12_HELPER_ACCESS_CODE = Read-Host "请输入网页访问口令"
```

写入当前 Windows 用户环境变量，后续新开的 PowerShell 也能读取：

```powershell
[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", (Read-Host "请输入 DeepSeek API Key"), "User")
[Environment]::SetEnvironmentVariable("K12_HELPER_ACCESS_CODE", (Read-Host "请输入网页访问口令"), "User")
```

写入用户环境变量后，请重新打开一个 PowerShell 窗口再运行项目。

不要把 API key 或访问口令写进代码、`.env`、`.bat`、截图或可提交文件。

### 4. 准备古诗数据

默认数据文件位于项目根目录：

- `古诗词1-80_整理版.txt`：建库用的 80 首古诗词整理文本。
- `诗名-标签对照表.txt`：主题标签对照表。

如果你的数据放在其他位置，可以通过环境变量覆盖默认路径：

```powershell
$env:K12_HELPER_DATA_DIR = "D:\your\data\dir"
```

也可以分别设置 `K12_POEM_1_80_PATH`、`K12_POEM_TAGS_PATH`、`K12_CHROMA_DB_PATH`、`K12_LEARNING_DB_PATH`。

### 5. 构建本地向量库

```powershell
python build_rag_db.py
```

脚本会读取 `古诗词1-80_整理版.txt`，按 `=====` 切分成一首一块，使用中文 embedding 模型向量化，并写入本地 `chroma_db/`。

如果已有旧的 `chroma_db/`，脚本会先备份为带时间戳的目录，再重建新库。

### 6. 生成并写入标签

首次完整重建时，按下面顺序运行：

```powershell
python tag_poems.py
python update_chroma_tags.py
```

`tag_poems.py` 会调用 DeepSeek，为 80 首诗生成题材、情感、手法和意象标签，因此会消耗 API 调用。若本地已经有可用的 `诗名-标签对照表.txt`，可以跳过 `tag_poems.py`，只运行：

```powershell
python update_chroma_tags.py
```

这样会把现有标签写入 Chroma metadata，供网页检索使用。

### 7. 启动网页应用

本机访问：

```powershell
python -m streamlit run app.py
```

浏览器打开：

```text
http://localhost:8501
```

首次进入需要输入 `K12_HELPER_ACCESS_CODE`。勾选“在此设备记住 7 天”后，刷新页面不需要反复输入口令；点击侧边栏“退出登录”会清除记住状态。

同一局域网访问：

```powershell
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

局域网用户打开：

```text
http://你的局域网IP:8501
```

如果无法访问，请检查 Windows 防火墙是否允许 Python 或 8501 端口入站连接。

## 使用说明

启动后可以直接在聊天框提问，例如：

- 和友情有关的诗有哪些？
- 望庐山瀑布好在哪里？
- 有没有描写春天的诗？
- 再讲一首同类型的。
- 它的作者是谁？

侧边栏会显示学习概览，包括总提问次数、已学习古诗数、复习次数、仅提及次数和高频主题。只有模型真正展开讲解或复习过的诗，才会计入“已学习”；候选诗和仅顺嘴提到的诗不会算作已学习。

聊天正文会按浏览器会话保存到本地 SQLite。刷新页面或重新打开浏览器时，会自动恢复最近 5 轮对话；点击“开始新对话”会新建一个聊天会话，不会删除原有学习统计。

点击“生成学情报告”后，报告会在弹窗中显示，不需要回到页面顶部查看。关闭弹窗后，侧边栏会保留“查看上次报告”入口；需要使用最新学习记录重新分析时，再点“重新生成学情报告”。

## 命令行工具

检索测试：

```powershell
python search_rag.py
```

命令行 RAG 对话：

```powershell
python rag_chat.py
```

错题讲解与 OCR：

```powershell
python k12_helper.py
```

OCR 功能需要本机安装 Tesseract。默认路径是 `C:\Program Files\Tesseract-OCR\tesseract.exe`，也可以用 `TESSERACT_CMD` 环境变量覆盖。

## 系统流程

### 建库流程

```text
古诗词整理文本
  -> 按 ===== 切分
  -> BAAI/bge-small-zh-v1.5 向量化
  -> 写入本地 Chroma collection: poems
  -> 生成主题标签
  -> 标签写入 Chroma metadata
```

### 问答流程

```text
学生提问
  -> 输入长度与频率校验
  -> 语义向量检索
  -> 关键词/标签匹配
  -> 合并排序候选诗
  -> 拼接 RAG 上下文、最近对话历史和讲解规则
  -> 调用 DeepSeek
  -> 展示回答
  -> 解析隐藏学习标记
  -> 写入本地 SQLite 学习记录
```

核心原则是：检索负责“找资料”，模型负责“基于资料讲解”。如果检索结果不支持回答，模型应该诚实说明知识库里暂时没有合适内容。

## 问题与解决亮点

### 1. 依赖版本冲突

早期搭建 RAG 时遇到 Python 包版本互相不兼容，导致向量化模型报错。当前项目把关键依赖固定在 `requirements.txt` 中，并使用 Chroma 内置的 `SentenceTransformerEmbeddingFunction`，减少手动拼接 embedding 流程带来的兼容问题。

### 2. 纯向量检索漏召回

纯语义检索适合主题匹配，但对注释里的具体地点、文学手法或抽象标签容易漏召回。例如“江西的诗”“借物言志的诗”这类问题，如果相关信息只藏在注释或赏析里，语义向量可能不会把正确诗排到前面。

当前解决方案是混合检索：

- 保留 Chroma 语义向量检索。
- 新增零依赖中文 n-gram 关键词匹配。
- 为每首诗补充题材、情感、手法、意象标签。
- 合并两路结果并对标签命中加权。

这样用户无论问“托物言志”“借物喻人”还是“咏志”，都更容易召回《石灰吟》《竹石》《墨梅》这类相关作品。

### 3. 检索失手时不硬凑答案

RAG 的上限很大程度由检索决定。检索没召回正确材料时，模型不能靠训练记忆硬编。当前 Prompt 明确要求：如果检索到的诗里没有真正符合问题的内容，必须如实说明“知识库里目前的诗都不太符合这个问题”。

### 4. Prompt 与知识库赏析对齐

知识库里每首诗有整理好的赏析。早期 Prompt 只让模型“讲讲写得好的地方”，模型可能绕开知识库赏析自由发挥。当前规则要求模型在赏析环节优先转述知识库中的赏析内容，只有资料未覆盖时再补充。

### 5. 多轮对话与学习统计

Streamlit 的 `session_state` 保存最近几轮对话，使用户能自然追问“再讲一首”“它的作者是谁”。同时，模型回答末尾会生成隐藏学习标记，系统据此区分真正学习、复习、仅提及和未命中，避免把候选诗误计入已学习。

## 数据与安全说明

- API key 只从系统环境变量 `DEEPSEEK_API_KEY` 读取。
- 网页访问口令只从系统环境变量 `K12_HELPER_ACCESS_CODE` 读取。
- `chroma_db/`、`learning_records.db`、`.env`、本地启动脚本和凭证文件不应提交到 Git。
- 当前 Chroma 只允许本地 `PersistentClient` 方式，不运行 HTTP server。
- 学习记录保存在本地 SQLite；如果后续接入真实学生或家长数据，需要补充隐私提示、数据保留与清空策略。
- 聊天正文也会保存在本地 SQLite，用于恢复最近对话；局域网多人使用前，应明确告知使用者本机保存聊天记录。
- DeepSeek API 调用涉及成本，当前代码对输入长度和调用频率做了基础限制。

## 项目结构

```text
.
├─ app.py                         # Streamlit 网页入口
├─ config.py                      # 路径、环境变量和限制配置
├─ build_rag_db.py                # 构建 Chroma 向量库
├─ tag_poems.py                   # 调用 DeepSeek 生成诗歌标签
├─ update_chroma_tags.py          # 标签写入 Chroma metadata
├─ rag_chat.py                    # 命令行 RAG 对话
├─ search_rag.py                  # 命令行检索测试
├─ k12_helper.py                  # 命令行错题/OCR 助手
├─ learning_db.py                 # SQLite 学习记录
├─ learning_record_utils.py       # 学习标记解析与记录构建
├─ auth_utils.py                  # 访问口令记住设备 token
├─ safe_io.py                     # 备份与原子写入工具
├─ 古诗词1-80_整理版.txt           # 古诗词知识库文本
├─ 诗名-标签对照表.txt             # 诗歌主题标签
└─ requirements.txt               # Python 依赖
```

运行后会在本地生成：

- `chroma_db/`：Chroma 向量库。
- `learning_records.db`：SQLite 学习记录和聊天记录。
- `*.bak_*`：脚本自动生成的数据备份。

这些运行时文件默认不提交到 Git。

## 后续规划

1. 检索继续升级：把当前 n-gram 关键词匹配升级为 BM25 或更成熟的混合检索方案。
2. 强化 RAG 忠实度：增加来源标注、引用片段和更严格的回答校验。
3. 扩展教育场景：把同一套 RAG 能力迁移到错题讲解、知识点辅导等方向。
4. 扩充知识库：从 80 首小学古诗词扩展到更多学段和更多学科内容。
5. 完善部署能力：云服务器环境重建、HTTPS、域名、进程守护和更完整的访问控制。
6. 探索成熟 RAG 框架：在理解原理后，评估 LightRAG、RAG-Anything 等方案对知识图谱和多模态内容的支持。

## 开发方式说明

这是一个 AI 辅助编程项目。项目需求、技术路线、问题定位、取舍判断和验收标准由人来把控，代码实现与调试过程中使用 AI 编程工具协助完成。这个项目重点展示的是：如何把一个教育场景拆成可运行的 RAG 工程链路，并在真实问题中持续修正检索、Prompt、安全和交互体验。
