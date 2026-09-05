"""启动脚本：python run.py（开发模式热重载）。

热重载原理：uvicorn --reload 监听源码变化自动重启 worker。
注意：改完代码若行为未变，先删 __pycache__（Windows 上偶发旧字节码）。
"""

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,  # 开发时可改 True；生产/联调稳定用 False
    )
