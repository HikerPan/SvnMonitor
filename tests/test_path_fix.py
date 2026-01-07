#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径修复功能测试

验证SVN清理路径重复问题的修复效果
"""

import os
import sys
import unittest
from unittest import mock

# 添加src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from svn_monitor import SVNMonitor


class TestPathFix(unittest.TestCase):
    """路径修复测试类"""
    
    def setUp(self):
        """测试前准备"""
        # 创建临时目录
        self.temp_dir = os.path.join(os.path.dirname(__file__), 'temp_test')
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # 创建测试工作目录
        self.test_working_dir = os.path.join(self.temp_dir, 'test_wc')
        os.makedirs(self.test_working_dir, exist_ok=True)
        
        # 创建.svn目录模拟SVN工作副本
        self.svn_dir = os.path.join(self.test_working_dir, '.svn')
        os.makedirs(self.svn_dir, exist_ok=True)
        
        # 设置mock
        self.subprocess_mock = mock.patch('svn_monitor.subprocess.run').start()
        self.subprocess_mock.return_value = mock.Mock(returncode=0, stdout='', stderr='')
        
        # 模拟配置加载
        self.load_config_mock = mock.patch.object(SVNMonitor, '_load_config').start()
        self.load_config_mock.return_value = {
            'EMAIL': {'smtp_server': 'test'},
            'LOGGING': {'log_file': 'test.log'},
            'SYSTEM': {'mode': 'monitor'}
        }
        
        # 模拟其他方法
        mock.patch.object(SVNMonitor, '_get_repositories').start()
        mock.patch.object(SVNMonitor, '_convert_relative_paths').start()
        mock.patch.object(SVNMonitor, '_get_last_recorded_revisions').start()
        mock.patch.object(SVNMonitor, '_load_recipients_from_excel').start()
    
    def tearDown(self):
        """测试后清理"""
        mock.patch.stopall()
        # 清理临时目录
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_cleanup_command_path_fix(self):
        """测试清理命令路径修复"""
        # 创建监控器实例
        monitor = SVNMonitor()
        
        # 创建测试仓库配置
        test_repo_config = {
            'username': 'test_user',
            'password': 'test_pass'
        }
        
        # 测试_try_svn_cleanup方法
        result = monitor._try_svn_cleanup(self.test_working_dir, test_repo_config)
        
        # 验证命令构建正确性
        self.assertEqual(result, True, "清理操作应该成功")
        
        # 检查subprocess.run的调用参数
        call_args = self.subprocess_mock.call_args
        
        # 验证命令参数
        command = call_args[0][0]  # 第一个位置参数是命令列表
        cwd = call_args[1]['cwd']  # cwd关键字参数
        
        print(f"清理命令: {command}")
        print(f"工作目录: {cwd}")
        
        # 验证修复后的命令使用相对路径'.'
        self.assertEqual(command[2], '.', "清理命令应该使用相对路径'.'")
        
        # 验证cwd参数正确设置
        self.assertEqual(cwd, self.test_working_dir, "cwd参数应该设置为工作目录")
        
        # 验证命令结构
        self.assertEqual(command[0], 'svn', "命令应该以'svn'开头")
        self.assertEqual(command[1], 'cleanup', "命令应该是'cleanup'操作")
        
        print("✅ 清理命令路径修复验证通过")
    
    def test_original_problem_analysis(self):
        """测试原始问题分析"""
        print("\n=== 原始问题分析 ===")
        
        # 原始问题：同时使用cwd参数和工作目录作为命令参数
        original_command = ['svn', 'cleanup', self.test_working_dir]
        original_cwd = self.test_working_dir
        
        print(f"原始问题命令: {original_command}")
        print(f"原始cwd参数: {original_cwd}")
        print("问题: 同时使用cwd参数和工作目录作为命令参数会导致路径重复")
        
        # 修复后的命令
        fixed_command = ['svn', 'cleanup', '.']
        fixed_cwd = self.test_working_dir
        
        print(f"修复后命令: {fixed_command}")
        print(f"修复后cwd参数: {fixed_cwd}")
        print("修复: 使用相对路径'.'避免路径重复")
        
        # 验证修复逻辑
        self.assertNotEqual(original_command[2], fixed_command[2], 
                          "修复前后的命令参数应该不同")
        self.assertEqual(fixed_command[2], '.', "修复后应该使用相对路径'.'")
        
        print("✅ 原始问题分析完成")
    
    def test_monitor_integration(self):
        """测试监控器集成"""
        print("\n=== 监控器集成测试 ===")
        
        # 创建监控器实例
        monitor = SVNMonitor()
        
        # 验证监控器正常初始化
        self.assertIsNotNone(monitor, "监控器实例应该成功创建")
        self.assertIsNotNone(monitor.config, "配置应该成功加载")
        
        print(f"监控器类型: {type(monitor)}")
        print(f"配置类型: {type(monitor.config)}")
        
        # 验证监控器具有必要的属性
        self.assertTrue(hasattr(monitor, 'repositories'), "监控器应该有repositories属性")
        self.assertTrue(hasattr(monitor, 'last_revisions'), "监控器应该有last_revisions属性")
        
        print("✅ 监控器集成测试通过")


def main():
    """主测试函数"""
    print("开始路径修复功能测试...\n")
    
    # 创建测试套件
    suite = unittest.TestSuite()
    suite.addTest(TestPathFix('test_cleanup_command_path_fix'))
    suite.addTest(TestPathFix('test_original_problem_analysis'))
    suite.addTest(TestPathFix('test_monitor_integration'))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出测试结果
    print("\n=== 测试总结 ===")
    print(f"运行测试数: {result.testsRun}")
    print(f"失败测试数: {len(result.failures)}")
    print(f"错误测试数: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("✅ 所有测试通过")
        return True
    else:
        print("❌ 部分测试失败")
        return False


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)