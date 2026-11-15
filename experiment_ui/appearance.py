"""Read and observe GNOME appearance without changing desktop preferences."""
import shutil,subprocess
from PyQt6.QtCore import QObject,QProcess,QTimer,pyqtSignal
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication

def resolve_theme(scheme,gtk_theme='',fallback='light'):
 scheme=scheme.strip(" '\"\n")
 if scheme=='prefer-dark':return 'dark'
 if scheme=='prefer-light':return 'light'
 if gtk_theme:return 'dark' if 'dark' in gtk_theme.lower() or 'inverse' in gtk_theme.lower() else 'light'
 return fallback

def desktop_theme():
 app=QApplication.instance()
 fallback='dark' if app and app.palette().color(QPalette.ColorRole.Window).lightness()<128 else 'light'
 if not shutil.which('gsettings'):return fallback
 values=[]
 for key in ('color-scheme','gtk-theme'):
  try:
   result=subprocess.run(['gsettings','get','org.gnome.desktop.interface',key],capture_output=True,text=True,timeout=.35)
   values.append(result.stdout.strip() if result.returncode==0 else '')
  except (OSError,subprocess.TimeoutExpired):values.append('')
 return resolve_theme(*values,fallback=fallback)

class AppearanceMonitor(QObject):
 changed=pyqtSignal(str)
 def __init__(self,parent):
  super().__init__(parent);self.process=None;self.current=desktop_theme();self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(120);self.timer.timeout.connect(self.reload)
 def start(self):
  if self.process is not None or not shutil.which('gsettings'):return
  self.process=QProcess(self);self.process.readyReadStandardOutput.connect(self.read);self.process.start('gsettings',['monitor','org.gnome.desktop.interface'])
 def read(self):
  lines=bytes(self.process.readAllStandardOutput()).decode(errors='replace')
  if 'color-scheme:' in lines or 'gtk-theme:' in lines:self.timer.start()
 def reload(self):
  theme=desktop_theme()
  if theme!=self.current:self.current=theme;self.changed.emit(theme)
 def stop(self):
  self.timer.stop()
  if self.process is not None:
   if self.process.state()!=QProcess.ProcessState.NotRunning:
    self.process.terminate()
    if not self.process.waitForFinished(150):self.process.kill();self.process.waitForFinished(150)
   self.process.deleteLater();self.process=None
