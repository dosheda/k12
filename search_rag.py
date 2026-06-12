"""
K12 古诗词 RAG 知识库 —— 检索测试脚本
======================================
功能：加载本地 Chroma 向量库
     → 等待用户输入问题
     → 从库里检索最相关的诗（Chroma 自动管 embedding）
     → 打印诗名和内容
"""
import sys
import os

# 修复 Windows 终端中文乱码
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import chromadb
from chromadb.utils import embedding_functions


# ============================================================
# 第 1 步：加载 embedding 函数 + Chroma 客户端
# ============================================================
# 必须和建库时用同一个模型！
print("正在加载 embedding 模型...")
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="BAAI/bge-small-zh-v1.5",
    device="cpu",
    normalize_embeddings=True,
)

db_path = r"D:\k12 helper\chroma_db"

if not os.path.exists(db_path):
    print(f"[错误] 找不到向量库文件夹：{db_path}")
    print("请先运行 build_rag_db.py 建库！")
    sys.exit(1)

client = chromadb.PersistentClient(path=db_path)
collection = client.get_collection(
    name="poems",
    embedding_function=embedding_fn,
)

print(f"模型就绪。已加载向量库，共 {collection.count()} 首诗。")


# ============================================================
# 第 2 步：交互检索循环
# ============================================================
print("=" * 60)
print("  古诗词检索测试")
print("  输入你的问题，程序从 20 首诗里找出最相关的。")
print("  输入 quit 退出。")
print("=" * 60)
print()

while True:
    query = input("请输入问题> ").strip()

    if query.lower() == "quit":
        print("再见！")
        break

    if not query:
        continue

    # ----- 检索 -----
    # query_texts: 直接传文字！Chroma 用 embedding_fn 自动转成向量
    # n_results:  返回前几首
    # include:    要哪些字段
    results = collection.query(
        query_texts=[query],
        n_results=3,
        include=["documents", "metadatas", "distances"]
    )

    # ----- 打印结果 -----
    print()
    print("=" * 60)
    print(f'  检索结果："{query}"')
    print("=" * 60)

    ids_list = results["ids"][0]
    docs_list = results["documents"][0]
    metas_list = results["metadatas"][0]
    dists_list = results["distances"][0]

    for i in range(len(ids_list)):
        title = metas_list[i]["title"]
        distance = dists_list[i]
        content = docs_list[i]

        print(f"\n{'─' * 40}")
        print(f"  第 {i+1} 首 | {title}")
        print(f"  距离: {distance:.4f}（越小越相关）")
        print(f"{'─' * 40}")
        # 太长就截断
        if len(content) > 300:
            print(content[:300] + "\n  ...（省略）")
        else:
            print(content)

    print(f"\n{'=' * 60}")
    print(f"  共 {len(ids_list)} 首")
    print(f"{'=' * 60}\n")
