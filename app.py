"""
K12 古诗词 RAG 讲解助手 —— Streamlit 网页版（支持多轮对话）
============================================================
把 rag_chat.py 的检索 + DeepSeek 讲解逻辑搬到网页上。
v2 改动：从单轮问答 → 聊天界面多轮对话。

核心流程每一轮：
  用户输入 → RAG 检索（仍用当前问题）→ 组 prompt（包含对话历史）
  → 调 DeepSeek → 把回答加入对话历史 → 渲染全部聊天记录
"""

import os
import sys
import json      # 用于把 Python 字符串安全嵌入 JavaScript
import re        # 用于清理 markdown 格式符号
import hmac
import time
import streamlit as st

# 学习行为记录模块（新增：智能学情分析）
import learning_db
from api_utils import classify_api_error, extract_chat_content
from auth_utils import (
    AUTH_COOKIE_MAX_AGE_SECONDS,
    AUTH_COOKIE_NAME,
    create_remember_token,
    validate_remember_token,
)
from learning_record_utils import build_interaction_payload, parse_learning_marker
from config import (
    ACCESS_CODE,
    ACCESS_CODE_ENV,
    API_COOLDOWN_SECONDS,
    CHROMA_DB_PATH,
    DEEPSEEK_API_KEY_ENV,
    MAX_REPORT_FIELD_CHARS,
    MAX_REPORT_PROMPT_CHARS,
    MAX_REPORT_RECORDS,
    MAX_USER_QUERY_CHARS,
    POEM_1_80_PATH,
)

# ============================================================
# 修复 Windows 终端中文乱码（Streamlit 自己的日志输出也会用到）
# ============================================================
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# ============================================================
# 依赖导入：和 rag_chat.py 一模一样
# ============================================================
import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI


# ============================================================
# 第 1 步：页面基础配置
# ============================================================
st.set_page_config(
    page_title="K12 古诗词讲解助手",
    page_icon="📖",
    layout="wide",
)

# ============================================================
# 第 2 步：会话状态初始化
# ============================================================
# st.session_state 是 Streamlit 用来跨页面刷新保存数据的字典。
# 普通变量每次刷新都会重置，但 session_state 里的东西会一直保留，
# 直到用户关掉浏览器标签页或我们手动清除。
#
# 这里初始化两个东西：
#   messages: 对话历史，列表里的每个元素是 {"role": "...", "content": "..."}
#   对话轮数从 messages 长度自动计算（len(messages) // 2）

if "messages" not in st.session_state:
    st.session_state.messages = []  # 对话历史，初始为空


def remembered_access_ok() -> bool:
    """Return True when this browser has a valid remembered login cookie."""
    try:
        token = st.context.cookies.get(AUTH_COOKIE_NAME)
    except Exception:
        token = None
    return validate_remember_token(token, ACCESS_CODE)


def write_auth_cookie_script(token: str | None, reload_page: bool = False):
    """Write or clear the browser auth cookie from a tiny Streamlit component."""
    if token:
        cookie_value = (
            f"{AUTH_COOKIE_NAME}={token}; "
            f"Max-Age={AUTH_COOKIE_MAX_AGE_SECONDS}; Path=/; SameSite=Lax"
        )
    else:
        cookie_value = f"{AUTH_COOKIE_NAME}=; Max-Age=0; Path=/; SameSite=Lax"

    reload_js = "window.parent.location.reload();" if reload_page else ""
    html = f"""
<script>
(function() {{
  const cookieValue = {json.dumps(cookie_value)};
  try {{ document.cookie = cookieValue; }} catch (err) {{}}
  try {{ window.parent.document.cookie = cookieValue; }} catch (err) {{}}
  {reload_js}
}})();
</script>
"""
    st.components.v1.html(html, height=0)


def require_access_code():
    """Require a local access code before exposing LAN-visible functions."""
    if not ACCESS_CODE:
        st.error(f"未设置访问口令环境变量 {ACCESS_CODE_ENV}")
        st.info(
            "为了安全地给局域网用户访问，请先设置访问口令后再启动：\n\n"
            f'`$env:{ACCESS_CODE_ENV} = "你自己的访问口令"`\n\n'
            "`python -m streamlit run app.py`"
        )
        st.stop()

    if st.session_state.get("_access_ok"):
        return

    if remembered_access_ok():
        st.session_state._access_ok = True
        return

    st.title("K12 古诗词讲解助手")
    st.caption("请输入访问口令后继续。验证通过后，此设备可记住 7 天。")
    entered = st.text_input("访问口令", type="password")
    remember_device = st.checkbox("在此设备记住 7 天", value=True)
    if st.button("进入", use_container_width=True):
        if hmac.compare_digest(entered, ACCESS_CODE):
            st.session_state._access_ok = True
            if remember_device:
                token = create_remember_token(ACCESS_CODE)
                st.success("验证通过，此设备 7 天内刷新免输入。")
                write_auth_cookie_script(token, reload_page=True)
                st.stop()
            st.rerun()
        else:
            st.error("访问口令不正确。")
    st.stop()


