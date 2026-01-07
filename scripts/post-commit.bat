@echo off

:: SVN post-commit钩子脚本 - 平衡版本

:: 设置常量路径（使用简单变量，避免复杂语法）
set LOG_DIR=d:\B_Code\B_project\snake\logs
set PYTHON_EXE=C:\Python312\python.exe
set MONITOR_SCRIPT=d:\B_Code\B_project\snake\src\svn_monitor.py
set CONFIG_FILE=d:\B_Code\B_project\snake\config\svn_monitor_config.xlsx

:: 确保日志目录存在（使用简单的if语句）
if not exist %LOG_DIR% mkdir %LOG_DIR%

:: 使用固定日志文件名
echo Hook started > %LOG_DIR%\hook.log

:: 切换到脚本目录
cd /d d:\B_Code\B_project\snake

:: 执行Python脚本（使用最基本的命令格式）
%PYTHON_EXE% %MONITOR_SCRIPT% --repository %1 --revision %2 --config %CONFIG_FILE% > %LOG_DIR%\script.log 2>&1

echo Hook completed >> %LOG_DIR%\hook.log

exit 0
