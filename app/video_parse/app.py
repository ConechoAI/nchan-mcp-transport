import logging
import asyncio
import json
import os
from mcp.server.fastmcp import Context
from mcp.types import *
from fastapi import FastAPI, Response
from httmcp import HTTMCP
from app.core.utils import fetchUserInfo, addCount, fetchRequest
from dotenv import load_dotenv
import nest_asyncio
nest_asyncio.apply()


# 加载 .env 文件
load_dotenv()

# 读取环境变量
api_key = os.getenv("API_KEY", "")
api_base = os.getenv("API_BASE", "")
if not api_key:
    raise ValueError("API_KEY environment variable is required")
if not api_base:
    raise ValueError("API_BASE environment variable is required")


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
publish_server = "http://nchan:80"

app = FastAPI()
server = HTTMCP(
    "videoparse",
    publish_server=publish_server,
)


async def json_response(request_id, session_id, message):
    await server.publish_to_channel(session_id, JSONRPCResponse(
        jsonrpc="2.0",
        id=request_id,
        result=CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=message
                )
            ],
        ).model_dump(),
    ).model_dump_json(by_alias=True, exclude_none=True))


@server.tool()
async def long_task(video_url: str, ctx: Context) -> bool | None:
    async def task():
        # 可以通过 ctx.request_context.meta 获取请求token
        request_id = ctx.request_context.request_id
        session_id = ctx.request_context.meta.session_id
        try:
            token = ctx.request_context.meta.token
            if not token:
                await json_response(request_id, session_id, "Token not found. You must log in the app:Conecho.")
                return
            logger.info(f"JWT Token: {token}")
            userInfo, err = await fetchUserInfo(token)
            logger.info(f"userInfo: {userInfo}")

            if err:
                await json_response(request_id, session_id, "Auth failed.")
                return
            else:
                call_limit = userInfo["data"]["extra"]["call_limit"]
                if call_limit <= 0:
                    await json_response(request_id, session_id, "Reach the limit.")
                    return
                else:
                    res = await addCount(token)
                    logger.info(f"addCount: {res}")

            if not video_url:
                raise ValueError("Missing video_url parameter")

            data = {
                "formItemParams": {
                    "url": [
                        {"type": "url", "text": f"{video_url}", "link": f"{video_url}"}]
                },
                "context": {
                    "logID": "",
                    "timeZone": "Asia/Shanghai",
                    "baseID": "",
                    "tableID": "",
                    "bitable": {"logID": "", "timeZone": "Asia/Shanghai", "baseID": "", "tableID": ""},
                    "tenantKey": "145916e72a9f5740",
                    "userID": "",
                    "packID": "",
                    "extensionID": "",
                    "baseSignature": ""
                }
            }

            result = await fetchRequest(api_base, headers={"Authorization": f"Bearer {api_key}"}, data=data, timeout=60)
            await json_response(request_id, session_id, json.dumps(result.get("data", {}), ensure_ascii=False))
            return
        except Exception as e:
            await json_response(request_id, session_id, f'Video Parse error: {str(e)}')
            return

    asyncio.gather(task())
    # skip message and send result by using
    return Response(status_code=204)


logger.debug("Server started %r", server.router.routes)
app.include_router(server.router)


if __name__ == "__main__":
    import uvicorn
    from mcp.server.fastmcp.server import Settings
    settings = Settings()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
