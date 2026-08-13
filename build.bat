@echo off
chcp 65001 >nul
title DeskDear 一键打包

echo ==========================================
echo  DeskDear PyInstaller 一键打包脚本
echo ==========================================
echo.

echo [1/3] 安装依赖...
pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [2/3] 清理旧的构建产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [3/3] 开始打包（单文件 exe）...
pyinstaller --noconfirm --clean DeskDear.spec
if errorlevel 1 goto :error

echo.
echo ==========================================
echo  打包完成！产物位置：dist\DeskDear.exe
echo  将 DeskDear.exe 拷贝到任意位置即可运行，
echo  配置文件 user_config.json 会生成在 exe 同目录。
echo ==========================================
pause
exit /b 0

:error
echo.
echo 构建失败，请检查上方错误信息。
pause
exit /b 1
