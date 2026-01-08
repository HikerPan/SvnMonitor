#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试环境变量是否正确传递的脚本
"""
import os
import subprocess

def main():
    # 打印当前进程的环境变量
    print("当前进程环境变量:")
    print(f"OPENSSL_CONF: {os.environ.get('OPENSSL_CONF', '未设置')}")
    
    # 执行一个简单的svn命令测试
    print("\n执行SVN命令测试:")
    cmd = ['svn', '--version']
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"SVN版本: {result.stdout.strip()}")
    
    # 尝试获取SSL配置信息
    print("\n执行openssl命令测试SSL配置:")
    cmd = ['openssl', 'ciphers']
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"SSL密码套件: {result.stdout.strip()[:200]}...")

if __name__ == "__main__":
    main()