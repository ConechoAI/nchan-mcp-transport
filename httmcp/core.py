import base64
import logging
import json
import uuid
from typing import Any
from fastapi import FastAPI, Header, Response
from mcp.types import *
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.server import _convert_to_content
from mcp.server.lowlevel.server import request_ctx, RequestContext
import httpx
from fastapi.routing import APIRouter
from openapiclient import OpenAPIClient


logger = logging.getLogger(__name__)



class HTTMCP(FastMCP):

    def __init__(
        self, name: str | None = None,
        instructions: str | None = None,
        publish_server: str | None = None,
        api_prefix: str = "",
        **settings: Any
    ):
        self._publish_server = publish_server
        self.api_prefix = api_prefix
        super().__init__(name, instructions, **settings)

    async def publish_to_channel(self, channel_id: str, message: dict, event: str = "message") -> bool:
        """Publish a message to an nchan channel."""
        async with httpx.AsyncClient() as client:
            # In a real scenario, you'd need the actual URL of your nchan server
            headers = {
                "Content-Type": "application/json",
                "X-EventSource-Event": event,
            }
            try:
                data = message
                if isinstance(message, dict):
                    data = json.dumps(message)
                elif isinstance(message, BaseModel):
                    data = message.model_dump_json()
                response = await client.post(
                    f"{self._publish_server}/mcp/{self.name}/{channel_id}", 
                    data=data,
                    headers=headers
                )
                return response.status_code == 200
            except Exception as e:
                logger.error(f"Error publishing to channel: {str(e)}")
                return False

    @property
    def router(self) -> APIRouter:
        router = APIRouter(prefix=self.api_prefix if self.api_prefix else f"/mcp/{self.name}")
        router.add_api_route("/", self.start_session, methods=["GET"])
        router.add_api_route("/endpoint", self.send_endpoint, methods=["GET"])
        router.add_api_route("/initialize", self.wrap_method(self.initialize), methods=["POST"])
        router.add_api_route("/resources/list", self.wrap_method(self.list_resources_handler), methods=["POST"])
        router.add_api_route("/resources/read", self.wrap_method(self.read_resource_handler), methods=["POST"])
        router.add_api_route("/prompts/list", self.wrap_method(self.list_prompts_handler), methods=["POST"])
        router.add_api_route("/prompts/get", self.wrap_method(self.get_prompt_handler), methods=["POST"])
        router.add_api_route("/resources/templates/list", self.wrap_method(self.list_resource_templates_handler), methods=["POST"])
        router.add_api_route("/tools/list", self.wrap_method(self.list_tools_handler), methods=["POST"])
        router.add_api_route("/tools/call", self.wrap_method(self.call_tools_handler), methods=["POST"])
        # empty response
        async def empty_response(message: JSONRPCMessage, **kwargs): 
            return ServerResult(EmptyResult())
        router.add_api_route("/ping", self.wrap_method(empty_response), methods=["POST"])
        router.add_api_route("/notifications/initialized", self.wrap_method(empty_response), methods=["POST"])
        router.add_api_route("/notifications/cancelled", self.wrap_method(empty_response), methods=["POST"])
        return router

    def wrap_method(self, method):
        async def wrapper(
            message: JSONRPCMessage,
            x_mcp_session_id: Annotated[str | None, Header()] = None,
            x_mcp_transport: Annotated[str | None, Header()] = None,
        ):
            requst_id = message.root.id if hasattr(message.root, "id") else None
            try:
                result = await method(message, session_id=x_mcp_session_id, transport=x_mcp_transport)
                if isinstance(result, Response):
                    return result
                try:
                    result = result.model_dump(exclude_unset=True, exclude_none=True, by_alias=True)
                except Exception as e:
                    pass
                response = JSONRPCResponse(id=requst_id or "", jsonrpc=message.root.jsonrpc, result=result)
            except Exception as e:
                logger.exception(e)
                logger.error(f"Error processing request {message}: {str(e)}")
                response = JSONRPCError(id=requst_id, error=ErrorData(code=0, message=str(e)))
            return Response(
                content=response.model_dump_json(),
                media_type="application/json",
                status_code=200,
            )
        return wrapper

    async def initialize(self, message: JSONRPCMessage, **kwargs) -> InitializeResult:
        """Initialize the MCP server."""
        options = self._mcp_server.create_initialization_options()
        return InitializeResult(
            protocolVersion=LATEST_PROTOCOL_VERSION,
            capabilities=options.capabilities,
            serverInfo=Implementation(
                name=options.server_name,
                version=options.server_version,
            ),
            instructions=options.instructions,
        )

    async def start_session(self):
        session_id = str(uuid.uuid4())
        return Response(
            status_code=200,
            headers={
                "X-Accel-Redirect": f"/internal/{self.name}/{session_id}",
                "X-Accel-Buffering": "no"
            }
        )
    
    async def send_endpoint(
        self, x_mcp_session_id: Annotated[str | None, Header()] = None,
        x_mcp_transport: Annotated[str | None, Header()] = None,
    ):
        if x_mcp_transport == "sse":
            await self.publish_to_channel(x_mcp_session_id, f"/mcp/{self.name}/{x_mcp_session_id}", "endpoint")

    async def list_resources_handler(self, message: JSONRPCMessage, **kwargs) -> ListResourcesResult:
        resources = await super().list_resources()
        return ListResourcesResult(resources=resources)
    
    async def read_resource_handler(self, message: JSONRPCMessage, **kwargs) -> ReadResourceResult:
        uri = message.root.params.get("uri")
        data = await super().read_resource(uri)

        return ReadResourceResult(contents=[TextResourceContents(
            uri=uri,
            mimeType=c.mime_type or "text/plain",
            text=c.content,
        ) if isinstance(c.content, str) else BlobResourceContents(
            uri=uri,
            mimeType=c.mime_type or "application/octet-stream",
            blob=base64.urlsafe_b64encode(c.content).decode(),
        ) for c in data])

    async def list_prompts_handler(self, message: JSONRPCMessage, **kwargs) -> ListPromptsResult:
        prompts = await super().list_prompts()
        return ListPromptsResult(prompts=prompts)

    async def get_prompt_handler(self, message: JSONRPCMessage, **kwargs) -> GetPromptResult:
        return await super().get_prompt(message.root.method, message.root.params)

    async def list_resource_templates_handler(self, message: JSONRPCMessage, **kwargs) -> ListResourceTemplatesResult:
        templates = await super().list_resource_templates()
        return ListResourceTemplatesResult(resourceTemplates=templates)

    async def list_tools_handler(self, message: JSONRPCMessage, **kwargs) -> ListToolsResult:
        tools = await super().list_tools()
        return ListToolsResult(tools=tools)

    async def call_tools_handler(self, message: JSONRPCMessage, **kwargs) -> CallToolResult:
        content, isError = [], False
        token = None
        try:
            validated_request = ClientRequest.model_validate(
                message.root.model_dump(
                    by_alias=True, mode="json", exclude_none=True
                )
            )
            # Set our global state that can be retrieved via
            # app.get_request_context()
            meta = validated_request.root.params.meta if validated_request.root.params else None
            # store session_id in meta
            if meta:
                meta.session_id = kwargs.get("session_id")
            token = request_ctx.set(
                RequestContext(
                    message.root.id,
                    meta,
                    None,
                    None,
                )
            )
            name, arguments = message.root.params.get('name', ''), message.root.params.get('arguments', {})
            context = self.get_context()
            result = await self.call_tool_with_context(name, arguments, context=context)
            if isinstance(result, Response):
                return result
            content = _convert_to_content(result)
            # response = await handler(req)
        except Exception as err:
            isError = True
            logger.error(f"Error calling tool: {str(err)}")
        finally:
            # Reset the global state after we are done
            if token is not None:
                request_ctx.reset(token)
        return CallToolResult(content=list(content), isError=isError)

    async def call_tool_with_context(self, name: str, arguments: dict, context: Context) -> Any:
        return await self._tool_manager.call_tool(name, arguments, context=context)