require_access_code()

# 当前轮数直接从 messages 长度算，不用手动维护（避免时序 bug）
current_round = len(st.session_state.messages) // 2

# 最大保留轮数（一对问答算一轮）
MAX_ROUNDS = 5
# 换算成消息条数（一轮 = 用户 + 助手 = 2 条）
MAX_MESSAGES = MAX_ROUNDS * 2


# ============================================================
# 第 3 步：用 Streamlit 缓存加载慢资源
# ============================================================
# 和之前一样：embedding 模型和 Chroma 向量库各缓存一次，后续秒出。

@st.cache_resource
def load_embedding_function():
    """加载中文 embedding 模型，只跑一次"""
    print("正在加载中文 embedding 模型（BAAI/bge-small-zh-v1.5）...")
    print("（首次运行会下载约 100MB 模型文件，之后秒启动）")

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="BAAI/bge-small-zh-v1.5",
        device="cpu",
        normalize_embeddings=True,
    )
    return ef


@st.cache_resource
def load_chroma_collection():
    """加载 Chroma 向量库，只跑一次"""
    db_path = CHROMA_DB_PATH

    if not os.path.exists(db_path):
        st.error("找不到向量库文件夹。")
        st.info("请先运行 build_rag_db.py 建库！")
        st.stop()

    embedding_fn = load_embedding_function()
    chroma_client = chromadb.PersistentClient(path=str(db_path))
    collection = chroma_client.get_collection(
        name="poems",
        embedding_function=embedding_fn,
    )
    return collection


# ============================================================
# 第 4 步：获取 DeepSeek 客户端
# ============================================================

def get_deepseek_client():
    """从环境变量读取 API Key，创建 DeepSeek 客户端"""
    api_key = os.environ.get(DEEPSEEK_API_KEY_ENV)

    if api_key is None:
        st.error(f"找不到环境变量 {DEEPSEEK_API_KEY_ENV}")
        st.info(
            "请在 PowerShell 中先运行：\n\n"
            f'`$env:{DEEPSEEK_API_KEY_ENV} = "sk-你的key"`\n\n'
            "然后再用 `streamlit run app.py` 启动。"
        )
        st.stop()

    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )


# ============================================================
# 第 5 步：System Prompt（原封不动，多轮对话也能用）
# ============================================================
SYSTEM_PROMPT = (
    '你是一位温和博学的语文老师，名叫「小K老师」。\n'
    '你的学生是小学生和初中生，所以讲话要温暖、易懂、不拽文。\n'
    '\n'
    '这是一场连续的多轮对话。学生可能会用"它""刚才那首""再讲一首"来指代上一轮聊过的诗，'
    '你要结合前面的对话来理解学生指的是什么。\n'
    '\n'
    '每次回答，你会收到一份「知识库里检索到的古诗列表」和一个「学生的问题」。\n'
    '请严格按下面的规则来讲解：\n'
    '\n'
    '规则一：只能依据提供的诗来回答\n'
    '  - 不要自己编造知识库里没有的诗。\n'
    '  - 不要引用你训练数据里记住的诗（哪怕你确定是对的）。\n'
    '  - 如果检索列表里的诗确实没有符合学生问题的，但前面聊过的诗里有符合的，'
    '你可以基于前面聊过的诗来回答。\n'
    '  - 如果确实没有任何诗符合，必须如实说：\n'
    '    "知识库里目前的诗都不太符合这个问题"，不要硬凑一首来讲。\n'
    '\n'
    '规则二：讲解结构\n'
    '  如果找到了符合的诗，按下面的板块来讲（板块之间空行隔开）：\n'
    '  【原文】\n'
    '   先把诗的标题和作者写在第一行，然后必须换行，从第二行开始贴诗句原文。\n'
    '   标题作者和诗句绝不能挤在同一行！格式示例：\n'
    '    《静夜思》 李白\n'
    '    床前明月光，疑是地上霜。\n'
    '    举头望明月，低头思故乡。\n'
    '  【这首诗讲了什么】\n'
    '   用一两句话说清楚诗的内容，可以用"想象一下……"开头，让学生有画面感。\n'
    '  【作者想表达什么】\n'
    '   分析诗人的情感：是开心、思乡、孤独、还是对朋友的想念？为什么诗人会有这种心情？\n'
    '  【写得好的地方】\n'
    '   重要：我提供的每首诗里都有一段【赏析】，里面已经写好了这首诗的妙处。\n'
    '   你必须优先用赏析里的内容！把赏析提到的妙处，用自己的话（适合孩子听）转述出来。\n'
    '   比如赏析里说""挂"字化动为静，维纱维肖地写出遥望中的瀑布"，\n'
    '   你可以转述成"老师说这个"挂"字特别妙——你远远看过去，瀑布就像一条大白布，\n'
    '   一动不动地挂在山前面，是不是很有画面感？"\n'
    '   只有赏析里确实没提到某处妙处时，你才可以补充自己的理解。\n'
    '  【小知识】（可选，有的话就加）\n'
    '   和这首诗或诗人有关的有趣小故事、写作背景。\n'
    '\n'
    '规则三：语气\n'
    '  - 用"我们可以一起看看""你有没有想过"这种邀请式的语气\n'
    '  - 不要用"你应该记住""必考"这种命令或应试口吻\n'
    '  - 适当用感叹号和拟声词增加亲切感，但不要太夸张\n'
)


