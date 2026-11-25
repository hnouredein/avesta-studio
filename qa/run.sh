#!/bin/bash
set -x
cd qa
adb install -r app-debug.apk
[ -f old.apk ] && adb install -r old.apk
adb shell wm size
adb push out.mp4 /sdcard/Download/test.mp4
timeout -k 5 1500 python3 -u "$1" 2>&1 | tee walk.log
curl -s localhost:18089/__log | python3 -c "import sys,json;d=json.load(sys.stdin);print('SERVERLOG',d['log'][-60:]);print('BODIES',[b[:900] for b in d['bodies']])" | tee -a walk.log
