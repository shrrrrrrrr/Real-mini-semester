"""应用配置：从环境变量或 .env 读取。

本地优先架构：数据库为本地 SQLite 单文件，无云服务依赖；
LLM 通过 OpenAI 兼容协议访问云端 API（联网 + API Key）。
"""

from pathlib import Path

from pydantic_settings import BaseSettings

# 仓库后端根目录（backend/）
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # ---- 数据与存储 ----
    # SQLite 数据库文件路径：所有学习数据（课程/块/问答/测验/闪卡）的单文件主存储
    db_path: Path = BASE_DIR / "data" / "zhiyuan.db"
    # 上传的原始文件保存目录：保留原件，支持"重新索引"而无需重传
    upload_dir: Path = BASE_DIR / "data" / "uploads"

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
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    class Config:
        env_file = BASE_DIR / ".env"
        env_file_encoding = "utf-8"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
