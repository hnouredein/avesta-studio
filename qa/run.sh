#!/bin/bash
set -x
cd qa
adb install -r app-debug.apk
true
adb shell wm size
true
timeout -k 5 1500 python3 -u "$1" 2>&1 | tee walk.log
curl -s localhost:18089/__log | python3 -c "import sys,json;d=json.load(sys.stdin);print('SERVERLOG',d['log'][-60:]);print('BODIES',[b[:900] for b in d['bodies']])" | tee -a walk.log
