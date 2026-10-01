"""User-initiated Android Wi-Fi pairing. No upload, app launch or posting."""
import copy
from contextlib import contextmanager
import ipaddress
import os
import re
import subprocess
import threading
import time

from core.cancellable_process import hidden_process_kwargs


class WifiError(RuntimeError):
    """Only fixed, user-safe messages may leave the ADB boundary."""


def endpoint(value):
    value = str(value or '').strip()
    try:
        host, port = value.rsplit(':', 1)
        address = ipaddress.IPv4Address(host)
        networks = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16')
        if not any(address in ipaddress.IPv4Network(n) for n in networks):
            raise ValueError()
        if not re.fullmatch(r'[0-9]{1,5}', port) or not 1 <= int(port) <= 65535:
            raise ValueError()
    except (ValueError, TypeError):
        raise WifiError('กรอก IPv4:พอร์ต ของมือถือในเครือข่ายภายใน เช่น 192.168.1.103:35157') from None
    return f'{address}:{int(port)}'


def parse_services(output):
    services = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 3 or parts[1] not in ('_adb-tls-pairing._tcp', '_adb-tls-connect._tcp'):
            continue
        if not re.fullmatch(r'[\w.-]{1,200}', parts[0], re.ASCII):
            continue
        try:
            address = endpoint(parts[2])
        except WifiError:
            continue
        row = {'name': parts[0], 'kind': 'pairing' if 'pairing' in parts[1] else 'connect', 'endpoint': address}
        if row not in services:
            services.append(row)
    return services


