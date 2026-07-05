"""
学习行为记录模块 —— SQLite 持久化存储
======================================
记录每次用户的提问、真正讲解/复习/仅提及/候选的诗（每首诗完整标签）、时间戳。
跨会话累积 —— 数据存在本地 learning_records.db 文件里，
关掉浏览器下次打开还在。

为什么选 SQLite 而不是 JSON？
  - SQLite 查询方便：统计总数、按标签聚合、排序都一句 SQL
  - 不用装任何东西，Python 自带 sqlite3 模块
  - 并发安全：多个请求同时写不会把文件写坏
  - 轻量：一个文件就是整个数据库

核心表结构：
  learning_records
    ├── id           INTEGER PRIMARY KEY AUTOINCREMENT
    ├── question     TEXT    — 用户的问题
    ├── poem_data    TEXT    — 旧版兼容列，曾表示被记录的诗
    ├── tags         TEXT    — （已弃用，保留列兼容旧记录，存空字符串）
    ├── record_type  TEXT    — explained/reviewed/mixed/mentioned/no_match
    ├── explained_poems TEXT — 真正展开讲解的新诗
    ├── reviewed_poems  TEXT — 已学过、这次又展开复习的诗
    ├── mentioned_poems TEXT — 只是点名/对比/建议，未展开的诗
    ├── candidate_poems TEXT — 本轮检索候选，存档但不计入学习统计
    └── created_at   TEXT    — ISO 8601 时间戳

  chat_messages
    ├── id           INTEGER PRIMARY KEY AUTOINCREMENT
    ├── session_id   TEXT    — 浏览器会话 ID，不是密钥
    ├── role         TEXT    — user/assistant
    ├── content      TEXT    — 聊天消息正文
    └── created_at   TEXT    — ISO 8601 时间戳

v2 改动：
  - poem_data 从简单标题列表改为 [{title, tags}, ...] 结构化存储
  - get_stats() 的标签统计从「按记录计次」改为「按诗计次」
    旧的按记录计次：每条记录里合并了 8 首诗的全部标签（100+ 个），
    导致公共标签几乎每条记录都有，计数全部相同（都等于总记录数）。
    新的按诗计次：每首诗独立计数，跨记录累加，
    标签出现频次真正反映它在所有讲解/复习过的诗里出现了多少次。

v3 改动：
  - 候选诗、真正讲解/复习诗、仅提及诗分开存储。
  - “已学习古诗数”和主题统计只看真正讲解/复习的诗，不再把候选诗算作接触。

v4 改动：
  - 新增 chat_messages 表，按浏览器会话保存完整问答正文。
  - 聊天正文只用于恢复最近对话，不参与“已学习古诗数”和主题统计。
"""

import json
import sqlite3
from datetime import datetime
from json import JSONDecodeError

from config import LEARNING_DB_PATH, MAX_USER_QUERY_CHARS

# 数据库文件路径（和 app.py 在同一目录）
DB_PATH = LEARNING_DB_PATH

JSON_COLUMNS = {
    "explained_poems": "TEXT NOT NULL DEFAULT '[]'",
    "reviewed_poems": "TEXT NOT NULL DEFAULT '[]'",
    "mentioned_poems": "TEXT NOT NULL DEFAULT '[]'",
    "candidate_poems": "TEXT NOT NULL DEFAULT '[]'",
    "record_type": "TEXT NOT NULL DEFAULT 'no_match'",
}

CHAT_ROLES = {"user", "assistant"}
MAX_CHAT_SESSION_ID_CHARS = 64
MAX_CHAT_CONTENT_CHARS = 12000
MAX_LEARNER_ID_CHARS = 64


def _normalize_learner_id(learner_id) -> str | None:
    """Normalize a learner id; None/invalid means 'no filter / legacy'."""
    if learner_id is None:
        return None
    learner_id = str(learner_id).strip()
    if not learner_id or len(learner_id) > MAX_LEARNER_ID_CHARS:
        return None
    return learner_id


