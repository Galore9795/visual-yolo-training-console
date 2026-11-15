"""Ultralytics detection/pose worker; run by the console in its training environment."""
import argparse,csv,json,os,time,traceback
from pathlib import Path
ROOT=Path(os.environ.get('RM_WORKSPACE',str(Path(__file__).resolve().parents[1])))
OUT=ROOT/'state'
def save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2));temp.replace(path)
def run(rid,check=False):
 import torch
 from ultralytics import YOLO
 from ultralytics.data.dataset import YOLODataset
 from ultralytics.data.augment import Compose,LetterBox,Format
 from ultralytics.models.yolo.pose.train import PoseTrainer
 from ultralytics.models.yolo.detect.train import DetectionTrainer
 config=json.loads((ROOT/'training.json').read_text())
 spec=next(s for s in json.loads((ROOT/'experiments.json').read_text()) if s['id']==rid)
 hw=tuple(spec['hw']);model=YOLO(spec['model'])
 if model.task not in ('pose','detect'):raise ValueError('当前支持 detection / pose 模型')
 if not Path(config['data']).is_file():raise ValueError('请在 training.json 指定存在的 data.yaml')
 class Dataset(YOLODataset):
  def build_transforms(self,hyp):
   self.rect=False
   return Compose([LetterBox(new_shape=hw,auto=False,scaleup=self.augment),Format(bbox_format='xywh',normalize=True,return_keypoint=model.task=='pose',batch_idx=True)])
 base=PoseTrainer if model.task=='pose' else DetectionTrainer
 class Trainer(base):
  def build_dataset(self,img_path,mode='train',batch=None):
   return Dataset(img_path=img_path,imgsz=hw[1],batch_size=batch or 1,augment=mode=='train',hyp=self.args,rect=False,cache=False,stride=32,data=self.data,task=model.task)
  def preprocess_batch(self,batch):
   if tuple(batch['img'].shape[-2:])!=hw:raise ValueError('训练尺寸不匹配')
   return super().preprocess_batch(batch)
  def get_dataloader(self,dataset_path,batch_size=16,rank=0,mode='train'):
   return super().get_dataloader(dataset_path,min(batch_size,self.args.batch),rank,mode)
 if check:
  # Dataset/architecture compatibility is checked by the framework before the first batch.
  save(OUT/'precheck'/f'{rid}.json',{'status':'PASS','task':model.task,'hw':hw})
  return
 state={**spec,'status':'STARTING','completed_epochs':0,'epochs':spec.get('epochs',100)}
 path=OUT/'states'/f'{rid}.json'
 def update(**values):state.update(values);save(path,state)
 def epoch(trainer):
  rows=list(csv.DictReader(trainer.csv.open())) if trainer.csv.exists() else []
  update(status='TRAINING',completed_epochs=max([int(float(r['epoch'])) for r in rows],default=0))
 try:
  update(pid=os.getpid());model.add_callback('on_fit_epoch_end',epoch)
  result=model.train(trainer=Trainer,data=config['data'],imgsz=max(hw),epochs=state['epochs'],batch=spec['batch'],device=config.get('device',0),seed=spec.get('seed',42),workers=spec.get('workers',4),optimizer=spec.get('optimizer','auto'),lr0=spec.get('lr0',.01),pose=spec['pose'],box=spec['box'],amp=False,patience=0,project=str(OUT/'runs'),name=rid,exist_ok=False,save_period=10,multi_scale=False,mosaic=0,mixup=0,copy_paste=0,fliplr=0,flipud=0,degrees=0,translate=0,scale=0,hsv_h=0,hsv_s=0,hsv_v=0,close_mosaic=0)
  if state['completed_epochs']!=state['epochs']:raise RuntimeError('训练提前停止，已保留 checkpoint')
  update(status='COMPLETE',metrics={str(k):float(v) for k,v in (result.results_dict if result else {}).items()})
 except BaseException: update(status='FAILED',error=traceback.format_exc());raise
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('id');parser.add_argument('--check',action='store_true');args=parser.parse_args();run(args.id,args.check)