class AndroidWifi:
    def __init__(self, adb, saved_identity='', save_selection=None, notify=None):
        self.adb = adb
        self.saved_identity = str(saved_identity or '')
        self.save_selection = save_selection or (lambda serial, identity: None)
        self.notify = notify or (lambda message, connected: None)
        self._lock = threading.RLock()
        self._operation = threading.Lock()
        self._thread = None
        self._state = dict(busy=False, phase='idle', message='กดตรวจมือถือเพื่ออ่านสถานะล่าสุด',
                           error='', checked_at=0, devices=[], services=[], selected=None,
                           paired_endpoint='', discovery_warning='')

    def state(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def _set(self, **values):
        with self._lock:
            self._state.update(values)

    def _run(self, *args, code=None, timeout=12):
        if not self.adb.path.is_file():
            raise WifiError('ไม่พบ ADB ในโปรแกรม กรุณาตรวจไฟล์ติดตั้งหรือการตั้งค่า ADB')
        env = os.environ.copy()
        env.pop('ADB_TRACE', None)  # Do not enable credential-bearing ADB diagnostics.
        try:
            result = subprocess.run([str(self.adb.path), *args], input=(code + '\n') if code else None,
                                    capture_output=True, text=True, encoding='utf-8', errors='replace',
                                    timeout=timeout, env=env, **hidden_process_kwargs())
        except subprocess.TimeoutExpired:
            raise WifiError('มือถือยังไม่ตอบรับ กรุณาตรวจหน้าจอและเครือข่าย แล้วกดตรวจมือถือก่อนลองใหม่') from None
        except (OSError, ValueError):
            raise WifiError('เรียก ADB ไม่สำเร็จ กรุณาตรวจไฟล์ติดตั้งและสิทธิ์ของโปรแกรม') from None
        # Never return raw pairing output/errors, even when adb unexpectedly echoes stdin.
        if code:
            text = result.stdout or ''
            match = re.search(r'Successfully paired to ([0-9.:]+) \[guid=([\w.-]+)\]', text)
            if result.returncode or not match or match[1] != args[-1]:
                raise WifiError('จับคู่ไม่สำเร็จ ตรวจพอร์ตจับคู่และรหัสใหม่ โดยเปิดหน้าต่างรหัสบนมือถือค้างไว้')
            return match[2]
        if result.returncode:
            raise WifiError('ADB ตรวจอุปกรณ์ไม่สำเร็จ ตรวจการเชื่อมต่อและการอนุญาตบนมือถือ')
        return result.stdout or ''

    def _discover(self):
        try:
            services = parse_services(self._run('mdns', 'services', timeout=6))
            self._set(services=services, discovery_warning='')
        except WifiError:
            services = []
            self._set(services=[], discovery_warning='ค้นหาอัตโนมัติไม่ได้ ยังสามารถกรอก IP และพอร์ตเองได้')
        return services

    def _devices(self, services):
        output = self._run('devices', '-l')
        rows = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[1] not in ('device', 'offline', 'unauthorized'):
                continue
            serial, status = parts[:2]
            if not re.fullmatch(r'[\w.:\[\]-]{1,240}', serial, re.ASCII):
                continue
            service = next((s for s in services if s['kind'] == 'connect' and
                            serial in (s['endpoint'], s['name'] + '._adb-tls-connect._tcp')), None)
            key = service['name'] if service else serial
            row = next((r for r in rows if r['key'] == key and r['state'] == status), None)
            if row:
                row['aliases'].append(serial)
                if serial == self.adb.serial:
                    row['serial'] = serial
                continue
            model = next((x[6:].replace('_', ' ') for x in parts if x.startswith('model:')), 'Android')
            rows.append(dict(key=key, serial=serial, aliases=[serial], state=status, model=model,
                             transport='Wi-Fi' if service or ':' in serial or '._adb-tls-' in serial else 'USB'))
        self._set(devices=rows)
        return rows

    def _probe(self, serial):
        def read(*args):
            return self._run('-s', serial, 'shell', *args, timeout=6).strip()
        identity = read('getprop', 'ro.serialno')
        model = read('getprop', 'ro.product.model')
        if not identity or identity.lower() in ('unknown', 'null') or not model:
            raise WifiError('ยังยืนยันตัวตนมือถือไม่ได้ กรุณาปลดล็อกแล้วตรวจใหม่')
        android = read('getprop', 'ro.build.version.release')
        try:
            shopee = read('pm', 'path', 'com.shopee.th').startswith('package:')
        except WifiError:
            shopee = False
        return dict(serial=serial, device_id=identity, model=model, android=android, shopee_installed=shopee)

    @contextmanager
    def verified_device(self):
        """Legacy manual tools must not run during pairing or against a recycled IP."""
        if not self._operation.acquire(blocking=False):
            raise WifiError('กำลังตรวจหรือจับคู่มือถือ กรุณารอให้เสร็จก่อน')
        try:
            state = self.state()
            if state['phase'] != 'connected' or not state['selected']:
                raise WifiError('กรุณาตรวจและเลือกมือถือในหน้าโพสนายหน้า Shopee ก่อน')
            selected = state['selected']
            try:
                actual = self._probe(selected['serial'])
            except WifiError:
                self._set(selected=None, phase='disconnected', message='มือถือไม่ตอบรับหรือพอร์ตเปลี่ยน กดตรวจมือถือก่อนทำต่อ')
                raise
            if actual['device_id'] != selected['device_id']:
                self._set(selected=None, phase='disconnected')
                raise WifiError('มือถือไม่ตรงกับเครื่องที่เลือก หยุดคำสั่งและตรวจเครื่องใหม่ก่อน')
            from core.adb_manager import AdbManager
            yield AdbManager(self.adb.path, selected['serial'], self.adb.root)
        finally:
            self._operation.release()

    def _choose(self, serial, services=None, expected_identity=''):
        rows = self._devices(services if services is not None else self._discover())
        row = next((r for r in rows if serial in r['aliases']), None)
        if not row or row['state'] != 'device':
            raise WifiError('เครื่องที่เลือกยังไม่พร้อม กรุณาปลดล็อกและอนุญาต Debugging บนมือถือ')
        selected = self._probe(serial)
        if expected_identity and selected['device_id'] != expected_identity:
            raise WifiError('ที่อยู่นี้เป็นมือถือคนละเครื่องกับที่บันทึกไว้ กรุณาตรวจสอบแล้วเลือกเครื่องใหม่เอง')
        try:
            self.save_selection(serial, selected['device_id'])
        except Exception:
            raise WifiError('เชื่อมต่อมือถือได้ แต่บันทึกเครื่องที่เลือกไม่สำเร็จ กรุณาตรวจพื้นที่เก็บข้อมูล') from None
        self.adb.serial, self.saved_identity = serial, selected['device_id']
        self._set(selected=selected, phase='connected', error='', checked_at=time.time(),
                  message=f"เชื่อมต่อ {selected['model']} แล้ว • ตรวจสอบตัวเครื่องสำเร็จ • ยังไม่ได้โพสต์")

    def _refresh(self):
        services = self._discover()
        rows = self._devices(services)
        serial = self.adb.serial
        row = next((r for r in rows if serial in r['aliases']), None)
        if row and row['state'] == 'device':
            selected = self._probe(serial)
            if self.saved_identity and selected['device_id'] != self.saved_identity:
                raise WifiError('ที่อยู่เดิมเป็นมือถือคนละเครื่อง กรุณาเลือกมือถือใหม่ก่อนใช้งาน')
            self._set(selected=selected, phase='connected', checked_at=time.time(), error='',
                      message=f"เชื่อมต่อ {selected['model']} แล้ว • ยังไม่ได้โพสต์")
        else:
            if self._recover_connected_identity(services, rows):
                return
            message = ('เครื่องที่เลือกไม่ได้เชื่อมต่อ กรุณาเชื่อมต่อหรือเลือกเครื่องเอง' if serial else
                       'เลือกมือถือจากรายการด้านล่าง หรือจับคู่เครื่องใหม่')
            self._set(selected=None, phase='selection_required' if rows else 'disconnected',
                      checked_at=time.time(), error='', message=message)

    def _recover_connected_identity(self, services, rows):
        """Rebind only an already-connected, unique, hardware-verified Wi-Fi peer.

        Runs under _operation during refresh; never pair/connect/launch/post here.
        """
        if not self.saved_identity:
            return False
        candidates = [r for r in rows if r['state'] == 'device' and r['transport'] == 'Wi-Fi']
        if not candidates or len(candidates) > 8:
            return False
        matches = []
        for row in candidates:
            try:
                peer = self._probe(row['serial'])
            except WifiError:
                return False  # Cannot establish uniqueness while another peer is unknown.
            if peer['device_id'] == self.saved_identity:
                matches.append(row['serial'])
        if len(matches) != 1:
            return False
        self._choose(matches[0], services, expected_identity=self.saved_identity)
        self._set(message='พบมือถือเครื่องเดิมที่การเชื่อมต่อใหม่ • ตรวจตัวเครื่องแล้ว • ยังไม่ได้โพสต์หรือทำคิวต่อ')
        return True

    def _connect(self, address, expected_identity=''):
        self._set(phase='connecting', message='กำลังเชื่อมต่อและตรวจตัวตนมือถือ')
        output = self._run('connect', address, timeout=15)
        if not any(line.strip() in (f'connected to {address}', f'already connected to {address}')
                   for line in output.splitlines()):
            raise WifiError('เชื่อมต่อไม่ได้ ใช้พอร์ตจากหน้าหลัก Wireless debugging ไม่ใช่พอร์ตจับคู่')
        self._choose(address, expected_identity=expected_identity)

    def action(self, action, payload=None):
        payload = dict(payload or {})
        if action == 'android_wifi_status':
            return {'ok': True, 'android_wifi': self.state()}
        if action not in ('android_wifi_refresh', 'android_wifi_pair', 'android_wifi_connect', 'android_wifi_select'):
            return {'ok': False, 'error': 'ไม่รู้จักคำสั่งเชื่อมต่อมือถือ'}
        # Only a small, validated argument tuple reaches the worker; no request body is logged.
        try:
            args = ()
            if action in ('android_wifi_pair', 'android_wifi_connect'):
                address = endpoint(payload.get('endpoint'))
                args = (address,)
            if action == 'android_wifi_pair':
                code = str(payload.pop('code', '')).strip()
                if not re.fullmatch(r'[0-9]{6}', code):
                    raise WifiError('กรอกรหัสจับคู่ 6 หลักจากมือถือ')
                args = (address, code)
            if action == 'android_wifi_select':
                serial = str(payload.get('serial') or '')
                if not re.fullmatch(r'[\w.:\[\]-]{1,240}', serial, re.ASCII):
                    raise WifiError('เลือกมือถือจากรายการที่ตรวจพบ')
                args = (serial,)
        except WifiError as exc:
            return {'ok': False, 'error': str(exc)}
        if not self._operation.acquire(blocking=False):
            return {'ok': False, 'error': 'กำลังตรวจหรือเชื่อมต่อมือถืออยู่ กรุณารอรายการปัจจุบัน'}
        self._set(busy=True, error='', phase='pairing' if action == 'android_wifi_pair' else 'checking',
                  message='กำลังจับคู่ • เปิดหน้ารหัสบนมือถือค้างไว้' if action == 'android_wifi_pair' else 'กำลังตรวจการเชื่อมต่อมือถือ')
        self._thread = threading.Thread(target=self._work, args=(action, args), daemon=True)
        try:
            self._thread.start()
        except Exception:
            self._set(busy=False, phase='error', error='เริ่มการเชื่อมต่อไม่สำเร็จ')
            self._operation.release()
            return {'ok': False, 'error': 'เริ่มการเชื่อมต่อไม่สำเร็จ'}
        return {'ok': True, 'accepted': True, 'android_wifi': self.state()}

    def _work(self, action, args):
        try:
            if action == 'android_wifi_refresh':
                self._refresh()
            elif action == 'android_wifi_pair':
                address, code = args
                guid = self._run('pair', address, code=code, timeout=30)
                code = None
                args = ()
                self._set(paired_endpoint=address, selected=None, phase='paired',
                          message='จับคู่สำเร็จ • รอเชื่อมต่อหรือกรอกพอร์ตจากหน้าหลัก Wireless debugging')
                services = self._discover()
                targets = [s for s in services if s['kind'] == 'connect' and s['name'] == guid
                           and s['endpoint'].split(':')[0] == address.split(':')[0]]
                if len(targets) == 1:
                    self._connect(targets[0]['endpoint'])
                else:
                    self._devices(services)
            elif action == 'android_wifi_connect':
                expected = self.saved_identity if args[0] == self.adb.serial else ''
                self._connect(args[0], expected_identity=expected)
            else:
                self._choose(args[0])
        except WifiError as exc:
            self._set(selected=None, phase='error', error=str(exc), message=str(exc), checked_at=time.time())
        except Exception:
            self._set(selected=None, phase='error', error='ตรวจการเชื่อมต่อไม่สำเร็จ กรุณาตรวจมือถือแล้วลองใหม่',
                      message='ตรวจการเชื่อมต่อไม่สำเร็จ กรุณาตรวจมือถือแล้วลองใหม่', checked_at=time.time())
        finally:
            self._set(busy=False)
            self._operation.release()
            state = self.state()
            self.notify(state['message'], state['phase'] == 'connected')
