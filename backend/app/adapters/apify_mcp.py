import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ACTOR = "compass/crawler-google-places"
MCP_URL = "https://mcp.apify.com?tools=call-actor,get-dataset-items"
MAX_RUN_CHARGE_USD = 0.50  # Minimum accepted cap for this pay-per-event Actor.


class ApifyVenueLookup:
    def __init__(self, token: str):
        self._token = token
        self._cache: dict[tuple[str, str], str] = {}

    async def category(self, location: str, city: str) -> str | None:
        key = (location.casefold().strip(), city.casefold().strip())
        if key in self._cache:
            return self._cache[key]
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {self._token}"}, timeout=22) as http:
            async with streamable_http_client(MCP_URL, http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    names = {tool.name for tool in (await session.list_tools()).tools}
                    if not {"call-actor", "get-dataset-items"} <= names:
                        raise RuntimeError("Expected Apify tools are unavailable")
                    run = await session.call_tool("call-actor", {
                        "actor": ACTOR,
                        "input": {"searchStringsArray": [location], "locationQuery": city,
                                  "maxCrawledPlacesPerSearch": 1, "language": "en"},
                        "callOptions": {"timeout": 30, "maxTotalChargeUsd": MAX_RUN_CHARGE_USD},
                        "waitSecs": 20,
                    })
                    run_data = run.structuredContent or {}
                    if run.isError or run_data.get("status") != "SUCCEEDED":
                        return None
                    dataset_id = run_data["storages"]["datasets"]["default"]["id"]
                    result = await session.call_tool("get-dataset-items", {
                        "datasetId": dataset_id, "limit": 1, "fields": "categoryName", "clean": True,
                    })
                    rows = (result.structuredContent or {}).get("items") or []
                    if result.isError or not rows or not rows[0].get("categoryName"):
                        return None
                    category = str(rows[0]["categoryName"])
        if len(self._cache) >= 128:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = category
        return category
