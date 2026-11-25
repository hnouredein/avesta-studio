def back(): adb('shell', 'input', 'keyevent', '4'); time.sleep(1)
def bounds(txt):
    return find(txt)
def tapxy(x, y, wait=1.2): adb('shell', 'input', 'tap', str(x), str(y)); time.sleep(wait)
def center(b): return ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
def chip(name): return tap(name, 1.5)
def fgcheck():
    if not find('إنتاج'):
        adb('shell', 'am', 'start', '-n', PKG + '/.MainActivity'); time.sleep(2)
def typein(hint, s, wait=1.0):
    b = find(hint)
    if not b: print('MISSING field', hint, flush=True); return False
    tapxy(*center(b), 0.6); text(s); time.sleep(wait); back(); return True
def drag_el(txt, dy, name):
    b = find(txt)
    if not b: print('MISSING el', txt, flush=True); return
    x, y = center(b); swipe(x, y, x, y + dy, 600); shot(name)

# ---- editor: preview + selection
shot('editor_start')
b = find('عنوان الهوك'); print('HOOKBOUNDS', b, flush=True)
tapxy(*center(b)) if b else None; shot('select_hook')
# type hook text, preview must update
b = find('عنوان الهوك (اختياري)')
if b:
    tapxy(*center(b), 0.6); text('Hello_Hook'); time.sleep(0.8); back(); shot('hook_text_typed')
for ft in ['أميري', 'لالزار']:
    if tap(ft, 1.2, 0): shot('hook_font_' + ft)
drag_el('Hello_Hook', 500, 'hook_dragged_down')
# colors
b = find('اتركه فاضي للافتراضي')
if b:
    tapxy(*center(b), 0.6); text('#2255AA'); time.sleep(0.5); back(); shot('hook_color_typed')
# captions
chip('💬 الترجمة'); shot('captions_panel')
chip('كلمة كلمة'); shot('captions_wordbyword')
chip('صندوق'); shot('captions_box')
tap('خط الترجمة', 0.5, 0)
# cta
chip('📣 الخاتمة'); shot('cta_panel')
# logo + identities
chip('🏷️ الهوية'); shot('logo_panel')
if tap('الهوية المصرية', 1.5): shot('identity_egy_selected')
tap('دولة', 1.5); shot('identity_dawla')
# hide via right toggle
tap('ظاهر', 1.2); shot('toggle_hidden')
tap('مخفي', 1.2)
# video / audio
chip('✂️ الفيديو'); shot('video_panel')
scroll_down(); shot('video_panel2'); scroll_up()
chip('🎧 الصوت'); shot('audio_panel')
# source
chip('🔗 المصدر'); shot('source_panel')
chip('English'); chip('سريع')
# dispatch
typein('الصق رابط', 'https://www.tiktok.com/@x/video/123', 0.5); shot('url_typed')
tap('إنتاج ▶', 3); shot('dispatched')
# videos sheet
tap('🎞️', 4); shot('videos_sheet')
if tap('تشغيل', 14): shot('playing'); time.sleep(3); shot('playing2'); back()
tap('حفظ', 3); shot('saved')
tap('🗑', 1.5); shot('delete_dialog'); tap('حذف', 3); shot('after_delete')
back(); time.sleep(1)
# settings
tap('⚙️', 2.5); shot('settings_1')
scroll_down(); shot('settings_2'); scroll_down(); shot('settings_3'); scroll_up(); scroll_up()
# auto mode write, no token prompt
tap('تشغيل الوضع التلقائي', 6); shot('auto_toggled')
b = find('الصق روابط')
if b:
    tapxy(*center(b), 0.6); text('https://youtu.be/abc'); back(); tap('ضيف للطابور', 7); shot('queue_added')
back(); time.sleep(1)
# identity editor
chip('🏷️ الهوية'); tap('تعديل بيانات الهوية', 2.5); shot('brand_editor_1')
b = find('اسم الهوية')
scroll_down(); shot('brand_editor_2')
if tap('حفظ الهوية', 9, 3): shot('brand_saved')
back(); time.sleep(1)
# add identity
chip('🏷️ الهوية')
if tap('هوية جديدة', 2): shot('add_identity_dialog'); text('NewId'); time.sleep(0.5); shot('add_identity_typed'); tap('حفظ', 9); shot('add_identity_saved')
shot('final')
