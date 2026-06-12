"""
K12 古诗词 RAG 讲解助手 —— RAG 闭环脚本
==========================================
流程：用户提问 → Chroma 检索相关古诗 8 首 →
     把诗 + 问题组进 prompt → 发给 DeepSeek →
     DeepSeek 基于检索结果给出讲解

这是之前 search_rag.py（检索）+ k12_helper.py（讲解）的合体。
"""

import os
import sys
from api_utils import classify_api_error, extract_chat_content
from config import CHROMA_DB_PATH, DEEPSEEK_API_KEY_ENV, MAX_USER_QUERY_CHARS, POEM_1_80_PATH

# ============================================================
# 修复 Windows 终端中文乱码
# ============================================================
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# ============================================================
# 检索端：和 search_rag.py 一模一样的加载方式
# ============================================================
import chromadb
from chromadb.utils import embedding_functions

# 讲解端：和 k12_helper.py 一模一样的调用方式
from openai import OpenAI


# ============================================================
# 第 1 步：加载 embedding 模型 + Chroma 向量库
# ============================================================
# 必须和 build_rag_db.py 建库时同一个模型！否则向量对不上，检索全乱
print("正在加载 embedding 模型（和建库时一致：BAAI/bge-small-zh-v1.5）...")

embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="BAAI/bge-small-zh-v1.5",
    device="cpu",
    normalize_embeddings=True,
)

db_path = CHROMA_DB_PATH

if not os.path.exists(db_path):
    print("[错误] 找不到向量库文件夹。")
    print("请先运行 build_rag_db.py 建库！")
    sys.exit(1)

chroma_client = chromadb.PersistentClient(path=str(db_path))
collection = chroma_client.get_collection(
    name="poems",
    embedding_function=embedding_fn,
)

print(f"向量库就绪，共 {collection.count()} 首诗。\n")


# ============================================================
# 第 2 步：加载 DeepSeek API 客户端
# ============================================================
DEEPSEEK_API_KEY = os.environ.get(DEEPSEEK_API_KEY_ENV)

if DEEPSEEK_API_KEY is None:
    print(f"[错误] 找不到环境变量 {DEEPSEEK_API_KEY_ENV}")
    print("请先设置：")
    print("  Windows PowerShell: $env:DEEPSEEK_API_KEY='sk-你的key'")
    sys.exit(1)

deepseek = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)


