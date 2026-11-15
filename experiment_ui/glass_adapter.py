"""Call the user's existing CrossPet glass component; do not duplicate its renderer."""
from functools import lru_cache
from pathlib import Path
import ast,importlib,sys
from PyQt6.QtWidgets import QMenu

@lru_cache(maxsize=1)
def glass_api():
 # Resolve the currently managed installation, rather than choosing an old version directory.
 launcher=Path.home()/'.local/bin/crosspet'
 try:
  tree=ast.parse(launcher.read_text())
  root=next(Path(node.value.args[0].value) for node in tree.body if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='chdir' and node.value.args and isinstance(node.value.args[0],ast.Constant))
  if not (root/'crosspet/glass.py').is_file():return None
  sys.path.insert(0,str(root))
  return importlib.import_module('crosspet.glass')
 except (OSError,ValueError,StopIteration,ImportError,SyntaxError):return None

def glass(title,parent):
 api=glass_api()
 menu=api.GlassMenu(title,parent,preferences={'menuAppearance':'auto'}) if api else QMenu(title,parent)
 menu.setProperty('desktopGlass',api is not None)
 return menu

def refresh_glass(menu,theme):
 if menu.property('desktopGlass'):
  menu.preferences['menuAppearance']=theme
  menu.refresh_appearance();menu.update()
