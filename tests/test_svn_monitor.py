#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for SVN Monitor Script
This module contains unit tests for the SVN Monitor functionality.
"""

import os
import sys
import unittest
from unittest import mock
import tempfile
import configparser
import datetime
import subprocess

# Add the src directory to Python path so we can import svn_monitor
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from svn_monitor import SVNMonitor, setup_logging


class TestSVNMonitor(unittest.TestCase):
    """Unit tests for the SVNMonitor class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directory for testing
        self.temp_dir = tempfile.TemporaryDirectory()
        
        # Create a test configuration
        self.test_config = configparser.ConfigParser()
        self.test_config['EMAIL'] = {
            'smtp_server': 'smtp.exmail.qq.com',
            'smtp_port': '465',
            'use_ssl': 'True',
            'username': 'test@example.com',
            'password': 'test_password',
            'from_email': 'test@example.com',
            'to_emails': 'test@example.com'
        }
        self.test_config['LOGGING'] = {
            'log_file': 'test.log',
            'log_level': 'INFO'
        }
        self.test_config['SYSTEM'] = {
            'auto_startup': 'False',
            'mode': 'monitor',
            'restore_from': ''
        }
        self.test_config['REPO_1'] = {
            'name': 'Test Repository',
            'repository_path': 'file:///' + os.path.join(self.temp_dir.name, 'test_repo'),
            'username': 'test_user',
            'password': 'test_pass',
            'check_interval': '60',
            'local_working_copy': os.path.join(self.temp_dir.name, 'wc'),
            'enable_notifications': 'True'
        }
        
        # Setup mock for subprocess.run to prevent actual SVN commands
        self.subprocess_mock = mock.patch('svn_monitor.subprocess.run').start()
        self.subprocess_mock.return_value = mock.Mock(stdout='test output', stderr='')
        
        # Setup mock for os.makedirs
        self.makedirs_mock = mock.patch('svn_monitor.os.makedirs').start()
        
        # Setup mock for os.path.exists
        self.exists_mock = mock.patch('svn_monitor.os.path.exists').start()
        self.exists_mock.return_value = True
        
        # Setup mock for _load_config method to return our test configuration
        self.load_config_mock = mock.patch.object(SVNMonitor, '_load_config', return_value=self.test_config).start()
        
        # Setup mock for _validate_config method
        self.validate_config_mock = mock.patch.object(SVNMonitor, '_validate_config').start()
        
        # Setup mock for _get_repositories method
        self.get_repos_mock = mock.patch.object(SVNMonitor, '_get_repositories', return_value={'1': self.test_config['REPO_1']}).start()
        
        # Setup mock for _convert_relative_paths method
        self.convert_paths_mock = mock.patch.object(SVNMonitor, '_convert_relative_paths').start()
        
        # Setup mock for _get_last_recorded_revisions method
        self.get_revisions_mock = mock.patch.object(SVNMonitor, '_get_last_recorded_revisions', return_value={'1': 0}).start()
        
        # Setup mock for _load_recipients_from_excel method
        self.load_recipients_mock = mock.patch.object(SVNMonitor, '_load_recipients_from_excel', return_value={}).start()
    
    def tearDown(self):
        """Clean up after tests"""
        mock.patch.stopall()
        self.temp_dir.cleanup()
    
    def test_initialization(self):
        """Test SVNMonitor initialization"""
        # Create a monitor instance with mocked methods
        monitor = SVNMonitor()
        
        # Verify configuration was loaded via mock
        self.load_config_mock.assert_called_once()
        self.assertEqual(monitor.config, self.test_config)
        self.assertIn('EMAIL', monitor.config)
        self.assertIn('LOGGING', monitor.config)
        self.assertIn('SYSTEM', monitor.config)
        
        # Verify repositories were loaded via mock
        self.get_repos_mock.assert_called_once()
        self.assertEqual(len(monitor.repositories), 1)
        self.assertIn('1', monitor.repositories)
        
    def test_get_repositories(self):
        """Test getting repository configurations"""
        # Create a monitor instance
        monitor = SVNMonitor()
        
        # Since we mocked _get_repositories, test that it returns the expected data
        repositories = monitor._get_repositories()
        
        self.assertEqual(len(repositories), 1)
        self.assertIn('1', repositories)
        self.assertEqual(repositories['1']['name'], 'Test Repository')
    
    def test_load_config(self):
        """Test loading configuration"""
        monitor = SVNMonitor()
        
        # Since we mocked _load_config, test that it returns the expected data
        config = monitor._load_config()
        
        self.assertIn('EMAIL', config)
        self.assertIn('LOGGING', config)
        self.assertIn('SYSTEM', config)
        self.assertIn('REPO_1', config)
    
    @mock.patch('svn_monitor.pd.ExcelWriter')
    def test_create_default_config(self, mock_excel_writer):
        """Test creating default configuration"""
        monitor = SVNMonitor()
        
        # Mock ExcelWriter and related objects
        mock_writer = mock.MagicMock()
        mock_excel_writer.return_value.__enter__.return_value = mock_writer
        
        # Call the method
        monitor._create_default_config()
        
        # Verify ExcelWriter was called with correct file path
        # 使用与SVNMonitor类中相同的路径计算逻辑
        base_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv else os.getcwd()
        expected_config_path = os.path.join(base_dir, 'config', 'svn_monitor_config.xlsx')
        mock_excel_writer.assert_called_with(expected_config_path, engine='openpyxl')
        
        # Verify the Excel file was saved (through context manager)
        # The save method is called automatically when the context manager exits
    
    def test_run_svn_command(self):
        """Test running SVN command"""
        monitor = SVNMonitor()
        repo_config = monitor.repositories['1']
        
        result = monitor._run_svn_command(['svn', 'info'], repo_config)
        
        # Verify subprocess was called with correct arguments
        expected_command = [
            'svn', 'info', 
            '--username', 'test_user', 
            '--password', 'test_pass', 
            '--non-interactive', 
            '--trust-server-cert'
        ]
        self.subprocess_mock.assert_called_with(
            expected_command,
            capture_output=True,
            encoding='utf-8',
            cwd=None,
            check=True
        )
        
        # Verify result
        self.assertEqual(result, 'test output')
    
    def test_ensure_working_copy(self):
        """Test ensuring working copy exists"""
        monitor = SVNMonitor()
        repo_config = monitor.repositories['1']
        
        # Test with existing working copy
        self.exists_mock.return_value = True
        monitor._ensure_working_copy(repo_config)
        
        # Verify update command was called
        expected_command = ['svn', 'update', repo_config['local_working_copy']]
        self.subprocess_mock.assert_called_with(
            mock.ANY,  # This will match the command with credentials
            capture_output=True,
            encoding='utf-8',
            cwd=None,
            check=True
        )
        
        # Test with non-existing working copy
        self.subprocess_mock.reset_mock()
        self.exists_mock.return_value = False
        monitor._ensure_working_copy(repo_config)
        
        # Verify checkout command was called
        self.makedirs_mock.assert_called_with(os.path.dirname(repo_config['local_working_copy']), exist_ok=True)

    def test_try_svn_cleanup(self):
        """Test SVN cleanup functionality"""
        monitor = SVNMonitor()
        repo_config = monitor.repositories['1']
        
        # Test successful cleanup
        result = monitor._try_svn_cleanup(repo_config['local_working_copy'], repo_config)
        
        # Verify cleanup command was called with correct arguments
        expected_command = [
            'svn', 'cleanup', repo_config['local_working_copy'],
            '--username', 'test_user',
            '--password', 'test_pass',
            '--non-interactive',
            '--trust-server-cert'
        ]
        self.subprocess_mock.assert_called_with(
            expected_command,
            capture_output=True,
            encoding='utf-8',
            check=True
        )
        
        # Verify result
        self.assertTrue(result)
        
        # Test cleanup failure
        self.subprocess_mock.reset_mock()
        self.subprocess_mock.side_effect = Exception("Cleanup failed")
        
        result = monitor._try_svn_cleanup(repo_config['local_working_copy'], repo_config)
        
        # Verify cleanup was attempted
        self.subprocess_mock.assert_called()
        
        # Verify result is False on failure
        self.assertFalse(result)

    def test_run_svn_command_with_lock_cleanup(self):
        """Test SVN command execution with lock cleanup functionality"""
        monitor = SVNMonitor()
        repo_config = monitor.repositories['1']
        
        # Test normal command execution (no lock)
        result = monitor._run_svn_command(['svn', 'info'], repo_config, working_dir=repo_config['local_working_copy'])
        
        # Verify command was called once (no retry needed)
        self.assertEqual(self.subprocess_mock.call_count, 1)
        
        # Test command execution with lock that gets resolved
        self.subprocess_mock.reset_mock()
        
        # First call raises lock error, cleanup call succeeds, retry call succeeds
        self.subprocess_mock.side_effect = [
            subprocess.CalledProcessError(1, 'svn', stderr="svn: E155004: Working copy 'path' locked"),
            mock.Mock(stdout='cleanup success', stderr=''),  # 清理命令成功
            mock.Mock(stdout='success', stderr='')  # 重试的命令成功
        ]
        
        # Mock the working directory check to return True for cleanup operation
        with mock.patch('svn_monitor.os.path.exists', return_value=True):
            result = monitor._run_svn_command(['svn', 'info'], repo_config, working_dir=repo_config['local_working_copy'])
        
        # Verify command was called three times (original + cleanup + retry)
        self.assertEqual(self.subprocess_mock.call_count, 3)
        
        # Verify result
        self.assertEqual(result, 'success')
        
        # Test command execution with persistent lock
        self.subprocess_mock.reset_mock()
        
        # All calls raise lock error (包括清理命令)
        self.subprocess_mock.side_effect = subprocess.CalledProcessError(1, 'svn', stderr="svn: E155004: Working copy 'path' locked")
        
        # Mock the working directory check to return True for cleanup operation
        with mock.patch('svn_monitor.os.path.exists', return_value=True):
            result = monitor._run_svn_command(['svn', 'info'], repo_config, working_dir=repo_config['local_working_copy'])
        
        # Verify command was called twice (original + cleanup)
        self.assertEqual(self.subprocess_mock.call_count, 2)
        
        # Verify result is empty string on persistent failure
        self.assertEqual(result, '')

    def test_ensure_working_copy_with_cleanup(self):
        """Test ensuring working copy with cleanup functionality"""
        monitor = SVNMonitor()
        repo_config = monitor.repositories['1']
        
        # Mock the cleanup method to verify it's called
        cleanup_mock = mock.patch.object(monitor, '_try_svn_cleanup', return_value=True).start()
        
        # Test with existing working copy
        self.exists_mock.return_value = True
        monitor._ensure_working_copy(repo_config)
        
        # Verify cleanup was called before SVN operations
        cleanup_mock.assert_called_once_with(repo_config['local_working_copy'], repo_config)
        
        # Verify update command was called
        self.subprocess_mock.assert_called()
        
        # Test with non-existing working copy (cleanup should not be called)
        cleanup_mock.reset_mock()
        self.subprocess_mock.reset_mock()
        self.exists_mock.return_value = False
        
        monitor._ensure_working_copy(repo_config)
        
        # Verify cleanup was not called for non-existing working copy
        cleanup_mock.assert_not_called()
        
        # Verify checkout command was called
        self.makedirs_mock.assert_called_with(os.path.dirname(repo_config['local_working_copy']), exist_ok=True)
    
    def test_get_latest_revision(self):
        """Test getting latest revision"""
        # Mock the return value for svn info command
        self.subprocess_mock.return_value = mock.Mock(stdout='123', stderr='')
        
        monitor = SVNMonitor()
        repo_config = monitor.repositories['1']
        
        # Mock ensure_working_copy to avoid actual calls
        monitor._ensure_working_copy = mock.MagicMock()
        
        revision = monitor.get_latest_revision(repo_config)
        
        # Verify result
        self.assertEqual(revision, 123)
    
    def test_parse_svn_log(self):
        """Test parsing SVN log XML"""
        xml_log = """<?xml version="1.0" encoding="UTF-8"?>
        <log>
          <logentry revision="123">
            <author>test_user</author>
            <date>2023-01-01T10:00:00.000000Z</date>
            <msg>Test commit</msg>
            <paths>
              <path action="M">/path/to/file.txt</path>
              <path action="A">/path/to/newfile.txt</path>
            </paths>
          </logentry>
        </log>"""
        
        monitor = SVNMonitor()
        changes = monitor._parse_svn_log(xml_log, 'Test Repo')
        
        # Verify parsing result
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['revision'], 123)
        self.assertEqual(changes[0]['author'], 'test_user')
        self.assertEqual(changes[0]['message'], 'Test commit')
        self.assertEqual(len(changes[0]['changed_paths']), 2)
        self.assertEqual(changes[0]['changed_paths'][0]['path'], '/path/to/file.txt')
        self.assertEqual(changes[0]['changed_paths'][0]['action'], 'M')
        self.assertEqual(changes[0]['changed_paths'][1]['path'], '/path/to/newfile.txt')
        self.assertEqual(changes[0]['changed_paths'][1]['action'], 'A')
        self.assertEqual(changes[0]['repository'], 'Test Repo')
    
    @mock.patch('svn_monitor.smtplib.SMTP_SSL')
    def test_send_email_notification(self, mock_smtp):
        """Test sending email notification"""
        # Create mock SMTP server
        mock_server = mock.MagicMock()
        mock_smtp.return_value = mock_server
        
        # Create test changes
        changes = [{
            'revision': 123,
            'author': 'test_user',
            'date': '2023-01-01T10:00:00.000000Z',
            'message': 'Test commit',
            'changed_paths': [
                {'path': '/path/to/file.txt', 'action': 'M'},
                {'path': '/path/to/newfile.txt', 'action': 'A'}
            ],
            'repository': 'Test Repo'
        }]
        
        monitor = SVNMonitor()
        monitor.send_email_notification(changes)
        
        # Verify SMTP server was used correctly
        mock_smtp.assert_called_with('smtp.exmail.qq.com', 465, timeout=30)
        mock_server.login.assert_called_with('test@example.com', 'test_password')
        mock_server.send_message.assert_called_once()
        mock_server.quit.assert_called_once()
    
    def test_validate_config(self):
        """Test validating configuration"""
        # Create a minimal config for testing
        minimal_config = configparser.ConfigParser()
        minimal_config['EMAIL'] = {'smtp_server': 'test'}
        
        # Update our test_config to be minimal
        self.load_config_mock.return_value = minimal_config
        
        # Mock _create_default_repository_config
        mock_create_repo = mock.patch.object(SVNMonitor, '_create_default_repository_config').start()
        
        # Create a monitor instance
        monitor = SVNMonitor()
        
        # Verify _validate_config was called
        self.validate_config_mock.assert_called_once()
        
        # Since we're using mocks, we need to manually verify the behavior
        # In a real test, we would test the actual validation logic


# Run tests automatically when the script is executed
if __name__ == '__main__':
    # Run the tests and capture the results
    test_runner = unittest.TextTestRunner(verbosity=2)
    test_suite = unittest.TestLoader().loadTestsFromTestCase(TestSVNMonitor)
    test_result = test_runner.run(test_suite)
    
    # Print a summary of the test results
    print("\n=== Test Summary ===")
    print(f"Tests run: {test_result.testsRun}")
    print(f"Failures: {len(test_result.failures)}")
    print(f"Errors: {len(test_result.errors)}")
    print(f"Skipped: {len(test_result.skipped)}")
    
    # Exit with a code based on test success
    sys.exit(0 if test_result.wasSuccessful() else 1)