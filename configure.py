"""Create local configuration without overwriting an existing workspace."""
import argparse,json,os
from pathlib import Path

def configure(root,data,model):
    root=Path(root);data=Path(data).expanduser().resolve();model=Path(model).expanduser().resolve()
    if not data.is_file() or not model.is_file():
        raise ValueError('模型与 data.yaml 必须存在')
    files={
        root/'training.json':{'data':str(data),'device':0},
        root/'experiments.json':[dict(id='Experiment_01',label='第一个实验',model=str(model),hw=[640,640],batch=4,pose=12.,box=7.5,epochs=100,seed=42,workers=4,enabled=False)]}
    for path in files:
        if path.exists():raise FileExistsError(f'保留已有配置：{path.name}')
    (root/'state').mkdir(parents=True,exist_ok=True)
    for path,value in files.items():
        with path.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',required=True);parser.add_argument('--model',required=True);args=parser.parse_args()
    configure(Path(os.environ.get('RM_WORKSPACE',str(Path(__file__).resolve().parent))),args.data,args.model)
