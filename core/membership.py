"""SmartFlow online membership. Secrets never enter config, bridge state or logs.

Activation tokens are used once, then discarded. Windows Credential Manager
holds installation proof and revocable renewal credentials; leases are memory
only. A restart must contact the server, and a kick requires manual login.
"""
import json
import math
import os
import re
import secrets
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener


API = 'https://www.catfufu.com/api/smartflow-membership'
# Identify this transport honestly; urllib's generic identity is rejected by
# the site's edge. This is the membership client protocol, not a browser or
# an Extension build number. Never include a Token/device/member in this header.
USER_AGENT = 'SmartFlowAI-Membership/1.0 (Windows)'
MESSAGES = {
    'LOGIN_REQUIRED': 'กรุณากรอก API Token เพื่อเข้าสู่ SmartFlow AI',
    'MEMBERSHIP_BLOCKED': 'บัญชีถูกระงับ กรุณาติดต่อแอดมิน',
    'MEMBERSHIP_EXPIRED': 'สิทธิ์หมดอายุ กรุณาติดต่อแอดมินเพื่อต่ออายุ',
    'MEMBERSHIP_INACTIVE': 'สิทธิ์ยังไม่พร้อมใช้งาน กรุณาติดต่อแอดมิน',
    'TOKEN_SCOPE_MISMATCH': 'Token ไม่ตรงประเภท กรุณาใช้ Token สำหรับส่วนนี้',
    'TOKEN_BOUND_TO_ANOTHER_DEVICE': 'Token นี้ผูกกับเครื่องหรือโปรไฟล์อื่นแล้ว กรุณาติดต่อแอดมิน',
    'DESKTOP_PAIRING_REQUIRED': 'เข้าสู่ระบบในโปรแกรมด้วยสมาชิกเดียวกันก่อนเชื่อม Extension',
    'SERVER_UNAVAILABLE': 'ติดต่อเซิร์ฟเวอร์ไม่ได้ กำลังตรวจการเชื่อมต่อใหม่ โดยไม่ส่งงานซ้ำ',
    'SECURE_STORAGE_UNAVAILABLE': 'อ่านหรือบันทึกสิทธิ์ใน Windows ไม่สำเร็จ กรุณาลองใหม่',
    'INVALID_REQUEST': 'รูปแบบ Token ไม่ถูกต้อง กรุณาตรวจสอบแล้วลองใหม่',
    'TOO_MANY_REQUESTS': 'ตรวจสิทธิ์ถี่เกินไป กรุณารอสักครู่แล้วลองใหม่',
    'EXTENSION_LOGIN_REQUIRED': 'กรุณากรอก Token สำหรับ Extension ในปุ่ม SmartFlow บน Chrome',
    'RESTORING_SESSION': 'กำลังเชื่อมสิทธิ์ที่บันทึกไว้ ไม่ต้องกรอก Token ใหม่',
    'EXTENSION_PROFILE_CHANGED': 'พบ Extension คนละตัวกับที่ผูกสิทธิ์ไว้ ให้ใช้ตัวเดิมในโปรไฟล์และโฟลเดอร์เดิม หากตั้งใจย้ายให้ตรวจการผูกสิทธิ์กับแอดมินก่อน',
    'EXTENSION_CONNECTION_REQUIRED': 'เปิด Chrome ที่ติดตั้ง Extension รุ่นเดียวกับโปรแกรม แล้วตรวจการเชื่อมต่ออีกครั้ง',
    'DESKTOP_LOGIN_ONLY': 'เข้าสู่ระบบหรือออกจากระบบที่โปรแกรม SmartFlow AI เท่านั้น ไม่ต้องกรอก Token ใน Extension',
}


class MembershipError(ValueError):
    def __init__(self, code='LOGIN_REQUIRED'):
        self.code = code if code in MESSAGES else 'LOGIN_REQUIRED'
        super().__init__(MESSAGES[self.code])


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward a credential to a redirect, even within HTTPS.


