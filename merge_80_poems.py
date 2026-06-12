"""
合并全部 80 首古诗 —— v4：基于"标题+作者"结构识别诗歌边界
===========================================================
关键启发式：
  - 诗歌标题行后紧跟空行 + 作者/朝代行（2-8字，无冒号句号）
  - 注释项后紧跟的是解释文字（含"："或很长）
"""

import re
import os
from config import (
    POEM_1_80_PATH,
    POEM_21_40_PATH,
    SOURCE_POEMS_1_20_PATH,
    SOURCE_POEMS_41_60_PATH,
    SOURCE_POEMS_61_80_PATH,
)
from safe_io import atomic_write_text

# ============================================================
# 工具函数
# ============================================================

def is_author_line(line: str) -> bool:
    """判断一行是否为作者/朝代行"""
    line = line.strip()
    if not line:
        return False
    if len(line) > 15:
        return False  # 作者行不会太长
    if re.search(r'[：。，！？、]', line):
        return False  # 作者行不含这些标点
    if line.startswith('【'):
        return False
    # 作者行通常很短，不含解释性文字
    return True


def extract_poems_from_file(filepath: str) -> list[str]:
    """用"数字.诗名 + 空行 + 作者"结构识别诗歌"""
    if not os.path.exists(filepath):
        print(f"  [警告] 文件不存在：{filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    # 找所有候选诗歌标题行：行首「数字 + .或．+ 诗名」
    candidates = list(re.finditer(r'^(\d+)[.．]\s*(.+)$', text, re.MULTILINE))

    poem_starts = []
    for m in candidates:
        title = m.group(2).strip()

        # 标题行本身如果含"："则跳过（注释项特征）
        if '：' in title[:10]:
            continue

        # 标题太长不像诗名
        if len(title) > 40:
            continue

        # 获取标题行之后的文本
        after = text[m.end():]

        # 跳过头部的空行，取第一个非空行
        next_lines = after.strip().split("\n")
        non_empty = []
        for nl in next_lines:
            nl = nl.strip()
            if nl:
                non_empty.append(nl)
            if len(non_empty) >= 3:
                break

        if not non_empty:
            continue

        # 检查：第一个非空行是否为作者行
        if not is_author_line(non_empty[0]):
            continue

        # 通过！这是一个诗歌标题
        poem_starts.append(m.start())

    if not poem_starts:
        print(f"  [警告] 未提取到诗歌：{filepath}")
        return []

    # 去重 + 排序
    poem_starts = sorted(set(poem_starts))

    # 切分
    poems = []
    for i, start in enumerate(poem_starts):
        if i + 1 < len(poem_starts):
            end = poem_starts[i + 1]
        else:
            end = len(text)
        poem_text = text[start:end].strip()
        poems.append(poem_text)

    return poems


def extract_poems_separator(filepath: str) -> list[str]:
    """从 ===== 分隔的文件中提取诗歌"""
    if not os.path.exists(filepath):
        print(f"  [警告] 文件不存在：{filepath}")
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    poems = [c.strip() for c in content.split("=====") if c.strip()]
    return poems


# ============================================================
# 主流程
# ============================================================

def main():
    all_files = [
        (str(SOURCE_POEMS_1_20_PATH), False, "1-20首"),
        (str(POEM_21_40_PATH), True, "21-40首"),
        (str(SOURCE_POEMS_41_60_PATH), False, "41-60首"),
        (str(SOURCE_POEMS_61_80_PATH), False, "61-80首"),
    ]

    all_poems = []

    for filepath, use_sep, label in all_files:
        if use_sep:
            poems = extract_poems_separator(filepath)
        else:
            poems = extract_poems_from_file(filepath)
        print(f"  {label}: {len(poems)} 首")
        all_poems.extend(poems)
        for p in poems:
            first = p.split("\n")[0].strip()[:60]
            print(f"    -> {first}")

    print(f"\n合并完成，共 {len(all_poems)} 首诗")

    if len(all_poems) != 80:
        print(f"  [警告] 预期 80 首，实际 {len(all_poems)} 首")

    # 写入合并文件
    output_path = POEM_1_80_PATH
    output_text = "\n\n=====\n\n".join(all_poems)
    backup = atomic_write_text(output_path, output_text, encoding="utf-8")
    if backup:
        print(f"已备份原文件到：{backup}")

    file_size = os.path.getsize(output_path)
    print(f"\n已写入：{output_path}")
    print(f"文件大小：{file_size:,} 字节")


if __name__ == "__main__":
    main()
