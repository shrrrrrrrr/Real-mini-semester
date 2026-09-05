---
title: 航友 API
emoji: 📚
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# 航友后端服务（HF Space · Docker）

「航友」= 面向大学生的课程资料智能问答与复习系统。本 Space 承载 FastAPI 后端：
多格式资料解析、BM25+向量+RRF 混合检索、双层 RAG 问答、测验生成、FSRS 复习调度。

## 运行时配置（Space Settings → Variables and secrets）

| 变量 | 说明 |
|---|---|
| `LLM_BASE_URL` | OpenAI 兼容接口，如 `https://api.deepseek.com/v1` |
| `LLM_API_KEY` | 供应商 Key（建议放 Secrets） |
| `LLM_MODEL` | 模型名，如 `deepseek-chat` |
| `EXTRA_CORS_ORIGINS` | 前端域名白名单（逗号分隔），如 `https://hangyou.vercel.app` |

## 持久化

- `/data` 挂 HF Space 持久存储（SQLite + 上传原件）；未挂载时数据在容器内（重启丢失）。
- 嵌入模型（MiniLM 90MB）已烘焏进镜像，运行离线加载。

## 健康检查

`GET /api/health` → `{"ok": true, "llm_configured": ...}`