def request_server(route, body, bearer=''):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
               'User-Agent': USER_AGENT}
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    request = Request(API + '/' + route, data=json.dumps(body).encode(), headers=headers, method='POST')
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=8) as response:
            raw = response.read(16385)
            if len(raw) > 16384:
                raise MembershipError('SERVER_UNAVAILABLE')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise MembershipError('SERVER_UNAVAILABLE')
            return result
    except HTTPError as error:
        # The response body may echo untrusted data. Only return allowlisted codes.
        try:
            code = json.loads(error.read(4096)).get('detail')
        except Exception:
            code = None
        if isinstance(code, str) and code in MESSAGES:
            raise MembershipError(code) from None
        raise MembershipError('SERVER_UNAVAILABLE') from None
    except MembershipError:
        raise
    except Exception:
        raise MembershipError('SERVER_UNAVAILABLE') from None


class Membership:
    def __init__(self, stores, version, *, transport=request_server, clock=time.monotonic, extension_from_desktop=False):
        self.stores, self.version, self.transport, self.clock = stores, version, transport, clock
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.identity = None
        self.saved = {'desktop': {}, 'extension': {}}
        self.sessions = {'desktop': {}, 'extension': {}}
        self.errors = {'desktop': 'LOGIN_REQUIRED', 'extension': 'EXTENSION_LOGIN_REQUIRED'}
        self.next_check = {'desktop': 0.0, 'extension': 0.0}
        self.extension_seen = -float('inf')
        self.extension_version = ''
        self.extension_from_desktop = extension_from_desktop
        self.extension_profiles = {}  # Presence only, never a cloud credential/lease.
        try:
            raw = stores['identity'].load()
            self.identity = json.loads(raw) if raw else {
                'device_id': secrets.token_hex(24), 'device_proof': secrets.token_urlsafe(48)}
            if not all(isinstance(self.identity.get(k), str) and 40 <= len(self.identity[k]) <= 128
                       for k in ('device_id', 'device_proof')):
                raise ValueError()
            if not raw:
                self._save('identity', self.identity)
            for scope in self.saved:
                if scope == 'extension' and self.extension_from_desktop:
                    continue  # Leave historical customer vault data untouched.
                raw = stores[scope].load()
                data = json.loads(raw) if raw else {}
                if data and (not isinstance(data, dict) or not self._secret(data.get('credential'))):
                    raise ValueError()
                self.saved[scope] = data
        except Exception:
            self.errors['desktop'] = 'SECURE_STORAGE_UNAVAILABLE'
            self.identity = None

    @staticmethod
    def _secret(value):
        return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{40,128}', value))

    def _save(self, scope, value):
        try:
            self.stores[scope].save(json.dumps(value, separators=(',', ':')))
        except Exception:
            raise MembershipError('SECURE_STORAGE_UNAVAILABLE') from None

    def start(self):
        if self.thread:
            return
        self.thread = threading.Thread(target=self._loop, daemon=True, name='SmartFlowMembership')
        self.thread.start()

    def close(self):
        self.stop_event.set()

    def _loop(self):
        while not self.stop_event.is_set():
            self.tick()
            self.stop_event.wait(1)

    def _accept(self, scope, result, started, commit=True):
        try:
            remaining = float(result['lease_until']) - float(result['server_time'])
            expires = float(result['expires_at'])
            if result.get('scope') != scope or not math.isfinite(remaining) or not 0 < remaining <= 301 or not math.isfinite(expires):
                raise ValueError()
            session = result.get('session') or self.sessions[scope].get('session')
            if not self._secret(session):
                raise ValueError()
            # Start-of-request monotonic time is conservative; wall-clock changes
            # cannot extend an offline lease. Leases are never restored from disk.
            state = {'session': session, 'deadline': started + min(300, remaining),
                     'expires_at': expires, 'member_id': result.get('member_id') or self.saved[scope].get('member_id', '')}
            if not re.fullmatch(r'[a-f0-9]{32}', state['member_id']):
                raise ValueError()
            if commit:
                self.sessions[scope] = state
                self.errors[scope] = ''
                self.next_check[scope] = self.clock() + 30
            return state
        except (KeyError, TypeError, ValueError):
            raise MembershipError('SERVER_UNAVAILABLE') from None

    def _clear(self, scope, code):
        self.sessions[scope] = {}
        self.saved[scope] = {}
        self.errors[scope] = code
        if scope == 'extension' and self.extension_from_desktop:
            self.extension_profiles = {}
            return  # Do not read, migrate or delete the retired Extension vault.
        try:
            self.stores[scope].delete()
        except Exception:
            self.errors[scope] = 'SECURE_STORAGE_UNAVAILABLE'
        if scope == 'desktop':
            self._clear('extension', 'DESKTOP_PAIRING_REQUIRED')

    def logout(self, scope='desktop'):
        if scope == 'extension' and self.extension_from_desktop:
            raise MembershipError('DESKTOP_LOGIN_ONLY')
        with self.lock:
            self._clear(scope, 'LOGIN_REQUIRED' if scope == 'desktop' else 'EXTENSION_LOGIN_REQUIRED')
            return self.status()

    def login(self, token, scope='desktop', profile_id='', version=''):
        with self.lock:
            if scope == 'extension' and self.extension_from_desktop:
                raise MembershipError('DESKTOP_LOGIN_ONLY')
            if scope not in self.saved or not self._secret(token):
                raise MembershipError('INVALID_REQUEST')
            if not self.identity:
                raise MembershipError('SECURE_STORAGE_UNAVAILABLE')
            body = {**self.identity, 'activation_token': token, 'scope': scope,
                    'device_label': 'SmartFlow Windows', 'version': self.version}
            if scope == 'extension':
                self.require()
                if not re.fullmatch(r'[a-f0-9]{48}', profile_id):
                    raise MembershipError('INVALID_REQUEST')
                body.update(profile_id=profile_id, parent_credential=self.saved['desktop']['credential'], version=version[:48])
            started = self.clock()
            result = self.transport('activate', body)
            if not self._secret(result.get('credential')):
                raise MembershipError('SERVER_UNAVAILABLE')
            session = self._accept(scope, result, started, commit=False)
            saved = {'credential': result['credential'], 'member_id': session['member_id']}
            if scope == 'extension':
                saved['profile_id'] = profile_id
                self.extension_seen, self.extension_version = self.clock(), version[:48]
            try:
                self._save(scope, saved)
            except MembershipError:
                self._clear(scope, 'SECURE_STORAGE_UNAVAILABLE')
                raise
            self.saved[scope] = saved
            self.sessions[scope] = session
            self.errors[scope] = ''
            self.next_check[scope] = self.clock() + 30
            if scope == 'desktop' and not self.extension_from_desktop:
                # Re-activation invalidates desktop renewal credentials. Existing
                # extension binding remains but must revalidate with the server.
                self.sessions['extension'] = {}
                self.next_check['extension'] = 0
                if self.saved['extension'].get('member_id') != saved['member_id']:
                    self._clear('extension', 'EXTENSION_LOGIN_REQUIRED')
            return self.status(profile_id)

    def observe_extension(self, profile_id, version, *, required_version=''):
        if self.extension_from_desktop:
            if re.fullmatch(r'[a-f0-9]{48}', profile_id or '') and required_version and version == required_version:
                now = self.clock()
                self.extension_profiles = {**{p: seen for p, seen in self.extension_profiles.items() if now - seen <= 45}, profile_id: now}
            else:
                self.forget_extension(profile_id)
            return
        if profile_id and profile_id == self.saved['extension'].get('profile_id'):
            self.extension_seen, self.extension_version = self.clock(), version[:48]

    def forget_extension(self, profile_id):
        self.extension_profiles = {p: seen for p, seen in self.extension_profiles.items() if p != profile_id}

    def tick(self):
        with self.lock:
            if not self.identity:
                return
            for scope in ('desktop', 'extension'):
                if scope == 'extension' and self.extension_from_desktop:
                    continue
                if not self.saved[scope] or self.clock() < self.next_check[scope]:
                    continue
                if scope == 'extension' and (not self.allowed() or self.clock() - self.extension_seen > 45):
                    continue
                started = self.clock()
                previous = self.sessions[scope]
                fresh = previous.get('deadline', 0) > started
                route = 'heartbeat' if fresh else 'renew'
                body = {'scope': scope, 'version': self.extension_version if scope == 'extension' else self.version}
                bearer = previous.get('session') if fresh else self.saved[scope]['credential']
                if not fresh:
                    body.pop('scope')
                    body['device_proof'] = self.identity['device_proof']
                try:
                    result = self.transport(route, body, bearer)
                    self._accept(scope, result, started)
                except MembershipError as error:
                    self.next_check[scope] = self.clock() + 30
                    if error.code in {'SERVER_UNAVAILABLE', 'TOO_MANY_REQUESTS'}:
                        self.errors[scope] = error.code  # Keep only the original bounded lease.
                    else:
                        self._clear(scope, error.code)  # Kick never silently re-activates.
                except Exception:
                    self.next_check[scope] = self.clock() + 30
                    self.errors[scope] = 'SERVER_UNAVAILABLE'

    def allowed(self, scope='desktop', profile_id=''):
        # Read immutable, atomically replaced snapshots without waiting behind
        # HTTPS. Status and cancellation stay responsive during a server outage.
        if scope == 'extension' and self.extension_from_desktop:
            return self.allowed() and self.clock() - self.extension_profiles.get(profile_id, -float('inf')) <= 45
        valid = self.sessions.get(scope, {}).get('deadline', 0) > self.clock()
        if scope == 'extension':
            valid = (valid and self.allowed() and profile_id == self.saved[scope].get('profile_id') and bool(profile_id)
                     and self.saved[scope].get('member_id') == self.saved['desktop'].get('member_id'))
        return bool(valid)

    def require(self, scope='desktop', profile_id=''):
        if not self.allowed(scope, profile_id):
            if scope == 'extension' and self.extension_from_desktop:
                self.require()  # Surface actual desktop expiry/kick, not a Chrome Token form.
                raise MembershipError('EXTENSION_CONNECTION_REQUIRED')
            raise MembershipError(self.errors.get(scope) or ('LOGIN_REQUIRED' if scope == 'desktop' else 'EXTENSION_LOGIN_REQUIRED'))

    def browser_allowed(self):
        if self.extension_from_desktop:
            return any(self.allowed('extension', profile) for profile in self.extension_profiles)
        return self.allowed('extension', self.saved['extension'].get('profile_id', ''))

    def require_browser(self):
        self.require()
        if self.extension_from_desktop:
            if not self.browser_allowed():
                raise MembershipError('EXTENSION_CONNECTION_REQUIRED')
            return
        self.require('extension', self.saved['extension'].get('profile_id', ''))

    def status(self, profile_id=''):
        state = {'ok': True, 'required': True}
        for scope in ('desktop', 'extension'):
            if scope == 'extension' and self.extension_from_desktop:
                desktop = state['desktop']
                allowed = self.allowed(scope, profile_id) if profile_id else self.browser_allowed()
                code = desktop['code'] if not desktop['allowed'] else '' if allowed else 'EXTENSION_CONNECTION_REQUIRED'
                state[scope] = {**desktop, 'allowed': allowed, 'source': 'desktop', 'contract_version': 1,
                                'code': code, 'message': MESSAGES.get(code, 'ใช้สิทธิ์จาก SmartFlow AI • พร้อมรับงาน'),
                                'profile_changed': False}
                continue
            session = self.sessions[scope]
            allowed = self.allowed(scope, profile_id)
            code = self.errors[scope] or ('' if allowed else 'LOGIN_REQUIRED' if scope == 'desktop' else 'EXTENSION_LOGIN_REQUIRED')
            saved = self.saved[scope]
            profile_changed = scope == 'extension' and bool(saved.get('profile_id')) and bool(profile_id) and profile_id != saved['profile_id']
            remembered = bool(self.identity and saved.get('credential')) and (
                scope == 'desktop' or bool(profile_id) and profile_id == saved.get('profile_id'))
            restoring = remembered and not allowed
            if profile_changed:
                code = 'EXTENSION_PROFILE_CHANGED'
            elif restoring and code in {'LOGIN_REQUIRED', 'EXTENSION_LOGIN_REQUIRED'}:
                code = 'RESTORING_SESSION'
            state[scope] = {'allowed': allowed, 'code': code, 'message': MESSAGES.get(code, 'เชื่อมต่อแล้ว'),
                            'remembered': remembered, 'restoring': restoring, 'profile_changed': profile_changed,
                            'expires_at': session.get('expires_at'),
                            'lease_seconds': max(0, int(session.get('deadline', 0) - self.clock()))}
        return state


