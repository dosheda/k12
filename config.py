"""Central project configuration.

All paths default to this repository directory and can be overridden with
environment variables when needed.
"""

from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("K12_HELPER_DATA_DIR", BASE_DIR)).expanduser()

CHROMA_DB_PATH = Path(os.environ.get("K12_CHROMA_DB_PATH", DATA_DIR / "chroma_db")).expanduser()
LEARNING_DB_PATH = Path(os.environ.get("K12_LEARNING_DB_PATH", DATA_DIR / "learning_records.db")).expanduser()
POEM_1_80_PATH = Path(os.environ.get("K12_POEM_1_80_PATH", DATA_DIR / "古诗词1-80_整理版.txt")).expanduser()
POEM_21_40_PATH = Path(os.environ.get("K12_POEM_21_40_PATH", DATA_DIR / "古诗词21-40_整理版.txt")).expanduser()
POEM_TAGS_PATH = Path(os.environ.get("K12_POEM_TAGS_PATH", DATA_DIR / "诗名-标签对照表.txt")).expanduser()

SOURCE_POEMS_1_20_PATH = Path(os.environ.get("K12_SOURCE_POEMS_1_20_PATH", DATA_DIR / "古诗20.txt")).expanduser()
SOURCE_POEMS_41_60_PATH = Path(os.environ.get("K12_SOURCE_POEMS_41_60_PATH", DATA_DIR / "60.txt")).expanduser()
SOURCE_POEMS_61_80_PATH = Path(os.environ.get("K12_SOURCE_POEMS_61_80_PATH", DATA_DIR / "80.txt")).expanduser()

DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
ACCESS_CODE_ENV = "K12_HELPER_ACCESS_CODE"
ACCESS_CODE = os.environ.get(ACCESS_CODE_ENV, "")

MAX_USER_QUERY_CHARS = int(os.environ.get("K12_MAX_QUERY_CHARS", "500"))
API_COOLDOWN_SECONDS = float(os.environ.get("K12_API_COOLDOWN_SECONDS", "3"))
MAX_REPORT_RECORDS = int(os.environ.get("K12_MAX_REPORT_RECORDS", "50"))
MAX_REPORT_FIELD_CHARS = int(os.environ.get("K12_MAX_REPORT_FIELD_CHARS", "120"))
MAX_REPORT_PROMPT_CHARS = int(os.environ.get("K12_MAX_REPORT_PROMPT_CHARS", "12000"))

TESSERACT_CMD = os.environ.get(
    "TESSERACT_CMD",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
)
MAX_OCR_IMAGE_BYTES = int(os.environ.get("K12_MAX_OCR_IMAGE_BYTES", str(8 * 1024 * 1024)))
MAX_OCR_IMAGE_PIXELS = int(os.environ.get("K12_MAX_OCR_IMAGE_PIXELS", str(12_000_000)))
