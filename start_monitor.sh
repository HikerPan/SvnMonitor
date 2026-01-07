#!/bin/bash

# 激活虚拟环境
source venv/bin/activate

# 设置SSL配置
export OPENSSL_CONF="$(dirname "$0")/ssl_config.cnf"

# 进入src目录并启动程序
cd src
python svn_monitor.py