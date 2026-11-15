"""RM native desktop experiment console. GUI uses system Qt; training keeps its own venv."""
import sys,os,math,json,subprocess
from pathlib import Path
from PyQt6.QtCore import Qt,QTimer,QUrl,QPointF
from PyQt6.QtGui import QColor,QPainter,QPen,QDesktopServices,QFont,QPalette
from PyQt6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTreeWidget,QTreeWidgetItem,QFormLayout,QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QCheckBox,QFileDialog,QProgressBar,QPlainTextEdit,QSplitter,QMessageBox,QGroupBox,QFrame,QAbstractItemView,QScrollArea,QGridLayout,QSizePolicy)
import control as ctl
from themes import palette,stylesheet
from appearance import desktop_theme,AppearanceMonitor
from glass_adapter import glass,refresh_glass
LABELS={'CTRL_640':'640 本机对照','B10_pose24':'B1 · 提高角点权重','B11_pose24_boxhalf':'B1 · 提高角点并降低框权重','C10_yolo11n':'C1 · YOLO11 代际对照','CTRL_960_b4':'960 同批量对照','A40_p2p4':'A4 · P2 小目标结构'}
STATUS={'TRAINING':'训练中','STARTING':'准备中','PRECHECK':'检查配置','EVALUATING':'评估权重','COMPLETE':'已完成','FAILED':'异常停止','QUEUED':'待运行','PAUSED':'已暂停'}
class Chart(QWidget):
 def __init__(self):super().__init__();self.rows=[];self.colors=palette('light');self.setMinimumHeight(125)
 def paintEvent(self,event):
  c=self.colors;p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);w=self.width();h=self.height();p.fillRect(self.rect(),QColor(c['surface']));p.setPen(QColor(c['secondary']));p.drawText(14,22,'验证趋势 · 框 mAP50')
  vals=[]
  for r in self.rows:
   try:vals.append(float(r['metrics/mAP50(B)']))
   except (KeyError,ValueError):pass
  if not vals:p.drawText(14,65,'完成首轮验证后显示');return
  p.setPen(QColor(c['border']));p.drawLine(40,h-25,w-18,h-25);p.drawLine(40,35,40,h-25)
  p.setPen(QColor(c['muted']));p.drawText(8,45,'1.0');p.drawText(15,h-22,'0');p.drawText(w-110,h-5,f'已验证 {len(vals)} 轮')
  p.setPen(QPen(QColor(c['accent']),2))
  pts=[QPointF(40+i*(w-60)/max(1,len(vals)-1),h-25-v*(h-65)) for i,v in enumerate(vals)]
  if len(pts)==1:p.drawEllipse(pts[0],3,3)
  for a,b in zip(pts,pts[1:]):p.drawLine(a,b)