class DevelopmentMembership:
    """Explicit local source-checkout mode with no credential or server access."""

    def start(self):
        pass

    def close(self):
        pass

    def allowed(self, scope='desktop', profile_id=''):
        return scope == 'desktop'

    def require(self, scope='desktop', profile_id=''):
        if not self.allowed(scope, profile_id):
            raise MembershipError('EXTENSION_CONNECTION_REQUIRED')

    def status(self, profile_id=''):
        desktop = {'allowed': True, 'code': '', 'message': 'DEV MODE • ไม่ตรวจ API Token',
                   'remembered': False, 'restoring': False, 'profile_changed': False,
                   'expires_at': None, 'lease_seconds': 0}
        extension = {**desktop, 'allowed': False, 'source': 'desktop', 'contract_version': 1,
                     'code': 'EXTENSION_CONNECTION_REQUIRED',
                     'message': MESSAGES['EXTENSION_CONNECTION_REQUIRED']}
        return {'ok': True, 'required': True, 'dev_mode': True,
                'desktop': desktop, 'extension': extension}

    def login(self, *args, **kwargs):
        raise MembershipError('INVALID_REQUEST')

    def logout(self, *args, **kwargs):
        raise MembershipError('INVALID_REQUEST')


def _development_checkout():
    root = Path(__file__).resolve().parents[1]
    return (root / '.git').exists() and (root / '.venv' / 'pyvenv.cfg').is_file()


