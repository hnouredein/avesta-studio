@echo off
set ELECTRON_RUN_AS_NODE=
cd /d "%~dp0"
if not exist "desktop-app\node_modules\electron\dist\electron.exe" (
    pushd desktop-app
    call npm install --prefer-offline
    popd
)
start "Avesta Studio" "desktop-app\node_modules\electron\dist\electron.exe" "desktop-app"
