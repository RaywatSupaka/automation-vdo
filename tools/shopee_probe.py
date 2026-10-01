"""Explicit developer exploration of the one user-authorized Shopee flow; never auto-post."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.config import ROOT, load_config
from core.adb_manager import AdbManager
from core.shopee_posting.device import ShopeeDevice

p=argparse.ArgumentParser()
p.add_argument('--open',action='store_true')
p.add_argument('--text'); p.add_argument('--resource'); p.add_argument('--description'); p.add_argument('--bounds')
p.add_argument('--value'); p.add_argument('--back',action='store_true')
p.add_argument('--scroll',action='store_true')
p.add_argument('--album')
p.add_argument('--name',default='current')
args=p.parse_args()
cfg=load_config(); device=ShopeeDevice(AdbManager(cfg['adb_path'],cfg.get('device_serial'),ROOT),cfg.get('android_device_identity'))
try:
    if args.open: device.open()
    if args.back: device.foreground(); device.ui.press('back')
    if args.album: device.album(args.album)
    if args.scroll:
        _, nodes = device.snapshot()
        scrolls = [n for n in nodes if n.get('scrollable') == 'true' and n.get('package') == device.package]
        if len(scrolls) != 1: raise RuntimeError('Need exactly one observed scroll area')
        device.ui(scrollable=True).scroll.forward()
    conditions={k:v for k,v in [('text',args.text),('resource-id',args.resource),('content-desc',args.description),('bounds',args.bounds)] if v is not None}
    if conditions:
        if any(v in ('โพสต์','Post','เผยแพร่') for v in conditions.values()):
            raise RuntimeError('Publish must use the durable posting controller, not this probe')
        if args.value is None: device.tap(**conditions)
        else: device.set_text(args.value,**conditions)
    # Caller inspects a fresh screen after each single action, not a blind tap loop.
    import time
    time.sleep(1)
    folder=ROOT/'workspace'/'shopee_posting'/'probe'
    nodes=device.capture(folder,args.name)
    print(json.dumps({'screenshot':str(folder/(args.name+'.png')),'nodes':[{k:n.get(k) for k in ('text','resource-id','class','content-desc','clickable','bounds')} for n in nodes if n.get('text') or n.get('content-desc') or n.get('clickable')=='true']},ensure_ascii=False))
finally:
    device.close()
