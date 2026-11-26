"""把店铺接口、网页接口、对话转发和静态页面拼成一个服务。"""

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from demo_shop import relay, settings, shop_api, site

WEB = settings.ROOT / "web"

app = FastAPI(title="模拟店铺")
for module in (shop_api, site, relay):
    app.include_router(module.router)


@app.exception_handler(httpx.TransportError)
def agent_unreachable(request: Request, error: httpx.TransportError) -> JSONResponse:
    return JSONResponse({"detail": "客服服务暂时连不上"}, status_code=503)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


class Revalidated(StaticFiles):
    """每次都让浏览器先问一下文件变了没有（ETag），没变回 304。聊天窗更新后买家马上用上新的，不用改文件名。"""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/web", Revalidated(directory=WEB), name="web")
app.mount("/widget", Revalidated(directory=settings.WIDGET_DIR, check_dir=False), name="widget")
