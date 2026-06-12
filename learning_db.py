"""
学习行为记录模块 —— SQLite 持久化存储
======================================
记录每次用户的提问、检索到的诗（每首诗完整标签）、时间戳。
跨会话累积 —— 数据存在本地 learning_records.db 文件里，
关掉浏览器下次打开还在。

为什么选 SQLite 而不是 JSON？
  - SQLite 查询方便：统计总数、按标签聚合、排序都一句 SQL
  - 不用装任何东西，Python 自带 sqlite3 模块
  - 并发安全：多个请求同时写不会把文件写坏
  - 轻量：一个文件就是整个数据库

表结构（只有一张表，够用）：
  learning_records
    ├── id           INTEGER PRIMARY KEY AUTOINCREMENT
    ├── question     TEXT    — 用户的问题
    ├── poem_data    TEXT    — JSON，每首诗的名字和标签列表
    │                         格式：[{"title": "《静夜思》 李白", "tags": ["思乡", "月亮", "借景抒情"]}, ...]
    ├── tags         TEXT    — （已弃用，保留列兼容旧记录，存空字符串）
    └── created_at   TEXT    — ISO 8601 时间戳

v2 改动：
  - poem_data 从简单标题列表改为 [{title, tags}, ...] 结构化存储
  - get_stats() 的标签统计从「按记录计次」改为「按诗计次」
    旧的按记录计次：每条记录里合并了 8 首诗的全部标签（100+ 个），
    导致公共标签几乎每条记录都有，计数全部相同（都等于总记录数）。
    新的按诗计次：每首诗独立计数，跨记录累加，
    标签出现频次真正反映它在所有接触过的诗里出现了多少次。
"""

import sqlite3
import json
import os
from datetime import datetime

# 数据库文件路径（和 app.py 在同一目录）
DB_PATH = r"D:\k12 helper\learning_records.db"


# ============================================================
# 内部工具：获取数据库连接
# ============================================================
def _get_conn():
    """
    获取 SQLite 连接。
    - 自动创建数据库文件（如果还不存在）
    - row_factory = sqlite3.Row：让查询结果可以用 ["字段名"] 取值
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# 初始化：建表（如果不存在）
# ============================================================
def init_db():
    """
    创建 learning_records 表（如果还不存在的话）。
    这个函数在每次操作前都会被调用，非常轻量。
    """
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS learning_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,          -- 用户的问题
            poem_data TEXT NOT NULL,          -- JSON，每首诗的名字和标签：[{"title": "...", "tags": ["...", ...]}, ...]
            tags TEXT NOT NULL,               -- 已弃用列，保留兼容旧记录，存空字符串
            created_at TEXT NOT NULL           -- ISO 8601 时间，如 2026-06-12T15:30:00
        )
    """)
    conn.commit()
    conn.close()


# ============================================================
# 记录一次学习行为
# ============================================================
def record_learning(question: str, poem_data: list):
    """
    写入一条学习记录。

    参数：
      question:  用户的问题原文
      poem_data: 检索到的诗的结构化数据，每项包含 title 和 tags_list
                 格式：[{"title": "《静夜思》 李白", "tags": ["思乡", "月亮", "借景抒情"]}, ...]
                 其中 tags 是 list 而非字符串 —— 每首诗的标签独立保存，
                 这样统计时可以按诗计数，反映每个标签真正出现在多少首诗里。
    """
    init_db()

    conn = _get_conn()
    conn.execute(
        "INSERT INTO learning_records (question, poem_data, tags, created_at) VALUES (?, ?, ?, ?)",
        (
            question,
            json.dumps(poem_data, ensure_ascii=False),  # 结构化诗数据 → JSON
            "",  # tags 列已弃用，留空
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


# ============================================================
# 获取统计概览
# ============================================================
def get_stats() -> dict:
    """
    从数据库里算出基础统计数据，供侧边栏显示。

    v2 改动：标签统计改成「按诗计次」。
      旧逻辑：每条记录里的标签合并成一个大字符串 → 标签出现在几条记录里就计几次
              → 每记录 100+ 标签，公共标签必出现于所有记录，计数全等于总记录数
      新逻辑：遍历每首诗的标签 → 每个标签每出现在一首诗里计 1 次
              → 不同标签因为覆盖度不同，计数就有高有低了

    返回：
      {
        "total_questions": int,          # 一共问了多少次
        "total_poems": int,              # 接触了多少首不同的诗（按诗名去重）
        "top_tags": [(tag, count), …],   # 出现最多的标签 Top 10（按诗计次）
        "all_poems": [str, …],           # 接触过的所有诗名（排序去重）
      }
    """
    init_db()
    conn = _get_conn()

    # ---- 总提问次数 ----
    total_questions = conn.execute(
        "SELECT COUNT(*) FROM learning_records"
    ).fetchone()[0]

    # ---- 标签按诗计次 + 诗名收集 ----
    rows = conn.execute("SELECT poem_data FROM learning_records").fetchall()
    tag_counts = {}    # {标签: 出现在多少首诗里}
    all_poems = set()  # 去重诗名集合

    for row in rows:
        poems = json.loads(row["poem_data"])  # [{title, tags: [...]}, ...]

        for poem in poems:
            title = poem.get("title", "")
            if title:
                all_poems.add(title)

            # 每个标签在这首诗里计 1 次
            tags = poem.get("tags", [])
            for tag in tags:
                tag = tag.strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # 按出现次数降序，取前 10
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    conn.close()

    return {
        "total_questions": total_questions,
        "total_poems": len(all_poems),
        "top_tags": top_tags,
        "all_poems": sorted(all_poems),
    }


# ============================================================
# 获取全部学习记录（用于生成学情报告）
# ============================================================
def get_all_records() -> list:
    """
    返回所有学习记录，按时间从早到晚排列。
    每条记录是一个 dict：
      {
        "question": str,
        "poem_data": [
            {"title": "《静夜思》 李白", "tags": ["思乡", "月亮", ...]},
            ...
        ],
        "created_at": str,
      }
    """
    init_db()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT question, poem_data, created_at FROM learning_records ORDER BY created_at"
    ).fetchall()
    conn.close()

    records = []
    for row in rows:
        poem_data = json.loads(row["poem_data"])
        # poem_data 是 [{title, tags: [...]}, ...]
        records.append({
            "question": row["question"],
            "poem_data": poem_data,
            "created_at": row["created_at"],
        })
    return records
