#!/bin/bash

# MindPair 部署脚本
# 用法: ./deploy.sh

set -e

SERVER="ubuntu@43.160.222.242"
PASSWORD="Zf870723~"
APP_DIR="/home/ubuntu/mindpair"

echo "=== MindPair 部署脚本 ==="

# 1. 在服务器上安装依赖
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no $SERVER << 'EOF'
    set -e

    echo "==> 更新系统..."
    sudo apt update && sudo apt upgrade -y

    echo "==> 安装 Python 和依赖..."
    sudo apt install -y python3 python3-pip python3-venv git

    echo "==> 创建应用目录..."
    mkdir -p $APP_DIR
    cd $APP_DIR

    echo "==> 克隆代码（如已有仓库）..."
    # 如果使用 Git 仓库，取消下行注释并修改 URL
    # git clone https://github.com/YOUR_USER/MindPair.git .

    echo "==> 创建虚拟环境..."
    python3 -m venv venv
    source venv/bin/activate

    echo "==> 安装 Python 依赖..."
    pip install -r requirements.txt

    echo "==> 创建 systemd 服务文件..."
    sudo tee /etc/systemd/system/mindpair.service > /dev/null << 'SERVICE'
[Unit]
Description=MindPair - 双AI协作设计系统
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/mindpair
ExecStart=/home/ubuntu/mindpair/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE

    echo "==> 启用服务..."
    sudo systemctl daemon-reload
    sudo systemctl enable mindpair

    echo "==> 启动服务..."
    sudo systemctl restart mindpair

    echo "==> 检查状态..."
    sudo systemctl status mindpair --no-pager

    echo "==> 完成！访问 http://43.160.222.242:8000"
EOF

echo "=== 部署完成 ==="
