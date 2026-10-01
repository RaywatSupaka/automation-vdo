"""ADB-backed UI evidence. Coordinates must come from the current Android tree."""
import re
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path


class ReviewRequired(RuntimeError):
    pass


class DeviceUnavailable(ReviewRequired):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


class ShopeeDevice:
    package = 'com.shopee.th'

    def __init__(self, adb, identity, stop=None):
        if not adb.serial or not identity:
            raise ReviewRequired('กรุณาเลือกมือถือที่ยืนยันตัวตนแล้ว')
        self.adb, self.identity = adb, identity
        self.stop = stop
        self.verify()
        os.environ['ADBUTILS_ADB_PATH'] = str(adb.path.resolve())
        import uiautomator2 as u2
        self.ui = u2.connect(adb.serial)

    def verify(self):
        if self.stop and self.stop.is_set():
            raise ReviewRequired('พักคิวแล้ว • เก็บสถานะเดิมไว้')
        actual = self.adb.prop('ro.serialno')
        if not actual:
            raise ReviewRequired('มือถือไม่ตอบรับหรือพอร์ตเปลี่ยน • กดตรวจมือถือเพื่อเชื่อมเครื่องเดิมก่อนทำต่อ')
        if actual != self.identity:
            raise ReviewRequired('มือถือไม่ตรงกับเครื่องที่เลือก หยุดเพื่อป้องกันโพสต์ผิดเครื่อง')

    def foreground(self, timeout=8, stable_samples=1):
        # Android16/Samsung dumpsys activities can report a different resumed app.
        # The accessibility root represents the actual foreground window.
        deadline, stable, waiting = time.monotonic() + timeout, 0, False
        evidence = {}
        while True:
            self.verify()
            current = self.ui.info
            evidence = {'screen_on': current.get('screenOn'),
                        'foreground_package': str(current.get('currentPackageName') or ''),
                        'observed_at': time.time()}
            if current.get('screenOn') is False:
                raise DeviceUnavailable('หน้าจอมือถือปิดอยู่ • ปลดล็อกและเปิด Shopee ก่อนทำต่อ ยังไม่กดปุ่มใดเพิ่ม', evidence)
            ready = current.get('screenOn') is True and current.get('currentPackageName') == self.package
            stable = stable + 1 if ready else 0
            if stable >= max(stable_samples, 2 if waiting else 1):
                if waiting:
                    self._device_observation(False, 'มือถือกลับมาพร้อมแล้ว • ตรวจขั้นตอนเดิมต่อ', evidence)
                return current
            if not ready and not waiting:
                waiting = True
                self._device_observation(True, 'รอหน้า Shopee พร้อม • ยังไม่แตะหน้าจอหรือส่งซ้ำ', evidence)
            if time.monotonic() >= deadline:
                raise DeviceUnavailable('หน้า Shopee ยังไม่พร้อม • เปิด Shopee แล้วทำต่อจากคิวเดิม', evidence)
            if self.stop:
                if self.stop.wait(.25):
                    self.verify()
            else:
                time.sleep(.25)

    def _device_observation(self, waiting, message, evidence):
        callback = getattr(self, 'on_device_state', None)
        if callback:
            callback(waiting, message, evidence)

    def open(self):
        self.verify()
        current = self.ui.info
        if current.get('screenOn') is False:
            self.foreground(timeout=0)
        # Relaunching an already-visible app can interrupt an in-app transition.
        if getattr(self, '_shopee_closed', False) is True or current.get('currentPackageName') != self.package:
            self.ui.app_start(self.package)
        self.foreground(timeout=20, stable_samples=3)
        self._shopee_closed = False

    def profile_account(self):
        """Read the observed Me header, scrolling only its exact profile list."""
        deadline, scrolls = time.monotonic() + 15, 0
        while time.monotonic() < deadline:
            _, nodes = self.snapshot()
            labels = [n for n in nodes if n.get('package') == self.package
                      and n.get('resource-id') == 'labelUserName' and n.get('text', '').strip()]
            if len(labels) == 1:
                return labels[0]['text'].strip()
            if len(labels) > 1:
                raise ReviewRequired('พบชื่อบัญชีมากกว่าหนึ่งตำแหน่ง หยุดก่อนเลือกบัญชีผิด')
            lists = [n for n in nodes if n.get('package') == self.package
                     and n.get('resource-id') == self.package+':id/main_view' and n.get('scrollable') == 'true']
            profile = any(n.get('resource-id') in {'meCircleView', 'meCircleDisplayName'} for n in nodes)
            if profile and len(lists) == 1:
                if scrolls >= 6:
                    break
                self.foreground()
                self.ui(resourceId=self.package+':id/main_view').scroll.backward()
                scrolls += 1
                time.sleep(.6)
            else:
                time.sleep(.3)
        raise ReviewRequired('ยังอ่านชื่อบัญชีบนหน้า ฉัน ไม่ได้ • กรุณาเปิดส่วนบนของหน้า ฉัน ก่อนทำต่อ')

    def snapshot(self):
        self.verify(); self.foreground()
        xml = self.ui.dump_hierarchy(compressed=False)
        root = ET.fromstring(xml)
        return xml, [dict(n.attrib) for n in root.iter('node')]

    @staticmethod
    def center(bounds):
        values = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
        if not values:
            raise ReviewRequired('ตำแหน่งปุ่มไม่ถูกต้อง')
        x1,y1,x2,y2 = map(int, values.groups())
        if x2 <= x1 or y2 <= y1:
            raise ReviewRequired('ปุ่มยังไม่พร้อม')
        return (x1+x2)//2, (y1+y2)//2

    def find(self, **conditions):
        _, nodes = self.snapshot()
        return self.find_node(nodes, **conditions)

    @classmethod
    def find_node(cls, nodes, **conditions):
        found = [n for n in nodes if all(n.get(k)==v for k,v in conditions.items()) and n.get('enabled')=='true' and n.get('package')==cls.package and n.get('visible-to-user','true')=='true']
        if len(found) != 1:
            raise ReviewRequired('ยังระบุปุ่มเป้าหมายเดียวไม่ได้ กรุณาตรวจหน้ามือถือ')
        return found[0]

    def stable_target(self, timeout=20, **conditions):
        # Wi-Fi hierarchy reads can be slow. Time alone is not layout evidence:
        # still require the same in-screen bounds in three actual observations.
        deadline, previous, stable = time.monotonic() + timeout, None, 0
        samples, inside = 0, False
        while time.monotonic() < deadline:
            node = self.find(**conditions)
            samples += 1
            info = self.ui.info
            match = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
            bounds = tuple(map(int, match.groups())) if match else ()
            inside = bool(bounds and bounds[2] > bounds[0] and bounds[3] > bounds[1]
                          and bounds[2] <= info.get('displayWidth', 0) and bounds[3] <= info.get('displayHeight', 0))
            stable = stable + 1 if inside and node['bounds'] == previous else 0
            if stable >= 2:
                return node
            previous = node['bounds']
            if self.stop and self.stop.wait(.2):
                self.verify()
            elif self.stop is None:
                time.sleep(.2)
        reason = 'ยังอ่านหน้าจอไม่ครบ 3 ครั้ง' if samples < 3 else ('ปุ่มอยู่นอกจอ' if not inside else 'ตำแหน่งปุ่มยังเปลี่ยนอยู่')
        raise ReviewRequired('ยังไม่กด: '+reason+' • รอตรวจหน้าเดิม')

    def tap(self, **conditions):
        node = self.stable_target(**conditions)
        self._tap_node(node)

    def _tap_node(self, node):
        # uiautomator2 retries a JSON-RPC click after some transport failures.
        # Use one ADB input call instead, so a lost ACK can never double-Post.
        # Observed Samsung/Shopee sometimes ignores an instantaneous down/up.
        # A stationary 100ms touchscreen gesture releases once, with no movement,
        # second click or transport-level retry (also for the public Post).
        x, y = self.center(node['bounds'])
        result = self.adb.shell('input', 'touchscreen', 'swipe', str(x), str(y), str(x), str(y), '100', timeout=15)
        if result.returncode:
            raise ReviewRequired('ยังยืนยันการแตะไม่ได้ ตรวจหน้าปัจจุบันก่อน ห้ามกดซ้ำอัตโนมัติ')

    def commit_observed_post(self, observation, claim):
        """All phone reads precede the durable barrier; never retry the gesture.

        The final shared observation already checked identity, foreground, draft,
        options and target bounds. No slow target search is allowed after claim.
        A crash at/after claim remains ambiguous, even before ADB returns.
        """
        if time.monotonic() - observation['monotonic_at'] > 5:
            raise ReviewRequired('หลักฐานก่อนกดหมดความสด • ยังไม่เริ่มส่งโพสต์')
        node = self.find_node(observation['nodes'], **{
            'resource-id': 'com.shopee.th.dfpluginshopee16:id/btn_post', 'text': 'โพสต์'})
        if self.stop and self.stop.is_set():
            raise ReviewRequired('พักคิวแล้ว • ยังไม่เริ่มส่งโพสต์')
        claim()
        # Local guards only: a slow durable write or pause must not trigger a
        # stale gesture. The already-written intent stays protected as unknown.
        if time.monotonic() - observation['monotonic_at'] > 5 or self.stop and self.stop.is_set():
            raise ReviewRequired('พักก่อนแตะหลังบันทึกเจตนาส่ง • เก็บหลักฐานไว้ ไม่ส่งซ้ำ')
        # No automatic second tap, including a lost transport acknowledgement.
        self._tap_node(node)

    def wait(self, timeout=30, **conditions):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Foreground/identity/cancellation failures must not be swallowed.
            _, nodes = self.snapshot()
            hits = [n for n in nodes if n.get('package') == self.package and n.get('enabled') == 'true'
                    and all(n.get(k) == v for k,v in conditions.items())]
            if len(hits) == 1:
                return hits[0]
            time.sleep(.4)
        raise ReviewRequired('หน้าจอยังไม่ถึงขั้นที่ต้องการ หยุดตรวจโดยไม่กดซ้ำ')

    def hide_keyboard(self):
        _, nodes = self.snapshot()
        if any(n.get('resource-id') == 'android:id/input_method_nav_back' for n in nodes):
            self.ui.press('back')
            deadline, stable = time.monotonic() + 8, 0
            while time.monotonic() < deadline:
                _, nodes = self.snapshot()
                visible = any(n.get('resource-id') == 'android:id/input_method_nav_back' for n in nodes)
                stable = 0 if visible else stable + 1
                if stable >= 2:
                    return
                time.sleep(.25)
            raise ReviewRequired('แป้นพิมพ์ยังไม่ปิด • ยังไม่กดขั้นตอนถัดไปหรือกดย้อนกลับซ้ำ')

    def album(self, name):
        """Only scroll the observed folder list, never the video feed."""
        previous = None
        for _ in range(25):
            _, nodes = self.snapshot()
            matches = [n for n in nodes if n.get('text') == name and n.get('resource-id') == self.package+':id/tv_folder_name']
            if len(matches) == 1:
                self.tap(text=name, **{'resource-id': self.package+':id/tv_folder_name'})
                return
            self.find(**{'resource-id': self.package+':id/rv_folder'})
            signature = [(n.get('text'), n.get('bounds')) for n in nodes if n.get('resource-id') == self.package+':id/tv_folder_name']
            if signature == previous:
                break
            previous = signature
            self.ui(resourceId=self.package+':id/rv_folder').scroll.forward()
            time.sleep(.6)  # Let the Android fling finish before binding bounds.
        raise ReviewRequired('ยังไม่พบอัลบั้มของงานนี้ ไม่เลือกไฟล์จากลำดับล่าสุด')

    def set_text(self, value, **conditions):
        node = self.find(**conditions)
        if node.get('class') != 'android.widget.EditText':
            raise ReviewRequired('เป้าหมายไม่ใช่ช่องกรอกข้อความ')
        selector = {'resourceId':node['resource-id']} if node.get('resource-id') else {'className':node['class'], 'text':node.get('text','')}
        target = self.ui(**selector)
        target.set_text(value)
        # React Native input without a resource ID changes its text selector
        # immediately after setText. Re-query the new value instead of waiting
        # for the now-nonexistent placeholder selector.
        if node.get('resource-id'):
            actual = self.find(**{'resource-id': node['resource-id']})
        else:
            actual = self.find(**{'class': node['class'], 'text': value})
        if actual.get('text') != value:
            raise ReviewRequired('ข้อความที่กรอกไม่ตรงกับต้นฉบับ หยุดก่อนโพสต์')

    def capture(self, folder, name='screen'):
        xml, nodes = self.snapshot()
        folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
        (folder / (name+'.xml')).write_text(xml, encoding='utf-8')
        self.ui.screenshot().save(folder / (name+'.png'))
        return nodes

    def close(self):
        self.ui.stop_uiautomator()

    def observe_controls(self, resources, validate=None, previous=None):
        """Share 3 hierarchies + 2 screenshots across the observed controls.

        A final guard extends an existing stable proof with 2 fresh hierarchies
        surrounding 1 screenshot. It must match that proof, never stale pixels.
        Observations are ephemeral and cannot be restored from queue JSON.
        """
        allowed = {'allow_reuse_toggle', 'allow_duet_toggle', 'allow_stitch_toggle', 'ai_generated_toggle', 'iv_whatsapp', 'iv_facebook'}

        def read():
            xml, nodes = self.snapshot()
            resolved = resources(nodes) if callable(resources) else resources
            if not resolved or len(set(resolved)) != len(resolved) or any(r.rsplit('/', 1)[-1] not in allowed for r in resolved):
                raise ReviewRequired('ไม่รองรับการตรวจสวิตช์ชุดนี้')
            targets = {r: self.find_node(nodes, **{'resource-id': r})['bounds'] for r in resolved}
            context = validate(xml, nodes) if validate else None
            return xml, nodes, targets, context

        xml, nodes, targets, context = read()
        if previous and (targets != previous['targets'] or context != previous['context']):
            raise ReviewRequired('หน้าส่งเปลี่ยนระหว่างตรวจ • ยังไม่เริ่มส่งโพสต์')
        values = previous['values'] if previous else None
        for _ in range(1 if previous else 2):
            shot_at = time.monotonic()
            shot = self.ui.screenshot().convert('RGB')
            xml, nodes, current, current_context = read()
            if current != targets or current_context != context:
                raise ReviewRequired('หน้าจอขยับระหว่างตรวจสวิตช์ • ยังไม่โพสต์')
            sample = {}
            for resource, bounds in targets.items():
                self.center(bounds)  # Reject malformed, negative or empty bounds.
                x1, y1, x2, y2 = map(int, re.findall(r'\d+', bounds))
                if x2 > shot.width or y2 > shot.height:
                    raise ReviewRequired('สวิตช์อยู่นอกหน้าจอ • ยังไม่โพสต์')
                sample[resource] = self.classify_control(shot.crop((x1, y1, x2, y2)), resource.rsplit('/', 1)[-1])
            if any(v is None for v in sample.values()) or values is not None and sample != values:
                raise ReviewRequired('อ่านสถานะสวิตช์ไม่ชัดหรือกำลังเปลี่ยน • ยังไม่โพสต์')
            values = sample
        return dict(values=values, targets=targets, context=context, xml=xml, nodes=nodes,
                    image=shot, checked_at=time.time(), monotonic_at=shot_at)

    @staticmethod
    def save_observation(observation, folder, name):
        # Reuse exactly the pixels/tree already validated, without another read.
        folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
        (folder / (name + '.xml')).write_text(observation['xml'], encoding='utf-8')
        observation['image'].save(folder / (name + '.png'))

    def visual_green(self, resource):
        """Observed Shopee custom switches do not expose checked in accessibility.

        Restrict color proof to these exact observed controls; unknown themes stop.
        """
        control = resource.rsplit('/', 1)[-1]
        if control not in {'allow_reuse_toggle', 'allow_duet_toggle', 'allow_stitch_toggle', 'ai_generated_toggle', 'iv_whatsapp', 'iv_facebook'}:
            raise ReviewRequired('ไม่รองรับการตรวจสวิตช์นี้')
        node = self.stable_target(**{'resource-id': resource})
        results = []
        for _ in range(2):
            bounds = list(map(int, re.findall(r'\d+', node['bounds'])))
            shot = self.ui.screenshot().convert('RGB')
            if bounds[2] > shot.width or bounds[3] > shot.height or self.find(**{'resource-id': resource})['bounds'] != node['bounds']:
                raise ReviewRequired('หน้าจอขยับระหว่างตรวจสวิตช์')
            crop = shot.crop(tuple(bounds))
            results.append(self.classify_control(crop, control))
            time.sleep(.15)
        if results[0] is None or results[0] != results[1]:
            raise ReviewRequired('อ่านสถานะสวิตช์ไม่ชัดหรือกำลังเปลี่ยน • ยังไม่โพสต์')
        return results[0]

    @staticmethod
    def classify_control(crop, control):
        """Three-state screenshot proof; blank/occluded/unknown is not OFF."""
        pixels = list(crop.getdata())
        if not pixels or crop.width < 12 or crop.height < 12:
            return None
        def green(px):
            return sum(g > 120 and g > r*1.35 and g > b*1.15 for r,g,b in px)/len(px)
        if control.endswith('_toggle'):
            if not 1.3 < crop.width/crop.height < 2.8:
                return None
            def patch(x):
                return list(crop.crop((int(crop.width*(x-.09)),int(crop.height*.35),
                                       int(crop.width*(x+.09)),int(crop.height*.65))).getdata())
            left, right = patch(.25), patch(.75)
            def white(px):
                return sum(min(rgb)>242 and max(rgb)-min(rgb)<15 for rgb in px)/len(px)
            gray_right = sum(150 < min(rgb) < 240 and max(rgb)-min(rgb)<18 for rgb in right)/len(right)
            if green(left) > .8 and white(right) > .8:
                return True
            if white(left) > .8 and gray_right > .8 and green(pixels) < .02:
                return False
            return None
        if green(pixels) > .20:
            return True
        gray = sum(max(rgb)-min(rgb)<18 for rgb in pixels)/len(pixels)
        contrast = sum(100 < min(rgb) < 240 for rgb in pixels)/len(pixels)
        if gray > .92 and .02 < contrast < .95:
            return False
        return None