def _learner_filter(learner_id: str | None) -> tuple[str, tuple]:
    """Return a (WHERE clause, params) pair; empty when no learner given."""
    if learner_id:
        return "WHERE learner_id = ?", (learner_id,)
    return "", ()


# ============================================================
# 内部工具：获取数据库连接
# ============================================================
def _get_conn():
    """
    获取 SQLite 连接。
    - 自动创建数据库文件（如果还不存在）
    - row_factory = sqlite3.Row：让查询结果可以用 ["字段名"] 取值
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _load_poem_data(raw_text: str) -> list:
    """Parse poem_data JSON defensively; bad records are ignored by callers."""
    try:
        data = json.loads(raw_text)
    except (TypeError, JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []

    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        tags = item.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split("、") if t.strip()]
        elif isinstance(tags, list):
            tags = [str(t).strip() for t in tags if str(t).strip()]
        else:
            tags = []
        cleaned.append({"title": title, "tags": tags})
    return cleaned


def _dump_poem_data(poem_data: list) -> str:
    return json.dumps(poem_data or [], ensure_ascii=False)


def _ensure_columns(conn):
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(learning_records)").fetchall()
    }
    for column, definition in JSON_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE learning_records ADD COLUMN {column} {definition}")
    # learner_id 可为空：NULL 表示尚未归属（旧记录），首个浏览器会一次性认领
    if "learner_id" not in existing:
        conn.execute("ALTER TABLE learning_records ADD COLUMN learner_id TEXT")


def _ensure_chat_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id_id
        ON chat_messages (session_id, id)
    """)


def _normalize_chat_session_id(session_id: str) -> str:
    session_id = str(session_id or "").strip()
    if not session_id or len(session_id) > MAX_CHAT_SESSION_ID_CHARS:
        raise ValueError("invalid chat session id")
    return session_id


def _normalize_chat_message(message: dict) -> tuple[str, str] | None:
    role = str(message.get("role", "")).strip()
    if role not in CHAT_ROLES:
        return None

    content = str(message.get("content", ""))
    if not content.strip():
        return None

    return role, content[:MAX_CHAT_CONTENT_CHARS]


def _row_poem_groups(row) -> dict:
    explained = _load_poem_data(row["explained_poems"]) if "explained_poems" in row.keys() else []
    reviewed = _load_poem_data(row["reviewed_poems"]) if "reviewed_poems" in row.keys() else []
    mentioned = _load_poem_data(row["mentioned_poems"]) if "mentioned_poems" in row.keys() else []
    candidates = _load_poem_data(row["candidate_poems"]) if "candidate_poems" in row.keys() else []

    legacy_poems = _load_poem_data(row["poem_data"])
    if not (explained or reviewed or mentioned) and legacy_poems:
        explained = legacy_poems

    return {
        "explained_poems": explained,
        "reviewed_poems": reviewed,
        "mentioned_poems": mentioned,
        "candidate_poems": candidates,
        "poem_data": explained + reviewed,
    }


def _record_type(groups: dict, stored_type: str = "") -> str:
    if groups["explained_poems"] and groups["reviewed_poems"]:
        return "mixed"
    if groups["explained_poems"]:
        return "explained"
    if groups["reviewed_poems"]:
        return "reviewed"
    if groups["mentioned_poems"]:
        return "mentioned"
    return stored_type or "no_match"


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
    _ensure_columns(conn)
    _ensure_chat_tables(conn)
    conn.commit()
    conn.close()


