import logging
from datetime import date
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ToolAnnotations

from .ports import CalendarProvider, HourlyWeatherProvider
from .services.outfits import OutfitService
from .services.wardrobe import summarise

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
CONTEXT_TOOLS = ("get_wardrobe", "get_calendar_events", "get_weather", "get_recent_outfits", "get_commute")
log = logging.getLogger(__name__)


async def read_outfit_tools(server: FastMCP) -> dict:
    results = {}
    async with create_connected_server_and_client_session(server) as session:
        async def read(name: str) -> None:
            try:
                with anyio.fail_after(12):
                    result = await session.call_tool(name)
                if not result.isError:
                    results[name] = result.structuredContent or {}
            except TimeoutError:
                log.warning("Outfit context tool timed out: %s", name)

        async with anyio.create_task_group() as tasks:
            available = {tool.name for tool in (await session.list_tools()).tools}
            for name in CONTEXT_TOOLS:
                if name in available:
                    tasks.start_soon(read, name)
    return results


def outfit_mcp(
    outfits: OutfitService, uid: str, user: dict, day: date, timezone: str,
    calendar: CalendarProvider | None, weather: HourlyWeatherProvider | None,
) -> FastMCP:
    """The internal MCP session is scoped to the request's user, city, and local date."""
    server = FastMCP("Good Enough outfit context")

    @server.tool(annotations=READ_ONLY)
    async def get_calendar_events() -> dict[str, Any]:
        """Read today's timed calendar events. Use title, location, and start time to infer the occasion."""
        if calendar is None:
            return {"events": None}
        events = await anyio.to_thread.run_sync(calendar.events, uid, day, timezone, abandon_on_cancel=True)
        return {"events": events}

    @server.tool(annotations=READ_ONLY)
    async def get_weather() -> dict[str, Any]:
        """Read hourly temperatures, feels-like temperatures, and precipitation probability (0 to 1)."""
        if weather is None:
            return {}
        return await anyio.to_thread.run_sync(weather.hourly, user["city"], day, timezone, abandon_on_cancel=True)

    @server.tool(annotations=READ_ONLY)
    async def get_wardrobe() -> dict[str, Any]:
        """List the user's owned, available clothes. Choose outfit item IDs from this list."""
        items = await anyio.to_thread.run_sync(outfits.available, uid, abandon_on_cancel=True)
        return {"items": summarise(items)}

    @server.tool(annotations=READ_ONLY)
    async def get_recent_outfits() -> dict[str, Any]:
        """Read item IDs from the user's three latest outfits to avoid repeating combinations."""
        ids = await anyio.to_thread.run_sync(outfits.recent, uid, abandon_on_cancel=True)
        return {"item_ids": ids}

    @server.tool(annotations=READ_ONLY)
    def get_commute() -> dict[str, Any]:
        """Read the user's usual transport mode. Use it to decide how practical the outfit should be."""
        mode = (user.get("fit_prefs") or {}).get("commute_mode")
        return {"mode": mode if mode in ("metro", "bike", "walk", "car") else None}

    return server
