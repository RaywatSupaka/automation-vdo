"""One count contract for newly submitted product stories and queue edits."""
def product_scene_count(value=None):
    if value is None or value == '':
        return 3
    if isinstance(value, bool) or not (isinstance(value, int) or isinstance(value, str) and value.isdecimal()):
        raise ValueError('จำนวนฉากสินค้าต้องเป็นจำนวนเต็ม 3–15')
    count = int(value)
    if not 3 <= count <= 15:
        raise ValueError('จำนวนฉากสินค้าต้องอยู่ระหว่าง 3–15')
    return count
