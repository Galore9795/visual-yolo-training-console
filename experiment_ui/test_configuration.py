import tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from configure import configure
class ConfigurationTests(unittest.TestCase):
 def test_configure_preserves_existing(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);model=root/'model.pt';model.touch();data=root/'data.yaml';data.touch()
   configure(root,data,model);before=(root/'experiments.json').read_bytes()
   with self.assertRaises(FileExistsError):configure(root,data,model)
   self.assertEqual((root/'experiments.json').read_bytes(),before)
 def test_missing_model_creates_no_config(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)
   with self.assertRaises(ValueError):configure(root,root/'missing.yaml',root/'missing.pt')
   self.assertFalse((root/'experiments.json').exists())
