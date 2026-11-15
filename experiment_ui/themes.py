"""Semantic light/dark palettes; no training settings are stored here."""
THEMES={
 'light':dict(bg='#f5f5f7',surface='#ffffff',raised='#ffffff',field='#ffffff',text='#1d1d1f',secondary='#515158',muted='#626269',border='#85858e',subtle='#dfdfe5',accent='#005fce',accent_hover='#004caa',accent_text='#ffffff',selection='#eaf2ff',focus='#0064d8',disabled_bg='#e9e9ed',disabled_text='#57575f',track='#dedee4',positive='#176b3a',positive_bg='#e7f3eb',warning='#805000',warning_bg='#fff1d6',danger='#ac2323',danger_bg='#fdeaea'),
 'dark':dict(bg='#151517',surface='#232326',raised='#2d2d31',field='#1b1b1e',text='#f5f5f7',secondary='#d0d0d5',muted='#b2b2bb',border='#74747d',subtle='#45454d',accent='#70b1ff',accent_hover='#98c8ff',accent_text='#111113',selection='#25374f',focus='#8bc0ff',disabled_bg='#303034',disabled_text='#bfbfc7',track='#47474f',positive='#8fdaa9',positive_bg='#20382a',warning='#ffd280',warning_bg='#41331d',danger='#ffa3a3',danger_bg='#452727')
}
def palette(name):return THEMES.get(name,THEMES['light']).copy()
def luminance(color):
 vals=[int(color[i:i+2],16)/255 for i in (1,3,5)]
 vals=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in vals]
 return sum(v*w for v,w in zip(vals,(.2126,.7152,.0722)))
def contrast(a,b):
 x,y=sorted((luminance(a),luminance(b)));return (y+.05)/(x+.05)
def stylesheet(c):
 from pathlib import Path
 icon=Path(__file__).resolve().parent/'assets'/('check_dark.svg' if c['bg']=='#151517' else 'check_light.svg')
 return f'''
 QMainWindow, QWidget {{background:{c['bg']};color:{c['text']};font-size:13px;}}
 QLabel {{background:transparent;}}
 QLabel#title {{font-size:24px;font-weight:600;}}
 QLabel#active {{font-size:18px;font-weight:600;}}
 QLabel#muted {{color:{c['muted']};}}
 QLabel#queueBadge {{padding:7px 11px;border-radius:12px;font-weight:600;}}
 QPushButton {{background:{c['surface']};color:{c['text']};border:1px solid {c['border']};border-radius:8px;padding:9px 13px;font-weight:500;}}
 QPushButton:hover {{background:{c['selection']};border-color:{c['focus']};}}
 QPushButton:pressed {{background:{c['subtle']};}}
 QPushButton:focus {{border:2px solid {c['focus']};padding:8px 12px;}}
 QPushButton#primary {{background:{c['accent']};color:{c['accent_text']};border:1px solid {c['accent']};}}
 QPushButton#primary:hover {{background:{c['accent_hover']};}}
 QPushButton:disabled, QPushButton#primary:disabled {{color:{c['disabled_text']};background:{c['disabled_bg']};border:1px solid {c['subtle']};}}
 QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{background:{c['field']};color:{c['text']};border:1px solid {c['border']};border-radius:6px;padding:7px;selection-background-color:{c['accent']};selection-color:{c['accent_text']};}}
 QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{border:2px solid {c['focus']};padding:6px;}}
 QLineEdit[readOnly="true"],QSpinBox[readOnly="true"],QDoubleSpinBox[readOnly="true"] {{background:{c['disabled_bg']};color:{c['text']};border-color:{c['subtle']};}}
 QComboBox:disabled,QCheckBox:disabled {{color:{c['disabled_text']};}}
 QComboBox QAbstractItemView {{background:{c['raised']};color:{c['text']};selection-background-color:{c['selection']};selection-color:{c['text']};}}
 QGroupBox {{background:{c['surface']};border:1px solid {c['subtle']};border-radius:10px;margin-top:10px;padding:18px 10px 10px;}}
 QGroupBox::title {{subcontrol-origin:margin;left:13px;padding:0px 5px;color:{c['text']};font-weight:600;}}
 QProgressBar {{background:{c['track']};color:{c['text']};border:0;border-radius:5px;text-align:center;min-height:20px;}}
 QProgressBar::chunk {{background:{c['accent']};border-radius:5px;}}
 QProgressBar#overallProgress {{background:{c['track']};border-radius:4px;min-height:8px;max-height:8px;}}
 QProgressBar#overallProgress::chunk {{border-radius:4px;}}
 QScrollArea {{background:transparent;border:0;}}
 QScrollBar:vertical {{background:{c['bg']};width:10px;margin:0;border:0;}}
 QScrollBar::handle:vertical {{background:{c['border']};border-radius:4px;min-height:25px;}}
 QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
 QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{background:transparent;}}
 QCheckBox::indicator {{width:17px;height:17px;border:1px solid {c['border']};border-radius:4px;background:{c['field']};}}
 QCheckBox::indicator:checked {{background:{c['accent']};border-color:{c['accent']};image:url({icon});}}
 QSplitter::handle {{background:{c['subtle']};width:1px;}}
 QToolTip {{background:{c['raised']};color:{c['text']};border:1px solid {c['border']};padding:5px;}}
 '''
