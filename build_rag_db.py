"""
K12 古诗词 RAG 知识库 —— 建库脚本
======================================
功能：读取整理好的古诗词文件
     → 按 ===== 切分成一首一块
     → 向量化 + 存入本地 Chroma 向量库

技术选型：用 Chroma 内置的 SentenceTransformerEmbeddingFunction，
        让 Chroma 自己管 embedding，避开版本兼容问题。
"""
import os
import sys

# 修复 Windows 终端中文乱码
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import chromadb
# Chroma 官方提供的 embedding function wrapper，内置兼容处理
from chromadb.utils import embedding_functions


# ============================================================
# 第 1 步：读取 + 切分
# ============================================================
file_path = r"D:\k12 helper\古诗词1-80_整理版.txt"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

print(f"已读取文件，共 {len(content)} 个字符")

raw_chunks = content.split("=====")

ids = []
docs = []
metadatas = []

for i, chunk in enumerate(raw_chunks):
    chunk = chunk.strip()
    if not chunk:
        continue
    first_line = chunk.split("\n")[0].strip()
    ids.append(f"poem_{i:02d}")
    docs.append(chunk)
    metadatas.append({"title": first_line, "index": i})

print(f"切分完成，共 {len(docs)} 首诗")
for m in metadatas[:3]:
    print(f"  - {m['title']}")


# ============================================================
# 第 2 步：创建 embedding 函数 + Chroma 客户端
# ============================================================
# embedding function: Chroma 自己封装好的 SentenceTransformer wrapper
# 选了 BAAI/bge-small-zh-v1.5：中文好、免费、本地跑、约 100MB
print("\n正在加载中文 embedding 模型...")
print("（首次运行会下载约 100MB 模型文件，之后秒启动）")

embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="BAAI/bge-small-zh-v1.5",
    device="cpu",
    normalize_embeddings=True,
)

db_path = r"D:\k12 helper\chroma_db"

# 清旧库
if os.path.exists(db_path):
    import shutil
    shutil.rmtree(db_path)

client = chromadb.PersistentClient(path=db_path)

# 创建 collection，绑定 embedding function
# Chroma 会在 add/query 时自动调 embedding_fn 来向量化
collection = client.create_collection(
    name="poems",
    embedding_function=embedding_fn,
    metadata={"description": "小学古诗词1-80首"}
)


# ============================================================
# 第 3 步：存入数据
# ============================================================
# 注意：不传 embeddings 参数！Chroma 会用 embedding_fn 自己算
print("\n正在向量化并存入 Chroma...")
collection.add(
    ids=ids,
    documents=docs,
    metadatas=metadatas,
)

print(f"\n建库完成！")
print(f"  数据位置：{db_path}")
print(f"  库中记录：{collection.count()} 首")