# ============================================================
# 第 6 步：核心函数 —— 混合检索（语义 + 关键词/标签）+ 调 DeepSeek
# ============================================================
# v3 改动：从纯语义检索 → 混合检索（Hybrid Retrieval）
#   第一路：语义向量检索（bge 模型 + Chroma，和原来一样，不动）
#   第二路：关键词/标签匹配（用户问题里的 n-gram 关键词 × 诗的全文+标签）
#   合并去重，标签/关键词命中的加权（×2.0），让它排到更前面
#   最终取前 8 首交给 DeepSeek

@st.cache_resource
def load_poem_data():
    """
    加载全部 80 首诗的全文和标签，缓存一次，后续秒出。
    用于关键词/标签匹配——需要扫描全部诗的文本和标签来找关键词命中。
    数据来源：
      - 全文：从古诗词1-80_整理版.txt 读取
      - 标签：从 Chroma metadata 读取（上一步 update_chroma_tags.py 写入的）
    """
    file_path = POEM_1_80_PATH
    if not file_path.exists():
        st.error("找不到古诗词数据文件。")
        st.stop()
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    poems = [c.strip() for c in content.split("=====") if c.strip()]

    # 从 Chroma 拿已有 metadata（含 tags 字段）
    collection = load_chroma_collection()
    try:
        all_meta = collection.get(include=["metadatas"])
    except Exception:
        st.error("读取向量库 metadata 失败，请检查 chroma_db 是否完整。")
        st.stop()
    metadatas = all_meta.get("metadatas") or []

    poem_list = []
    for i in range(len(poems)):
        meta = metadatas[i] if i < len(metadatas) and isinstance(metadatas[i], dict) else {}
        poem_list.append({
            "id": f"poem_{i:02d}",      # 和建库时的 ID 一致
            "title": str(meta.get("title", "") or ""),
            "text": poems[i],
            "tags": str(meta.get("tags", "") or ""),
        })
    return poem_list


def extract_keywords(query: str) -> list:
    """
    从用户问题中提取搜索关键词。

    方法：中文 n-gram 切词。
      不需要额外安装 jieba 等分词库，零依赖。
      把用户问题去掉标点后，切成 2字词、3字词、4字词，
      用这些 n-gram 去诗的全文和标签里做子串匹配。

    例子："有没有描写春天的诗"
      → 2字：["有没", "没有", "有描", "描写", "写春", "春天", "天的", "的诗"]
      → 3字：["有没有", "没有描", "有描写", "描写春", "写春天", "春天的", "天的诗"]
      → 4字：["有没有描", "没有描写", "有描写春", "描写春天", "写春天的", "天的诗"]
      其中"描写"、"春天"、"描写春天"等会在诗的标签（"写景、春天……"）里命中
    """
    # 去掉标点符号和空白
    stop_chars = set('，。！？、；：""''（）《》【】 \t\n,.!?;:()[]{}…—-—')
    clean = ''.join(c for c in query if c not in stop_chars)

    keywords = set()
    # 2字词（最短有意义单元）
    for i in range(len(clean) - 1):
        keywords.add(clean[i:i+2])
    # 3字词
    for i in range(len(clean) - 2):
        keywords.add(clean[i:i+3])
    # 4字词
    for i in range(len(clean) - 3):
        keywords.add(clean[i:i+4])

    return list(keywords)


def keyword_search(query: str, poem_data: list) -> list:
    """
    第二路检索：关键词/标签匹配。

    原理：
      把用户问题拆成 n-gram 关键词，
      每个关键词去每首诗的全文 + 标签里查找（子串匹配），
      命中一个关键词就加分，按关键词长度加权（长词命中比短词更有价值）。
      比如"春天"（2字）命中加 2 分，"描写春天"（4字）命中加 4 分。

    返回：所有有命中的诗，按关键词得分降序排列。
          每项：{poem_id, title, content, keyword_score}
    """
    keywords = extract_keywords(query)

    results = []
    for poem in poem_data:
        # 全文 + 标签拼在一起搜
        search_text = poem["text"] + " " + poem["tags"]

        score = 0
        for kw in keywords:
            if kw in search_text:
                score += len(kw)  # 长词命中权重更高

        if score > 0:
            results.append({
                "poem_id": poem["id"],
                "title": poem["title"],
                "content": poem["text"],
                "keyword_score": score,
                "tags": poem["tags"],  # 带上标签，供学情记录使用
            })

    results.sort(key=lambda x: x["keyword_score"], reverse=True)
    return results


