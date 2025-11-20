#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
免费音乐MCP WebSocket服务器
为小智AI音响提供音乐控制服务 - WebSocket版本
"""

import asyncio, io, os, logging, json, socket
from aiohttp import web, WSMsgType   
import  re,  websockets
from typing import Dict, Any, List
from datetime import datetime
from websockets import serve as ws_serve
from websockets.exceptions import ConnectionClosed
# 顶部导入补充
from websockets.asyncio.server import ServerConnection
# 15 专用

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("music-mcp")

# 新增：aiohttp 统一入口 
async def websocket_handler(request: web.Request):
    """aiohttp 接管 WebSocket"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            await server.handle_message(ws, msg.data)
        elif msg.type == WSMsgType.ERROR:
            logger.error("WebSocket error: %s", ws.exception())

    return ws

async def health(_: web.Request):
    """Render 健康检查（HEAD/GET 均可）"""
    return web.Response(text="OK")

def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/ws", websocket_handler)  # WebSocket 入口
    app.router.add_get("/", health)               # GET + HEAD 探活（HEAD 由 aiohttp 自动处理）
    # app.router.add_head("/", health)            # ← 删除这一行
    return app
    
# 播放状态管理
playback_state = {
    "is_playing": False,
    "current_song": None,
    "volume": 50,
    "position": 0,
    "playlist": []
}

# 模拟音乐数据库
MOCK_MUSIC_DATABASE = [
    {"id": "1", "name": "青花瓷", "artist": "周杰伦", "album": "我很忙", "duration": 238},
    {"id": "2", "name": "稻香", "artist": "周杰伦", "album": "魔杰座", "duration": 223},
    {"id": "3", "name": "夜曲", "artist": "周杰伦", "album": "十一月的萧邦", "duration": 237},
    {"id": "4", "name": "告白气球", "artist": "周杰伦", "album": "周杰伦的床边故事", "duration": 207},
    {"id": "5", "name": "晴天", "artist": "周杰伦", "album": "叶惠美", "duration": 269},
    {"id": "6", "name": "演员", "artist": "薛之谦", "album": "绅士", "duration": 253},
    {"id": "7", "name": "体面", "artist": "于文文", "album": "体面", "duration": 247},
    {"id": "8", "name": "成都", "artist": "赵雷", "album": "无法长大", "duration": 327},
    {"id": "9", "name": "南山南", "artist": "马頔", "album": "孤岛", "duration": 293},
    {"id": "10", "name": "理想", "artist": "赵雷", "album": "吉姆餐厅", "duration": 279}
]

class MCPWebSocketServer:
    """MCP WebSocket服务器"""
    
    def __init__(self):
        self.tools = {}
        self.resources = {}
        
    def add_tool(self, name: str, description: str, input_schema: Dict[str, Any], handler):
        """添加工具"""
        self.tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "handler": handler
        }
        
    def add_resource(self, uri: str, name: str, description: str = ""):
        """添加资源"""
        self.resources[uri] = {
            "uri": uri,
            "name": name,
            "description": description
        }
    
    async def handle_message(self, websocket, message: str):
        """处理WebSocket消息（aiohttp版）"""
        if not message or not message.strip():          # ① 空消息直接丢
            logger.warning("收到空消息，忽略")
            return
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            logger.error("JSON解析错误: %s", e)
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            await websocket.send_str(json.dumps(err))   # ② 用 send_str
            return

        try:
            method = data.get("method")
            msg_id = data.get("id")
            params = data.get("params", {})
            logger.info("收到消息: %s", method)

            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {"listChanged": True},
                            "resources": {"subscribe": True, "listChanged": True}
                        },
                        "serverInfo": {"name": "music-mcp-server", "version": "1.0.0"}
                    }
                }
            elif method == "tools/list":
                tools = [{"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
                         for t in self.tools.values()]
                resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}}
            elif method == "resources/list":
                resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"resources": list(self.resources.values())}}
            else:
                resp = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}

            await websocket.send_str(json.dumps(resp))      # ③ 统一 send_str

        except Exception as e:
            logger.exception("处理消息异常")
            err = {"jsonrpc": "2.0", "id": data.get("id"), "error": {"code": -32603, "message": f"Internal error: {str(e)}"}}
            await websocket.send_str(json.dumps(err))       # ④ 统一 send_str
    
    async def get_resource_content(self, uri: str) -> str:
        """获取资源内容"""
        if uri == "music://current_playlist":
            playlist = playback_state["playlist"]
            if not playlist:
                return "播放列表为空"
            
            content = "当前播放列表:\n\n"
            for i, song in enumerate(playlist, 1):
                content += f"{i}. {song['name']} - {song['artist']}\n"
            return content
            
        elif uri == "music://current_playing":
            current = playback_state["current_song"]
            if not current:
                return "当前没有播放歌曲"
            
            status = "播放中" if playback_state["is_playing"] else "已暂停"
            return f"当前播放: {current['name']} - {current['artist']}\n状态: {status}\n音量: {playback_state['volume']}%"
            
        return "未知资源"

