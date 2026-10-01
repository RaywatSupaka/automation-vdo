"""Trust one synthetic browser identity in isolated HTTP contract tests only."""
import time


def pair_fixture(bridge, origin='chrome-extension://'+'a'*32, profile='', token=None):
    bridge._extension_identity.ids={origin.removeprefix('chrome-extension://')}
    bridge._extension_identity.cached_at=time.monotonic()+3600
    bridge._extension_sessions[(origin,profile)]=token or bridge._extension_token
    return origin
