import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
import app
import control as c
from test_support import IsolatedWorkspace
class UITests(IsolatedWorkspace,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_cards_edit_save_clone_and_controls(self):
  with tempfile.TemporaryDirectory() as temp:
   out=Path(temp);specfile=out/'experiments.json';values=c.specs();c.write(specfile,values);c.write(out/'states/CTRL_640.json',dict(status='TRAINING',completed_epochs=3,epochs=100))
   with patch.object(c,'OUT',out),patch.object(c,'SPEC',specfile),patch.object(c,'CONTROL',out/'control.json'):
    w=app.Window();w.timer.stop()
    try:
     self.assertEqual(len(w.cards),6);w.card_clicked('CTRL_640');self.assertFalse(w.savebutton.isEnabled())
     w.card_clicked('B10_pose24');self.assertTrue(w.savebutton.isEnabled());w.fields['pose'].setValue(25.);w.refresh();self.assertEqual(w.fields['pose'].value(),25.);w.save();self.assertEqual(c.specs()[1]['pose'],25.)
     w.clone();self.assertIsNone(w.current);self.assertFalse(w.fields['enabled'].isChecked());self.assertIn('_copy',w.fields['id'].text());w.save();self.assertEqual(len(c.specs()),7);self.assertEqual(len(w.cards),7)
     with patch.object(c,'start_backend') as start:w.resume();start.assert_called_once()
     w.pause_queue();self.assertTrue(c.read(c.CONTROL)['manual_pause'])
    finally:w.dirty=False;w.close()
if __name__=='__main__':unittest.main()
