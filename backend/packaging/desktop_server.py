"""Windows 桌面端后端启动入口。

由 Electron 启动，而不是由用户手动运行。运行时数据目录和监听地址通过
HANGYOU_DATA_DIR / HANGYOU_HOST 注入，避免安装目录权限和跨设备联调问题。
"""

import uvicorn

from app.config import settings
from app.main import app


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port, reload=False)
