def pages(name, n=4):
    shot(name + '_p1')
    for i in range(2, n + 1):
        scroll_down(); shot('%s_p%d' % (name, i))
    for i in range(n): scroll_up()
def back(): adb('shell', 'input', 'keyevent', '4'); time.sleep(1)
def tab(name): tap(name, 2.5)
# ---- produce
tab('إنتاج'); pages('produce', 4)
for ident in ['الهوية المصرية', 'دولة التلاوة', 'غناوي هلنا']:
    tap(ident, 1); 
shot('produce_identity_picked')
# type a link
if tap('رابط الفيديو'):
    text('https://www.tiktok.com/@x/video/123'); time.sleep(1); back(); shot('produce_link_typed')
# drag hook box on stage
b = find('عنوان الهوك')
if b:
    cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
    swipe(cx, cy, cx, cy + 250, 700); shot('produce_dragged_hook')
for t in ['الترجمة', 'خاتمة الصلاة']: tap(t, 0.8)
shot('produce_toggled')
scroll_down(); scroll_down(); shot('produce_bottom')
tap('ابدأ الإنتاج', 3); shot('produce_dispatched'); dumpnames('after dispatch')
# ---- studio
tab('الاستوديو'); pages('studio_open', 2)
for sec in ['الترجمة والكابشن', 'الخطوط والهوية', 'القص والمدة', 'الصورة والألوان', 'الصوت والموسيقى', 'تعليق صوتي']:
    tap(sec, 0.8); shot('studio_' + sec[:6].replace(' ', '_')); tap(sec, 0.5)
tap('كلمة كلمة', 0.8); tap('أميري', 0.8); shot('studio_picked')
tab('الاستوديو'); shot('studio_after')
# ---- library
tab('فيديوهاتي'); time.sleep(4); pages('library', 2)
if tap('تشغيل', 12): shot('library_playing'); time.sleep(3); shot('library_playing2'); back()
tab('فيديوهاتي'); shot('library_after_play')
tap('حفظ', 3); shot('library_saved')
tap('🗑', 1.5); shot('library_delete_dialog'); tap('حذف', 3); tap('نعم', 3); shot('library_after_delete')
# ---- brand
tab('الهوية'); pages('brand', 3)
# ---- settings
tab('الإعدادات'); time.sleep(2); pages('settings', 3)
tap('ضيف للطابور', 2); shot('settings_queue_add')
