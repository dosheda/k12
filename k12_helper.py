"""
K12 错题讲解助手 —— 最小起步版本
功能：
  - 命令行输入题目文字 → 调用 DeepSeek API → 返回分步讲解
  - 支持拖入/粘贴题目图片路径，自动 OCR 识别文字后再讲解
"""

# ============================================================
# 第 1 步：导入需要的库
# ============================================================
import os       # 用于读取环境变量
import sys      # 用于退出程序、读取命令行输入
from pathlib import Path

# ============================================================
# 修复 Windows 终端中文乱码问题
# ============================================================
# Windows 终端默认用 GBK 编码，但 DeepSeek API 返回的是 UTF-8 中文
# 下面把 stdin/stdout 都强制改成 UTF-8，中文就不会乱码了
# errors="replace": 遇到打印不了的怪字符用 ? 代替，不会崩溃
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# openai 是 OpenAI 官方提供的 Python SDK
# DeepSeek API 兼容 OpenAI 的接口格式，所以直接用这个库就行
from openai import OpenAI

# ============================================================
# 图片 OCR 相关库
# ============================================================
# pytesseract：Python 驱动 Tesseract OCR 引擎的"遥控器"
# PIL (Pillow)：用来打开各种格式的图片文件
import pytesseract
from PIL import Image
from api_utils import classify_api_error, extract_chat_content
from config import (
    DEEPSEEK_API_KEY_ENV,
    MAX_OCR_IMAGE_BYTES,
    MAX_OCR_IMAGE_PIXELS,
    MAX_USER_QUERY_CHARS,
    TESSERACT_CMD,
)

# 告诉 pytesseract Tesseract 引擎装在哪里
# 你刚才装的 Tesseract 就在这里
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# 常见的图片文件后缀（用来判断用户是不是拖了一张图进来）
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"}


# ============================================================
# 第 2 步：从环境变量读取 API Key
# ============================================================
# 这样做的好处：key 不会写死在代码里，不会不小心上传到 GitHub
DEEPSEEK_API_KEY = os.environ.get(DEEPSEEK_API_KEY_ENV)

# 如果用户忘了设置环境变量，给一个友好的提示并退出
if DEEPSEEK_API_KEY is None:
    print(f"[错误] 找不到环境变量 {DEEPSEEK_API_KEY_ENV}")
    print("请先设置环境变量：")
    print("  Windows PowerShell: $env:DEEPSEEK_API_KEY='sk-你的key'")
    print("  Windows CMD:        set DEEPSEEK_API_KEY=<你的 DeepSeek API Key>")
    sys.exit(1)  # 非 0 退出码表示程序异常结束


# ============================================================
# 第 3 步：创建 DeepSeek API 客户端
# ============================================================
# api_key:   从环境变量传入
# base_url:  DeepSeek 的 API 地址（兼容 OpenAI 格式）
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)


# ============================================================
# 第 4 步：设定 system prompt（系统提示词）
# ============================================================
# system prompt 用来"设定 AI 的角色"，告诉它该怎么回答问题
# 这段提示词会让 AI 扮演一位耐心老师，分步引导而不是直接给答案
SYSTEM_PROMPT = (
    '你是一位微笑的、永远不会发脾气的小学/初中数学老师，名叫「小K老师」。\n'
    '你的学生可能是有点害怕数学的孩子，所以你讲话永远温暖、鼓励、具体，\n'
    '多用比喻和生活例子。\n'
    '讲解时严格使用「苏格拉底式提问」：用一连串小问题引导学生自己说出答案，\n'
    '而不是直接把答案告诉学生。\n'
    '\n'
    '每次讲解必须严格按下面四个板块输出，板块之间用空行隔开：\n'
    '\n'
    '【考点】\n'
    '用一两句话点明这道题考的是什么知识点，用学生能听懂的语言说。\n'
    '比如不要说"考察一元一次方程"，要说"考的是怎么设未知数、怎么根据条件列出方程"。\n'
    '\n'
    '【你可能错在哪里】\n'
    '列出 2~3 个最常见的错误做法，每个都像在跟学生聊天一样说出来。\n'
    '格式："有的同学会……但其实……"。让学生感觉到"哦，原来犯这个错很正常"。\n'
    '\n'
    '【我们来一步步想】\n'
    '这是核心板块，用苏格拉底式提问。\n'
    '把解题过程拆成 3~5 个小台阶，每个台阶只问一个小问题。\n'
    '比如"先想一想…""接下来你觉得该怎么做？"\n'
    '每个问题后面给一点停顿提示（比如"别着急，慢慢想"）。\n'
    '注意：这一板块只提问和引导，不揭晓答案，让学生自己先试试。\n'
    '\n'
    '【完整步骤】\n'
    '用清晰、工整的格式写出完整解题过程，每一步标上序号。\n'
    '公式用换行单独写，方便学生对着检查。\n'
    '最后把最终答案用【答：xxx】标出来。\n'
    '如果学生前面自己想出来了，这里的步骤就是给他核对用的。\n'
    '\n'
    '禁止事项：\n'
    '- 不要说"你应该""你必须"这种命令语气，改用"我们可以""试试看"；\n'
    '- 不要用大学数学词汇，全部用中小学生能听懂的话；\n'
    '- 不要在第一板块就开始讲解题步骤，板块之间内容不要串；\n'
    '- 如果题目超纲（比如小学生遇到二次方程），温柔告诉学生这是几年级会学的，\n'
    '  但依然用现有知识尽量讲解。'
)


