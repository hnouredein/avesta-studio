# Avesta AI Video Studio — Portable Complete Package (Telegram / Server Ready)

## 1. المتطلبات الأساسية (System Requirements)
- Python 3.10+
- Node.js 22+
- FFmpeg + FFprobe in PATH
- Google Chrome (for HyperFrames rendering)

## 2. التثبيت لمرة واحدة (One-Time Setup)
`ash
pip install -r requirements.txt
`
(اختياري لتشغيل تطبيق الديسكتوب Electron فقط):
`ash
cd desktop-app && npm install
`

## 3. التشغيل التلقائي من بوت تليجرام (Headless 1-Command Auto-Edit)
عند استقبال فيديو من تليجرام:
1. احفظ الفيديو في: ideos/<job_id>/input.mp4
2. (اختياري) أنشئ ideos/<job_id>/settings.json بأي إعدادات مخصصة (أو سيعمل تلقائياً بالإعدادات الافتراضية في studio/brand-config.json والقصّ الذكي التلقائي).
3. شغّل الأمر:
`ash
python scripts/auto_edit.py videos/<job_id> --mode full
`
4. النتيجة الجاهزة للإرسال لتليجرام:
   - الفيديو النهائي: ideos/<job_id>/output.mp4
   - صورة الغلاف: ideos/<job_id>/cover.png
   - الكابشن والهاشتاجات: ideos/<job_id>/post.txt

## 4. تشغيل واجهة الاستوديو والـ API
`ash
node studio/server.mjs
`
يعمل على: http://localhost:3456
