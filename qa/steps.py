# v3 smoke steps (replaced for v4)
for tab in ['المكتبة', 'الهويات', 'إنتاج']:
    tap(tab, 3); shot('tab_' + tab); dumpnames(tab)
