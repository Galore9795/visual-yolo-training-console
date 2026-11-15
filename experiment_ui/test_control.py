import os,signal,subprocess,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import control as c
class ControlTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.out=Path(self.temp.name);self.spec=self.out/'experiments.json';self.spec.write_text('[]')
  self.patch1=patch.object(c,'OUT',self.out);self.patch2=patch.object(c,'SPEC',self.spec);self.patch1.start();self.patch2.start()
 def tearDown(self):self.patch1.stop();self.patch2.stop();self.temp.cleanup()
 def value(self):
  (self.out/'fake.pt').touch()
  return dict(id='Test',model=str(self.out/'fake.pt'),hw=[384,640],batch=16,pose=12.,box=7.5)
 def test_validation_and_lock(self):
  (self.out/'fake.pt').touch();s=self.value();c.edit_spec(s);self.assertEqual(len(c.specs()),1)
  s['pose']=24.;c.edit_spec(s,'Test');self.assertEqual(c.specs()[0]['pose'],24.)
  c.write(self.out/'states/Test.json',{'status':'TRAINING'})
  with self.assertRaises(ValueError):c.edit_spec(s,'Test')
  for changed in [dict(batch=0),dict(hw=[383,640]),dict(epochs=0),dict(id='../escape')]:
   v={**self.value(),**changed}
   with self.assertRaises(ValueError):c.validate(v)
 def test_pause_request(self):
  with patch.object(c,'CONTROL',self.out/'control.json'):
   c.request_pause(True);self.assertTrue(c.read(c.CONTROL)['manual_pause']);c.request_pause(False);self.assertFalse(c.read(c.CONTROL)['manual_pause'])
 def test_identity_rejects_reused_pid(self):
  p=subprocess.Popen(['/usr/bin/python3','-c','import time;time.sleep(10)'],start_new_session=True)
  try:
   ref=c.identity(p.pid);self.assertTrue(c.matches(ref));bad={**ref,'start':'-1'}
   with self.assertRaises(ValueError):c.send(bad,signal.SIGSTOP)
   c.send(ref,signal.SIGSTOP,True);time.sleep(.05);self.assertEqual(c.identity(p.pid)['state'],'T')
   c.send(ref,signal.SIGCONT,True)
  finally:p.terminate();p.wait()
  self.assertFalse(c.matches(ref))
 def test_progress_ignores_validation_percentage(self):
  (self.out/'runs/Test').mkdir(parents=True)
  (self.out/'runs/Test/results.csv').write_text('epoch,time\n1,100\n')
  (self.out/'Test.log').write_text('2/100 3.01G losses: 42% xxx\r Class all: 100% xxx')
  p=c.progress('Test');self.assertEqual(p['completed_epochs'],1);self.assertEqual(p['live_epoch'],2);self.assertEqual(p['epoch_percent'],42)
 def test_daemon_pause_resume_and_completion(self):
  import multiprocessing
  src=self.out/'src';src.mkdir();(src/'fake.pt').touch()
  out=self.out
  script="""import json,time,sys,os
from pathlib import Path
out=Path(OUT_LITERAL)
rid=sys.argv[1]
def write(path,data):
 path.parent.mkdir(exist_ok=True,parents=True);p=path.with_suffix('.tmp');p.write_text(json.dumps(data));p.replace(path)
if '--check' in sys.argv:
 write(out/'precheck'/f'{rid}.json',{'status':'PASS'})
else:
 for i in range(60):
  write(out/'states'/f'{rid}.json',{'status':'TRAINING','completed_epochs':i,'epochs':60,'pid':os.getpid()});time.sleep(.025)
 write(out/'states'/f'{rid}.json',{'status':'COMPLETE','completed_epochs':60,'epochs':60})
""".replace('OUT_LITERAL',repr(str(out)))
  (src/'train.py').write_text(script)
  value={**self.value(),'model':str(src/'fake.pt'),'epochs':60};c.write(self.spec,[value])
  with patch.object(c,'SRC',src),patch.object(c,'CONTROL',out/'control.json'),patch.object(c,'PYTHON',Path('/usr/bin/python3')),patch.object(c,'power',lambda:dict(ac=True,temperature_c=45.,at=c.now())):
   c.request_pause(False);p=multiprocessing.get_context('fork').Process(target=c.daemon);p.start()
   def wait(predicate,seconds=8):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
     if predicate():return
     time.sleep(.05)
    self.fail('Timed out: '+str(c.read(out/'queue.json')))
   try:
    wait(lambda:c.read(out/'states/Test.json').get('status')=='TRAINING')
    with self.assertRaises(ValueError):c.edit_spec(value,'Test')
    c.request_pause(True);wait(lambda:c.read(out/'queue.json').get('paused'))
    ref=c.read(out/'queue.json')['worker'];self.assertEqual(c.identity(ref['pid'])['state'],'T');before=c.read(out/'states/Test.json')['completed_epochs'];time.sleep(.15);self.assertEqual(c.read(out/'states/Test.json')['completed_epochs'],before)
    c.request_pause(False);wait(lambda:c.read(out/'queue.json').get('status')=='COMPLETE')
    p.join(3);self.assertEqual(p.exitcode,0);self.assertEqual(c.read(out/'states/Test.json')['status'],'COMPLETE')
   finally:
    if p.is_alive():p.terminate();p.join(3)
    q=c.read(out/'queue.json');ref=q.get('worker')
    if ref and c.matches(ref):c.send(ref,signal.SIGCONT,True);c.send(ref,signal.SIGTERM,True)

if __name__=='__main__':unittest.main()