# 音乐搜索API
async def search_music_api(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """搜索音乐API"""
    # 模拟搜索延迟
    await asyncio.sleep(0.1)
    
    # 简单的关键词匹配
    results = []
    query_lower = query.lower()
    
    for song in MOCK_MUSIC_DATABASE:
        if (query_lower in song["name"].lower() or 
            query_lower in song["artist"].lower() or 
            query_lower in song["album"].lower()):
            results.append(song)
            
        if len(results) >= limit:
            break
    
    # 如果没有匹配结果，返回一些默认结果
    if not results:
        results = MOCK_MUSIC_DATABASE[:limit]
    
    return results

# 工具处理函数
async def search_music_handler(arguments: Dict[str, Any]) -> str:
    query = arguments["query"]
    limit = arguments.get("limit", 10)
    
    results = await search_music_api(query, limit)
    
    response = f"搜索 '{query}' 的结果：\n\n"
    for i, song in enumerate(results, 1):
        response += f"{i}. {song['name']} - {song['artist']}\n"
        response += f"   专辑: {song['album']}\n"
        response += f"   时长: {song['duration']}秒\n"
        response += f"   ID: {song['id']}\n\n"
    
    return response

async def play_music_handler(arguments: Dict[str, Any]) -> str:
    song_id = arguments["song_id"]
    song_name = arguments.get("song_name", "未知歌曲")
    artist = arguments.get("artist", "未知歌手")
    
    playback_state["current_song"] = {
        "id": song_id,
        "name": song_name,
        "artist": artist
    }
    playback_state["is_playing"] = True
    playback_state["position"] = 0
    
    return f"正在播放: {song_name} - {artist}"

async def pause_music_handler(arguments: Dict[str, Any]) -> str:
    playback_state["is_playing"] = False
    return "音乐已暂停"

async def resume_music_handler(arguments: Dict[str, Any]) -> str:
    playback_state["is_playing"] = True
    current = playback_state["current_song"]
    if current:
        return f"继续播放: {current['name']} - {current['artist']}"
    else:
        return "没有可继续播放的歌曲"

async def stop_music_handler(arguments: Dict[str, Any]) -> str:
    playback_state["is_playing"] = False
    playback_state["current_song"] = None
    playback_state["position"] = 0
    return "音乐已停止"

async def set_volume_handler(arguments: Dict[str, Any]) -> str:
    volume = arguments["volume"]
    playback_state["volume"] = volume
    return f"音量已设置为: {volume}%"

async def add_to_playlist_handler(arguments: Dict[str, Any]) -> str:
    song_id = arguments["song_id"]
    song_name = arguments.get("song_name", "未知歌曲")
    artist = arguments.get("artist", "未知歌手")
    
    song = {
        "id": song_id,
        "name": song_name,
        "artist": artist
    }
    playback_state["playlist"].append(song)
    
    return f"已添加到播放列表: {song_name} - {artist}"

async def get_playlist_handler(arguments: Dict[str, Any]) -> str:
    playlist = playback_state["playlist"]
    if not playlist:
        return "播放列表为空"
    
    response = "当前播放列表:\n\n"
    for i, song in enumerate(playlist, 1):
        response += f"{i}. {song['name']} - {song['artist']}\n"
    
    return response

async def clear_playlist_handler(arguments: Dict[str, Any]) -> str:
    playback_state["playlist"] = []
    return "播放列表已清空"

async def next_song_handler(arguments: Dict[str, Any]) -> str:
    playlist = playback_state["playlist"]
    current = playback_state["current_song"]
    
    if not playlist:
        return "播放列表为空，无法切换到下一首"
    
    if current:
        try:
            current_index = next(i for i, song in enumerate(playlist) if song["id"] == current["id"])
            next_index = (current_index + 1) % len(playlist)
        except StopIteration:
            next_index = 0
    else:
        next_index = 0
    
    next_song = playlist[next_index]
    playback_state["current_song"] = next_song
    playback_state["is_playing"] = True
    
    return f"下一首: {next_song['name']} - {next_song['artist']}"

async def previous_song_handler(arguments: Dict[str, Any]) -> str:
    playlist = playback_state["playlist"]
    current = playback_state["current_song"]
    
    if not playlist:
        return "播放列表为空，无法切换到上一首"
    
    if current:
        try:
            current_index = next(i for i, song in enumerate(playlist) if song["id"] == current["id"])
            prev_index = (current_index - 1) % len(playlist)
        except StopIteration:
            prev_index = len(playlist) - 1
    else:
        prev_index = len(playlist) - 1
    
    prev_song = playlist[prev_index]
    playback_state["current_song"] = prev_song
    playback_state["is_playing"] = True
    
    return f"上一首: {prev_song['name']} - {prev_song['artist']}"

async def handle_client(websocket):
    """处理WebSocket客户端连接"""
    logger.info(f"新客户端连接: {websocket.remote_address}")
    
    try:
        async for message in websocket:
            await server.handle_message(websocket, message)
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"客户端断开连接: {websocket.remote_address}")
    except Exception as e:
        logger.error(f"处理客户端错误: {e}")