# ============================================================
# 第 5 步-0：OCR 图片识别函数 —— 把题目照片"读"成文字
# ============================================================
# 这个函数拿一张图片的路径，让 Tesseract OCR 引擎把里面的字读出来
# 成功返回识别出的文字，失败返回 None

def ocr_image(image_path, confirm=True):
    """
    用 OCR 识别图片里的题目文字。
    confirm=True：识别后让用户校对（交互模式用）
    confirm=False：直接返回结果（命令行一次性模式用）
    """
    # 1. 检查文件是否存在
    path = Path(image_path)
    if not path.is_file():
        print("[错误] 找不到这个文件，请检查路径是否正确。")
        return None
    if path.stat().st_size > MAX_OCR_IMAGE_BYTES:
        print(f"[错误] 图片太大，请控制在 {MAX_OCR_IMAGE_BYTES // (1024 * 1024)}MB 以内。")
        return None

    # 2. 检查是不是图片格式
    ext = path.suffix.lower()  # 取文件后缀名，转小写
    if ext not in IMAGE_EXTENSIONS:
        print(f"[错误] 这个文件后缀是 {ext}，不是常见的图片格式哦。")
        print(f" 支持的格式：{', '.join(sorted(IMAGE_EXTENSIONS))}")
        return None

    # 3. 用 Pillow 打开图片，交给 Tesseract 读文字
    print(f"\n[OCR] 正在识别图片：{path.name}")
    print("[OCR] 请稍候...")
    try:
        img = Image.open(path)               # 打开图片文件
        width, height = img.size
        if width * height > MAX_OCR_IMAGE_PIXELS:
            print(f"[错误] 图片像素过大，请控制在 {MAX_OCR_IMAGE_PIXELS:,} 像素以内。")
            return None
        # Tesseract 引擎识别文字，lang 参数告诉它用中英文混合识别
        text = pytesseract.image_to_string(
            img,
            lang="chi_sim+eng",                     # 简体中文 + 英文
            config="--psm 6",                       # 假设图片是一段均匀排列的文字
        )
        text = text.strip()                         # 去掉首尾空白

        if not text:
            print("[OCR] 图片没有识别出任何文字。请确认图片清晰且包含题目。")
            return None

        # 把识别结果展示给用户
        print("[OCR] 识别出的文字如下：")
        print("-" * 40)
        print(text)
        print("-" * 40)

        # ----- 关键一步：让用户补充图中信息 -----
        # OCR 只能读文字，读不了图（几何图形、坐标系、统计图等）
        # 所以让用户口头描述图中信息，我们把它和 OCR 文字拼成完整题目
        if confirm:
            print('\n[提示] 如果题目中有图（几何图、坐标图、统计图...），')
            print('OCR 只能读出[字],读不懂[图]。请用文字描述图中信息。')
            print('比如: 三角形ABC中,直角在B点,AB=3是底边,BC=4是竖边。')

            diagram_desc = input("\n请简要描述图中内容（没有图直接回车跳过）：").strip()

            # 如果用户描述了图，把图描述附到题目后面
            if diagram_desc:
                text = text + "\n（题目配图说明：" + diagram_desc + "）"
                print("\n[OCR] 已将图片描述合并到题目中：")
                print("-" * 40)
                print(text)
                print("-" * 40)

            # 最后再给一次校对机会
            user_edit = input("\n题目有需要修正的地方吗？直接回车确认，或输入修正后的完整题目：").strip()
            if user_edit:
                return user_edit   # 用户手动修正了

        # 用户确认无误，或命令行自动确认
        return text

    except Exception as e:
        print("[OCR] 识别失败，请确认图片格式和 Tesseract 配置。")
        return None


