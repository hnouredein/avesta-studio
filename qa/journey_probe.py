from walk import *
adb('shell','am','force-stop',PKG)
adb('shell','am','start','-n',PKG+'/.MainActivity','--es','api_base','http://10.0.2.2:18089','--es','token','READ')
time.sleep(7); shot('launch')
for t,b,c,k in nodes(): print('NODE',repr(t[:40]),b,c,k,flush=True)
