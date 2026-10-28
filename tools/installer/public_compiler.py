"""Offline Italian-only compiler. No server or account credentials."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,sys,threading
from datetime import datetime,timezone
import autonomous_engine as engine
from payload_contract import sha,need,read_executable,technical,MANIFEST_KEYS,RECEIPT_KEYS

def compile_patch(input_path,output_path,stub_path=None):
 cfg,template=engine.load_config();key=bytes.fromhex(cfg['localization_key']);baseline=engine.dat_codec.decode(template,key)
 source=Path(input_path);raw=source.read_bytes();raw=gzip.decompress(raw) if source.suffix=='.gz' else raw
 data=json.loads(raw.decode('utf-8-sig'));need(data.get('format')=='aion2-italian-editor-v1' and data.get('build_id')==cfg['steam_build'],'Il file italiano appartiene a un’altra build o formato.')
 entries=data['entries'];target={}
 for row in entries:
  name,value=row['key'],row['it'];need(isinstance(name,str) and isinstance(value,str) and name not in target,'Chiave duplicata o testo non valido.');target[name]=value
 need(set(target)==set(baseline) and len(entries)==len(baseline),'Mancano chiavi o sono state aggiunte chiavi estranee.')
 target={name:target[name] for name in baseline}
 for name,value in target.items():
  need(bool(value.strip()) or not baseline[name].strip(),'Testo italiano vuoto: '+name)
  try:engine.validate(baseline[name],value)
  except ValueError as exc:raise ValueError('Tag, numeri, segnaposto o a capo modificati in '+name+': '+str(exc)) from exc
 payload=engine.dat_codec.encode(target,template,key);need(engine.dat_codec.decode(payload,key)==target,'Rilettura DAT diversa.')
 need(engine.dat_codec.encode(target,template,key)==payload,'Codifica non deterministica.')
 folder=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent));stubfile=Path(stub_path) if stub_path else folder/'rebuild_stub.exe';stub=stubfile.read_bytes()
 if not stub_path:
  pin=json.loads((folder/'public_resources.json').read_text('utf8'));need(sha(stub)==pin['stub_sha256'],'Stub del generatore corrotto.')
 need(stub[:2]==b'MZ','Stub non valido.');digest=sha(payload)
 manifest={'schema_version':1,'steam_build':cfg['steam_build'],'runtime_locale':'es-ES','catalog_total':len(target),'payload_sha256':digest,'technical_errors':0,'deterministic_encoding':True,'decoded_readback_equal':True,'human_review_complete':False,'runtime_verified':False,'root_read_complete':False}
 receipt={'schema_version':1,'kind':'browser_patch_build_receipt','project_id':cfg['project_id'],'build_id':cfg['steam_build'],'base_patch':'v87','created_at_utc':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'payload_sha256':digest,'base_package_sha256':cfg['package_sha256'],'private_metadata_sha256':sha(raw),'template_sha256':cfg['template_sha256'],'key_order_sha256':cfg['key_order_sha256'],'versions_sha256':sha(raw),'source_identity_sha256':cfg['source_identity_sha256'],'catalog_total':len(target),'current_context_pending':1815,'technical_errors':0,'deterministic_encoding':True,'decoded_readback_equal':True,'human_review_complete':False,'runtime_verified':False,'root_read_complete':False,'account_tokens_in_receipt':False}
 technical(manifest,MANIFEST_KEYS);technical(receipt,RECEIPT_KEYS)
 envelope=json.dumps({'schema_version':1,'kind':'aion2_autonomous_browser_payload','dat_base64':base64.b64encode(payload).decode('ascii'),'manifest':manifest,'receipt':receipt},separators=(',',':'),ensure_ascii=True).encode('ascii')
 prefix=('A2EXEFOOTERv1___00000001'+f'{len(stub):016X}{len(envelope):016X}{len(payload):016X}'+sha(stub)+sha(envelope)+digest).encode('ascii');need(len(prefix)==264,'Footer errato.')
 result=stub+envelope+prefix+sha(prefix).encode('ascii');out=Path(output_path);need(out.suffix.lower()=='.exe' and not out.exists(),'Scegli un nuovo nome .exe. Non sovrascrivo file esistenti.')
 with out.open('xb') as stream:stream.write(result)
 try:
  verified,_,_,proof=read_executable(out);need(verified==payload,'EXE riletto diverso.');engine.validate_payload(out)
 except BaseException:
  out.unlink();raise
 return {'passed':True,'exe_sha256':sha(result),'payload_sha256':digest,'catalog_total':len(target),'changed_fields':sum(target[k]!=baseline[k] for k in target),'human_review_complete':False,'runtime_verified':False}

def gui():
 import tkinter as tk
 from tkinter import ttk,filedialog,messagebox
 from aion2_visual_theme import prepare_window,add_header
 root=tk.Tk();root.title('AION 2 · Genera patch offline');prepare_window(root,790,590);art=add_header(root,'Traduzione italiana · Release 1','Genera un installer dalla revisione','installer-art.png')
 frame=ttk.Frame(root,padding=20);frame.pack(fill='both',expand=True)
 ttk.Label(frame,text='Seleziona il JSON salvato dal laboratorio offline.\nLa patch viene generata sul tuo PC, senza account o caricamenti online.',wraplength=730).pack(anchor='w',pady=12)
 selected=tk.StringVar();ttk.Entry(frame,textvariable=selected).pack(fill='x')
 def choose():
  name=filedialog.askopenfilename(title='Italiano.json salvato dal laboratorio',filetypes=[('Italiano JSON','*.json *.gz')])
  if name:selected.set(name)
 ttk.Button(frame,text='Scegli italiano.json',command=choose).pack(anchor='w',pady=8)
 status=tk.StringVar(value='Steam build 26262663 · Español');ttk.Label(frame,textvariable=status,wraplength=730).pack(anchor='w',pady=8)
 bar=ttk.Progressbar(frame,mode='indeterminate');bar.pack(fill='x',pady=8)
 def generate():
  if not selected.get():messagebox.showinfo('Seleziona il testo','Scegli prima il JSON italiano.');return
  out=filedialog.asksaveasfilename(title='Salva il nuovo installer',defaultextension='.exe',initialfile='AION2_Italiano_Revisione_build26262663.exe',filetypes=[('Installer Windows','*.exe')])
  if not out:return
  button.configure(state='disabled');bar.start(10);status.set('Controllo testi e generazione installer…');root.protocol('WM_DELETE_WINDOW',lambda:None)
  def work():
   try:proof=compile_patch(selected.get(),out);message='Installer creato e verificato.\n'+out;ok=True
   except Exception as exc:message=str(exc);ok=False
   def done():
    bar.stop();button.configure(state='normal');status.set(message);root.protocol('WM_DELETE_WINDOW',root.destroy)
    (messagebox.showinfo if ok else messagebox.showerror)('Generazione patch',message)
   root.after(0,done)
  threading.Thread(target=work,daemon=True).start()
 button=ttk.Button(frame,text='Genera installer',command=generate);button.pack(anchor='w',pady=10)
 ttk.Label(frame,text='Un ringraziamento speciale ai ragazzi di LPI per il loro aiuto nella revisione.',wraplength=730).pack(anchor='w',pady=15)
 root.mainloop()

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--input');parser.add_argument('--output');parser.add_argument('--stub');parser.add_argument('--report');args=parser.parse_args()
 if args.input:
  result=compile_patch(args.input,args.output,args.stub)
  if args.report:Path(args.report).write_text(json.dumps(result,indent=2)+'\n','utf8')
  else:print(json.dumps(result))
 else:gui()
