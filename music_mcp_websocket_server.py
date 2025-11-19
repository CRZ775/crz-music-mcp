# -------------- 新增：aiohttp 统一入口 --------------
from aiohttp import web, WSMsgType

async def websocket_handler(request: web.Request):
    """处理 WebSocket 连接"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            await server.handle_message(ws, msg.data)
        elif msg.type == WSMsgType.ERROR:
            logger.error("WebSocket error: %s", ws.exception())

    return ws

async def health(_: web.Request):
    """Render 健康检查"""
    return web.Response(text="OK")

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/ws", websocket_handler)  # WebSocket 入口
    app.router.add_get("/", health)               # 健康检查
    app.router.add_head("/", health)              # Render 用 HEAD 探活
    return app

# -------------- 替换原来的 main() --------------
async def main():
    # 1. 注册工具（完全沿用你已有代码）
    server.add_resource("music://current_playlist", "当前播放列表", "")
    server.add_resource("music://current_playing", "当前播放", "")

    server.add_tool("search_music", "搜索音乐", {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50}
        },
        "required": ["query"]
    }, search_music_handler)

    server.add_tool("play_music", "播放音乐", {
        "type": "object",
        "properties": {
            "song_id": {"type": "string"},
            "song_name": {"type": "string"},
            "artist": {"type": "string"}
        },
        "required": ["song_id"]
    }, play_music_handler)

    server.add_tool("pause_music", "暂停音乐", {"type": "object"}, pause_music_handler)
    server.add_tool("resume_music", "继续播放", {"type": "object"}, resume_music_handler)
    server.add_tool("stop_music", "停止音乐", {"type": "object"}, stop_music_handler)
    server.add_tool("set_volume", "设置音量", {
        "type": "object",
        "properties": {"volume": {"type": "integer", "minimum": 0, "maximum": 100}},
        "required": ["volume"]
    }, set_volume_handler)
    server.add_tool("add_to_playlist", "添加到播放列表", {
        "type": "object",
        "properties": {
            "song_id": {"type": "string"},
            "song_name": {"type": "string"},
            "artist": {"type": "string"}
        },
        "required": ["song_id"]
    }, add_to_playlist_handler)
    server.add_tool("get_playlist", "获取播放列表", {"type": "object"}, get_playlist_handler)
    server.add_tool("clear_playlist", "清空播放列表", {"type": "object"}, clear_playlist_handler)
    server.add_tool("next_song", "下一首", {"type": "object"}, next_song_handler)
    server.add_tool("previous_song", "上一首", {"type": "object"}, previous_song_handler)

    # 2. 启动 aiohttp
    port = int(os.getenv("PORT", 10000))
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Listening on http://0.0.0.0:%s  (WebSocket: ws://0.0.0.0:%s/ws)", port, port)

    # 3. 永久挂起
    await asyncio.Event().wait()

# -------------- 入口不变 --------------
if __name__ == "__main__":
    asyncio.run(main())
