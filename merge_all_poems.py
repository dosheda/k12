r"""
合并全部 80 首古诗为统一格式
==============================
输入：
  1. C:/Users/aa/Music/shi/古诗20.txt    （1-20首，序号分隔）
  2. D:/k12 helper/古诗词21-40_整理版.txt （21-40首，===== 分隔）
  3. C:/Users/aa/Music/shi/60.txt        （41-60首，序号分隔）
  4. C:/Users/aa/Music/shi/80.txt        （61-80首，序号分隔）

输出：
  D:/k12 helper/古诗词1-80_整理版.txt    （全部80首，===== 分隔）
"""

import re
import os

# ============================================================
# 工具函数：按诗编号匹配 + 切分
# ============================================================

def split_by_poem_number(text: str) -> list[str]:
    """
    把「序号分隔」格式的文件切成一首一首。
    匹配行首的「数字.」或「数字．」作为分隔点。
    返回纯诗文本列表（不含文件名头部信息）。
    """
    # 匹配行首的序号：如 "1." "41." "61．"（有中文句点的情况）
    pattern = re.compile(r'^(\d+)[.．]\s*', re.MULTILINE)

    # 找到所有匹配位置
    matches = list(pattern.finditer(text))

    if not matches:
        return []

    chunks = []
    for i, m in enumerate(matches):
        start = m.start()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(text)
        chunk = text[start:end].strip()
        chunks.append(chunk)

    return chunks


# ============================================================
# 处理函数：读 → 切 → 标准化
# ============================================================

def process_file(filepath: str, use_separator: bool = False) -> list[str]:
    """
    读取一个文件，返回诗文本列表。
    use_separator=True 时用 ===== 切分（旧格式），
    use_separator=False 时用序号切分（新格式）。
    """
    if not os.path.exists(filepath):
        print(f"  [警告] 文件不存在，跳过：{filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if use_separator:
        # 旧格式：用 ===== 切
        raw = content.split("=====")
        poems = [c.strip() for c in raw if c.strip()]
        print(f"  读取 {os.path.basename(filepath)}：{len(poems)} 首（===== 分隔）")
    else:
        # 新格式：用序号切
        poems = split_by_poem_number(content)
        print(f"  读取 {os.path.basename(filepath)}：{len(poems)} 首（序号分隔）")

    return poems


# ============================================================
# 主流程
# ============================================================

def main():
    all_poems = []  # 按 1-80 顺序存放

    # ---- 第 1 批：古诗20.txt（诗的 1-20）----
    poems_1_20 = process_file(r"C:\Users\aa\Music\shi\古诗20.txt", use_separator=False)
    all_poems.extend(poems_1_20)

    # ---- 第 2 批：古诗词21-40_整理版.txt（21-40）----
    poems_21_40 = process_file(r"D:\k12 helper\古诗词21-40_整理版.txt", use_separator=True)
    all_poems.extend(poems_21_40)

    # ---- 第 3 批：60.txt（41-60）----
    poems_41_60 = process_file(r"C:\Users\aa\Music\shi\60.txt", use_separator=False)
    all_poems.extend(poems_41_60)

    # ---- 第 4 批：80.txt（61-80）----
    poems_61_80 = process_file(r"C:\Users\aa\Music\shi\80.txt", use_separator=False)
    all_poems.extend(poems_61_80)

    print(f"\n合并完成，共 {len(all_poems)} 首诗。")

    # ---- 检查数量 ----
    if len(all_poems) != 80:
        print(f"  [警告] 预期 80 首，实际 {len(all_poems)} 首，请检查！")

    # ---- 写入合并文件 ----
    output_path = r"D:\k12 helper\古诗词1-80_整理版.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        for i, poem in enumerate(all_poems):
            f.write(poem)
            if i < len(all_poems) - 1:
                f.write("\n\n=====\n\n")  # 统一用 ===== 分隔

    print(f"已写入：{output_path}")
    print(f"文件大小：{os.path.getsize(output_path):,} 字节")

    # ---- 打印前 5 首和后 2 首标题，确认顺序 ----
    print("\n--- 前 5 首预览 ---")
    for poem in all_poems[:5]:
        first_line = poem.split("\n")[0].strip()
        print(f"  {first_line}")

    print("\n--- 后 3 首预览 ---")
    for poem in all_poems[-3:]:
        first_line = poem.split("\n")[0].strip()
        print(f"  {first_line}")


if __name__ == "__main__":
    main()