class ExperimentCard(QFrame):
 def __init__(self,rid,clicked):
  super().__init__();self.rid=rid;self.clicked=clicked;self.colors=palette('light');self.setObjectName('experimentCard');self.setCursor(Qt.CursorShape.PointingHandCursor);self.setMinimumHeight(148);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.setAccessibleName(rid)
  v=QVBoxLayout(self);v.setContentsMargins(14,10,14,10);v.setSpacing(5)
  top=QHBoxLayout();self.code=QLabel(rid);self.code.setStyleSheet('color:#aaa4c9;font-size:11px;');top.addWidget(self.code);top.addStretch();self.tag=QLabel();self.tag.setStyleSheet('font-size:11px;');top.addWidget(self.tag);v.addLayout(top)
  self.title=QLabel();self.title.setWordWrap(True);self.title.setStyleSheet('font-size:16px;font-weight:600;');v.addWidget(self.title)
  self.recipe=QLabel();self.recipe.setStyleSheet('color:#a9a3bb;font-size:12px;');v.addWidget(self.recipe)
  self.config=QLabel();self.config.setStyleSheet('color:#a9a3bb;font-size:12px;');v.addWidget(self.config)
  self.progress=QProgressBar();self.progress.setRange(0,1000);self.progress.setFixedHeight(6);self.progress.setStyleSheet('min-height:6px;max-height:6px;');self.progress.setTextVisible(False);v.addWidget(self.progress)
  self.foot=QLabel();self.foot.setStyleSheet('color:#aaa4c9;font-size:11px;');v.addWidget(self.foot)
 def mousePressEvent(self,event):
  if event.button()==Qt.MouseButton.LeftButton:self.clicked(self.rid)
  super().mousePressEvent(event)
 def update_data(self,s,state,status,selected=False):
  self.title.setText(s.get('label',LABELS.get(s['id'],s['id'])))
  self.tag.setText(STATUS.get(status,status) if s.get('enabled',True) else '草稿')
  self.recipe.setText(f"{s['hw'][0]} × {s['hw'][1]}  ·  batch {s['batch']}  ·  {Path(s['model']).stem}")
  self.config.setText(f"pose {s['pose']:g}   /   box {s['box']:g}   /   seed {s.get('seed',42)}")
  done=state.get('completed_epochs',0);total=state.get('epochs',s.get('epochs',100));self.progress.setValue(int(done/max(1,total)*1000))
  self.foot.setText(f"{done} / {total} 轮已完成"+('   ·   点击编辑' if not state else '   ·   参数已锁定'))
  self.selected_card=selected;self.status_code=status;self.restyle()
 def restyle(self):
  c=self.colors;selected=getattr(self,'selected_card',False);status=getattr(self,'status_code','QUEUED')
  bg=c['selection'] if selected else c['surface']
  self.setStyleSheet(f"QFrame#experimentCard {{background:{bg};border:{'2' if selected else '1'}px solid {c['accent'] if selected else c['subtle']};border-radius:12px;}} QFrame#experimentCard:hover,QFrame#experimentCard:focus {{border:2px solid {c['focus']};}}")
  for label in (self.code,self.recipe,self.config,self.foot):label.setStyleSheet(f"background:transparent;color:{c['secondary']};font-size:12px;")
  self.title.setStyleSheet(f"background:transparent;color:{c['text']};font-size:16px;font-weight:600;")
  fg,badge=(c['positive'],c['positive_bg']) if status in ('TRAINING','COMPLETE') else (c['warning'],c['warning_bg']) if status=='PAUSED' else (c['danger'],c['danger_bg']) if status=='FAILED' else (c['secondary'],c['disabled_bg'])
  self.tag.setStyleSheet(f"background:{badge};color:{fg};padding:3px 7px;border-radius:7px;font-size:11px;font-weight:600;")
 def keyPressEvent(self,event):
  if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space):self.clicked(self.rid)
  else:super().keyPressEvent(event)

