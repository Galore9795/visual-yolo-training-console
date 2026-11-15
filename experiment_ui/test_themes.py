import os,tempfile,time,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPoint
import control as c
import app
import appearance
from themes import palette,contrast
from glass_adapter import glass_api
from test_support import IsolatedWorkspace
class ThemeTests(IsolatedWorkspace,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_color_contrast(self):
  for name in ('light','dark'):
   p=palette(name)
   for bg in ('bg','surface','selection','field'):
    for fg in ('text','secondary','muted'):
     with self.subTest(theme=name,fg=fg,bg=bg):self.assertGreaterEqual(contrast(p[fg],p[bg]),4.5)
   for fg,bg in [('accent_text','accent'),('disabled_text','disabled_bg'),('positive','positive_bg'),('warning','warning_bg'),('danger','danger_bg')]:self.assertGreaterEqual(contrast(p[fg],p[bg]),4.5)
   self.assertGreaterEqual(contrast(p['border'],p['field']),3.)
 def test_system_theme_resolution(self):
  for scheme,gtk,expected in [('prefer-dark','WhiteSur-Light','dark'),('prefer-light','WhiteSur-Dark','light'),('default','WhiteSur-Dark','dark'),('default','WhiteSur-Light','light')]:self.assertEqual(appearance.resolve_theme(scheme,gtk),expected)
 def test_system_changes_preserve_draft(self):
  with tempfile.TemporaryDirectory() as temp:
   out=Path(temp);spec=out/'experiments.json';c.write(spec,c.specs())
   with patch.object(c,'OUT',out),patch.object(c,'SPEC',spec),patch.object(app,'desktop_theme',return_value='light'):
    w=app.Window();w.timer.stop();w.appearance_monitor.stop()
    try:
     self.assertFalse(hasattr(w,'theme_switch'));self.assertFalse(hasattr(w,'contrast_switch'))
     w.card_clicked('B10_pose24');w.fields['pose'].setValue(25.);before=w.values();self.assertTrue(w.dirty)
     w.appearance_monitor.current='light'
     with patch.object(appearance,'desktop_theme',return_value='dark'):w.appearance_monitor.reload()
     self.assertEqual(w.theme,'dark');self.assertEqual(w.values(),before);self.assertTrue(w.dirty);self.assertEqual(w.current,'B10_pose24');self.assertEqual(w.chart.colors['bg'],palette('dark')['bg']);self.assertEqual(w.cards['B10_pose24'].colors['bg'],palette('dark')['bg'])
     with patch.object(appearance,'desktop_theme',return_value='light'):w.appearance_monitor.reload()
     self.assertEqual(w.values(),before);self.assertEqual(w.theme,'light')
     c.write(out/'states/B10_pose24.json',dict(status='TRAINING',completed_epochs=2,epochs=100));w.refresh();self.assertTrue(w.fields['pose'].isReadOnly());self.assertTrue(w.formbox.isEnabled());self.assertFalse(w.savebutton.isEnabled())
    finally:w.dirty=False;w.close()
 def test_glass_uses_existing_component(self):
  w=app.Window();w.timer.stop()
  try:
   api=glass_api()
   if api:self.assertIsInstance(w.more_menu,api.GlassMenu);self.assertTrue(w.more_menu.property('desktopGlass'))
   else:self.assertFalse(w.more_menu.property('desktopGlass'))
   # Render the actual shared popup, not a locally painted imitation.
   w.more_menu.popup(QPoint(10,10))
   self.app.processEvents();self.assertFalse(w.more_menu.grab().isNull());w.more_menu.hide()
  finally:w.close()
 def test_live_monitor_with_isolated_gsettings(self):
  with tempfile.TemporaryDirectory() as temp:
   out=Path(temp);state=out/'scheme';state.write_text('prefer-light');fake=out/'gsettings'
   fake.write_text('#!/usr/bin/python3\nimport sys,time\nfrom pathlib import Path\np=Path('+repr(str(state))+')\nif sys.argv[1]=="get":\n print(repr(p.read_text()) if sys.argv[-1]=="color-scheme" else "\\\'WhiteSur-Light\\\'")\nelse:\n last=p.read_text()\n while True:\n  value=p.read_text()\n  if value!=last: print("color-scheme: "+value,flush=True);last=value\n  time.sleep(.03)\n');fake.chmod(0o755)
   with patch.dict(os.environ,{'PATH':str(out)+':'+os.environ['PATH']}):
    monitor=appearance.AppearanceMonitor(None);changes=[];monitor.changed.connect(changes.append);monitor.start()
    try:
     end=time.monotonic()+1.
     while time.monotonic()<end:self.app.processEvents();time.sleep(.02)
     state.write_text('prefer-dark');end=time.monotonic()+3.
     while not changes and time.monotonic()<end:self.app.processEvents();time.sleep(.02)
     self.assertEqual(changes,['dark'])
    finally:monitor.stop()
if __name__=='__main__':unittest.main()
