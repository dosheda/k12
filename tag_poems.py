"""
K12 古诗词标签生成脚本 v2 —— 用 DeepSeek 逐首打标签
=====================================================
v1 的关键字匹配太粗糙，杂讯太多。
v2 改用 DeepSeek 直接读每首诗，从四个维度生成标签。
每首诗都带"近义说法"（如同一意思的不同问法都覆盖）。

标签维度：
  1. 题材类型 —— 写景/山水/送别/咏物/田园/边塞/爱国/咏史/节令/哲理/思乡/羁旅/友情/亲情/讽喻/惜时/劝学/宫怨/隐逸
  2. 表达情感 —— 思乡/惜时/喜悦/悲愤/孤独/闲适/忧愁/豪迈/乐观/热爱/惜别/母爱/怀旧/失意/坚贞/童趣/沧桑/同情民生
  3. 表现手法 —— 托物言志/借景抒情/直抒胸臆/比喻/夸张/拟人/对比/对偶/用典/双关/互文/设问/白描/渲染/以动衬静/虚实结合
  4. 关键意象 —— 诗中出现的重要人物、地点、自然物、特定事物
"""

import os
import sys
import json
import re
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openai import OpenAI

# ============================================================
# 环境准备
# ============================================================

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    print("[错误] 找不到环境变量 DEEPSEEK_API_KEY")
    sys.exit(1)

deepseek = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# ============================================================
# 第 1 步：读取全部 80 首诗
# ============================================================

def load_poems(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    chunks = content.split("=====")
    poems = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        poems.append(chunk)
    return poems

# ============================================================
# 第 2 步：调用 DeepSeek 为一批诗打标签
# ============================================================

TAGGING_PROMPT = """你是一位古诗词专家。请为下面提供的每首古诗生成主题标签，便于检索系统用。

对每一首诗，从四个维度打标签，每个标签要配上近义说法（用顿号连接），让不同措辞都能命中：

维度一：题材类型
  可选：写景/山水/风景、送别/赠别/离别、咏物/咏物诗、田园/乡村/农事、边塞/战争/征战、
        爱国/忧国/报国、咏史/怀古/怀旧、节令/节日/节气、思乡/怀乡、哲理/说理/寓理、
        亲情/母爱/骨肉情、友情/友谊/知己、讽喻/讽刺/讥讽、惜时/劝学/劝勉、
        羁旅/行旅/旅愁、隐逸/隐居/隐士、宫怨/闺怨

维度二：表达情感
  可选：思乡/想家/乡愁、惜时/珍惜光阴、喜悦/欣喜/欢快、悲愤/愤慨/激愤、
        孤独/孤寂/寂寞、闲适/悠闲/自在/恬淡、忧愁/哀愁/感伤/惆怅、
        豪迈/豪放/激昂/慷慨、乐观/旷达/豁达/积极向上、热爱/赞美/讴歌/喜爱、
        惜别/不舍/离愁/留恋、母爱/亲情/感恩、怀旧/思友/念旧、
        失意/怀才不遇/抑郁、坚贞/高洁/傲岸不屈/清高、童趣/天真/可爱、
        沧桑感/今昔之感/盛衰无常、同情民生/悯农/关怀百姓

维度三：表现手法
  可选：托物言志/咏物言志/借物喻人、借景抒情/寓情于景/情景交融/触景生情、
        直抒胸臆/直白表达、比喻/比兴、夸张/浪漫夸张、拟人/拟人化/人格化、
        对比/衬托/映衬/对照、对偶/对仗、用典/化用典故、双关/谐音双关/一语双关、
        互文/互文见义、设问/自问自答、白描/朴素描写、渲染/铺陈/烘托、
        以动衬静/动静结合/以声衬静、虚实结合/虚实相生、借古讽今/借古喻今

维度四：关键意象（诗中出现的具体人名、地名、自然物、特定事物）
  提取诗中涉及的关键实体，如：李白、杜甫、庐山、西湖、月亮/明月、梅花/墨梅、石灰、竹子/竹石、桃花潭、黄鹤楼、瀑布、柳树/杨柳、长江、黄河、春风、夕阳/落日、牧童、渔翁等。每个实体也尽量给出同义说法。

【重要规则】
1. 只根据这首诗本身的内容打标签，不要受其他诗影响。
2. 每个标签后面尽量跟 2-4 个近义说法，用顿号连接。比如"思乡、想家、乡愁、怀乡"。
3. 标签要客观描述诗本身有什么，不要根据预设问题来凑。
4. 一首诗如果确实没有某个维度的内容，那个维度可以留空。
5. 不要编造诗里没有的东西。

请按以下 JSON 格式返回（只返回 JSON，不要其他文字）：
```json
[
  {
    "title": "诗名",
    "author": "作者",
    "dynasty": "朝代",
    "题材类型": "标签1、近义1、近义2",
    "表达情感": "标签1、近义1、近义2",
    "表现手法": "标签1、近义1、近义2",
    "关键意象": "意象1、近义1、意象2、近义2"
  }
]
```
"""

def tag_poems_batch(poems_batch, batch_num):
    """把一批诗发给 DeepSeek 打标签，返回解析后的列表"""
    poems_text = "\n\n========\n\n".join(poems_batch)
    user_msg = f"下面是 {len(poems_batch)} 首古诗，请为每首生成标签：\n\n{poems_text}"

    print(f"  批次 {batch_num}：正在请 DeepSeek 为 {len(poems_batch)} 首诗打标签……")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = deepseek.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": TAGGING_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                stream=False,
                temperature=0.2,  # 低温度，让输出稳定
            )
            result_text = response.choices[0].message.content

            # 清理掉可能的 markdown 代码块标记
            result_text = result_text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()

            # 解析 JSON
            data = json.loads(result_text)
            if isinstance(data, list):
                print(f"  批次 {batch_num}：√ 成功生成 {len(data)} 首诗的标签")
                return data
            else:
                print(f"  批次 {batch_num}：× JSON 格式不对（不是列表），重试第 {attempt+1} 次")
        except json.JSONDecodeError as e:
            print(f"  批次 {batch_num}：× JSON 解析失败：{e}")
            print(f"  原始返回前 200 字符：{result_text[:200]}")
            if attempt < max_retries - 1:
                print(f"  重试第 {attempt+1} 次……")
                time.sleep(2)
        except Exception as e:
            print(f"  批次 {batch_num}：× API 调用失败：{e}")
            if attempt < max_retries - 1:
                print(f"  重试第 {attempt+1} 次……")
                time.sleep(5)

    print(f"  批次 {batch_num}：× 重试全部失败，跳过此批次")
    return []


