#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试SVN SSL连接的脚本，用于验证环境变量OPENSSL_CONF是否正确传递
"""
import os
import subprocess

# 确保环境变量正确设置
os.environ['OPENSSL_CONF'] = '/home/alex/aidev/SvnMonitor/ssl_config.cnf'

print(f"当前OPENSSL_CONF: {os.environ.get('OPENSSL_CONF')}")

# 测试SVN命令
test_url = 'https://106.14.40.14:8443/svn/采购'
username = 'svn_bot'
password = 'svn_bot'

cmd = [
    'svn', 'info', test_url,
    '--show-item', 'revision',
    '--username', username,
    '--password', password,
    '--non-interactive',
    '--trust-server-cert',
    '--trust-server-cert-failures', 'unknown-ca,cn-mismatch,expired,not-yet-valid,other'
]

print(f"执行命令: {' '.join(cmd)}")

try:
    # 显式传递环境变量
    env = os.environ.copy()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        check=True
    )
    print(f"成功! 输出: {result.stdout.strip()}")
except subprocess.CalledProcessError as e:
    print(f"错误! 返回码: {e.returncode}")
    print(f"标准输出: {e.stdout}")
    print(f"标准错误: {e.stderr}")
