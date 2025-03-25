import express, { Request, Response, Router } from "express";
import { randomUUID as nanoid } from "node:crypto";
import { McpServer,  } from "@modelcontextprotocol/sdk/server/mcp.js";
import { ServerOptions } from "@modelcontextprotocol/sdk/server/index.js";
import { ErrorCode, Implementation, JSONRPCRequest } from "@modelcontextprotocol/sdk/types.js";
import { RequestHandlerExtra } from "@modelcontextprotocol/sdk/shared/protocol.js";


type HTTMCPImplementation = Implementation & {
    publishServer?: string;
    apiPrefix?: string;
};

export class HTTMCP extends McpServer {
    private name: string = "httmcp";
    private publishServer?: string;
    private apiPrefix: string;

    constructor(serverInfo: HTTMCPImplementation, options?: ServerOptions) {
        const { publishServer, apiPrefix, ...restServerInfo } = serverInfo;
        super(restServerInfo, options);
        this.name = serverInfo.name;
        this.publishServer = publishServer;
        this.apiPrefix = apiPrefix || "";
    }

    async publishToChannel(channelId: string, message: any, event: string = "message"): Promise<boolean> {
        try {
            if (!this.publishServer) {
                console.error("Publish server not configured");
                return false;
            }

            const data = typeof message === 'object' ? JSON.stringify(message) : message;
            
            const response = await fetch(`${this.publishServer}/mcp/${this.name}/${channelId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-EventSource-Event': event
                },
                body: data
            });
            
            return response.status === 200;
        } catch (e) {
            console.error(`Error publishing to channel: ${e}`);
            return false;
        }
    }

    Router(): Router {
        const router = express.Router();
        router.use(express.json()); // for parsing application/json
        const prefix = this.apiPrefix || `/mcp/${this.name}`;
        
        // Session start endpoint
        router.get("/", (_: Request, res: Response) => {
            const sessionId = nanoid();
            res.setHeader('X-Accel-Redirect', `/internal/${this.name}/${sessionId}`);
            res.setHeader('X-Accel-Buffering', 'no');
            res.status(200).end();
        });

        // Endpoint info
        router.get("/endpoint", async (req: Request, res: Response) => {
            const sessionId = req.header('X-MCP-Session-ID');
            const transport = req.header('X-MCP-Transport');
            
            if (transport === "sse" && sessionId) {
                await this.publishToChannel(
                    sessionId, 
                    `${prefix}/${sessionId}`, 
                    "endpoint"
                );
            }
            res.status(200).end();
        });

        // MCP protocol endpoints - These match what's in the Python implementation
        router.post("/initialize", this.handleMcpRequest.bind(this));
        router.post("/resources/list", this.handleMcpRequest.bind(this));
        router.post("/resources/read", this.handleMcpRequest.bind(this));
        router.post("/prompts/list", this.handleMcpRequest.bind(this));
        router.post("/prompts/get", this.handleMcpRequest.bind(this));
        router.post("/resources/templates/list", this.handleMcpRequest.bind(this));
        router.post("/tools/list", this.handleMcpRequest.bind(this));
        router.post("/tools/call", this.handleMcpRequest.bind(this));
        router.post("/ping", this.handleEmptyResponse.bind(this));
        router.post("/notifications/initialized", this.handleEmptyResponse.bind(this));
        router.post("/notifications/cancelled", this.handleEmptyResponse.bind(this));

        return router;
    }

    private _onrequest(request: JSONRPCRequest): Promise<any> {
        // @ts-ignore
        const handler = this.server._requestHandlers.get(request.method) ?? this.server.fallbackRequestHandler;
    
        const abortController = new AbortController();
        // @ts-ignore  // skip canceling request
        // this.server._requestHandlerAbortControllers.set(request.id, abortController);

        // Create extra object with both abort signal and sessionId from transport
        const extra: RequestHandlerExtra = {
          signal: abortController.signal,
          sessionId: request.params?._meta?.sessionId as string,
        };
    
        // Starting with Promise.resolve() puts any synchronous errors into the monad as well.
        return Promise.resolve()
          .then(() => {
            if (handler === undefined) {
              return Promise.reject({
                code: ErrorCode.MethodNotFound,
                message: "Method not found",
              });
            }
            return handler(request, extra)
        })
          .then(
            (result) => ({ result }),
            (error) => ({ error: {
                code: Number.isSafeInteger(error["code"])
                    ? error["code"]
                    : ErrorCode.InternalError,
                message: error.message ?? "Internal error",
              }
            })
          )
          .then(res => {
            if (abortController.signal.aborted) {
              throw new Error("Request was aborted");
            }
            return {
              jsonrpc: "2.0",
              id: request.id,
              result: (res as any)?.result,
              error: (res as any)?.error,
            };
          })
          .finally(() => {
            // this.server._requestHandlerAbortControllers.delete(request.id);
          });
      }

    private async handleMcpRequest(req: Request, res: Response): Promise<void> {
        try {
            const sessionId = req.header('X-MCP-Session-ID');
            const request = req.body as JSONRPCRequest;
            if (request.params?._meta) {
                request.params._meta.sessionId = sessionId
            }
            // @ts-ignore
            const response = await this._onrequest(request);
            res.status(200).json(response);
        } catch (error) {
            console.error(`Error handling MCP request: ${error}`);
            res.status(200).json({
                jsonrpc: "2.0", 
                id: req.body?.id || null,
                error: {
                    code: 0,
                    message: `Internal server error: ${error}`
                }
            });
        }
    }
    
    private async handleEmptyResponse(req: Request, res: Response): Promise<void> {
        res.status(200).json({
            jsonrpc: "2.0",
            id: req.body?.id || "",
            result: {}
        });
    }
}

export default HTTMCP;