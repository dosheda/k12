"""
古诗格式整理 —— 把全部 80 首统一为规定结构
==========================================
输入：古诗词1-80_整理版.txt（合并后的原始数据）
输出：古诗词1-80_整理版.txt（覆盖为统一格式）

统一结构：
  《诗名》 作者 朝代
  【原文】
  （诗句）
  【注释】
  （字词解释）
  【赏析】
  （理解和情感分析）

每首诗用 ===== 分隔，诗内部绝对不出现 =====
"""

import re
import os
from config import POEM_1_80_PATH
from safe_io import atomic_write_text

# ============================================================
# 已知诗人→朝代映射（小学常见诗人）
# ============================================================
POET_DYNASTY = {
    # 汉
    "汉乐府": "汉",
    # 三国
    "曹植": "三国·魏",
    # 北朝
    "北朝乐府": "北朝",
    # 唐
    "骆宾王": "唐", "贺知章": "唐", "王之涣": "唐",
    "孟浩然": "唐", "王翰": "唐", "王昌龄": "唐",
    "王维": "唐", "高适": "唐", "李白": "唐",
    "杜甫": "唐", "张继": "唐", "韦应物": "唐",
    "卢纶": "唐", "孟郊": "唐", "刘禹锡": "唐",
    "白居易": "唐", "李绅": "唐", "杜牧": "唐",
    "李商隐": "唐", "温庭筠": "唐", "柳宗元": "唐",
    "贾岛": "唐", "韩翃": "唐", "张志和": "唐",
    "韩愈": "唐", "刘长卿": "唐", "胡令能": "唐",
    "林杰": "唐", "虞世南": "唐",
    # 宋
    "王安石": "宋", "苏轼": "宋", "李清照": "宋",
    "陆游": "宋", "杨万里": "宋", "范成大": "宋",
    "朱熹": "宋", "辛弃疾": "宋", "林升": "宋",
    "叶绍翁": "宋", "范仲淹": "宋", "欧阳修": "宋",
    "曾几": "宋", "翁卷": "宋",
    # 元
    "王冕": "元",
    # 明
    "于谦": "明", "王磐": "明",
    # 清
    "郑燮": "清", "龚自珍": "清", "高鼎": "清",
    "袁枚": "清", "查慎行": "清", "纳兰性德": "清",
}


def find_dynasty(author_raw, poem_text=""):
    """推断朝代：优先从作者行括号提取，其次查表，最后尝试从赏析里找"""
    # 1. 作者行本身含括号
    m = re.search(r'[（(](.+?)[）)]', author_raw)
    if m:
        return m.group(1)
    # 2. 查表
    if author_raw in POET_DYNASTY:
        return POET_DYNASTY[author_raw]
    # 3. 尝试在赏析文字里找 "唐代诗人" 等
    m2 = re.search(r'([唐宋元明清])[代朝]', poem_text[:300])
    if m2:
        return m2.group(1)
    return ""


def clean_title(raw_title):
    """去掉序号前缀，返回纯诗名"""
    t = re.sub(r'^\d+[.．]\s*', '', raw_title)
    return t.strip()