class Window(QMainWindow):
 def __init__(self):
  super().__init__();self.setWindowTitle('可视化的yolo模型训练控制台');self.resize(1360,920);self.current=None;self.dirty=False;self.loading=False;self.last_signature=None;self.cards={};self.theme=desktop_theme()
  shell=QWidget();self.setCentralWidget(shell);layout=QVBoxLayout(shell);layout.setContentsMargins(24,20,24,18);layout.setSpacing(14)
  header=QHBoxLayout();title=QLabel('YOLO  /  模型训练控制台');title.setObjectName('title');header.addWidget(title);header.addStretch();appearance_label=QLabel('外观 · 跟随系统');appearance_label.setObjectName('muted');header.addWidget(appearance_label);header.addSpacing(14);self.badge=QLabel('正在连接本机队列');self.badge.setObjectName('queueBadge');header.addWidget(self.badge);layout.addLayout(header)
  sub=QLabel('本机训练  ·  串行实验队列  ·  日志与验证趋势');sub.setObjectName('muted');layout.addWidget(sub)
  buttons=QHBoxLayout();self.start=QPushButton('▶  开始 / 继续队列');self.start.setObjectName('primary');self.start.clicked.connect(self.resume);buttons.addWidget(self.start)
  self.pause=QPushButton('Ⅱ  暂停队列');self.pause.clicked.connect(self.pause_queue);buttons.addWidget(self.pause)
  for text,slot in [('＋ 新建实验',self.new),('复制所选',self.clone),('打开结果目录',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctl.OUT))))]:
   b=QPushButton(text);b.clicked.connect(slot);buttons.addWidget(b)
  self.more_button=QPushButton('更多 ▾');self.more_menu=glass('实验工作台',self);self.more_menu.addAction('显示 / 收起日志',lambda:self.log.setVisible(not self.log.isVisible()));self.more_menu.addAction('打开结果目录',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctl.OUT))));self.more_button.setMenu(self.more_menu);buttons.addWidget(self.more_button);buttons.addStretch();layout.addLayout(buttons)
  self.active=QLabel('当前实验：—');self.active.setObjectName('active');layout.addWidget(self.active)
  self.detail=QLabel();self.detail.setWordWrap(True);layout.addWidget(self.detail)
  self.bar=QProgressBar();self.bar.setRange(0,10000);self.bar.setFormat('%p%');self.bar.setObjectName('overallProgress');self.bar.setFixedHeight(8);self.bar.setTextVisible(False);layout.addWidget(self.bar)
  self.power=QLabel();self.power.setObjectName('muted');layout.addWidget(self.power)
  split=QSplitter();layout.addWidget(split,1)
  left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(0,0,10,0);ll.addWidget(QLabel('实验队列'))
  self.tree=QTreeWidget();self.tree.setHeaderLabels(['实验名称 / 编号','状态','轮次']);self.tree.setRootIsDecorated(False);self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.tree.setColumnWidth(0,270);self.tree.setColumnWidth(1,85);self.tree.itemSelectionChanged.connect(self.choose);self.tree.setParent(left);self.tree.hide()
  self.cardscroll=QScrollArea();self.cardscroll.setWidgetResizable(True);self.cardscroll.setFrameShape(QFrame.Shape.NoFrame);self.cardhost=QWidget();self.cardgrid=QGridLayout(self.cardhost);self.cardgrid.setContentsMargins(0,0,4,0);self.cardgrid.setSpacing(12);self.cardscroll.setWidget(self.cardhost);ll.addWidget(self.cardscroll,1);split.addWidget(left)
  right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(10,0,0,0)
  self.formbox=QGroupBox('实验参数');form=QFormLayout(self.formbox);form.setSpacing(9);self.fields={}
  def field(key,label,widget):
   self.fields[key]=widget;form.addRow(label,widget)
   if isinstance(widget,QLineEdit):widget.textChanged.connect(self.changed)
   elif isinstance(widget,QComboBox):widget.currentTextChanged.connect(self.changed)
   elif isinstance(widget,QCheckBox):widget.toggled.connect(self.changed)
   else:widget.valueChanged.connect(self.changed)
  field('id','实验编号',QLineEdit());field('label','显示名称',QLineEdit());field('model','模型文件',QLineEdit())
  browse=QPushButton('选择权重 / 结构文件…');browse.clicked.connect(self.browse);form.addRow('',browse);self.browse_button=browse
  for key,label,lo,hi,step in [('height','输入高度',128,2048,32),('width','输入宽度',128,2048,32),('batch','每批图片数',1,32,1),('epochs','训练轮数',1,1000,1),('seed','随机种子',0,2147483647,1),('workers','数据加载进程',0,8,1)]:
   widget=QSpinBox();widget.setRange(lo,hi);widget.setSingleStep(step);field(key,label,widget)
  for key,label,lo,hi,dec,step in [('pose','角点损失权重',.01,100.,3,.1),('box','检测框损失权重',.01,100.,3,.1),('lr0','初始学习率',.000001,.1,6,.001)]:
   widget=QDoubleSpinBox();widget.setRange(lo,hi);widget.setDecimals(dec);widget.setSingleStep(step);field(key,label,widget)
  combo=QComboBox();combo.addItems(['auto','MuSGD','SGD','AdamW']);field('optimizer','优化器',combo)
  field('enabled','加入自动队列',QCheckBox())
  note=QLabel('FP32 · AMP关闭 · nbs=64 · 无增强\nauto 优化器由框架选择学习率，手填学习率仅对指定优化器生效。');note.setWordWrap(True);note.setObjectName('muted');form.addRow(note)
  formscroll=QScrollArea();formscroll.setWidgetResizable(True);formscroll.setFrameShape(QFrame.Shape.NoFrame);formscroll.setWidget(self.formbox);rl.addWidget(formscroll,1)
  self.locknote=QLabel();self.locknote.setWordWrap(True);rl.addWidget(self.locknote)
  savebar=QHBoxLayout();self.savebutton=QPushButton('保存参数');self.savebutton.setObjectName('primary');self.savebutton.clicked.connect(self.save);savebar.addWidget(self.savebutton);revert=QPushButton('放弃修改');revert.clicked.connect(self.reload_form);savebar.addWidget(revert);rl.addLayout(savebar);rl.addStretch();split.addWidget(right);split.setSizes([800,480])
  self.chart=Chart();ll.addWidget(self.chart);self.chart.setMaximumHeight(135)
  self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumBlockCount(100);self.log.setMinimumHeight(105);self.log.setMaximumHeight(130);ll.addWidget(self.log);self.log.hide()
  self.message=QLabel('关闭窗口不会停止后台实验。暂停保留内存并占用显存；关机后不能靠“继续”恢复内存状态。');self.message.setObjectName('muted');self.message.setWordWrap(True);layout.addWidget(self.message)
  self.apply_theme(self.theme)
  self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(1500);self.refresh();self.appearance_monitor=AppearanceMonitor(self);self.appearance_monitor.changed.connect(self.apply_theme);self.appearance_monitor.start()
 def apply_theme(self,name):
  self.theme=name;self.colors=palette(name);c=self.colors
  # Apply a matching native palette so popup menus/dialogs inherit the same appearance.
  pal=QPalette()
  for role,key in [(QPalette.ColorRole.Window,'bg'),(QPalette.ColorRole.WindowText,'text'),(QPalette.ColorRole.Base,'field'),(QPalette.ColorRole.AlternateBase,'surface'),(QPalette.ColorRole.Text,'text'),(QPalette.ColorRole.Button,'surface'),(QPalette.ColorRole.ButtonText,'text'),(QPalette.ColorRole.Highlight,'accent'),(QPalette.ColorRole.HighlightedText,'accent_text'),(QPalette.ColorRole.ToolTipBase,'raised'),(QPalette.ColorRole.ToolTipText,'text')]:pal.setColor(role,QColor(c[key]))
  for role in (QPalette.ColorRole.Text,QPalette.ColorRole.ButtonText,QPalette.ColorRole.WindowText):pal.setColor(QPalette.ColorGroup.Disabled,role,QColor(c['disabled_text']))
  QApplication.instance().setPalette(pal);self.setStyleSheet(stylesheet(c));self.chart.colors=c;self.chart.update()
  self.chart.setToolTip('曲线采用训练框架每轮验证指标；最终 Precision / Recall / 角点误差另按 conf=0.50 选模。')
  for card in self.cards.values():card.colors=c;card.restyle()
  refresh_glass(self.more_menu,name)
  if hasattr(self,'timer'):self.refresh()
 def changed(self,*args):
  if not self.loading:self.dirty=True;self.locknote.setText('有未保存的参数修改。')
 def problem(self,e):QMessageBox.warning(self,'操作未完成',str(e))
 def resume(self):
  try:ctl.start_backend();self.message.setText('已请求开始 / 继续，状态将在数秒内更新。');self.refresh()
  except Exception as e:self.problem(e)
 def pause_queue(self):
  try:ctl.request_pause(True);self.message.setText('已请求暂停整个队列，等待后台确认；当前训练保留在内存中。');self.refresh()
  except Exception as e:self.problem(e)
 def card_clicked(self,rid):
  for i in range(self.tree.topLevelItemCount()):
   item=self.tree.topLevelItem(i)
   if item.data(0,Qt.ItemDataRole.UserRole)==rid:self.tree.setCurrentItem(item);break
 def selected(self):
  items=self.tree.selectedItems();return items[0].data(0,Qt.ItemDataRole.UserRole) if items else None
 def choose(self):
  rid=self.selected()
  if rid==self.current:return
  if self.dirty:
   result=QMessageBox.question(self,'尚未保存','切换实验将放弃当前修改，是否切换？')
   if result!=QMessageBox.StandardButton.Yes:
    self.select_id(self.current);return
  self.load(next((s for s in ctl.specs() if s['id']==rid),None));self.refresh()
 def select_id(self,rid):
  self.tree.blockSignals(True)
  for i in range(self.tree.topLevelItemCount()):
   item=self.tree.topLevelItem(i)
   if item.data(0,Qt.ItemDataRole.UserRole)==rid:self.tree.setCurrentItem(item)
  self.tree.blockSignals(False)
 def load(self,s,new=False):
  if not s:return
  self.loading=True;self.current=None if new else s['id'];self.original=None if new else s['id']
  values={**s,'height':s['hw'][0],'width':s['hw'][1],'label':s.get('label',LABELS.get(s['id'],s['id'])),'epochs':s.get('epochs',100),'seed':s.get('seed',42),'workers':s.get('workers',4),'optimizer':s.get('optimizer','auto'),'lr0':s.get('lr0',.01),'enabled':s.get('enabled',True)}
  for key,widget in self.fields.items():
   if isinstance(widget,QLineEdit):widget.setText(str(values[key]))
   elif isinstance(widget,QComboBox):widget.setCurrentText(values[key])
   elif isinstance(widget,QCheckBox):widget.setChecked(values[key])
   else:widget.setValue(values[key])
  self.loading=False;self.dirty=new;self.apply_lock()
 def apply_lock(self):
  q=ctl.read(ctl.OUT/'queue.json');locked=bool(self.current and ((ctl.OUT/'states'/f'{self.current}.json').exists() or (q.get('active')==self.current and ctl.supervisor_alive(q))))
  self.formbox.setEnabled(True);self.savebutton.setEnabled(not locked);self.browse_button.setEnabled(not locked)
  for key,widget in self.fields.items():
   readonly=locked or (key=='id' and self.current is not None)
   if isinstance(widget,(QLineEdit,QSpinBox,QDoubleSpinBox)):
    widget.setReadOnly(readonly)
    if isinstance(widget,(QSpinBox,QDoubleSpinBox)):widget.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons if readonly else QSpinBox.ButtonSymbols.UpDownArrows)
   else:widget.setEnabled(not locked)
  self.locknote.setText('此实验已启动，参数已锁定。可使用“复制所选”建立新实验。' if locked else '只修改待运行实验；保存后自动队列将采用新参数。' if not self.dirty else '有未保存的参数修改。')
 def reload_form(self):
  self.load(next((s for s in ctl.specs() if s['id']==self.current),None))
 def values(self):
  v={}
  for key,w in self.fields.items():
   v[key]=w.text().strip() if isinstance(w,QLineEdit) else w.currentText() if isinstance(w,QComboBox) else w.isChecked() if isinstance(w,QCheckBox) else w.value()
  v['hw']=[v.pop('height'),v.pop('width')];return v
 def save(self):
  try:
   value=self.values();ctl.edit_spec(value,self.original);self.dirty=False;self.current=value['id'];self.original=value['id'];self.last_signature=None;self.refresh();self.select_id(value['id']);self.load(value);self.refresh();self.message.setText('参数已保存。派发前会重新检查显存和反传；已运行实验保持原参数。')
  except Exception as e:self.problem(e)
 def new(self):
  if not self.confirm_discard():return
  s=dict(id='EXP_new',label='新实验',model=str(ctl.ROOT/'weights/pretrained/yolo26n-pose.pt'),hw=[384,640],batch=16,pose=12.,box=7.5,enabled=False)
  self.tree.clearSelection();self.load(s,True)
 def clone(self):
  s=next((s.copy() for s in ctl.specs() if s['id']==self.selected()),None)
  if s is None:return
  if not self.confirm_discard():return
  used={v['id'] for v in ctl.specs()};base=s['id']+'_copy';rid=base;i=2
  while rid in used:rid=base+str(i);i+=1
  s.update(id=rid,label=s.get('label',LABELS.get(s['id'],s['id']))+' 副本',enabled=False);self.load(s,True)
 def confirm_discard(self):return not self.dirty or QMessageBox.question(self,'尚未保存','放弃当前未保存修改？')==QMessageBox.StandardButton.Yes
 def browse(self):
  p,_=QFileDialog.getOpenFileName(self,'选择模型文件',str(ctl.ROOT/'weights'),'模型 (*.pt *.yaml *.yml)')
  if p:self.fields['model'].setText(p)
 def refresh(self):
  specs=ctl.specs();q=ctl.read(ctl.OUT/'queue.json');alive=ctl.supervisor_alive(q);paused=q.get('paused',False)
  badge='已暂停 · '+q.get('pause_reason','') if alive and paused else '队列运行中' if alive else STATUS.get(q.get('status'), '后台未启动')
  self.badge.setText('● '+badge);c=self.colors;self.badge.setStyleSheet(f"color:{c['warning'] if paused else c['positive'] if alive else c['secondary']};background:{c['warning_bg'] if paused else c['positive_bg'] if alive else c['disabled_bg']};");self.pause.setEnabled(alive and not paused);self.start.setEnabled(not alive or paused)
  if q.get('error') and not alive:self.message.setText('队列异常已停止，原有记录保留。查看日志定位原因；未完成实验可复制后再运行。')
  signature=tuple(s['id'] for s in specs)
  if signature!=self.last_signature:
   selected=self.current;self.tree.blockSignals(True);self.tree.clear()
   for card in self.cards.values():self.cardgrid.removeWidget(card);card.deleteLater()
   self.cards={}
   for s in specs:
    item=QTreeWidgetItem(['','','']);item.setData(0,Qt.ItemDataRole.UserRole,s['id']);self.tree.addTopLevelItem(item)
    card=ExperimentCard(s['id'],self.card_clicked);card.colors=self.colors;self.cards[s['id']]=card;index=len(self.cards)-1;self.cardgrid.addWidget(card,index//2,index%2)
   self.tree.blockSignals(False);self.last_signature=signature
   self.select_id(selected or q.get('active') or (specs[0]['id'] if specs else None))
   if not self.current and not self.dirty and specs:self.load(next((s for s in specs if s['id']==self.selected()),specs[0]))
  for i,s in enumerate(specs):
   state=ctl.read(ctl.OUT/'states'/f"{s['id']}.json");active=alive and q.get('active')==s['id'];status='PAUSED' if active and paused else q.get('phase','TRAINING') if active else state.get('status','QUEUED')
   item=self.tree.topLevelItem(i);item.setText(0,s.get('label',LABELS.get(s['id'],s['id']))+'\n'+s['id']);item.setText(1,STATUS.get(status,status) if s.get('enabled',True) else '未加入队列');item.setText(2,f"{state.get('completed_epochs',0)} / {state.get('epochs',s.get('epochs',100))}");self.cards[s['id']].update_data(s,state,status,self.current==s['id'])
  rid=q.get('active') if alive else self.selected();rid=rid or self.selected()
  if rid:
   spec=next((s for s in specs if s['id']==rid),{});p=ctl.progress(rid);total=p.get('epochs',spec.get('epochs',100));done=p.get('completed_epochs',0);live=p.get('live_epoch',done);within=p.get('epoch_percent',0)
   self.active.setText(('当前实验：' if alive else '实验：')+spec.get('label',LABELS.get(rid,rid))+'  /  '+rid)
   phase=STATUS.get(q.get('phase'),q.get('phase','等待启动')) if alive else STATUS.get(p.get('status','QUEUED'),'待运行')
   self.detail.setText(f"{phase}  ·  已完成 {done} / {total} 轮"+(f"  ·  第 {live} 轮 {within}%" if live>done else '')+f"  ·  输入 {' × '.join(map(str,spec.get('hw',[])))}  ·  batch {spec.get('batch','—')}")
   fraction=(done+(within/100 if live>done else 0))/max(1,total);self.bar.setValue(min(10000,int(10000*fraction)));self.chart.rows=p.get('history',[]);self.chart.update()
   if not self.log.textCursor().hasSelection():self.log.setPlainText(p.get('log',''));self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
  power=q.get('power',{});fmt=lambda k,suffix:f"{power[k]:.0f}{suffix}" if isinstance(power.get(k),(int,float)) else '—'
  self.power.setText(f"显卡 {fmt('temperature_c','°C')}   /   {fmt('power_w','W')}（上限 {fmt('limit_w','W')}）   /   显存 {fmt('memory_mib','MiB')}   /   {'已接电' if power.get('ac') else '供电待确认'}   ·   更新 {q.get('updated_at','—')[11:19]}")
  self.apply_lock()
 def closeEvent(self,event):
  if not self.confirm_discard():event.ignore()
  else:self.appearance_monitor.stop();event.accept()
if __name__=='__main__':
 app=QApplication(sys.argv);app.setStyle('Fusion');app.setApplicationName('visual-yolo-training-console');app.setDesktopFileName('visual-yolo-training-console');app.setFont(QFont('Noto Sans CJK SC',10));win=Window();win.show()
 if '--theme' in sys.argv:
  win.apply_theme(sys.argv[sys.argv.index('--theme')+1])  # screenshot-only appearance fixture
 if '--screenshot' in sys.argv:
  QTimer.singleShot(1200,lambda:(win.grab().save(str(ctl.OUT/f'控制台预览_{win.theme}.png')),app.quit()))
 sys.exit(app.exec())
