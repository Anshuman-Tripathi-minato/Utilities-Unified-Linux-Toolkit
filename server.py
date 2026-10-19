#!/usr/bin/env python3
import os, re, json, time, socket, shutil, subprocess, sys
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import psutil

BASE = Path(__file__).resolve().parent
STATIC = BASE / 'static'
HOST = '127.0.0.1'


def run(cmd, timeout=8):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, '', str(e)


def cmd_exists(name): return shutil.which(name) is not None


def _read_num(p):
    try: return float(Path(p).read_text().strip())
    except Exception: return None


def battery():
    b = psutil.sensors_battery()
    out = {
        'present': bool(b), 'percent': round(float(b.percent), 1) if b else None,
        'plugged': bool(b.power_plugged) if b else None, 'state': 'Unavailable',
        'health': None, 'degradation': None, 'design_wh': None, 'full_wh': None,
        'voltage': None, 'power_w': None, 'current_a': None, 'cycle_count': None,
        'temperature': None, 'energy_now_wh': None, 'seconds_left': None,
    }
    if b:
        out['state'] = 'Charging' if b.power_plugged and b.percent < 100 else ('Full' if b.percent >= 100 else 'Discharging')
        if b.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN): out['seconds_left'] = b.secsleft
    ps=Path('/sys/class/power_supply')
    for d in (ps.glob('*') if ps.exists() else []):
        try:
            if (d/'type').read_text().strip() != 'Battery': continue
            ef, ed = d/'energy_full', d/'energy_full_design'
            cf, cd = d/'charge_full', d/'charge_full_design'
            if ef.exists() and ed.exists():
                f, design = _read_num(ef), _read_num(ed)
                if f is not None and design:
                    out['full_wh'], out['design_wh'] = f/1e6, design/1e6
            elif cf.exists() and cd.exists():
                f, design = _read_num(cf), _read_num(cd)
                if f is not None and design:
                    # Charge capacity (Ah), keep separate from energy.
                    out['full_ah'], out['design_ah'] = f/1e6, design/1e6
                    v = _read_num(d/'voltage_now')
                    if v is not None: out['full_wh'], out['design_wh'] = (f/1e6)*(v/1e6), (design/1e6)*(v/1e6)
            if out.get('full_wh') and out.get('design_wh'):
                out['health'] = round(max(0, min(100, out['full_wh']/out['design_wh']*100)), 1)
                out['degradation'] = round(max(0, 100-out['health']), 1)
            en = d/'energy_now'
            if en.exists(): out['energy_now_wh'] = round((_read_num(en) or 0)/1e6, 3)
            else:
                cn = d/'charge_now'
                if cn.exists():
                    ah = (_read_num(cn) or 0)/1e6; v=(_read_num(d/'voltage_now') or 0)/1e6; out['energy_now_wh']=round(ah*v,3)
            vv=_read_num(d/'voltage_now'); pp=_read_num(d/'power_now'); cc=_read_num(d/'current_now')
            out['voltage']=round(vv/1e6,2) if vv is not None else None
            out['power_w']=round(pp/1e6,2) if pp is not None else None
            out['current_a']=round(cc/1e6,2) if cc is not None else None
            cy=_read_num(d/'cycle_count'); out['cycle_count']=int(cy) if cy is not None else None
            tt=_read_num(d/'temp'); out['temperature']=round(tt/10,1) if tt and tt>100 else (round(tt,1) if tt is not None else None)
            break
        except Exception: continue
    for p in ['/sys/class/power_supply/AC', '/sys/class/power_supply/AC0']:
        pass
    return out


def telemetry():
    vm=psutil.virtual_memory(); sm=psutil.swap_memory(); root=psutil.disk_usage('/')
    cpu=psutil.cpu_percent(interval=0.05); net=psutil.net_io_counters()
    return {'cpu':round(cpu,1),'memory':vm.percent,'memory_used_gb':round(vm.used/2**30,2),'memory_total_gb':round(vm.total/2**30,2),
            'swap':sm.percent,'disk':root.percent,'disk_used_gb':round(root.used/2**30,2),'disk_total_gb':round(root.total/2**30,2),
            'net_sent':net.bytes_sent,'net_recv':net.bytes_recv,'load':[round(x,2) for x in psutil.getloadavg()] if hasattr(psutil,'getloadavg') else []}


def processes():
    rows=[]
    for p in psutil.process_iter(['pid','name','username','status','memory_percent','num_threads']):
        try: rows.append({'pid':p.info['pid'],'name':p.info['name'] or '', 'user':p.info['username'] or '', 'status':p.info['status'] or '', 'memory':round(p.info['memory_percent'] or 0,2),'threads':p.info['num_threads'] or 0,'cpu':round(p.cpu_percent(None),2)})
        except Exception: pass
    rows.sort(key=lambda x:(-x['cpu'],-x['memory'])); return rows[:500]