def rag_search(query: str) -> str:
    """
    混合检索（Hybrid Retrieval）：语义向量 + 关键词/标签匹配
    ============================================================
    流程：
      1. 第一路：语义向量检索（扩到 15 个候选，给合并留空间）
      2. 第二路：关键词/标签匹配（扫描全部 80 首诗）
      3. 合并去重：
         - 语义得分 = 1.0 - 归一化距离（距离越小越相似，得分越高）
         - 关键词得分 = 归一化匹配分 × 2.0（标签命中的加权更高）
         - 同一首诗两路都命中 → 得分叠加
         - 只在关键词路命中的诗也收进来（不让纯标签匹配的诗漏掉）
      4. 按最终得分降序，取前 8 首
      5. 格式化为和原来一样的文字块
    """
    collection = load_chroma_collection()
    poem_data = load_poem_data()

    # ============================================================
    # 第一路：语义向量检索（和原来一样，n_results 扩到 15）
    # ============================================================
    try:
        semantic_results = collection.query(
            query_texts=[query],
            n_results=15,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        st.session_state._last_search_structured = []
        st.error("检索向量库失败，请检查知识库是否完整。")
        st.stop()

    # ============================================================
    # 第二路：关键词/标签匹配
    # ============================================================
    keyword_results = keyword_search(query, poem_data)

    # ============================================================
    # 合并 & 去重
    # ============================================================
    # candidates: {poem_id: {title, content, score}}
    candidates = {}

    # ---- 2a. 语义结果转得分 ----
    ids_list = (semantic_results.get("ids") or [[]])[0]
    docs_list = (semantic_results.get("documents") or [[]])[0]
    metas_list = (semantic_results.get("metadatas") or [[]])[0]
    distances = (semantic_results.get("distances") or [[]])[0]

    # 归一化用
    max_dist = max(distances) if distances else 1.0
    min_dist = min(distances) if distances else 0.0

    for i in range(len(ids_list)):
        pid = ids_list[i]
        meta = metas_list[i] if i < len(metas_list) and isinstance(metas_list[i], dict) else {}
        content = docs_list[i] if i < len(docs_list) else ""
        distance = distances[i] if i < len(distances) else max_dist
        # 距离 → 相似度（0 = 最像，1 = 最不像 → 映射到 1~0）
        raw_sem = 1.0 - (distance - min_dist) / (max_dist - min_dist + 0.001)
        candidates[pid] = {
            "title": meta.get("title", ""),
            "content": content,
            "score": raw_sem,  # 基础分：语义相似度
            "tags": str(meta.get("tags", "") or ""),  # 标签，供学情记录使用
        }

    # ---- 2b. 关键词结果加权叠加 ----
    if keyword_results:
        max_kw = max(k["keyword_score"] for k in keyword_results)
        for kw in keyword_results:
            pid = kw["poem_id"]
            norm_kw = kw["keyword_score"] / (max_kw + 0.001)  # 归一化到 0~1

            if pid in candidates:
                # 这首诗语义也命中了 → 关键词分作为加分项叠上去
                # × 2.0：标签/关键词命中的诗加权，让它排到更前面
                candidates[pid]["score"] += 2.0 * norm_kw
            else:
                # 只在关键词匹配里出现（语义没搜到）→ 也收进来
                candidates[pid] = {
                    "title": kw["title"],
                    "content": kw["content"],
                    "score": 2.0 * norm_kw,
                    "tags": kw.get("tags", ""),  # 标签，供学情记录使用
                }

    # ---- 2c. 排序，取前 8 ----
    sorted_candidates = sorted(
        candidates.items(),
        key=lambda x: x[1]["score"],
        reverse=True,
    )
    top_n = sorted_candidates[:8]
    if not top_n:
        st.session_state._last_search_structured = []
        return "（没有检索到候选诗。）"

    # ---- 2d. 把结构化检索结果存入 session_state，供学情记录模块使用 ----
    st.session_state._last_search_structured = [
        {"title": info["title"], "tags": info.get("tags", "")}
        for _pid, info in top_n
    ]

    # ============================================================
    # 格式化为和原来一样的文字块
    # ============================================================
    retrieved_texts = []
    for rank, (pid, info) in enumerate(top_n, 1):
        retrieved_texts.append(
            f"【候选诗 {rank}】{info['title']}\n{info['content']}"
        )

    return "\n\n---\n\n".join(retrieved_texts)


def build_messages_for_api(user_query: str) -> list[dict]:
    """
    构建发给 DeepSeek 的完整 messages 数组。

    结构：
      [system prompt]
      + [前几轮的对话历史（已裁剪到最近 MAX_MESSAGES 条）]
      + [当前用户消息（含 RAG 检索结果 + 当前问题）]

    注意：对话历史直接作为 assistant/user 消息传进去，
          让模型能看到"上一轮讲了什么诗"。
    """
    # ---- 1. system prompt ----
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ---- 2. 对话历史（已裁剪过的）----
    # st.session_state.messages 在每次提问后会被裁剪到 MAX_MESSAGES 条
    messages.extend(st.session_state.messages)

    # ---- 3. 当前用户消息：RAG 检索 + 问题 ----
    context_block = rag_search(user_query)

    current_user_message = (
        "下面是从知识库里检索到的一些古诗：\n\n"
        f"{context_block}\n\n"
        f"学生的问题是：{user_query}\n\n"
        f"请根据上面的诗来回答这个学生。"
        f"如果这些诗里没有真正符合学生问题的，但前面我们聊过的诗里有，你可以基于前面聊过的来回答。"
        f"如果确实没有任何诗符合，请如实告知。\n\n"
        f"【重要】请在回答最后单独加一行隐藏学习标记，格式必须是："
        f'<!-- learning: {{"explained":["诗名1"],"mentioned":["诗名2"],"no_match":false}} --> 。'
        f"explained 只放你真正展开解释、赏析或带学生学习的诗；"
        f"mentioned 只放你顺嘴点名、对比、建议以后学但没有展开讲的诗；"
        f"如果没有任何合适诗，也没有真正讲解诗，把 no_match 写成 true。"
        f"诗名只写标题中的诗名，不要带作者和朝代。这个标记不会显示给学生看。"
    )
    messages.append({"role": "user", "content": current_user_message})

    return messages


def chat_with_deepseek(messages: list[dict]) -> str:
    """调用 DeepSeek，返回回答文本"""
    deepseek = get_deepseek_client()
    response = deepseek.chat.completions.create(
        model="deepseek-v4-pro",
        messages=messages,
        stream=False,
    )
    return extract_chat_content(response)


# ============================================================
# 第 7 步：工具函数 —— 裁剪历史
# ============================================================


def trim_history():
    """确保对话历史不超过 MAX_MESSAGES 条，超过就从头部丢弃"""
    if len(st.session_state.messages) > MAX_MESSAGES:
        # 只保留最后 MAX_MESSAGES 条
        st.session_state.messages = st.session_state.messages[-MAX_MESSAGES:]


def validate_user_query(raw_query: str) -> str | None:
    """Validate chat input before recording or calling the API."""
    query = raw_query.strip()
    if not query:
        st.warning("请输入问题后再发送。")
        return None
    if len(query) > MAX_USER_QUERY_CHARS:
        st.error(f"问题太长了，请控制在 {MAX_USER_QUERY_CHARS} 个字符以内。")
        return None

    now = time.time()
    last_call = st.session_state.get("_last_api_call_ts", 0.0)
    remaining = API_COOLDOWN_SECONDS - (now - last_call)
    if remaining > 0:
        st.warning(f"请求太频繁，请 {remaining:.1f} 秒后再试。")
        return None

    st.session_state._last_api_call_ts = now
    return query


# ============================================================
# 学情分析报告生成器（新增模块）
# ============================================================
# 当用户点击侧边栏的「生成学情报告」按钮时触发。
# 流程：
#   1. 从 SQLite 读取所有学习记录
#   2. 计算统计概览（提问次数、接触诗数、高频标签）
#   3. 如果记录太少（< 3 次），直接返回提示，不调 API（省钱）
#   4. 如果记录足够，整理成结构化摘要发给 DeepSeek
#   5. DeepSeek 返回温暖、鼓励性的分析报告

# 学情报告专用的 system prompt（和小K老师的教学 prompt 不同角色）
REPORT_SYSTEM_PROMPT = (
    "你是一位专业、温和的教育分析师，专注于中小学生的语文学情分析。\n"
    "你的报告读者是家长，所以语气要温暖、鼓励，让家长感受到孩子的成长。\n"
    "\n"
    "报告要求：\n"
    "1. 开头先简单总结：孩子一共提问了多少次，真正学习了多少首诗，复习了几次。\n"
    "2. 分析孩子目前对哪些主题感兴趣（根据真正讲解/复习过的高频标签得出）。\n"
    "3. 评估学习覆盖面是否均衡：\n"
    "   - 知识库涵盖了写景、送别、思乡、边塞、咏物、哲理、爱国、田园等多种类型\n"
    "   - 指出孩子目前关注较多的类型和关注较少的类型\n"
    "4. 给出拓展建议：还有哪些类型的诗可以多了解，为什么这些类型也值得读。\n"
    "5. 最后给出鼓励性的学习建议，让孩子保持对古诗词的兴趣。\n"
    "\n"
    "格式要求：\n"
    "  - 用「📊 学习概览」「🔍 兴趣分析」「⚖️ 均衡性评估」「💡 拓展建议」「🌟 学习寄语」作为板块标题\n"
    "  - 板块之间空一行\n"
    "  - 不要用 markdown 表格，用自然段落\n"
    "  - 整篇报告 300-500 字，不要太长\n"
    "\n"
    "诚实原则：\n"
    "  - 如果数据显示明显偏向某一类型，如实指出\n"
    "  - 建议要具体，不要泛泛而谈\n"
    "  - 语气温暖但不虚假——不要说「孩子非常优秀」之类没有数据支撑的话\n"
)


def generate_learning_report() -> str:
    """
    生成学情分析报告。
    从 SQLite 读取全部学习记录 → 算统计 → 调 DeepSeek 生成报告。

    返回：报告文本（str）
    """
    # ---- 1. 获取数据 ----
    try:
        records = learning_db.get_all_records()
        stats = learning_db.get_stats()
    except Exception:
        return (
            "## 📊 学情分析报告\n\n"
            "### ⚠️ 学习记录暂时无法读取\n\n"
            "请稍后再试；如果问题持续，请检查本地学习记录数据库。"
        )

    # ---- 2. 数据不足时，不调 API，直接返回提示 ----
    if stats["total_questions"] < 3:
        return (
            "## 📊 学情分析报告\n\n"
            "### 🕰️ 学习记录还比较少\n\n"
            f"目前孩子一共提出了 **{stats['total_questions']}** 个问题，"
            f"真正学习了 **{stats['learned_poem_count']}** 首诗。\n\n"
            "数据量还不够生成详细的分析报告。**再多用一会儿，小K老师就能给出更全面的学情分析！**\n\n"
            "建议：试着问一些不同类型的问题，比如：\n"
            "- 写景的诗有哪些？\n"
            "- 和友情有关的诗有哪些？\n"
            "- 李白写过哪些诗？\n\n"
            "等积累了 **5 次以上** 的提问记录，报告就会更丰富啦～"
        )

    # ---- 3. 整理数据摘要，准备发给 DeepSeek ----
    # 构建一份清晰的文字摘要，让 DeepSeek 基于它来分析

    # 3a. 标签频次（前 15）
    practice_tag_summary = "、".join(
        f"{tag}（{count}次）" for tag, count in stats["practice_tags"][:15]
    )
    coverage_tag_summary = "、".join(
        f"{tag}（{count}首）" for tag, count in stats["coverage_tags"][:15]
    )

    # 3b. 提问和诗名列表
    records_for_prompt = records[-MAX_REPORT_RECORDS:]
    def _titles(poems):
        return "、".join(p["title"][:MAX_REPORT_FIELD_CHARS] for p in poems[:3]) or "无"

    question_list = "\n".join(
        f"  {i+1}. {r['question'][:MAX_REPORT_FIELD_CHARS]}"
        f"（新学：{_titles(r['explained_poems'])}；"
        f"复习：{_titles(r['reviewed_poems'])}；"
        f"仅提及：{_titles(r['mentioned_poems'])}；"
        f"类型：{r['record_type']}）"
        for i, r in enumerate(records_for_prompt)
    )

    # 3c. 真正学习过的所有诗
    poem_list = "、".join(stats["all_poems"])[:MAX_REPORT_PROMPT_CHARS // 3]

    # ---- 4. 组装 prompt ----
    user_message = (
        "请根据以下学习数据，生成一份学情分析报告：\n\n"
        f"【基本统计】\n"
        f"  - 总提问次数：{stats['total_questions']}\n"
        f"  - 真正学习过的不同诗：{stats['learned_poem_count']} 首\n"
        f"  - 复习次数：{stats['review_count']}\n"
        f"  - 仅提及次数：{stats['mentioned_count']}\n"
        f"  - 未命中/未讲解次数：{stats['no_match_count']}\n"
        f"  - 最常练习的主题标签：{practice_tag_summary}\n"
        f"  - 已覆盖的主题标签：{coverage_tag_summary}\n\n"
        f"【提问记录】\n"
        f"{question_list}\n\n"
        f"【真正学习过的诗】\n"
        f"{poem_list}\n\n"
        f"请基于以上数据生成报告。记住：语气温暖、适合家长阅读、"
        f"给出具体的拓展建议。如果数据明显偏向某个类型，如实指出。"
    )
    if len(user_message) > MAX_REPORT_PROMPT_CHARS:
        user_message = user_message[:MAX_REPORT_PROMPT_CHARS] + "\n\n（后续记录已因长度限制省略。）"

    # ---- 5. 调 DeepSeek ----
    deepseek = get_deepseek_client()

    try:
        response = deepseek.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            stream=False,
        )
        report = extract_chat_content(response)

        # 加上标题
        return f"## 📊 学情分析报告\n\n{report}"

    except Exception:
        # 如果 API 调用失败，至少返回一个基于本地数据的简单报告
        return (
            "## 📊 学情分析报告\n\n"
            "### ⚠️ AI 报告生成暂时失败\n\n"
            f"但这里有一些基础数据：\n\n"
            f"- 总提问次数：**{stats['total_questions']}**\n"
            f"- 真正学习过的诗：**{stats['learned_poem_count']}** 首\n"
            f"- 复习次数：**{stats['review_count']}**\n"
            f"- 最常练习主题：{practice_tag_summary if practice_tag_summary else '暂无'}\n\n"
            f"等 API 恢复后再试一次就好～"
        )


@st.dialog("学情分析报告", width="large")
def render_learning_report_dialog():
    """Show the generated learning report without moving the chat viewport."""
    st.markdown(st.session_state.report_text)
    if st.button("关闭报告", use_container_width=True):
        st.session_state.show_report = False
        st.rerun()


# ============================================================
# 朗读功能（浏览器内置 TTS，免费，无需 API Key）
# ============================================================
# 原理：
#   st.components.v1.html 可以在页面里嵌入一小段 HTML+JavaScript。
#   这段 JS 调浏览器自带的 speechSynthesis API ——
#   所有现代浏览器都有，不用装插件、不用付费。
#
#   每次调用 render_tts_button 会在页面里生成一个微型 iframe，
#   里面只有"朗读"和"停止"两个按钮。
#   点击"朗读"→ JS 把文字交给 speechSynthesis 念出来。
#   语言设为 zh-CN，确保中文发音正确。

# 按钮计数器：每次调用 render_tts_button 自增，嵌入 HTML 作为唯一标记
# 防止 Streamlit 把多个 iframe 当成同一个 widget
_tts_counter = 0


def render_tts_button(text: str):
    """在消息下方渲染"🔊 朗读"和"⏹ 停止"按钮。"""
    global _tts_counter
    _tts_counter += 1
    unique_id = _tts_counter

    # ---- 清理 markdown 格式符号 ----
    # TTS 引擎不认识 **、#、` 这些符号，直接念出来很怪
    clean = text
    clean = re.sub(r'\*{1,3}', '', clean)       # 去掉 ** 和 *
    clean = re.sub(r'#{1,6}\s?', '', clean)     # 去掉 # ## ###
    clean = re.sub(r'`{1,3}', '', clean)        # 去掉代码标记
    clean = re.sub(r'~~', '', clean)            # 去掉删除线
    clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)  # 链接只留文字

    # ---- 安全嵌入 JavaScript ----
    # json.dumps 会把 Python 字符串安全转义成合法的 JS 字符串字面量
    # ensure_ascii=False 保留中文字符原样，可读性更好
    safe_text = json.dumps(clean, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<!-- tts-btn-{unique_id} -->
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  body {{
    margin: 0;
    padding: 4px 0;
    font-family: sans-serif;
  }}
  button {{
    font-size: 14px;
    padding: 6px 14px;
    cursor: pointer;
    border: none;
    border-radius: 5px;
    transition: opacity 0.2s;
  }}
  button:hover {{ opacity: 0.85; }}
  .speak-btn {{ background: #4CAF50; color: white; }}
  .stop-btn  {{ background: #f44336; color: white; margin-left: 8px; }}
</style>
</head>
<body>
<button class="speak-btn" onclick="speak()">🔊 朗读</button>
<button class="stop-btn"  onclick="stopSpeaking()">⏹ 停止</button>
<script>
const text = {safe_text};

let currentUtterance = null;

function speak() {{
    // 先停掉任何正在朗读的内容，避免叠加
    window.speechSynthesis.cancel();

    currentUtterance = new SpeechSynthesisUtterance(text);
    currentUtterance.lang = 'zh-CN';   // 中文发音，否则浏览器可能用英文腔念中文
    currentUtterance.rate = 0.9;       // 稍慢一点，适合小朋友听

    window.speechSynthesis.speak(currentUtterance);
}}

function stopSpeaking() {{
    window.speechSynthesis.cancel();
}}

// 页面关闭 / 切换时自动停止朗读
window.addEventListener('beforeunload', function() {{
    window.speechSynthesis.cancel();
}});
</script>
</body>
</html>'''

    # 只显示按钮行，高度固定 45px，不占多余空间
    st.components.v1.html(html, height=45)


# ============================================================
# 第 8 步：画网页界面
# ============================================================

# ---------- 侧边栏：工具区 ----------
with st.sidebar:
    st.markdown("### 🛠️ 工具")
    st.caption(f"当前对话：{current_round} 轮")
    st.caption(f"最多保留：{MAX_ROUNDS} 轮")

    # 清空对话按钮
    if st.button("🆕 开始新对话", use_container_width=True):
        st.session_state.messages = []
        st.rerun()  # 立刻刷新页面，让改动生效

    if st.button("🔒 退出登录", use_container_width=True):
        st.session_state._access_ok = False
        write_auth_cookie_script(None, reload_page=True)
        st.stop()

    st.divider()

    # ============================================================
    # 学情概览区：显示基础学习统计（新增）
    # ============================================================
    st.markdown("### 📈 学习概览")
    try:
        stats = learning_db.get_stats()
        if stats["total_questions"] > 0:
            st.metric("总提问次数", stats["total_questions"])
            st.metric("已学习古诗数", stats["learned_poem_count"])
            if stats["review_count"] > 0:
                st.caption(f"复习次数：{stats['review_count']}")
            if stats["mentioned_count"] > 0 or stats["no_match_count"] > 0:
                st.caption(
                    f"仅提及：{stats['mentioned_count']} 次 · 未命中/未讲解：{stats['no_match_count']} 次"
                )
            if stats["practice_tags"]:
                st.caption("最常练习主题：")
                tag_text = " · ".join(
                    f"{tag}({count})" for tag, count in stats["practice_tags"][:8]
                )
                st.info(tag_text)
            if stats["coverage_tags"]:
                st.caption("已覆盖主题：")
                coverage_text = " · ".join(
                    f"{tag}({count})" for tag, count in stats["coverage_tags"][:8]
                )
                st.info(coverage_text)
        else:
            st.caption("暂无学习记录")
            st.caption("开始提问后会自动记录～")
    except Exception:
        st.caption("（学习记录数据库待初始化）")

    # ---- 生成学情报告按钮 ----
    st.divider()
    if st.button("📊 生成学情报告", use_container_width=True):
        # 设置 pending 标记，在下次页面刷新时生成报告
        # （不能在 button 回调里直接做耗时操作，会阻塞 UI）
        st.session_state._pending_report = True
        st.rerun()

    st.divider()
    st.markdown("### 💡 试试这些")
    st.markdown(
        "- 和友情有关的诗有哪些？\n"
        "- 望庐山瀑布好在哪里？\n"
        "- 有没有描写春天的诗？\n"
        "- 再讲一首\n"
        "- 它的作者是谁？"
    )
    st.divider()
    st.caption("📖 K12 古诗词讲解助手 v2")
    st.caption("多轮对话 · RAG 检索 + DeepSeek")

# ---------- 主区域标题 ----------
st.title("📖K12 古诗词讲解助手")
st.markdown("我是**小K老师**，你的语文学习伙伴～ 在下面输入你的问题吧！")

# ============================================================
# 处理待生成的学情报告（新增）
# ============================================================
# 点击侧边栏按钮会设置 _pending_report = True，
# 然后在这次页面刷新中真正生成报告（避免阻塞按钮响应）
if st.session_state.get("_pending_report"):
    with st.spinner("小K老师正在分析学习数据，生成报告……📊"):
        report_text = generate_learning_report()
        st.session_state.report_text = report_text
        st.session_state.show_report = True
        st.session_state._pending_report = False
    st.rerun()

# ---- 弹窗显示已生成的报告 ----
if st.session_state.get("show_report") and st.session_state.get("report_text"):
    render_learning_report_dialog()

# ---------- 渲染对话历史 ----------
# st.chat_message 会画一个聊天气泡，role="user" 靠右，role="assistant" 靠左
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # 给每条老师的讲解加朗读按钮
        if msg["role"] == "assistant":
            render_tts_button(msg["content"])

# ---------- 聊天输入框 ----------
# st.chat_input 是 Streamlit 专门给聊天界面用的输入框，
# 固定在页面底部，回车发送，自带发送按钮。
# 用户输入后返回字符串，没输入时返回 None。
if raw_user_query := st.chat_input("在这里输入你的问题……"):
    user_query = validate_user_query(raw_user_query)
    if user_query is None:
        st.stop()

    # ---- 8a. 把用户消息加入历史并立刻显示 ----
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    # ---- 8b. 构建 messages、调 DeepSeek ----
    with st.chat_message("assistant"):
        with st.spinner("小K老师正在翻书思考中……📚"):
            try:
                # 构建完整 messages（含历史 + RAG 检索结果）
                api_messages = build_messages_for_api(user_query)

                # 调 API
                answer = chat_with_deepseek(api_messages)

                # ---- 解析模型标注：真正讲解 / 仅提及 / 未命中 ----
                clean_answer, learning_marker = parse_learning_marker(answer)

                # 显示回答（剥离标记后的干净版本）
                st.markdown(clean_answer)

                # 朗读按钮（用干净文本，不念标记行）
                render_tts_button(clean_answer)

                # 把回答加入对话历史（存干净版本）
                st.session_state.messages.append({"role": "assistant", "content": clean_answer})

                # 裁剪历史，防止过长
                trim_history()

                # ---- 记录学习行为：候选、讲解、复习、提及分开存 ----
                last_search = st.session_state.get("_last_search_structured", [])
                learned_titles = learning_db.get_learned_poem_titles()
                interaction = build_interaction_payload(
                    search_results=last_search,
                    poem_catalog=load_poem_data(),
                    learned_titles=learned_titles,
                    learning_marker=learning_marker,
                )
                learning_db.record_interaction(
                    question=user_query,
                    explained_poems=interaction["explained_poems"],
                    reviewed_poems=interaction["reviewed_poems"],
                    mentioned_poems=interaction["mentioned_poems"],
                    candidate_poems=interaction["candidate_poems"],
                    record_type=interaction["record_type"],
                )

                if interaction["explained_poems"] or interaction["reviewed_poems"]:
                    st.toast("学习概览已更新", icon="📈")
                elif interaction["mentioned_poems"]:
                    st.toast("已记录本次提问（仅提及不计入已学习）", icon="📝")
                else:
                    st.toast("已记录本次提问（未命中具体诗）", icon="📝")

                # 立刻重跑一次脚本，让侧边栏的轮数、对话历史全部刷新为最新
                st.rerun()

            # ---- 报错处理（和原来一样）----
            except Exception as e:
                st.error(classify_api_error(e))
