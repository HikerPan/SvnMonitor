#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试log_operation方法修复后的功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from svn_monitor import SVNMonitor
import configparser

def test_log_operation_fix():
    """测试修复后的log_operation方法"""
    print("=== 测试log_operation方法修复 ===")
    
    # 创建配置对象
    config = configparser.ConfigParser()
    config['SYSTEM'] = {
        'log_file': 'test.log',
        'log_level': 'INFO'
    }
    
    # 创建SVNMonitor实例
    monitor = SVNMonitor()
    monitor.config = config
    
    # 测试1: 字符串参数（正常情况）
    print("测试1: 字符串参数")
    try:
        monitor.log_operation('INFO', '测试字符串参数', repository='test-repo')
        print("✓ 字符串参数测试通过")
    except Exception as e:
        print(f"✗ 字符串参数测试失败: {e}")
    
    # 测试2: 字典参数（之前会出错的情况）
    print("\n测试2: 字典参数")
    try:
        repo_config = {'name': 'test-repo', 'path': '/svn/test'}
        monitor.log_operation('INFO', '测试字典参数', repository=repo_config)
        print("✓ 字典参数测试通过")
    except Exception as e:
        print(f"✗ 字典参数测试失败: {e}")
    
    # 测试3: None参数
    print("\n测试3: None参数")
    try:
        monitor.log_operation('INFO', '测试None参数', repository=None)
        print("✓ None参数测试通过")
    except Exception as e:
        print(f"✗ None参数测试失败: {e}")
    
    # 测试4: 整数参数
    print("\n测试4: 整数参数")
    try:
        monitor.log_operation('INFO', '测试整数参数', repository=123)
        print("✓ 整数参数测试通过")
    except Exception as e:
        print(f"✗ 整数参数测试失败: {e}")
    
    # 测试5: 列表参数
    print("\n测试5: 列表参数")
    try:
        monitor.log_operation('INFO', '测试列表参数', repository=['repo1', 'repo2'])
        print("✓ 列表参数测试通过")
    except Exception as e:
        print(f"✗ 列表参数测试失败: {e}")
    
    # 测试6: 没有name字段的字典
    print("\n测试6: 没有name字段的字典")
    try:
        repo_config = {'path': '/svn/test', 'url': 'http://svn.test.com'}
        monitor.log_operation('INFO', '测试无name字段字典', repository=repo_config)
        print("✓ 无name字段字典测试通过")
    except Exception as e:
        print(f"✗ 无name字段字典测试失败: {e}")
    
    print("\n=== 测试完成 ===")

if __name__ == '__main__':
    test_log_operation_fix()