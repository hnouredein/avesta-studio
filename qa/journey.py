from walk import *
import json
adb('shell', 'am', 'force-stop', PKG)
adb('shell', 'am', 'start', '-n', PKG + '/.MainActivity', '--es', 'api_base', 'http://10.0.2.2:18089', '--es', 'token', 'READ', '--es', 'wtoken', 'WRITE')
time.sleep(6); shot('launch'); dumpnames('launch')
exec(open('steps.py').read())
