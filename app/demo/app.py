import logging
import asyncio
from mcp.server.fastmcp import Context
from mcp.types import *
from fastapi import FastAPI, Response
from httmcp import HTTMCP, OpenAPIMCP
import nest_asyncio
nest_asyncio.apply()

logger = logging.getLogger(__name__)
publish_server = "http://nchan:80"

app = FastAPI()
server = HTTMCP(
    "httmcp",
    publish_server=publish_server,
)

@server.tool()
async def hello_world() -> str:
    return "Hello, world!"

@server.tool()
async def add(a: int, b: int) -> int:
    return a + b

@server.tool()
async def long_task(t: int, ctx: Context) -> bool | None:
    async def task():
        await asyncio.sleep(t)
        request_id = ctx.request_context.request_id
        session_id = ctx.request_context.meta.session_id
        logger.info(f"Task completed for session {session_id}")
        await server.publish_to_channel(session_id, JSONRPCResponse(
            jsonrpc="2.0",
            id=request_id,
            result=CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"sleep {t} Task completed"
                    )
                ],
            ).model_dump(),
        ).model_dump_json(by_alias=True, exclude_none=True))
        # logger.error("ctx %r", (ctx.client_id, ctx.request_context))
    asyncio.gather(task())
    # skip message and send result by using
    return Response(status_code=204)

@server.resource("resource://my-resource")
def get_data() -> str:
    return "Hello, world!"


logger.debug("Server started %r", server.router.routes)
app.include_router(server.router)

# can add more mcp servers here
# app.include_router(server2.router)

async def create_openapi_mcp_server():
    url = "https://ghfast.top/https://raw.githubusercontent.com/lloydzhou/openapiclient/refs/heads/main/examples/jinareader.json"
    server1 = await OpenAPIMCP.from_openapi(url, name="jinareader", publish_server=publish_server)
    logger.info("Server1 started %r", server1.router.routes)
    app.include_router(server1.router)

    url = "https://ghfast.top/https://raw.githubusercontent.com/APIs-guru/openapi-directory/refs/heads/main/APIs/notion.com/1.0.0/openapi.yaml"
    server2 = await OpenAPIMCP.from_openapi(
        url,
        name="notion",
        publish_server=publish_server,
        headers={"Authorization": "Bearer your_token"},
    )
    logger.info("Server2 started %r", server2.router.routes)
    app.include_router(server2.router)

    # create a custom OpenAPIMCP with user_api_key
    from openapiclient import OpenAPIClient
    class NotionAPI(OpenAPIMCP):
        def __init__(self, api: OpenAPIClient, name: str | None = None, publish_server: str | None = None, api_prefix: str = "", **settings: Any):
            client = api.Client().__enter__()
            super().__init__(api, client, name, publish_server, api_prefix, **settings)

        async def call_tool_with_context(self, name, arguments, context):
            # get user api key from context
            # context.client_id
            session_id = context.request_context.meta.session_id
            api_key = "" # get api key from session_id
            async with self.api.AsyncClient(headers={"Authorization": f"Bearer {api_key}"}) as client:
                return await client(name, arguments)

    api = OpenAPIClient(
        definition="https://ghfast.top/https://raw.githubusercontent.com/APIs-guru/openapi-directory/refs/heads/main/APIs/notion.com/1.0.0/openapi.yaml"
    )
    server3 = NotionAPI(api, name="notion_user", publish_server=publish_server)
    logger.info("Server3 started %r", server3.router.routes)
    app.include_router(server3.router)


asyncio.run(create_openapi_mcp_server())

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
