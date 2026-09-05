"""应用配置：从环境变量或 .env 读取。

本地优先架构：数据库为本地 SQLite 单文件，无云服务依赖；
LLM 通过 OpenAI 兼容协议访问云端 API（联网 + API Key）。
"""

import os
from pathlib import Path

from pydantic_settings import BaseSettings

# 仓库后端根目录（backend/）
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录解析优先级（覆盖点从粗到细）：
# 1. HANGYOU_DATA_DIR —— 桌面安装包用户可写目录（SQLite 与 uploads 一起重定位）；
# 2. HANGYOU_DB_PATH / HANGYOU_UPLOAD_DIR —— Docker/HF Spaces 精确覆盖
#    （SQLite 落 /data 持久卷，uploads 可另行指定）；
# 3. 默认 backend/data（本地开发）。
RUNTIME_DATA_DIR = Path(os.environ.get("HANGYOU_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
DB_PATH_OVERRIDE = os.environ.get("HANGYOU_DB_PATH")
UPLOAD_DIR_OVERRIDE = os.environ.get("HANGYOU_UPLOAD_DIR")


class Settings(BaseSettings):
    # ---- 数据与存储 ----
    # SQLite 数据库文件路径：所有学习数据（课程/块/问答/测验/闪卡）的单文件主存储
    db_path: Path = Path(DB_PATH_OVERRIDE) if DB_PATH_OVERRIDE else RUNTIME_DATA_DIR / "zhiyuan.db"
    # 上传的原始文件保存目录：保留原件，支持"重新索引"而无需重传
    upload_dir: Path = Path(UPLOAD_DIR_OVERRIDE) if UPLOAD_DIR_OVERRIDE else RUNTIME_DATA_DIR / "uploads"

    # ---- LLM（OpenAI 兼容协议，供应商可切换：DeepSeek / GLM / Qwen / OpenAI）----
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    # 结构化输出失败后的定向重试上限（宁缺毋滥策略）
    llm_max_retries: int = 2

    # ---- 嵌入模型 ----
    # 本地 sentence-transformers 模型名；首次使用时联网下载约 90MB，之后离线可用
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ---- 检索参数 ----
    retrieval_top_k: int = 6      # 最终送入 Prompt 的片段数
    retrieval_pool: int = 20      # 每路检索的候选池大小
    rrf_k: int = 60               # RRF 平滑常数（论文推荐值）

    # ---- 服务 ----
    host: str = "127.0.0.1"
    port: int = 8000
    # CORS 白名单：本地开发 + 环境变量注入的生产前端域名（逗号分隔，
    # 部署 Vercel 后把 https://xxx.vercel.app 加进 EXTRA_CORS_ORIGINS）
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost,capacitor://localhost"
    )
    extra_cors_origins: str = ""  # 部署环境追加（逗号分隔，支持通配符前缀校验见 main.py）

    class Config:
        env_file = BASE_DIR / ".env"
        env_file_encoding = "utf-8"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
