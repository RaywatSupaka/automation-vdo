"""Recognize only observed Shopee settings; missing is never equivalent to OFF."""
from core.shopee_posting.device import ReviewRequired, ShopeeDevice

P = 'com.shopee.th.dfpluginshopee16:id/'
COMBINED = ('allow_reuse_toggle', 'tv_allow_reuse', 'อนุญาตให้นำเนื้อหาไปใช้ซ้ำหรือเผยแพร่ต่อ')
SPLIT = (('allow_duet_toggle', 'tv_allow_duet', 'อนุญาตให้ Duet'),
         ('allow_stitch_toggle', 'tv_allow_stitch', 'อนุญาตให้ตัดต่อ'))
AI = ('ai_generated_toggle', 'tv_ai_generated_title', 'ครีเอเตอร์เพิ่มป้ายกำกับ AI ไปยังเนื้อหานี้')
SHARES = ('iv_whatsapp', 'iv_facebook')


class SettingsNotReady(ReviewRequired):
    """Incomplete known layout: only passive, bounded reads may retry."""


def detect_layout(nodes):
    own = [n for n in nodes if n.get('package') == ShopeeDevice.package]
    def present(resource):
        return any(n.get('resource-id') == P+resource for n in own)
    def require(resource, text=None):
        if not present(resource):
            raise SettingsNotReady('SHOPEE_SETTINGS_NOT_READY • ยังไม่พบเมนู: '+resource+' • ยังไม่โพสต์')
        conditions = {'resource-id': P+resource}
        if text is not None:
            conditions['text'] = text
        try:
            # Hidden/disabled/duplicate nodes are not a supported alternative.
            if sum(n.get('resource-id') == P+resource for n in own) != 1:
                raise ReviewRequired('duplicate')
            return ShopeeDevice.find_node(own, **conditions)
        except ReviewRequired as exc:
            raise ReviewRequired('SHOPEE_SETTINGS_REVIEW • เมนูไม่ชัดหรือไม่พร้อม: '+resource+' • ยังไม่โพสต์') from exc

    combined = any(present(r) for r in COMBINED[:2])
    split = any(present(r) for control in SPLIT for r in control[:2])
    if combined and split:
        raise ReviewRequired('SHOPEE_SETTINGS_REVIEW • พบสวิตช์ใช้ซ้ำสองรูปแบบพร้อมกัน • ยังไม่โพสต์')
    # Absence is accepted only on the positively identified native composer,
    # never a loading/foreign page. A half-present control remains incomplete.
    require('et_caption'); require('btn_post','โพสต์'); require('tv_product_title')
    controls = (COMBINED,) if combined else tuple(c for c in SPLIT if any(present(r) for r in c[:2]))
    for control, label, text in controls:
        require(control); require(label, text)
    ai_available = any(present(r) for r in AI[:2])
    if ai_available:
        require(AI[0]); require(AI[1], AI[2])
    for resource in SHARES:
        require(resource)
    return dict(layout='combined_reuse' if combined else 'split_duet_stitch' if split else 'no_reuse_controls',
                reuse_controls=[c[0] for c in controls], ai_label_available=ai_available,
                resources=[P+c[0] for c in controls]+([P+AI[0]] if ai_available else [])+[P+r for r in SHARES])
