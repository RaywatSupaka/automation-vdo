import re, subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs

@dataclass
class Device:
    serial: str
    state: str
    detail: str = ""

class AdbManager:
    def __init__(self, path, serial="", root=None): self.path=Path(path); self.serial=serial; self.root=Path(root or Path.cwd())
    def run(self, *args, serial=False, binary=False, timeout=20):
        if serial and not self.serial: raise RuntimeError("ยังไม่ได้เลือก Serial ของโทรศัพท์")
        cmd=[str(self.path)]+(["-s",self.serial] if serial else [])+list(args)
        codec = {} if binary else {'encoding': 'utf-8', 'errors': 'replace'}
        return subprocess.run(cmd,capture_output=True,text=not binary,timeout=timeout,**codec,**hidden_process_kwargs())
    def devices(self):
        rows=[]
        result=self.run("devices","-l")
        if result.returncode: raise RuntimeError(result.stderr.strip() or "ADB devices ไม่สำเร็จ")
        for line in result.stdout.splitlines()[1:]:
            parts=line.split(None,2)
            if parts: rows.append(Device(parts[0],parts[1] if len(parts)>1 else "unknown",parts[2] if len(parts)>2 else ""))
        return rows
    def shell(self,*args,timeout=20): return self.run("shell",*args,serial=True,timeout=timeout)
    def prop(self,key): return self.shell("getprop",key).stdout.strip()
    def info(self):
        battery=self.shell("dumpsys","battery").stdout; match=re.search(r"^\s*level:\s*(\d+)",battery,re.M)
        return {"serial":self.serial,"manufacturer":self.prop("ro.product.manufacturer"),"model":self.prop("ro.product.model"),"android":self.prop("ro.build.version.release"),"screen":self.shell("wm","size").stdout.strip().replace("Physical size:","").strip(),"battery":f"{match.group(1)}%" if match else "?"}
    def packages(self): return [x[8:].strip() for x in self.shell("pm","list","packages").stdout.splitlines() if x.startswith("package:") and "shopee" in x.lower()]
    def open_package(self,pkg): return self.shell("monkey","-p",pkg,"-c","android.intent.category.LAUNCHER","1")
    def screenshot(self,state="ERROR"):
        target=self.root/"screenshots"/f"DEVICE_{state}_{datetime.now():%Y%m%d_%H%M%S}.png"; target.parent.mkdir(exist_ok=True)
        result=self.run("exec-out","screencap","-p",serial=True,binary=True)
        if result.returncode: raise RuntimeError(result.stderr.decode(errors="replace") if isinstance(result.stderr,bytes) else result.stderr)
        target.write_bytes(result.stdout); return target
    def dump_ui(self):
        remote="/sdcard/window_dump.xml"; result=self.shell("uiautomator","dump",remote,timeout=30)
        if result.returncode: raise RuntimeError(result.stderr or result.stdout)
        target=self.root/"screenshots"/f"shopee_ui_{datetime.now():%Y%m%d_%H%M%S}.xml"
        pull=self.run("pull",remote,str(target),serial=True,timeout=30)
        if pull.returncode: raise RuntimeError(pull.stderr)
        return target
