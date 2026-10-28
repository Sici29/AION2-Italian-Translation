"""Double-click GUI; private autonomous EXE payload and reversible managed installer."""
from pathlib import Path
import argparse,json,sys,threading,traceback
import autonomous_engine as engine
from payload_contract import sha

def execute(command,game_dir):
    cfg,data,proof=engine.validate_payload(Path(sys.executable) if getattr(sys,'frozen',False) else Path(__file__))
    if command=='inspect':return {'message':'Payload autonomo verificato','proof':proof}
    root=engine.installer.find_game(game_dir)
    if command=='install':message=engine.install_or_update(cfg,root,data)
    elif command=='restore':message=engine.restore(cfg,root)
    else:message=engine.check(cfg,root,data)
    return {'message':message,'proof':proof,'game_dir':str(root)}

def gui(args):
    import tkinter as tk
    from tkinter import ttk,filedialog
    window=tk.Tk();window.title('AION 2 - Traduzione Italiana');window.geometry('780x720');window.minsize(690,620)
    from aion2_visual_theme import prepare_window,add_header
    prepare_window(window,780,720)
    artwork=add_header(window,'Traduzione italiana','Installer della patch','installer-art.png')
    if args.gui_smoke:window.withdraw()
    selected=[args.game_dir];frame=ttk.Frame(window,padding=(20,12));frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Release 1 · Steam build 26262663 · lingua del gioco: Español').pack(anchor='w',pady=(8,16))
    location=tk.StringVar(value='Ricerca dell’installazione Steam…');ttk.Label(frame,textvariable=location,wraplength=610).pack(anchor='w')
    headline=tk.StringVar(value='Controllo della traduzione e del gioco…');action=tk.StringVar(value='Attendi il controllo iniziale.')
    ttk.Separator(frame).pack(fill='x',pady=12)
    ttk.Label(frame,textvariable=headline,font=('Segoe UI',12,'bold'),wraplength=665).pack(anchor='w')
    ttk.Label(frame,text='COSA FARE',font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(12,3))
    ttk.Label(frame,textvariable=action,wraplength=665).pack(anchor='w')
    result=tk.Text(frame,wrap='word',height=8,font=('Segoe UI',10),background='#f4f7f9',relief='flat');result.pack(fill='both',expand=True,pady=12);result.insert('end','La patch conserva il backup originale. Dopo l’installazione seleziona Español nel gioco.\n')
    controls=ttk.Frame(frame);controls.pack(fill='x');buttons=[]
    def run(command):
        for button in buttons:button.configure(state='disabled')
        def task():
            ok=False;installed=False
            try:
                value=execute(command,selected[0]);message=value['message'];location_text=value.get('game_dir','Payload autonomo');ok=True
                if value.get('game_dir'):
                    root=Path(value['game_dir']);state=engine.installer.read_state(engine.installer.state_file(root,None));installed=bool(state and state.get('phase')=='installed')
            except Exception as exc:message='Operazione interrotta: '+str(exc);location_text=None
            def done():
                if location_text:location.set(location_text)
                headline.set('Traduzione installata' if installed and ok else 'Pronto per installare' if ok else 'Controllo da completare')
                action.set('Per usare la nuova patch scegli Aggiornare; Ripristinare recupera i file originali.' if installed else 'Chiudi AION 2 e scegli Installare. Il backup viene creato automaticamente.' if ok else 'Controlla il messaggio qui sotto; se necessario indica la cartella di AION 2.')
                buttons[0].configure(text='Aggiornare la traduzione' if installed else 'Installare la traduzione')
                result.delete('1.0','end');result.insert('end',message)
                for button in buttons:button.configure(state='normal')
            try:window.after(0,done)
            except (RuntimeError,tk.TclError):pass
        threading.Thread(target=task,daemon=True).start()
    def choose():
        value=filedialog.askdirectory(title='Cartella AION2')
        if value:selected[0]=Path(value);run('check')
    for label,command in [('Installare la traduzione','install'),('Controllare','check'),('Ripristinare','restore')]:
        button=ttk.Button(controls,text=label,command=lambda c=command:run(c));button.pack(side='left',padx=(0,8));buttons.append(button)
    button=ttk.Button(frame,text='Indicare o modificare la cartella del gioco',command=choose);button.pack(anchor='w',pady=(10,0));buttons.append(button)
    ttk.Label(frame,text='Backup e ripristino automatici · Un ringraziamento speciale ai ragazzi di LPI per la revisione',font=('Segoe UI',9)).pack(anchor='w',pady=(12,0))
    if args.gui_smoke:
        def smoke():
            value={'passed':window.winfo_exists()==1,'default_gui':True,'hidden_fixture':True,'window_mapped':window.winfo_ismapped()==1,'button_labels':[b.cget('text') for b in buttons],'official_artwork':True,'italian_flag':True,'icon_loaded':True,'artwork_size':[artwork.winfo_width(),artwork.winfo_height()],'title':window.title(),'human_review_complete':False,'runtime_verified':False}
            if args.report:args.report.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
            window.destroy()
        window.after(300,smoke)
    else:run('check')
    window.mainloop();return 0

def main():
    parser=argparse.ArgumentParser(description='AION 2 · Installer autonomo della traduzione italiana')
    parser.add_argument('command',nargs='?',choices=['inspect','check','install','restore'])
    parser.add_argument('--game-dir',type=Path);parser.add_argument('--report',type=Path)
    parser.add_argument('--gui-smoke',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.command is None:return gui(args)
    try:result={'passed':True,'technical_errors':0,**execute(args.command,args.game_dir)};code=0
    except Exception as exc:result={'passed':False,'technical_errors':1,'error':str(exc),'traceback':traceback.format_exc()};code=1
    result.update(human_review_complete=False,runtime_verified=False,root_read_complete=False)
    if args.report:
        with args.report.open('x',encoding='utf-8',newline='\n') as stream:stream.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if sys.stdout:print(json.dumps(result,ensure_ascii=False))
    return code
if __name__=='__main__':raise SystemExit(main())