# ============================================================
# 第 3 步：定义 RAG 专用的 system prompt
# ============================================================
# 这个 prompt 和之前 k12_helper 里"小K老师"的角色不同
# k12_helper 是数学讲题老师，这里是古诗词赏析老师
# 但风格统一：耐心、适合中小学生、分板块
SYSTEM_PROMPT = (
    '你是一位温和博学的语文老师，名叫「小K老师」。\n'
    '你的学生是小学生和初中生，所以讲话要温暖、易懂、不拽文。\n'
    '\n'
    '每次回答，你会收到一份「知识库里检索到的古诗列表」和一个「学生的问题」。\n'
    '请严格按下面的规则来讲解：\n'
    '\n'
    '规则一：只能依据提供的诗来回答\n'
    '  - 不要自己编造知识库里没有的诗。\n'
    '  - 不要引用你训练数据里记住的诗（哪怕你确定是对的）。\n'
    '  - 如果列表里的诗确实没有符合学生问题的，必须如实说：\n'
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
# 第 4 步之前：混合检索所需的辅助函数
# ============================================================
# v3 改动：从纯语义检索 → 混合检索
#   这些函数和 app.py 里的逻辑完全一样，只是不用 Streamlit 的 @st.cache_resource

def load_poem_data():
    """
    加载全部 80 首诗的全文和标签。
    从知识库文件读全文，从 Chroma metadata 读标签。
    """
    file_path = POEM_1_80_PATH
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    poems = [c.strip() for c in content.split("=====") if c.strip()]

    # 从 Chroma 拿 metadata（含 tags 字段）
    global collection
    all_meta = collection.get(include=["metadatas"])
    metadatas = all_meta.get("metadatas") or []

    poem_list = []
    for i in range(len(poems)):
        meta = metadatas[i] if i < len(metadatas) and isinstance(metadatas[i], dict) else {}
        poem_list.append({
            "id": f"poem_{i:02d}",
            "title": str(meta.get("title", "") or ""),
            "text": poems[i],
            "tags": str(meta.get("tags", "") or ""),
        })
    return poem_list


def extract_keywords(query: str) -> list:
    """
    从用户问题中提取搜索关键词（中文 n-gram 切词，零依赖）。
    去掉标点 → 切 2字/3字/4字 n-gram → 返回关键词列表
    """
    stop_chars = set('，。！？、；：""''（）《》【】 \t\n,.!?;:()[]{}…—-—')
    clean = ''.join(c for c in query if c not in stop_chars)

    keywords = set()
    for i in range(len(clean) - 1):
        keywords.add(clean[i:i+2])
    for i in range(len(clean) - 2):
        keywords.add(clean[i:i+3])
    for i in range(len(clean) - 3):
        keywords.add(clean[i:i+4])

    return list(keywords)


def keyword_search(query: str, poem_data: list) -> list:
    """第二路检索：关键词/标签匹配。返回有命中的诗及其关键词得分。"""
    keywords = extract_keywords(query)
    results = []
    for poem in poem_data:
        search_text = poem["text"] + " " + poem["tags"]
        score = 0
        for kw in keywords:
            if kw in search_text:
                score += len(kw)
        if score > 0:
            results.append({
                "poem_id": poem["id"],
                "title": poem["title"],
                "content": poem["text"],
                "keyword_score": score,
            })
    results.sort(key=lambda x: x["keyword_score"], reverse=True)
    return results


def rag_search_hybrid(query: str) -> str:
    """
    混合检索：语义向量 + 关键词/标签匹配 → 合并去重 → 返回 top 8 文字块。
    与 app.py 的 rag_search() 逻辑完全相同。
    """
    global collection
    poem_data = load_poem_data()

    # ---- 第一路：语义向量检索 ----
    semantic_results = collection.query(
        query_texts=[query],
        n_results=15,
        include=["documents", "metadatas", "distances"],
    )

    # ---- 第二路：关键词/标签匹配 ----
    keyword_results = keyword_search(query, poem_data)

    # ---- 合并 & 去重 ----
    candidates = {}

    ids_list = (semantic_results.get("ids") or [[]])[0]
    docs_list = (semantic_results.get("documents") or [[]])[0]
    metas_list = (semantic_results.get("metadatas") or [[]])[0]
    distances = (semantic_results.get("distances") or [[]])[0]

    max_dist = max(distances) if distances else 1.0
    min_dist = min(distances) if distances else 0.0

    for i in range(len(ids_list)):
        pid = ids_list[i]
        meta = metas_list[i] if i < len(metas_list) and isinstance(metas_list[i], dict) else {}
        content = docs_list[i] if i < len(docs_list) else ""
        distance = distances[i] if i < len(distances) else max_dist
        raw_sem = 1.0 - (distance - min_dist) / (max_dist - min_dist + 0.001)
        candidates[pid] = {
            "title": meta.get("title", ""),
            "content": content,
            "score": raw_sem,
        }

    if keyword_results:
        max_kw = max(k["keyword_score"] for k in keyword_results)
        for kw in keyword_results:
            pid = kw["poem_id"]
            norm_kw = kw["keyword_score"] / (max_kw + 0.001)
            if pid in candidates:
                candidates[pid]["score"] += 2.0 * norm_kw
            else:
                candidates[pid] = {
                    "title": kw["title"],
                    "content": kw["content"],
                    "score": 2.0 * norm_kw,
                }

    sorted_candidates = sorted(
        candidates.items(),
        key=lambda x: x[1]["score"],
        reverse=True,
    )
    top_n = sorted_candidates[:8]
    if not top_n:
        return "（没有检索到候选诗。）"

    retrieved_texts = []
    for rank, (pid, info) in enumerate(top_n, 1):
        retrieved_texts.append(
            f"【候选诗 {rank}】{info['title']}\n{info['content']}"
        )

    return "\n\n---\n\n".join(retrieved_texts)


# ============================================================
# 第 4 步：欢迎界面 + 主循环
# ============================================================
print("=" * 60)
print("  [K12] 古诗词 RAG 讲解助手")
print("=" * 60)
print("你可以问任何古诗词相关的问题，比如：")
print("  - 和友情有关的诗有哪些？")
print("  - 李白写过哪些写月亮的诗？")
print("  - 有没有描写春天风景的诗？")
print("输入 quit 或按 Ctrl+C 退出。")
print()

while True:
    # ============================================================
    # 4a. 获取用户问题
    # ============================================================
    query = input("请输入你的问题> ").strip()

    if query.lower() == "quit":
        print("再见！")
        break

    if not query:
        continue
    if len(query) > MAX_USER_QUERY_CHARS:
        print(f"[错误] 问题太长，请控制在 {MAX_USER_QUERY_CHARS} 个字符以内。")
        continue

    # ============================================================
    # 4b. 混合检索：语义向量 + 关键词/标签匹配
    # ============================================================
    print(f"\n[检索] 正在混合检索（语义 + 关键词/标签）...")
    context_block = rag_search_hybrid(query)
    candidate_count = context_block.count("【候选诗")
    print(f"[检索] 找到 {candidate_count} 首候选诗，正在发给小K老师...\n")

    # ============================================================
    # 4c. 组 prompt：把检索结果 + 用户问题一起发给 DeepSeek
    # ============================================================
    user_message = (
        "下面是从知识库里检索到的一些古诗：\n\n"
        f"{context_block}\n\n"
        f"学生的问题是：{query}\n\n"
        f"请根据上面的诗来回答这个学生。"
        f"如果这些诗里没有真正符合学生问题的，请如实告知。"
    )

    # 调试用：想看实际发给 DeepSeek 的 prompt 长什么样，去掉下面这行的 # 即可
    # print(f"[调试] === 发给 DeepSeek 的 prompt ===\n{user_message}\n[调试] === 结束 ===\n")

    # ============================================================
    # 4d. 调用 DeepSeek
    # ============================================================
    print("[思考中] 小K老师正在准备讲解...\n")

    try:
        response = deepseek.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            stream=False,
        )

        answer = extract_chat_content(response)

        # ============================================================
        # 4e. 打印讲解结果
        # ============================================================
        print("=" * 60)
        print("  [讲解]")
        print("=" * 60)
        print(answer)
        print("=" * 60)
        print()

    # ============================================================
    # 报错处理（和 k12_helper.py 一样的逻辑）
    # ============================================================
    except KeyboardInterrupt:
        print("\n\n[警告] 用户中断操作，再见！")
        break

    except Exception as e:
        print(f"\n[错误] {classify_api_error(e)}")

        print()