# ============================================================
# 第 3 步：主流程
# ============================================================

def main():
    input_path = r"D:\k12 helper\古诗词1-80_整理版.txt"
    output_path = r"D:\k12 helper\诗名-标签对照表.txt"

    poems = load_poems(input_path)
    print(f"读取完成，共 {len(poems)} 首诗\n")

    # 每批处理 10 首（太大容易超时解析出错，太小浪费 API 调用）
    BATCH_SIZE = 10
    all_tags = []

    for i in range(0, len(poems), BATCH_SIZE):
        batch = poems[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        batch_tags = tag_poems_batch(batch, batch_num)
        all_tags.extend(batch_tags)
        # 批次之间稍等，避免触发速率限制
        if i + BATCH_SIZE < len(poems):
            time.sleep(2)

    print(f"\n标签生成完成！共 {len(all_tags)} 首\n")

    # 写入文件
    print(f"正在写入标签对照表到：{output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("K12 古诗词 80 首 —— 诗名-标签对照表（DeepSeek 生成）\n")
        f.write("=" * 60 + "\n")
        f.write("每个标签包含近义说法（顿号分隔），确保不同问法都能命中。\n")
        f.write("=" * 60 + "\n\n")

        for entry in all_tags:
            f.write(f"【{entry.get('title', '?')}】 {entry.get('author', '?')} {entry.get('dynasty', '?')}\n")
            f.write(f"  题材类型：{entry.get('题材类型', '（无）')}\n")
            f.write(f"  表达情感：{entry.get('表达情感', '（无）')}\n")
            f.write(f"  表现手法：{entry.get('表现手法', '（无）')}\n")
            f.write(f"  关键意象：{entry.get('关键意象', '（无）')}\n")
            f.write("\n")

    print(f"标签对照表已保存到：{output_path}")

    # 打印完整内容到终端
    print("\n" + "=" * 60)
    print("以下是全部 80 首诗的标签，请逐首检查：")
    print("=" * 60 + "\n")
    for i, entry in enumerate(all_tags):
        print(f"[{i+1:02d}] 《{entry.get('title', '?')}》 {entry.get('author', '?')} {entry.get('dynasty', '?')}")
        print(f"    题材类型：{entry.get('题材类型', '（无）')}")
        print(f"    表达情感：{entry.get('表达情感', '（无）')}")
        print(f"    表现手法：{entry.get('表现手法', '（无）')}")
        print(f"    关键意象：{entry.get('关键意象', '（无）')}")
        print()

    # ============================================================
    # 第 4 步：自动抽查用户指定的重点诗
    # ============================================================
    print("=" * 60)
    print("【自动抽查】重点检查以下诗的标签：")
    print("=" * 60)

    checks = {
        "石灰吟": ["托物言志", "咏志", "言志", "石灰", "清白"],
        "竹石": ["托物言志", "咏物言志", "竹子", "竹石", "坚贞"],
        "墨梅": ["托物言志", "咏物言志", "梅花", "墨梅", "清气"],
        "望庐山瀑布": ["庐山", "香炉峰", "瀑布", "九江", "江西"],
        "静夜思": ["思乡", "想家", "乡愁", "怀乡", "明月", "月亮"],
        "九月九日忆山东兄弟": ["思乡", "想家", "乡愁", "怀乡", "重阳"],
    }

    for entry in all_tags:
        title = entry.get("title", "")
        for check_title, required_tags in checks.items():
            if check_title in title:
                print(f"\n  《{title}》 {entry.get('author', '')}")
                all_tag_text = "  ".join([str(entry.get(k, "")) for k in ["题材类型", "表达情感", "表现手法", "关键意象"]])
                missing = []
                for rt in required_tags:
                    if rt not in all_tag_text:
                        missing.append(rt)
                if missing:
                    print(f"  ⚠ 缺失：{', '.join(missing)}")
                else:
                    print(f"  ✓ 全部命中：{', '.join(required_tags)}")
                break


if __name__ == "__main__":
    main()
