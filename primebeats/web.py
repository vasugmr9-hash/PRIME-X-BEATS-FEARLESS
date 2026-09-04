from aiohttp import web

async def health(request):
    bot = request.app.get("bot")
    return web.json_response({
        "status": "ok",
        "service": "prime-x-beats",
        "bot": bool(bot and bot.running),
    })

async def root(request):
    return web.Response(text="⚝ PRIME × BEATS ULTRA • ONLINE")

async def start_web(port: int, bot):
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/", root)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner
    
