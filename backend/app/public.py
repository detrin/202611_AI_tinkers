"""Public entrypoint: the same API served under /api (https://goodenough.hermandaniel.com/api).

The Cloudflare tunnel forwards /api/... unchanged (it can't rewrite paths), so instead of a proxy-stripped
prefix we set the ASGI root_path for those requests. Starlette then routes /api/health as /health and FastAPI
builds docs/openapi URLs under /api. Unprefixed paths still work, so local tools hitting /health are fine.

Run: uv run uvicorn backend.app.public:app --port 8000
"""
from .main import create_app

PREFIX = "/api"
api = create_app()


async def app(scope, receive, send):
    if scope["type"] in ("http", "websocket"):
        path = scope["path"]
        if path == PREFIX or path.startswith(PREFIX + "/"):
            scope = {**scope, "root_path": scope.get("root_path", "") + PREFIX}
    await api(scope, receive, send)
