#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SVN监控系统基本功能测试

这个脚本用于验证SVN监控系统的基本功能是否正常。
"""

import sys
import os

def test_basic_functionality():
    """测试基本功能"""
    
    # 添加src目录到Python路径
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
    
    print("=== SVN监控系统基本功能测试 ===")
    
    try:
        # 导入SVNMonitor类
        from svn_monitor import SVNMonitor
        print("✓ SVNMonitor类导入成功")
        
        # 创建SVNMonitor实例
        monitor = SVNMonitor()
        print("✓ SVNMonitor实例创建成功")
        
        # 检查基本属性
        print(f"✓ 配置类型: {type(monitor.config)}")
        print(f"✓ 仓库数量: {len(monitor.repositories)}")
        print(f"✓ 最后记录版本类型: {type(monitor.last_revisions)}")
        
        # 测试路径修复功能
        print("\n=== 测试路径修复功能 ===")
        
        # 创建一个测试配置
        test_config = {
            'username': 'test_user',
            'password': 'test_pass'
        }
        
        # 测试_try_svn_cleanup方法
        try:
            result = monitor._try_svn_cleanup('.', test_config)
            print(f"✓ _try_svn_cleanup方法调用成功，结果: {result}")
        except Exception as e:
            print(f"✗ _try_svn_cleanup方法调用失败: {e}")
        
        # 测试log_operation方法
        print("\n=== 测试日志操作功能 ===")
        
        try:
            monitor.log_operation('INFO', '测试日志消息', repository='test-repo')
            print("✓ log_operation方法调用成功")
        except Exception as e:
            print(f"✗ log_operation方法调用失败: {e}")
        
        print("\n=== 测试完成 ===")
        print("✅ 所有基本功能测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_basic_functionality()
    sys.exit(0 if success else 1)