# ============================================================
# 聊天消息持久化
# ============================================================
def record_chat_messages(session_id: str, messages: list[dict]):
    """Append one or more chat messages for one browser session."""
    session_id = _normalize_chat_session_id(session_id)
    rows = []
    for message in messages or []:
        normalized = _normalize_chat_message(message)
        if normalized:
            role, content = normalized
            rows.append((session_id, role, content, datetime.now().isoformat()))

    if not rows:
        return

    init_db()
    conn = _get_conn()
    conn.executemany(
        """
        INSERT INTO chat_messages (session_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def get_chat_messages(session_id: str, limit: int = 10) -> list[dict]:
    """Return the latest chat messages for one browser session, oldest first."""
    session_id = _normalize_chat_session_id(session_id)
    limit = max(1, min(int(limit or 10), 100))

    init_db()
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT role, content
        FROM chat_messages
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    conn.close()

    return [
        {"role": row["role"], "content": row["content"]}
        for row in reversed(rows)
    ]


# ============================================================
# 记录一次学习行为
# ============================================================
def record_learning(question: str, poem_data: list, learner_id: str | None = None):
    """
    写入一条学习记录。

    参数：
      question:  用户的问题原文
      poem_data: 检索到的诗的结构化数据，每项包含 title 和 tags_list
                 格式：[{"title": "《静夜思》 李白", "tags": ["思乡", "月亮", "借景抒情"]}, ...]
                 其中 tags 是 list 而非字符串 —— 每首诗的标签独立保存，
                 这样统计时可以按诗计数，反映每个标签真正出现在多少首诗里。
      learner_id: 学习者标识，用于多用户隔离；None 表示不归属（旧口径）。
    """
    record_interaction(
        question=question,
        explained_poems=poem_data,
        reviewed_poems=[],
        mentioned_poems=[],
        candidate_poems=[],
        record_type="explained" if poem_data else "no_match",
        learner_id=learner_id,
    )


def record_interaction(
    question: str,
    explained_poems: list,
    reviewed_poems: list,
    mentioned_poems: list,
    candidate_poems: list,
    record_type: str,
    learner_id: str | None = None,
):
    """Write one long-term learning interaction record."""
    init_db()

    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO learning_records (
            question,
            poem_data,
            tags,
            created_at,
            record_type,
            explained_poems,
            reviewed_poems,
            mentioned_poems,
            candidate_poems,
            learner_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question[:MAX_USER_QUERY_CHARS],
            _dump_poem_data(explained_poems + reviewed_poems),  # 旧版兼容列
            "",  # tags 列已弃用，留空
            datetime.now().isoformat(),
            record_type,
            _dump_poem_data(explained_poems),
            _dump_poem_data(reviewed_poems),
            _dump_poem_data(mentioned_poems),
            _dump_poem_data(candidate_poems),
            _normalize_learner_id(learner_id),
        ),
    )
    conn.commit()
    conn.close()


def claim_legacy_records(learner_id: str | None) -> int:
    """Assign all未归属（learner_id IS NULL）的旧记录给指定学习者，只影响一次。

    首个建立 learner_id 的浏览器会认领全部历史记录；之后新学习者到来时
    已无 NULL 记录，此调用为无操作，天然实现「先到先得」。
    """
    learner_id = _normalize_learner_id(learner_id)
    if not learner_id:
        return 0

    init_db()
    conn = _get_conn()
    cursor = conn.execute(
        "UPDATE learning_records SET learner_id = ? WHERE learner_id IS NULL",
        (learner_id,),
    )
    conn.commit()
    claimed = cursor.rowcount
    conn.close()
    return claimed


# ============================================================
# 获取统计概览
# ============================================================
def get_stats(learner_id: str | None = None) -> dict:
    """
    从数据库里算出基础统计数据，供侧边栏显示。

    learner_id 给定时只统计该学习者的记录；None 表示全量（旧口径）。

    v3 口径：
      - 总提问次数：所有成功记录。
      - 已学习古诗数：真正讲解/复习过的诗，按诗名去重。
      - 最常练习主题：讲解/复习每发生一次就累计标签，反映近期练习焦点。
      - 已覆盖主题：每首已学习诗只计一次标签，反映覆盖面。
      - 仅提及诗、候选诗不计入已学习和主题覆盖。

    返回：
      {
        "total_questions": int,          # 一共问了多少次
        "total_poems": int,              # 兼容旧字段：已学习古诗数
        "learned_poem_count": int,
        "review_count": int,
        "mentioned_count": int,
        "no_match_count": int,
        "top_tags": [(tag, count), …],   # 兼容旧字段：最常练习主题
        "coverage_tags": [(tag, count), …],
        "all_poems": [str, …],           # 已学习诗名（排序去重）
      }
    """
    learner_id = _normalize_learner_id(learner_id)
    where, params = _learner_filter(learner_id)

    init_db()
    conn = _get_conn()

    # ---- 总提问次数 ----
    total_questions = conn.execute(
        f"SELECT COUNT(*) FROM learning_records {where}",
        params,
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT
            poem_data,
            record_type,
            explained_poems,
            reviewed_poems,
            mentioned_poems,
            candidate_poems
        FROM learning_records
        {where}
        """,
        params,
    ).fetchall()

    practice_tag_counts = {}
    learned_poem_tags = {}
    review_count = 0
    mentioned_count = 0
    no_match_count = 0

    for row in rows:
        groups = _row_poem_groups(row)
        learned_poems = groups["explained_poems"] + groups["reviewed_poems"]
        review_count += len(groups["reviewed_poems"])
        mentioned_count += len(groups["mentioned_poems"])

        if not learned_poems and not groups["mentioned_poems"]:
            no_match_count += 1

        for poem in learned_poems:
            title = poem.get("title", "")
            if title:
                learned_poem_tags.setdefault(title, poem.get("tags", []))

            tags = poem.get("tags", [])
            for tag in tags:
                tag = tag.strip()
                if tag:
                    practice_tag_counts[tag] = practice_tag_counts.get(tag, 0) + 1

    coverage_tag_counts = {}
    for tags in learned_poem_tags.values():
        for tag in tags:
            tag = tag.strip()
            if tag:
                coverage_tag_counts[tag] = coverage_tag_counts.get(tag, 0) + 1

    top_tags = sorted(practice_tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    coverage_tags = sorted(coverage_tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    all_poems = sorted(learned_poem_tags)

    conn.close()

    return {
        "total_questions": total_questions,
        "total_poems": len(all_poems),
        "learned_poem_count": len(all_poems),
        "review_count": review_count,
        "mentioned_count": mentioned_count,
        "no_match_count": no_match_count,
        "top_tags": top_tags,
        "practice_tags": top_tags,
        "coverage_tags": coverage_tags,
        "all_poems": all_poems,
    }


def get_learned_poem_titles(learner_id: str | None = None) -> set:
    """Return titles that have been truly explained or reviewed."""
    stats = get_stats(learner_id)
    return set(stats["all_poems"])


# ============================================================
# 获取全部学习记录（用于生成学情报告）
# ============================================================
def get_all_records(learner_id: str | None = None) -> list:
    """
    返回学习记录，按时间从早到晚排列。learner_id 给定时只返回该学习者的记录。
    每条记录是一个 dict：
      {
        "question": str,
        "poem_data": [...]         # 兼容旧字段：explained + reviewed
        "explained_poems": [...]
        "reviewed_poems": [...]
        "mentioned_poems": [...]
        "candidate_poems": [...]
        "record_type": str,
        "created_at": str,
      }
    """
    learner_id = _normalize_learner_id(learner_id)
    where, params = _learner_filter(learner_id)

    init_db()
    conn = _get_conn()
    rows = conn.execute(
        f"""
        SELECT
            question,
            poem_data,
            record_type,
            explained_poems,
            reviewed_poems,
            mentioned_poems,
            candidate_poems,
            created_at
        FROM learning_records
        {where}
        ORDER BY created_at
        """,
        params,
    ).fetchall()
    conn.close()

    records = []
    for row in rows:
        groups = _row_poem_groups(row)
        record_type = _record_type(groups, row["record_type"])
        records.append({
            "question": row["question"],
            "poem_data": groups["poem_data"],
            "explained_poems": groups["explained_poems"],
            "reviewed_poems": groups["reviewed_poems"],
            "mentioned_poems": groups["mentioned_poems"],
            "candidate_poems": groups["candidate_poems"],
            "record_type": record_type,
            "created_at": row["created_at"],
        })
    return records