def _development_membership_enabled(version):
    if os.environ.get('SMARTFLOW_DEV_BYPASS_MEMBERSHIP') != '1':
        return False
    if getattr(sys, 'frozen', False) or version != 'development':
        return False
    return _development_checkout()


def production_membership(version):
    if _development_membership_enabled(version):
        return DevelopmentMembership()
    from core.secure_store import WindowsCredentialStore
    try:
        stores = {scope: WindowsCredentialStore('SmartFlowAI/Membership/' + scope)
                  for scope in ('identity', 'desktop', 'extension')}
    except Exception:
        class UnavailableStore:
            def load(self): raise MembershipError('SECURE_STORAGE_UNAVAILABLE')
            def save(self, value): raise MembershipError('SECURE_STORAGE_UNAVAILABLE')
            def delete(self): raise MembershipError('SECURE_STORAGE_UNAVAILABLE')
        stores = {scope:UnavailableStore() for scope in ('identity', 'desktop', 'extension')}
    return Membership(stores, version, extension_from_desktop=True)


# Read/results, cancellation and updates remain accessible. Every other desktop
# action is guarded, including new actions added later (fail closed by default).
SAFE_ACTIONS = frozenset({
    'shutdown', 'prepare_app_update', 'reload_extension_after_update', 'creation_pause', 'story_queue_pause', 'cancel_product', 'cancel_story',
    'cancel_presenter', 'shopee_post_pause', 'facebook_planner_pause',
    'shopee_post_status', 'shopee_post_library', 'android_wifi_status', 'facebook_status',
    'product_cast_state', 'intro_status', 'green_status', 'story_native_status', 'story_native_cancel',
    'story_review', 'product_image_review', 'creation_state',
    'refresh', 'cancel_drama_series', 'presenter_cancel', 'creation_cancel', 'creation_cancel_all',
    'close_automation_browser', 'connect_browser', 'open_extension_folder', 'copy_extension_path', 'open_logs_folder',
    'get_library_detail', 'open_library_video', 'open_library_folder', 'open_library_cover',
})


def guard_action(owner, action):
    member = getattr(owner, 'membership', None)
    if member and action not in SAFE_ACTIONS:
        member.require()
