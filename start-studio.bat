@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting Avesta AI Video Studio UI...
start "" http://localhost:3456
node studio\server.mjs
pause