# 创建服务器实例
server = MCPWebSocketServer()

#unsupported HTTP method; expected GET; got HEAD
#Render 的健康检查默认用 HEAD 请求（不是 GET），而 websockets 库 只认 GET + Upgrade，于是直接抛 InvalidMessage，导致 handshake 失败。
#解决思路：让 同一个端口 既能返回 HEAD/GET 200，又能正常升级 WebSocket。
#最轻量的办法——在前面套一层 简单的 TCP 分流，先读第一行：
#是 HEAD 或 GET 但 没有 Upgrade: websocket → 按 HTTP 回 200
#是 GET 且 带 Upgrade: websocket → 交给 websockets 库做握手
#async def main():
#    """主函数"""
#   logger.info("启动免费音乐MCP WebSocket服务器...")
    
    # 添加资源
#    server.add_resource("music://current_playlist", "当前播放列表", "显示当前播放列表中的所有歌曲")
#    server.add_resource("music://current_playing", "当前播放", "显示当前正在播放的歌曲信息")
#


# ---------- 健康检查响应 ----------
async def http_200(writer):
    body = b"OK"
    writer.write(b"HTTP/1.1 200 OK\r\n"
                 b"Content-Length: %d\r\n"
                 b"Connection: close\r\n\r\n%s" % (len(body), body))
    await writer.drain()
    writer.close()
    await writer.wait_closed()

# ---------- TCP 分流 ----------
async def tcp_splitter(reader, writer):
    header = io.BytesIO()
    first_line = await reader.readline()
    if not first_line:
        writer.close()
        await writer.wait_closed()
        return
    header.write(first_line)
    while True:
        line = await reader.readline()
        header.write(line)
        if line == b'\r\n':
            break
    head_text = header.getvalue().decode('utf-8', 'ignore').lower()

    # 把数据塞回流
    reader._buffer = bytearray(header.getvalue()) + reader._buffer

    if 'upgrade: websocket' in head_text:
        sock = writer.get_extra_info('socket')
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        # ===== websockets 15.x 官方做法 =====
        from websockets.asyncio.server import ServerConnection
        conn = ServerConnection(
            handle_client,
            server_reader=reader,
            server_writer=writer,
            close_timeout=None,
            logger=logger,
        )
        await conn.run()          # 会阻塞到 WebSocket 关闭
    else:
        await http_200(writer)
        
# ---------- 启动 ----------
async def main():
    # 1. 注册工具/资源（完全沿用你已有代码）
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

# ================= 入口不变 =================
if __name__ == "__main__":
    asyncio.run(main())
