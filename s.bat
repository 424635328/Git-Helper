@echo off
chcp 65001 > nul
setlocal

:: 设置 Git 的编码选项
git config core.quotepath false
git config i18n.commitencoding utf-8

:: 获取时间戳 (使用 PowerShell)
for /f "delims=" %%a in ('powershell -command "(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"') do set "timestamp=%%a"

echo Timestamp: %timestamp%

:_main
echo Pulling...
git pull || (echo "Git pull 失败" && pause && exit /b 1)

echo Adding...
git add . || (echo "Git add 失败" && pause && exit /b 1)

echo Committing...
git commit -m "%timestamp%-S.bat" --no-verify || (echo "Git commit 失败" && pause && exit /b 1)

echo Pushing...
git push || (echo "Git push 失败" && pause && exit /b 1)

echo done

endlocal
pause
exit /b 0