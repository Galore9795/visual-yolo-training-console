"""Local experiment configuration, process identity checks, and queue supervisor."""
from pathlib import Path
import csv,fcntl,hashlib,json,os,re,signal,subprocess,sys,time,traceback
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(os.environ.get('RM_WORKSPACE', str(Path(__file__).resolve().parents[1]))).expanduser().resolve()
SRC=ROOT/'backend'
OUT=ROOT/'state'
PYTHON=Path(os.environ.get('YOLO_TRAIN_PYTHON', sys.executable))
SPEC=ROOT/'experiments.json'
CONTROL=OUT/'control.json'
def now():return datetime.now(ZoneInfo('Asia/Singapore')).isoformat()
def read(path,default=None):
 try:return json.loads(Path(path).read_text())
 except (FileNotFoundError,json.JSONDecodeError):return default if default is not None else {}
def write(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 temp=path.with_name(path.name+f'.{os.getpid()}.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False));temp.replace(path)
def specs():return read(SPEC,[])
def digest(spec):return hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
def identity(pid):
 try:
  if Path(f'/proc/{int(pid)}').stat().st_uid!=os.getuid():return None
  stat=Path(f'/proc/{int(pid)}/stat').read_text();rest=stat[stat.rfind(')')+2:].split()
  if rest[0]=='Z':return None
  cmd=Path(f'/proc/{int(pid)}/cmdline').read_bytes().replace(b'\0',b' ').decode()
  return dict(pid=int(pid),start=rest[19],cmd=cmd,state=rest[0])
 except (OSError,ValueError):return None
def matches(ref):
 current=identity(ref.get('pid',0)) if ref else None
 return bool(current and current['start']==ref.get('start') and current['cmd']==ref.get('cmd'))
def worker_ref(pid):
 ref=identity(pid)
 if not ref or str(SRC/'train.py') not in ref['cmd'] or os.getpgid(pid)!=pid:raise ValueError('训练进程身份不符，未发送控制信号')
 return ref
def send(ref,sig,group=False):
 if not matches(ref):raise ValueError('进程已经退出或发生变化，请刷新后重试')
 if group:os.killpg(ref['pid'],sig)
 else:os.kill(ref['pid'],sig)
def supervisor_alive(q=None):
 q=q or read(OUT/'queue.json');ref=q.get('supervisor')
 if ref:return matches(ref)
 p=identity(q.get('pid',0))
 return bool(p and str(SRC/'run_queue.py') in p['cmd'])
def validate(s):
 if not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,63}',s['id']):raise ValueError('实验编号需以英文字母开头，只含字母、数字、下划线或短横线')
 if not Path(s['model']).is_file() or Path(s['model']).suffix not in ('.pt','.yaml','.yml'):raise ValueError('请选择存在的模型权重或结构文件')
 h,w=s['hw']
 if any(type(x) is not int or x<128 or x>2048 or x%32 for x in (h,w)):raise ValueError('图像高宽需为128–2048之间的32倍数')
 for key,lo,hi,default in [('batch',1,32,16),('epochs',1,1000,100),('seed',0,2147483647,42),('workers',0,8,4)]:
  v=s.get(key,default)
  if type(v) is not int or not lo<=v<=hi:raise ValueError(f'{key}超出允许范围')
 for key in ('pose','box'):
  if not isinstance(s[key],(int,float)) or not 0<s[key]<=100:raise ValueError(f'{key}需大于0且不超过100')
 if not 0<float(s.get('lr0',.01))<=.1:raise ValueError('学习率需大于0且不超过0.1')
 if s.get('optimizer','auto') not in ('auto','MuSGD','SGD','AdamW'):raise ValueError('不支持的优化器')
 return s

def edit_spec(value,original=None):
 OUT.mkdir(parents=True,exist_ok=True)
 validate(value)
 with (OUT/'config.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  items=specs();q=read(OUT/'queue.json')
  old=original or value['id']
  if (OUT/'states'/f'{old}.json').exists() or (q.get('active')==old and supervisor_alive(q)):
   raise ValueError('此实验已经启动，参数已锁定；请复制为新实验')
  if any(s['id']==value['id'] and s['id']!=original for s in items):raise ValueError('实验编号已存在')
  index=next((i for i,s in enumerate(items) if s['id']==old),None)
  if index is not None:items[index]=value
  else:items.append(value)
  write(SPEC,items)
  with (OUT/'parameter_edits.jsonl').open('a') as f:f.write(json.dumps(dict(at=now(),original=original,value=value),ensure_ascii=False)+'\n')
def request_pause(paused):write(CONTROL,dict(manual_pause=bool(paused),at=now()))
def power():
 sample=dict(at=now(),ac=True)
 mains=[p for p in Path('/sys/class/power_supply').glob('*') if (p/'type').exists() and (p/'type').read_text().strip() in ('Mains','USB','USB_C')]
 if mains:sample['ac']=any((p/'online').exists() and (p/'online').read_text().strip()=='1' for p in mains)
 try:
  raw=subprocess.check_output(['nvidia-smi','--id=0','--query-gpu=power.draw,enforced.power.limit,temperature.gpu,utilization.gpu,memory.used','--format=csv,noheader,nounits'],text=True,timeout=4)
  v=[None if 'N/A' in x else float(x.strip()) for x in raw.strip().split(',')]
  sample.update(power_w=v[0],limit_w=v[1],temperature_c=v[2],utilization=v[3],memory_mib=v[4])
 except (OSError,ValueError,subprocess.SubprocessError) as e:sample.update(error=str(e))
 return sample

def progress(rid):
 s=read(OUT/'states'/f'{rid}.json');s.setdefault('completed_epochs',0)
 p=OUT/'runs'/rid/'results.csv'
 try:
  with p.open() as f:rows=list(csv.DictReader(f))
  s['history']=rows
  if rows:s['completed_epochs']=int(float(rows[-1]['epoch']))
 except (OSError,ValueError,KeyError):s['history']=[]
 p=OUT/f'{rid}.log'
 try:
  with p.open('rb') as f:f.seek(max(0,p.stat().st_size-40000));tail=f.read().decode(errors='replace')
  tail=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',tail)
  lines=[x.strip() for x in re.split('[\r\n]',tail) if x.strip()]
  s['log']='\n'.join(lines[-70:])
  # Limit parsing to the latest training line, not validation's separate percentage.
  train=[x for x in lines if re.search(r'\b\d+/\d+\s+\d+(?:\.\d+)?G',x)]
  if train:
   m=re.search(r'(\d+)/(\d+)\s+.*?:\s*(\d+)%',train[-1])
   if m:s['live_epoch']=int(m[1]);s['epoch_percent']=int(m[3])
 except OSError:s['log']='等待实验启动…'
 return s

def render_report(q):
 lines=['# 训练进度与结果','',f"更新时间：{now()}；队列：{q.get('status','—')}。",'']
 for spec in specs():
  r=read(OUT/'states'/f"{spec['id']}.json")
  lines += [f"## {spec.get('label',spec['id'])} · {spec['id']}",f"{r.get('status','QUEUED')}；{r.get('completed_epochs',0)}/{r.get('epochs',spec.get('epochs',100))}轮；输入{spec['hw']}，batch{spec['batch']}，pose{spec['pose']}，box{spec['box']}。",'']
  selection=r.get('selection') or read(OUT/'selection_conf050'/spec['id']/'selection.json')
  for label,key in [('Precision最高','precision_max'),('Recall参考条件下Precision最高','precision_max_with_recall_reference'),('角点RMSE最低','corner_rmse_min')]:
   m=selection.get(key)
   if m:lines.append(f"- {label}：{m['checkpoint']}；P={m['precision']:.4%}，R={m['recall']:.4%}，F1={m['f1']:.4%}，IoU={m['mean_iou']:.6f}，MSE={m['corner_mse_px2']:.4f}px²，RMSE={m['corner_rmse_px']:.4f}px。")
 lines+=['','框架验证指标见各实验结果目录；请按你的任务另行验收部署阈值与实际效果。']
 path=OUT/'实验进度与结果.md';tmp=path.with_suffix('.md.tmp');tmp.write_text('\n'.join(lines));tmp.replace(path)

def start_backend(replace=False):
 OUT.mkdir(parents=True,exist_ok=True)
 q=read(OUT/'queue.json')
 if supervisor_alive(q):
  if q.get('version')==2 and not replace:request_pause(False);return
  # Replace only the old supervisor. The training worker and dataloader continue untouched.
  ref=identity(q['pid']);send(ref,signal.SIGSTOP)
  try:
   snapshot=read(OUT/'queue.json');snapshot['worker']=worker_ref(snapshot['child_pid'])
   write(OUT/'adopt.json',snapshot)
   send(ref,signal.SIGTERM);send(ref,signal.SIGCONT)
  except BaseException:
   if matches(ref):send(ref,signal.SIGCONT)
   raise
  for _ in range(40):
   if not matches(ref):break
   time.sleep(.05)
  if matches(ref):raise ValueError('旧队列尚未退出，未启动第二条队列')
  args=['--adopt']
 else:
  qworker=q.get('worker')
  if qworker and matches(qworker):write(OUT/'adopt.json',q);args=['--adopt']
  else:args=[]
 request_pause(False)
 with (OUT/'supervisor.log').open('a') as log:
  subprocess.Popen(['/usr/bin/python3',str(Path(__file__).resolve()),'--daemon',*args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)

def daemon(adopt=False):
 OUT.mkdir(parents=True,exist_ok=True)
 lock=(OUT/'queue.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 q=dict(version=2,status='RUNNING',pid=os.getpid(),supervisor=identity(os.getpid()),started_at=now(),active=None,child_pid=None,completed=[],pending=[])
 sample=power();last_power=0;thermal=False;last_report=0
 def publish():
  nonlocal last_report
  q.update(updated_at=now(),completed=[s['id'] for s in specs() if read(OUT/'states'/f"{s['id']}.json").get('status')=='COMPLETE'],pending=[s['id'] for s in specs() if s.get('enabled',True) and not (OUT/'states'/f"{s['id']}.json").exists()]);write(OUT/'queue.json',q)
  if time.monotonic()-last_report>30 or q['status'] in ('COMPLETE','FAILED'):
   render_report(q);last_report=time.monotonic()
 def gate(ref=None):
  nonlocal sample,last_power,thermal
  if time.monotonic()-last_power>=5:
   sample=power();last_power=time.monotonic()
   with (OUT/'power.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  temp=sample.get('temperature_c')
  if temp is not None and temp>=87:thermal=True
  elif temp is not None and temp<=80:thermal=False
  manual=read(CONTROL).get('manual_pause',False)
  reason='手动暂停' if manual else '等待接通电源' if not sample.get('ac') else '等待温度恢复' if thermal else ''
  paused=bool(reason)
  if ref and matches(ref):
   stopped=identity(ref['pid'])['state'] in ('T','t')
   if paused and not stopped:send(ref,signal.SIGSTOP,True)
   if not paused and stopped:send(ref,signal.SIGCONT,True)
  q.update(paused=paused,pause_reason=reason,power=sample,status='PAUSED' if paused else 'RUNNING');publish()
  return not paused
 def watch(ref,phase,rid,proc=None):
  q.update(worker=ref,child_pid=ref['pid'],active=rid,phase=phase)
  while matches(ref):
   q['phase']=read(OUT/'states'/f'{rid}.json').get('status',phase) if phase!='PRECHECK' else phase
   gate(ref);time.sleep(1)
  if proc is not None and proc.wait()!=0:raise RuntimeError(f'{rid}退出异常，请查看日志')
  if phase!='PRECHECK' and read(OUT/'states'/f'{rid}.json').get('status')!='COMPLETE':raise RuntimeError(f'{rid}尚未完成，已保留现场；请查看日志')
  q.update(worker=None,child_pid=None,active=None);publish()
 def launch(s,check=False):
  while not gate():time.sleep(1)
  args=[str(PYTHON),str(SRC/'train.py'),s['id']]+(['--check'] if check else [])
  log=OUT/(f"precheck_{s['id']}.log" if check else f"{s['id']}.log")
  with log.open('a') as f:p=subprocess.Popen(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'PYTHONUNBUFFERED':'1','OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4'})
  ref=None
  for _ in range(40):
   try:ref=worker_ref(p.pid);break
   except ValueError:
    if p.poll() is not None:break
    time.sleep(.05)
  if not ref:raise RuntimeError(f"{s['id']}未能启动，请查看日志")
  watch(ref,'PRECHECK' if check else 'TRAINING',s['id'],p)
 try:
  if adopt:
   old=read(OUT/'adopt.json');ref=old['worker']
   if matches(ref):watch(ref,old.get('phase','TRAINING'),old['active'])
   elif read(OUT/'states'/f"{old['active']}.json").get('status')!='COMPLETE':raise RuntimeError('接管时原训练已经退出，请检查日志')
  while True:
   publish();eligible=[s for s in specs() if s.get('enabled',True) and read(OUT/'states'/f"{s['id']}.json").get('status')!='COMPLETE']
   if not eligible:break
   with (OUT/'config.lock').open('a') as configlock:
    fcntl.flock(configlock,fcntl.LOCK_EX)
    eligible=[s for s in specs() if s.get('enabled',True) and read(OUT/'states'/f"{s['id']}.json").get('status')!='COMPLETE']
    if not eligible:break
    s=eligible[0];validate(s)
    if (OUT/'states'/f"{s['id']}.json").exists():raise RuntimeError(f"{s['id']}有未完成记录，禁止覆盖；可复制为新实验")
    # Reserve this config under the same lock used by the editor.
    q.update(active=s['id'],phase='PRECHECK');publish()
   launch(s,True)
   assert read(OUT/'precheck'/f"{s['id']}.json").get('status')=='PASS'
   # GUI locks editing during precheck, keeping this checked config immutable through launch.
   write(OUT/'dispatched'/f"{s['id']}.json",dict(at=now(),spec=s,spec_digest=digest(s)))
   launch(s)
  q.update(status='COMPLETE',active=None,child_pid=None,worker=None,finished_at=now());publish()
 except BaseException:
  q.update(status='FAILED',error=traceback.format_exc());publish();raise
 finally:lock.close()
if __name__=='__main__' and '--daemon' in sys.argv:daemon('--adopt' in sys.argv)
