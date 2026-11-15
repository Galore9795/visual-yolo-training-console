from pathlib import Path
from unittest.mock import patch
import tempfile
import control as c
class IsolatedWorkspace:
 def setUp(self):
  self.workspace=tempfile.TemporaryDirectory();out=Path(self.workspace.name);model=out/'model.pt';model.touch()
  values=[dict(id=rid,model=str(model),hw=[640,640],batch=4,pose=12.,box=7.5) for rid in ['CTRL_640','B10_pose24','B11_pose24_boxhalf','C10_yolo11n','CTRL_960_b4','A40_p2p4']]
  c.write(out/'experiments.json',values)
  self.overrides=[patch.object(c,'SPEC',out/'experiments.json'),patch.object(c,'OUT',out),patch.object(c,'CONTROL',out/'control.json')]
  for p in self.overrides:p.start()
 def tearDown(self):
  for p in reversed(self.overrides):p.stop()
  self.workspace.cleanup()