def disks():
    result=[]
    for p in psutil.disk_partitions(all=False):
        if any(x in p.mountpoint for x in ['/proc','/sys','/run','/dev']): continue
        try:
            u=psutil.disk_usage(p.mountpoint)
            result.append({'device':p.device,'mount':p.mountpoint,'fstype':p.fstype,'total':u.total,'used':u.used,'free':u.free,'percent':u.percent})
        except Exception: pass
    return result


def net_info():
    data={'interfaces':[],'connections':[],'hostname':socket.gethostname()}; addrs=psutil.net_if_addrs(); stats=psutil.net_if_stats()
    for name, arr in addrs.items():
        st=stats.get(name); ips=[a.address for a in arr if a.family in (socket.AF_INET,socket.AF_INET6)]
        data['interfaces'].append({'name':name,'up':bool(st.isup) if st else False,'speed':st.speed if st else 0,'mtu':st.mtu if st else 0,'ips':ips})
    try:
        for c in psutil.net_connections(kind='inet')[:300]:
            data['connections'].append({'pid':c.pid,'status':c.status,'laddr':f'{c.laddr.ip}:{c.laddr.port}' if c.laddr else '', 'raddr':f'{c.raddr.ip}:{c.raddr.port}' if c.raddr else ''})
    except Exception: pass
    return data


def bluetooth():
    out={'available':cmd_exists('bluetoothctl'),'adapter':'','powered':None,'devices':[]}
    if not out['available']: return out
    _, stdout, _ = run(['bluetoothctl','show'])
    m=re.search(r'^\s*Name:\s*(.+)$',stdout,re.M); out['adapter']=m.group(1).strip() if m else ''
    m=re.search(r'^\s*Powered:\s*(yes|no)',stdout,re.M); out['powered']=m.group(1)=='yes' if m else None
    _, devout, _ = run(['bluetoothctl','devices'])
    for line in devout.splitlines():
        m=re.match(r'Device\s+([0-9A-F:]+)\s+(.+)',line)
        if not m: continue
        mac,name=m.group(1),m.group(2).strip(); _,info,_=run(['bluetoothctl','info',mac])
        def val(k):
            mm=re.search(rf'^\s*{re.escape(k)}:\s*(.+)$',info,re.M); return mm.group(1).strip() if mm else ''
        bp=val('Battery Percentage'); out['devices'].append({'mac':mac,'name':name,'connected':val('Connected')=='yes','paired':val('Paired')=='yes','trusted':val('Trusted')=='yes','battery':bp})
    return out


def usb_devices():
    if not cmd_exists('lsusb'): return []
    _,out,_=run(['lsusb']); return [{'text':x} for x in out.splitlines()]


def thermal():
    zones=[]
    for z in Path('/sys/class/thermal').glob('thermal_zone*'):
        try:
            raw=float((z/'temp').read_text().strip()); zones.append({'type':(z/'type').read_text().strip(),'c':round(raw/1000,1)})
        except Exception: pass
    fans=[]; pwm=[]
    for hw in Path('/sys/class/hwmon').glob('hwmon*'):
        name=(hw/'name').read_text(errors='ignore').strip() if (hw/'name').exists() else hw.name
        for f in hw.glob('fan*_input'):
            try: fans.append({'name':name,'sensor':f.name,'rpm':int(f.read_text().strip())})
            except Exception: pass
        for p in hw.glob('pwm*'):
            if p.name.endswith('_enable'): continue
            try: pwm.append({'path':str(p),'name':p.name,'value':int(p.read_text().strip()),'writable':os.access(p,os.W_OK)})
            except Exception: pass
    return {'zones':zones,'fans':fans,'pwm':pwm}


def packages():
    if not cmd_exists('dpkg-query'): return []
    _,out,_=run(['dpkg-query','-W','-f=${Package}\t${Version}\t${Status}\n'],timeout=25)
    rows=[]
    for line in out.splitlines():
        p=line.split('\t')
        if len(p)>=3 and 'install ok installed' in p[2]: rows.append({'name':p[0],'version':p[1]})
    return rows


def privacy():
    fw=None
    if cmd_exists('ufw'):
        _,out,_=run(['ufw','status']); fw={'tool':'ufw','status':out.splitlines()[0] if out else 'unknown','detail':out}
    elif cmd_exists('firewall-cmd'):
        _,out,_=run(['firewall-cmd','--state']); fw={'tool':'firewalld','status':out or 'unknown','detail':out}
    else: fw={'tool':'none detected','status':'Unavailable','detail':'No UFW or firewalld command found'}
    video=[str(x) for x in Path('/dev').glob('video*')]; audio=[str(x) for x in Path('/dev').glob('snd/*')]
    sb='Legacy/Unavailable'
    ef=Path('/sys/firmware/efi/efivars');
    if ef.exists():
        try:
            for f in ef.glob('SecureBoot-*'): sb='Enabled' if f.read_bytes()[-1]==1 else 'Disabled'; break
        except Exception: sb='Unknown'
    return {'firewall':fw,'video_nodes':video[:30],'audio_nodes':audio[:30],'secure_boot':sb}


