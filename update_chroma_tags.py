"""
更新 Chroma metadata —— 把标签写入每首诗的 metadata.tags 字段
==============================================================
为什么要做这一步？
  现有的 Chroma metadata 里只有 title 和 index，没有主题标签。
  混合检索的第二路（关键词/标签匹配）需要快速拿到每首诗的标签，
  所以把标签写进 metadata，检索时可以直接从 results["metadatas"] 里取。

做法：读"诗名-标签对照表.txt"，按诗名匹配 Chroma 里的记录，
      用 collection.update() 给每条记录加上 tags 字段。
      不重建库，不动 embedding 模型，只追加 metadata。
"""
import os
import re
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import chromadb
from chromadb.utils import embedding_functions
from config import CHROMA_DB_PATH, POEM_TAGS_PATH

# ---- 读标签文件，解析出 {诗名: tags_string} ----
tag_file = POEM_TAGS_PATH
poem_tags = {}

with open(tag_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

current_title = None
for line in lines:
    # 匹配标题行：如 "【长歌行（节录）】 汉乐府 汉"
    m = re.match(r'【(.+?)】\s+(.+?)\s+(.+)', line)
    if m:
        current_title = m.group(1)  # 取诗名
        continue

    # 收集四个维度的标签
    if current_title and line.startswith("  题材类型："):
        tags_str = line.replace("  题材类型：", "").strip()
        poem_tags[current_title] = tags_str
    elif current_title and line.startswith("  表达情感："):
        if current_title in poem_tags:
            poem_tags[current_title] += "、" + line.replace("  表达情感：", "").strip()
    elif current_title and line.startswith("  表现手法："):
        if current_title in poem_tags:
            poem_tags[current_title] += "、" + line.replace("  表现手法：", "").strip()
    elif current_title and line.startswith("  关键意象："):
        if current_title in poem_tags:
            poem_tags[current_title] += "、" + line.replace("  关键意象：", "").strip()

print(f"从标签文件解析出 {len(poem_tags)} 首诗的标签")

# ---- 连接 Chroma ----
db_path = CHROMA_DB_PATH
ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="BAAI/bge-small-zh-v1.5",
    device="cpu",
    normalize_embeddings=True,
)
client = chromadb.PersistentClient(path=str(db_path))
collection = client.get_collection(name="poems", embedding_function=ef)

# ---- 获取全部记录 ----
all_data = collection.get(include=["metadatas"])
print(f"Chroma 库中有 {len(all_data['ids'])} 条记录")

# ---- 按诗名匹配，更新 metadata ----
updated = 0
for i, poem_id in enumerate(all_data["ids"]):
    meta = all_data["metadatas"][i]
    chroma_title = meta.get("title", "")

    # 从 Chroma 的 title（格式："《诗名》 作者 朝代"）中提取诗名
    m = re.match(r'《(.+?)》', chroma_title)
    if m:
        poem_name = m.group(1)
    else:
        poem_name = chroma_title

    # 在标签字典里找匹配
    tag_str = poem_tags.get(poem_name, "")
    if not tag_str:
        # 尝试模糊匹配（诗名可能有细微差异）
        for key in poem_tags:
            if key in poem_name or poem_name in key:
                tag_str = poem_tags[key]
                break

    if tag_str:
        # 更新 metadata，加上 tags 字段
        collection.update(
            ids=[poem_id],
            metadatas=[{**meta, "tags": tag_str}]
        )
        updated += 1
    else:
        print(f"  ⚠ 未找到标签：{poem_name}")

print(f"\n更新完成！{updated}/{len(all_data['ids'])} 首诗的标签已写入 Chroma metadata")

# ---- 验证：随机抽查几条 ----
print("\n===== 验证抽查 =====")
if all_data["ids"]:
    sample_indexes = [0, min(19, len(all_data["ids"]) - 1), min(76, len(all_data["ids"]) - 1)]
    sample_ids = [all_data["ids"][i] for i in sorted(set(sample_indexes))]
    sample_data = collection.get(ids=sample_ids, include=["metadatas"])
    for i, poem_id in enumerate(sample_data["ids"]):
        meta = sample_data["metadatas"][i] or {}
        print(f"\n{meta.get('title', poem_id)}")
        print(f"  tags: {meta.get('tags', '（无）')[:120]}...")