class OpenAPIMCP(HTTMCP):
    def __init__(
        self, api: OpenAPIClient, client: Any,
        name: str | None = None,
        publish_server: str | None = None,
        api_prefix: str = "",
        **settings: Any,
    ):
        self.api = api
        self.client = client
        instructions = api.definition.get('info', {}).get('description', '')
        if not name:
            api_title = api.definition.get('info', {}).get('title', '')
            api_version = api.definition.get('info', {}).get('version', '')
            name = f"{api_title}MCP_{api_version}" if api_version else f"{api_title}"
            # Replace spaces, hyphens, dots and other special characters
            name = ''.join(c for c in name if c.isalnum())
        super().__init__(name, instructions, publish_server, api_prefix, **settings)

    async def list_tools_handler(self, message, **kwargs):  # type: ignore
        return ListToolsResult(tools=[Tool(
            name=tool["function"].get('name', ''),
            description=tool["function"].get('description', ''),
            inputSchema=tool["function"].get('parameters', {}),
        ) for tool in self.client.tools])

    async def call_tool_with_context(self, name: str, arguments: dict, context: Context) -> Any:
        # ignore context
        return await self.client(name, **arguments)

    @classmethod
    async def from_openapi(cls, definition: str, name: str | None = None, publish_server: str | None = None, **kwargs) -> "OpenAPIMCP":
        """
        Create an MCP server from an OpenAPI definition.

        :param definition: The OpenAPI definition as a string.
        :param name: The name of the MCP server.
        :param publish_server: The URL of the Nchan server for publishing messages.
        :param kwargs: Additional settings for the MCP server (passed to httox.AsyncClient).
        :return: An instance of OpenAPIMCP.
        """
        api = OpenAPIClient(definition=definition)
        # pass the timeout, proxies, etc. to the client
        client = await api.AsyncClient(**kwargs).__aenter__()  # type: ignore
        return cls(api, client, name=name, publish_server=publish_server)