from walk import *
adb('shell', 'am', 'force-stop', PKG)
adb('shell', 'am', 'start', '-n', PKG + '/.MainActivity', '--es', 'api_base', 'http://10.0.2.2:18089', '--es', 'token', 'READ')
time.sleep(7); shot('launch')
TABY = 1284
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
swipe(540, 1800, 540, 800, 500); shot('settings_2')
back(); time.sleep(1); shot('final')