def system_info():
    mem=psutil.virtual_memory()
    _,osname,_=run(['bash','-lc','. /etc/os-release 2>/dev/null; echo ${PRETTY_NAME:-Linux}'])
    _,cpu,_=run(['bash','-lc','lscpu 2>/dev/null | sed -n "s/^Model name:[[:space:]]*//p" | head -1'])
    return {'os':osname or 'Linux','kernel':run(['uname','-r'])[1],'arch':run(['uname','-m'])[1],'cpu':cpu or 'Unknown','cores':psutil.cpu_count(logical=False),'threads':psutil.cpu_count(logical=True),'ram_gb':round(mem.total/2**30,1),'uptime':int(time.time()-psutil.boot_time())}


def json_response(h,obj,code=200):
    body=json.dumps(obj).encode(); h.send_response(code); h.send_header('Content-Type','application/json'); h.send_header('Cache-Control','no-store'); h.send_header('Content-Length',str(len(body))); h.end_headers(); h.wfile.write(body)

class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
    def translate_path(self,path):
        p=path.split('?',1)[0]
        if p in ('/','/index.html'): return str(STATIC/'index.html')
        return str(STATIC/'index.html')
    def do_GET(self):
        path=urlparse(self.path).path
        table={'/api/telemetry':telemetry,'/api/battery':battery,'/api/processes':processes,'/api/disks':disks,'/api/network':net_info,'/api/bluetooth':bluetooth,'/api/usb':usb_devices,'/api/thermal':thermal,'/api/packages':packages,'/api/privacy':privacy,'/api/system':system_info}
        if path in table:
            try: return json_response(self,table[path]())
            except Exception as e: return json_response(self,{'error':str(e)},500)
        return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path; n=int(self.headers.get('Content-Length','0'))
        try: data=json.loads(self.rfile.read(n) or '{}')
        except Exception: data={}
        if path=='/api/process/action':
            try:
                p=psutil.Process(int(data.get('pid',0))); a=data.get('action')
                if a=='terminate': p.terminate()
                elif a=='kill': p.kill()
                elif a=='suspend': p.suspend()
                elif a=='resume': p.resume()
                else: raise ValueError('Unsupported action')
                return json_response(self,{'ok':True})
            except Exception as e: return json_response(self,{'ok':False,'error':str(e)},400)
        if path=='/api/bluetooth/action':
            if not cmd_exists('bluetoothctl'): return json_response(self,{'ok':False,'error':'bluetoothctl unavailable'},400)
            a=data.get('action'); mac=data.get('mac',''); value=data.get('value',''); name=data.get('name','') or value
            if a=='rename': cmd=['bluetoothctl','system-alias',name] if not mac else ['bluetoothctl','alias',mac,name]
            elif a in {'connect','disconnect','pair','remove','trust','untrust','block','unblock'}: cmd=['bluetoothctl',a,mac]
            elif a=='power': cmd=['bluetoothctl','power','on' if bool(value) else 'off']
            elif a=='scan': cmd=['bluetoothctl','scan','on']
            elif a=='scan-off': cmd=['bluetoothctl','scan','off']
            else: return json_response(self,{'ok':False,'error':'unknown action'},400)
            rc,out,err=run(cmd,15); return json_response(self,{'ok':rc==0,'out':out,'error':err})
        if path=='/api/fan/boost':
            p=str(data.get('path','')); value=max(0,min(255,int(data.get('value',0))))
            if not p.startswith('/sys/class/hwmon/'): return json_response(self,{'ok':False,'error':'Unsupported fan controller'},400)
            try: Path(p).write_text(str(value)); return json_response(self,{'ok':True,'value':value})
            except Exception as e: return json_response(self,{'ok':False,'error':str(e)},400)
        if path=='/api/open-folder':
            target=str(data.get('path','~'))
            try:
                resolved=os.path.expanduser(target)
                subprocess.Popen(['xdg-open',resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return json_response(self,{'ok':True})
            except Exception as e: return json_response(self,{'ok':False,'error':str(e)},400)
        if path=='/api/package/action':
            name=data.get('name','')
            if not re.fullmatch(r'[A-Za-z0-9+_.:-]+',name): return json_response(self,{'ok':False,'error':'Invalid package name'},400)
            rc,out,err=run(['pkexec','apt','remove','-y',name],120); return json_response(self,{'ok':rc==0,'out':out,'error':err})
        return json_response(self,{'ok':False,'error':'not found'},404)

def main():
    os.chdir(BASE); server=ThreadingHTTPServer((HOST,0),Handler); port=server.server_address[1]; print(f'UTILITIES_PORT={port}',flush=True); server.serve_forever()
if __name__=='__main__': main()