# ============================================================
# 第 5 步：核心函数 —— 把"调 API + 打印 + 报错"打包
# ============================================================
# 函数就是一段起好名字的代码，以后想用直接喊名字就行
# 这个函数收一道题，负责调 API 并把讲解打印出来
# 出错不会让程序崩溃，会打印中文提示然后返回 False

def ask(question):
    """发一条题目给 DeepSeek，打印讲解。成功返回 True，失败返回 False。"""
    print("[思考中] 正在思考中，请稍候...\n")

    try:
        # 发起聊天请求
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},   # AI 角色设定
                {"role": "user", "content": question},           # 用户的问题
            ],
            stream=False,  # 等全部生成完一次性返回
        )

        # 从返回结果里取出 AI 的回复文字
        answer = extract_chat_content(response)

        # 打印讲解结果
        print("=" * 60)
        print("  [讲解] 讲解如下：")
        print("=" * 60)
        print(answer)
        print("=" * 60)
        print()
        return True  # 成功

    except KeyboardInterrupt:
        # 用户按了 Ctrl+C
        print("\n\n[警告] 用户中断操作，再见！")
        sys.exit(0)

    except Exception as e:
        print(f"\n[错误] {classify_api_error(e)}")

        print()
        return False  # 失败


# ============================================================
# 第 6 步：两种运行模式 —— 命令行直接问 / 交互循环
# ============================================================

if len(sys.argv) > 1:
    # ----- 模式 A：命令行传了题目或图片路径 → 一次性，答完就退出 -----
    user_input = " ".join(sys.argv[1:])  # 把命令行参数拼成完整字符串

    # 去掉 Windows 拖文件时自动加的双引号（比如 "D:\我的图片.png"）
    user_input = user_input.strip('"')

    # 判断是不是拖了一张图片进来（后缀是图片格式）
    ext = os.path.splitext(user_input)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        # 图片 → 先 OCR 转文字
        question_text = ocr_image(user_input, confirm=False)  # 命令行模式不交互
        if question_text is None:
            sys.exit(1)  # OCR 失败，直接退出
        user_question = question_text
    else:
        # 普通文字 → 直接当题目
        user_question = user_input

    # 如果用户啥也没输入，友好退出
    if not user_question:
        print("[错误] 你没有输入任何题目，程序退出。")
        sys.exit(0)
    if len(user_question) > MAX_USER_QUERY_CHARS:
        print(f"[错误] 题目太长，请控制在 {MAX_USER_QUERY_CHARS} 个字符以内。")
        sys.exit(1)

    ask(user_question)

else:
    # ----- 模式 B：没传参数 → 交互循环，反复问直到用户退出 -----
    print("=" * 60)
    print("  [K12] K12 错题讲解助手")
    print("=" * 60)
    print("用法：")
    print("  直接打字输入题目  →  小K老师讲解")
    print("  拖入/粘贴图片路径  →  OCR 识别后讲解")
    print("  输入 quit 或按 Ctrl+C 退出程序。")
    print()

    while True:  # 死循环，直到用户主动退出才跳出
        user_input = input("请输入题目或图片路径> ").strip()

        # 去掉 Windows 拖文件时自动加的双引号
        user_input = user_input.strip('"')

        # 用户输入 quit 就退出
        if user_input.lower() == "quit":
            print("再见！")
            sys.exit(0)

        # 用户啥也没输入（直接按了回车），回到循环开头重新等
        if not user_input:
            print("[提示] 你没有输入任何内容，请重新输入。\n")
            continue  # 跳过本次循环，回到 while 顶部

        # ----- 判断是文字题还是图片路径 -----
        ext = os.path.splitext(user_input)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            # 用户拖了一张图片 → 先 OCR 识别
            question_text = ocr_image(user_input)
            if question_text is None:
                # OCR 失败了，回到循环让用户重试
                print()
                continue
            user_question = question_text
        else:
            # 普通文字题目
            user_question = user_input

        # 调用上面写好的 ask 函数
        if len(user_question) > MAX_USER_QUERY_CHARS:
            print(f"[错误] 题目太长，请控制在 {MAX_USER_QUERY_CHARS} 个字符以内。\n")
            continue
        ask(user_question)