def reformat_poem(raw_text):
    """将一首原始诗重整为统一结构"""
    raw_text = raw_text.strip()
    if not raw_text:
        return ""

    # ------ 已经是干净格式的直接放行 ------
    if raw_text.startswith('《'):
        return raw_text

    lines = raw_text.split('\n')

    # ------ 第一行：标题 ------
    title_raw = lines[0].strip()
    title = clean_title(title_raw)

    # ------ 找到作者行（标题后第一个非空行）------
    idx = 1
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    author_raw = lines[idx].strip() if idx < len(lines) else "佚名"

    # 顺便处理标题被折行的情况（极少，但预防）
    # 如果 author_raw 太短且看起来像标题的一部分，合并
    # 不过这种情况在数据里没有，跳过

    idx += 1  # 作者行之后开始找正文

    # ------ 找到第一个【标记】的位置 ------
    # 正文就是作者行之后到第一个【标记】之间的内容
    body_lines = []
    section_starts = {}  # 标记名 → 起始行号

    for i in range(idx, len(lines)):
        ln = lines[i].strip()
        m = re.match(r'^【(.+?)】', ln)
        if m:
            tag = m.group(1).strip()
            if tag not in section_starts:
                section_starts[tag] = i
            continue
        if not section_starts:
            body_lines.append(ln)

    # ------ 收集各区块内容 ------
    def get_section_content(start_line, end_line):
        """提取从 start_line 到 end_line 之间的文本（不含区块标记行）"""
        result = []
        for j in range(start_line + 1, end_line):
            ln = lines[j].strip()
            if ln:
                result.append(ln)
        return '\n'.join(result)

    # 给每个区块找结束位置
    sorted_tags = sorted(section_starts.items(), key=lambda x: x[1])
    sorted_tags.append(("__END__", len(lines)))

    section_texts = {}
    for k in range(len(sorted_tags) - 1):
        tag, start = sorted_tags[k]
        end = sorted_tags[k + 1][1]
        content = get_section_content(start, end)
        section_texts[tag] = content

    # ------ 组装 ------
    #   朝代
    dynasty = find_dynasty(author_raw, '\n'.join(body_lines))

    #   原文
    poem_body = '\n'.join([l for l in body_lines if l.strip()])

    #   注释
    annotation = section_texts.get('注释', '无').strip()
    if not annotation:
        annotation = '无'

    #   赏析：合并 简析 + 赏析 + 今译 + 译文 + 解说 + 解题
    analysis_parts = []
    extra_tags = ['简析', '赏析', '今译', '译文', '解说', '解题']
    for t in extra_tags:
        if t in section_texts and section_texts[t].strip():
            analysis_parts.append(section_texts[t].strip())
    # 也处理 "赏析 1"、"赏析 2" 这种
    for t in section_texts:
        if t.startswith('赏析') and t not in extra_tags:
            if section_texts[t].strip():
                analysis_parts.append(section_texts[t].strip())

    analysis = '\n\n'.join(analysis_parts).strip()
    if not analysis:
        analysis = '无'

    # ------ 输出 ------
    author_display = author_raw
    # 如果作者行含括号里的朝代，去掉括号只留作者名
    author_clean = re.sub(r'[（(].+?[）)]', '', author_raw).strip()

    if dynasty:
        header = f"《{title}》 {author_clean} {dynasty}"
    else:
        header = f"《{title}》 {author_clean}"

    return (
        f"{header}\n"
        f"【原文】\n{poem_body}\n"
        f"【注释】\n{annotation}\n"
        f"【赏析】\n{analysis}"
    )


# ============================================================
# 主流程
# ============================================================

def main():
    input_path = POEM_1_80_PATH

    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    raw_chunks = content.split("=====")
    raw_poems = [c.strip() for c in raw_chunks if c.strip()]

    print(f"读入 {len(raw_poems)} 首诗")

    clean_poems = []
    for p in raw_poems:
        clean = reformat_poem(p)
        clean_poems.append(clean)

    # 写回同一个文件：先备份，再原子替换
    output_text = "\n\n=====\n\n".join(clean_poems)
    backup = atomic_write_text(input_path, output_text, encoding="utf-8")
    if backup:
        print(f"已备份原文件到：{backup}")

    print(f"整理完成，输出 {len(clean_poems)} 首")
    print(f"文件：{input_path}")
    print(f"大小：{os.path.getsize(input_path):,} 字节")

    # 预览前 3 首和后 1 首
    print("\n===== 前 3 首预览 =====")
    for p in clean_poems[:3]:
        print(p[:200])
        print("---")

    print("\n===== 最后 1 首预览 =====")
    print(clean_poems[-1][:300])


if __name__ == "__main__":
    main()
