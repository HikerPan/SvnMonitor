#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SVN监控系统测试运行器

这个脚本用于运行SVN监控系统的所有测试，并生成测试报告。
"""

import sys
import os
import unittest

def run_all_tests():
    """运行所有测试"""
    
    # 添加src目录到Python路径
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
    
    print("=== SVN监控系统测试套件 ===")
    print("开始运行所有测试...\n")
    
    # 创建测试套件
    test_suite = unittest.TestSuite()
    
    # 导入测试模块
    from test_svn_monitor import TestSVNMonitor
    from test_path_fix import TestPathFix
    
    # 添加测试类
    test_suite.addTest(unittest.makeSuite(TestSVNMonitor))
    test_suite.addTest(unittest.makeSuite(TestPathFix))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # 输出测试总结
    print("\n=== 测试总结 ===")
    print(f"运行测试数: {result.testsRun}")
    print(f"失败测试数: {len(result.failures)}")
    print(f"错误测试数: {len(result.errors)}")
    print(f"跳过测试数: {len(result.skipped)}")
    
    if result.wasSuccessful():
        print("✅ 所有测试通过！")
        return 0
    else:
        print("❌ 有测试失败或错误")
        
        # 输出失败和错误的详细信息
        if result.failures:
            print("\n=== 失败测试 ===")
            for test, traceback in result.failures:
                print(f"{test}: {traceback}")
        
        if result.errors:
            print("\n=== 错误测试 ===")
            for test, traceback in result.errors:
                print(f"{test}: {traceback}")
        
        return 1

if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)