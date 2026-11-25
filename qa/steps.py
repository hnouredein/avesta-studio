def pages(name, n=4):
    shot(name + '_p1')
    for i in range(2, n + 1):
        scroll_down(); shot('%s_p%d' % (name, i))
    for i in range(n): scroll_up()
def top():
    for i in range(6): scroll_up()
def back(): adb('shell', 'input', 'keyevent', '4'); time.sleep(1)
TABX={'إنتاج':.9,'الاستوديو':.7,'فيديوهاتي':.5,'الهوية':.3,'الإعدادات':.1}
def tab(name):
    adb('shell','input','tap',str(int(1080*TABX[name])),'2260'); time.sleep(1.5); adb('shell','input','tap',str(int(1080*TABX[name])+3),'2262'); time.sleep(2)
def fg():
    # make sure the app is in front
    if not find('إنتاج') and not find('الاستوديو'):
        adb('shell', 'am', 'start', '-n', PKG + '/.MainActivity'); time.sleep(2)
# ---- produce
tab('إنتاج'); pages('produce', 4)
top()
tap('الهوية المصرية', 1.5); shot('produce_identity_egy')
tap('دولة', 1.5); tap('هلنا', 1.5); shot('produce_identity_back')
if tap('رابط الفيديو'):
    text('https://www.tiktok.com/@x/video/123'); time.sleep(1); back(); shot('produce_link_typed')
tap('قيد', 0.1)
scroll_down(); scroll_down(); shot('produce_scrolled')
b = find('عنوان الهوك')
if b:
    cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
    swipe(cx, cy, cx, cy + 220, 700); shot('produce_dragged_hook')
tap('الترجمة', 0.8, 0); tap('الصلاة', 0.8)
shot('produce_toggled')
tap('ابدأ الإنتاج', 3, 6); shot('produce_dispatched'); dumpnames('after dispatch')
# ---- studio
tab('الاستوديو'); pages('studio_open', 2)
for sec in ['الترجمة والكابشن', 'الخطوط والهوية', 'القص والمدة', 'الصورة والألوان', 'الصوت والموسيقى', 'تعليق صوتي']:
    if tap(sec, 0.8, 8): shot('studio_' + sec[:6].replace(' ', '_'))
    scroll_down()
tap('كلمة كلمة', 0.8, 3); shot('studio_picked')
# ---- library
fg(); tab('فيديوهاتي'); time.sleep(4); pages('library', 2)
if tap('تشغيل', 14): shot('library_playing'); time.sleep(3); shot('library_playing2'); back()
fg(); tab('فيديوهاتي'); time.sleep(1); shot('library_after_play')
tap('حفظ', 3); shot('library_saved')
tap('🗑', 1.5); shot('library_delete_dialog'); tap('حذف', 3); shot('library_after_delete')
# ---- brand
fg(); print('BAR',[(t,b) for t,b,c,k in nodes() if 'الهوية' in t or 'فيديوهاتي' in t], flush=True); tab('الهوية'); time.sleep(1); print('AFTER',[(t,b) for t,b,c,k in nodes() if 'الهوية' in t][:6], flush=True); print('LOGCAT', adb('shell','logcat','-d','-s','AndroidRuntime:E').stdout.decode('utf8','ignore')[-3000:], flush=True); pages('brand', 3)
# ---- settings
fg(); tab('الإعدادات'); time.sleep(2); pages('settings', 3)
