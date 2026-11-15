from pathlib import Path
import runpy,sys
ui=Path(__file__).resolve().parent/'experiment_ui'
sys.path.insert(0,str(ui))
runpy.run_path(str(ui/'app.py'),run_name='__main__')
