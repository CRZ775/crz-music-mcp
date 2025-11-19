FROM python:3.12-slim

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 10000

# 启动命令
CMD ["python3", "music_mcp_websocket_server.py"]
