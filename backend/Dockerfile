# 航友后端 · Docker 镜像（HF Spaces 部署用）
#
# 关键设计：
# 1. CPU 版 torch（+index-url）——体积约为 GPU 版 1/6，HF Space 免费 16GB 内存足够；
# 2. 构建期预下载嵌入模型并烘焏到镜像（sentence-transformers 缓存目录），
#    运行时离线可用，避免 Space 启动时联网拉模型（HF_HUB_OFFLINE=1）；
# 3. SQLite 写入 /data 卷（HF Space 持久存储挂载点）；
#    未挂载时回落容器内临时路径（功能完整，重启丢数据）。
# 4. HF Spaces 约定监听 7860 端口。

FROM python:3.12-slim

WORKDIR /app

# 系统依赖：libgomp（numpy/torch OpenMP 需要）
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（利用 Docker 层缓存：代码变化不重装依赖）
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# 构建期预下载嵌入模型（~90MB），烘焏进镜像层
ENV HF_HOME=/app/.hf_cache \
    SENTENCE_TRANSFORMERS_HOME=/app/.hf_cache/sentence_transformers
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# 应用代码
COPY app ./app
COPY run.py .

# 运行时：离线用缓存模型；SQLite 指向 /data 持久卷（HF Spaces 挂载）
ENV HF_HUB_OFFLINE=1 \
    HANGYOU_DB_PATH=/data/hangyou.db \
    HANGYOU_UPLOAD_DIR=/data/uploads \
    PORT=7860

# /data 由 HF Spaces 挂载；本地 docker run 可 -v hangyou_data:/data
VOLUME ["/data"]

EXPOSE 7860

# uvicorn 直接监听（run.py 读 PORT 环境变量）
CMD ["python", "run.py"]
