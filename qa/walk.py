import subprocess, re, time, sys, os, xml.etree.ElementTree as ET
OUT = sys.argv[1] if len(sys.argv) > 1 else 'shots'; os.makedirs(OUT, exist_ok=True)
PKG = 'com.ghenawi.helna'; n = [0]
def adb(*a, **k): return subprocess.run(['adb'] + list(a), capture_output=True, **k)
def shot(name):
    n[0] += 1; p = '%s/%02d_%s.png' % (OUT, n[0], name)
    open(p, 'wb').write(adb('exec-out', 'screencap', '-p').stdout); print('shot', p, flush=True)
def dump():
    for _ in range(3):
        r = adb('exec-out', 'uiautomator', 'dump', '/dev/tty').stdout.decode('utf8', 'ignore')
        i = r.find('<?xml'); j = r.rfind('</hierarchy>')
        if i >= 0 and j > 0:
            try: return ET.fromstring(r[i:j + 12])
            except Exception: pass
        time.sleep(1)
    return None
def nodes():
    t = dump(); out = []
    if t is None: return out
    for e in t.iter('node'):
        m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', e.get('bounds', ''))
        if m: out.append((e.get('text', '') or e.get('content-desc', ''), tuple(map(int, m.groups())), e.get('class', ''), e.get('clickable')))
    return out
def find(txt, ns=None):
    for t, b, c, k in (ns or nodes()):
        if txt in t: return b
def tap(txt, wait=1.2):
    b = find(txt)
    if not b: print('MISSING', txt, flush=True); return False
    adb('shell', 'input', 'tap', str((b[0] + b[2]) // 2), str((b[1] + b[3]) // 2)); time.sleep(wait); return True
def swipe(x1, y1, x2, y2, ms=500): adb('shell', 'input', 'swipe', str(x1), str(y1), str(x2), str(y2), str(ms)); time.sleep(0.8)
def text(s): adb('shell', 'input', 'text', s)
def scroll_down(): swipe(540, 1700, 540, 600); 
def scroll_up(): swipe(540, 600, 540, 1700)
def dumpnames(tag):
    print('--- UI', tag, [t for t, b, c, k in nodes() if t][:60], flush=True)
