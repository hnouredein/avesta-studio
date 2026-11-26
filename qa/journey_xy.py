from walk import *
adb('shell', 'am', 'force-stop', PKG)
adb('shell', 'am', 'start', '-n', PKG + '/.MainActivity', '--es', 'api_base', 'http://10.0.2.2:18089', '--es', 'token', 'READ')
time.sleep(7); shot('launch')
TABY = 1284
def back(): adb('shell','input','keyevent','4'); time.sleep(1)
def swipe(x1,y1,x2,y2,ms=500): adb('shell','input','swipe',str(x1),str(y1),str(x2),str(y2),str(ms)); time.sleep(0.8)
def text(s): adb('shell','input','text',s)
def tapxy(x, y, wait=1.2): adb('shell','input','tap',str(x),str(y)); time.sleep(wait)

# preview select hook
tapxy(540, 444, 1.5); shot('select_hook')
# type hook text in the field
tapxy(540, 1560, 1.0); text('Hello_Hook'); time.sleep(1); back(); shot('hook_typed')
# tabs visible: source, hook, captions, cta
tapxy(450, TABY, 1.5); shot('tab_captions')
tapxy(195, TABY, 1.5); shot('tab_cta')
tapxy(936, TABY, 1.5); shot('tab_source')
# reveal more tabs
swipe(200, TABY, 950, TABY, 500); shot('tabs_scrolled_1')
tapxy(540, TABY, 1.5); shot('tab_mid1')
tapxy(200, TABY, 1.5); shot('tab_left')
swipe(900, TABY, 100, TABY, 500); shot('tabs_scrolled_back')
tapxy(540, TABY, 1.5); shot('tab_mid2')
# panel scroll
swipe(540, 1800, 540, 1500, 400); shot('panel_scrolled')
# link + produce
tapxy(330, 2244, 0.8); text('https://www.tiktok.com/@x/video/123'); time.sleep(1); back(); shot('url_typed')
tapxy(921, 2244, 4); shot('dispatched')
# videos sheet
tapxy(234, 201, 4); shot('videos_sheet')
back(); time.sleep(1)
# settings
tapxy(102, 201, 2.5); shot('settings_1')
tapxy(156, 821, 9); shot('auto_toggled')
swipe(540, 1800, 540, 800, 500); shot('settings_2')
back(); time.sleep(1); shot('after_settings')
swipe(200, TABY, 950, TABY, 500)
tapxy(540, TABY, 1.5); shot('brand_tab')
tapxy(536, 1925, 2.5); shot('brand_editor_1')
swipe(540, 1800, 540, 900, 500); shot('brand_editor_2')
swipe(540, 1800, 540, 900, 500); shot('brand_editor_3')
shot('final')
