"""Private autonomous wrapper; exact existing v2 installer guards remain unchanged."""
from pathlib import Path
import json,re,struct,sys,tempfile
from Crypto.Cipher import AES
import aion2_it_installer as installer
import dat_codec
from protected_text import validate
from payload_contract import need,sha,read_executable
import build_adoption

CONFIG_SHA='260C53E52ED974DFFC52AA1E40AF4BC8EA235BDF880C454B2393CB1753F56B6E'
TEMPLATE_SHA='06B491F4651E6765E81CB9F87EEC3C1B1AA99C26BEC3F9E01E5CDBC7FA284F8A'

def resource(name):return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'private_resources'/name
def load_config():
    raw=resource('autonomous_config.json').read_bytes();need(sha(raw)==CONFIG_SHA,'Configurazione privata dello stub corrotta')
    template=resource('base_v69.dat').read_bytes();need(sha(template)==TEMPLATE_SHA,'Riferimento v69 corrotto')
    return json.loads(raw),template

def validate_payload(exe):
    cfg,template=load_config();data,manifest,receipt,framing=read_executable(exe)
    need(manifest.get('steam_build')==cfg['steam_build'] and manifest.get('runtime_locale')=='es-ES' and manifest.get('catalog_total')==cfg['catalog_total'],'Build/slot/catalogo del payload diverso')
    need(receipt.get('kind')=='browser_patch_build_receipt' and receipt.get('project_id')==cfg['project_id'] and receipt.get('build_id')==cfg['steam_build'],'Identità del receipt diversa')
    need(type(receipt.get('schema_version')) is int and receipt['schema_version']==1 and receipt.get('catalog_total')==cfg['catalog_total'] and type(receipt.get('current_context_pending')) is int and 0<=receipt['current_context_pending']<=cfg['common_catalog_total'],'Schema/catalogo/contesto receipt non valido')
    for field,pin in [('base_package_sha256',cfg['package_sha256']),('template_sha256',cfg['template_sha256']),('key_order_sha256',cfg['key_order_sha256']),('source_identity_sha256',cfg['source_identity_sha256'])]:need(receipt.get(field)==pin,'Pin del receipt diverso: '+field)
    need(receipt.get('root_read_complete') is False and receipt.get('account_tokens_in_receipt') is False,'Flag di prova/privacy diversi')
    for field in ['private_metadata_sha256','versions_sha256']:need(re.fullmatch('[A-F0-9]{64}',receipt.get(field,'')),'Hash del receipt non valido')
    need(re.fullmatch(r'v\d{1,6}',receipt.get('base_patch','')) and re.fullmatch(r'\d{4}-\d\d-\d\dT[0-9:.]+Z',receipt.get('created_at_utc','')),'Versione/data receipt non valida')
    key=bytes.fromhex(cfg['localization_key'])
    need(52<=len(data)<=64*1024*1024 and struct.unpack_from('<I',data)[0]==2,'Dimensione/versione DAT non valida')
    decoded_header=bytes(a^b for a,b in zip(data[4:20],dat_codec.header_key()))
    packed,kind,aligned,raw_size=struct.unpack('<4I',decoded_header)
    need(kind==2 and aligned%16==0 and len(data)==aligned+20 and 0<packed<=aligned-32 and 16<=raw_size<=256*1024*1024,'Header DAT non valido')
    need(aligned==((32+packed+15)&~15),'Padding DAT non canonico')
    plain=AES.new(key,AES.MODE_ECB).decrypt(data[20:]);origin=AES.new(key,AES.MODE_ECB).decrypt(template[20:])
    need(plain[:32]==origin[:32] and not any(plain[32+packed:]),'Prefisso/padding originale DAT modificato')
    baseline=dat_codec.decode(template,key);target=dat_codec.decode(data,key)
    need(len(target)==cfg['catalog_total'] and list(target)==list(baseline),'Chiavi/ordine del catalogo diversi')
    changed=0
    for name,text in target.items():
        if name in cfg['exclusive_keys']:need(text==baseline[name],'Voce esclusiva dello slot spagnolo modificata')
        else:
            reference=baseline[name]
            override=cfg.get('protected_reference_overrides',{}).get(name)
            if override is not None:
                need(set(override)=={'source_hash','template_reference','reference'} and re.fullmatch('[a-fA-F0-9]{64}',override.get('source_hash','')) and override['template_reference']==baseline[name] and isinstance(override['reference'],str),'Riferimento documentato non valido: '+name)
                reference=override['reference']
            validate(reference,text)
        changed+=text!=baseline[name]
    need(dat_codec.encode(target,template,key)==data,'Codifica DAT/prefisso non deterministica')
    return cfg,data,{**framing,'catalog_total':len(target),'changed_fields':changed,'technical_errors':0,'human_review_complete':False,'runtime_verified':False,'root_read_complete':False}

def verify_game(cfg,root):
    need(installer.steam_build(root)==cfg['steam_build'],'Build Steam cambiata: serve una patch per la nuova versione')
    manifest=root.parent.parent/('appmanifest_'+installer.APP_ID+'.acf')
    need(re.search(r'"StateFlags"\s+"4"',manifest.read_text('utf-8-sig')),'Aggiornamento Steam non completo')
    for relative,pin in cfg['game_source_pins'].items():
        file=root/relative;installer.safe_path(file)
        need(file.is_file() and installer.digest(file)==pin,'Archivio originale cambiato: '+relative)

def basic(description):return {key:description[key] for key in ['exists',*(['sha256','size'] if description['exists'] else [])]}
def release_for(cfg,data,before):
    release={**cfg['release_template'],'dat_sha256':sha(data),'dat_size':len(data),'pre_install':{name:basic(desc) for name,desc in before.items()},'human_review_complete':False,'runtime_verified':False}
    installer.validate_release(release);return release
def bundle_write(folder,data,release):
    (folder/'L10NString.dat').write_bytes(data)
    raw=(json.dumps(release,ensure_ascii=False,indent=2)+'\n').encode('utf-8');(folder/'release.json').write_bytes(raw)
    return sha(raw)

def stage(root,state_path,payload,release,before,sources,after_sources=None):
    transaction=installer.uuid.uuid4().hex;directory=state_path.parent/state_path.stem/transaction
    installer.safe_path(directory);directory.mkdir(parents=True,exist_ok=False)
    for name,desc in before.items():
        if desc['exists']:installer.copy_verified(sources[name],installer.snapshot_path(directory,'before',name),desc)
    raw=(json.dumps(release,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    with (directory/'release.json').open('xb') as stream:stream.write(raw);stream.flush();installer.os.fsync(stream.fileno())
    if after_sources is None:
        installer.copy_verified(payload,installer.snapshot_path(directory,'after','dat'),installer.describe(payload))
        with installer.snapshot_path(directory,'after','signature').open('xb') as stream:stream.flush();installer.os.fsync(stream.fileno())
    else:
        for name,source in after_sources.items():installer.copy_verified(source,installer.snapshot_path(directory,'after',name),installer.describe(source))
    after={name:installer.describe(installer.snapshot_path(directory,'after',name)) for name in installer.TARGET_PATHS}
    state={'schema_version':2,'phase':'installing','game_dir':str(root),'steam_build':release['steam_build'],'target_paths':installer.TARGET_PATHS,'manifest_sha256':sha(raw),'transaction_id':transaction,'before':before,'after':after}
    installer.validate_state(root,state_path,state);return state,directory

def update_path(state_path):return state_path.with_suffix('.update.json')
def pending_validate(root,state_path,pending):
    need(set(pending)=={'schema_version','kind','game_dir','prior_state','next_state','bridge_state'} and pending['schema_version']==1 and pending['kind']=='managed_autonomous_update' and pending['game_dir']==str(root),'Journal aggiornamento non valido')
    prior,next_state,bridge=[pending[key] for key in ['prior_state','next_state','bridge_state']]
    directories=[installer.validate_state(root,state_path,state) for state in [prior,next_state,bridge]]
    need(prior['phase']=='installed' and next_state['phase']==bridge['phase']=='installing','Fase aggiornamento non valida')
    need(next_state['before']==prior['before'] and bridge['before']==prior['after'],'Backup originale/prior non conservato')
    need(all(next_state['after'][name][key]==bridge['after'][name][key] for name in installer.TARGET_PATHS for key in ['exists','size','sha256','mode','mtime_ns']),'Staging aggiornamento diverso')
    return prior,next_state,bridge,directories
def recover_update(root,state_path):
    pending_path=update_path(state_path);pending=installer.read_state(pending_path)
    if pending is None:return False
    installer.require_closed();prior,next_state,bridge,dirs=pending_validate(root,state_path,pending)
    need(installer.steam_build(root)==prior['steam_build'],'Build cambiata durante aggiornamento')
    current=installer.read_state(state_path);paths=installer.targets(root)
    committed={**next_state,'phase':'installed'}
    if current==committed and installer.pair_matches(paths,next_state['after']):pending_path.unlink();return True
    need(current==prior or current==committed,'Journal principale cambiato durante aggiornamento')
    installer.apply_pair(root,dirs[2],bridge,'before',guard=True)
    installer.write_state(state_path,prior);pending_path.unlink();return True

def install_or_update(cfg,root,data):
    installer.require_closed();verify_game(cfg,root);state_path=installer.state_file(root,None)
    with installer.installation_lock(state_path):
        build_adoption.recover(cfg,root,state_path)
        existing=installer.read_state(state_path)
        if build_adoption.needed(cfg,root,existing):
            return build_adoption.install(cfg,root,data,state_path,existing)
    # Keep the previous install contract/lock intact for the initial installation.
    if not installer.read_state(state_path) and not installer.read_state(update_path(state_path)):
        before={name:installer.describe(file) for name,file in installer.targets(root).items()}
        sig=before['signature'];need(not sig['exists'] or sig['sha256'] in [installer.EMPTY_SHA256,*cfg['original_signature_pins']],'Firma iniziale inattesa')
        with tempfile.TemporaryDirectory(prefix='Aion2Autonomous_') as tmp:
            folder=Path(tmp);pin=bundle_write(folder,data,release_for(cfg,data,before))
            return installer.install(root,folder,manifest_sha256=pin)
    with installer.installation_lock(state_path):
        recover_update(root,state_path);prior=installer.read_state(state_path)
        need(prior is not None,'Installazione precedente non leggibile')
        prior_dir=installer.validate_state(root,state_path,prior);paths=installer.targets(root)
        need(prior['phase']=='installed' and installer.pair_matches(paths,prior['after']),'Installazione precedente cambiata: recupero verificato necessario')
        need(prior['steam_build']==cfg['steam_build'],'Installazione precedente di altra build')
        if prior['after']['dat']['sha256']==sha(data):return 'Traduzione già installata e integra. Seleziona Español nel gioco.'
        current={name:installer.describe(file) for name,file in paths.items()}
        with tempfile.TemporaryDirectory(prefix='Aion2AutonomousUpdate_') as tmp:
            folder=Path(tmp);payload=folder/'L10NString.dat';payload.write_bytes(data)
            next_state,next_dir=stage(root,state_path,payload,release_for(cfg,data,prior['before']),prior['before'],{name:installer.snapshot_path(prior_dir,'before',name) for name in paths})
            bridge,bridge_dir=stage(root,state_path,payload,release_for(cfg,data,current),prior['after'],paths,{name:installer.snapshot_path(next_dir,'after',name) for name in paths})
            pending={'schema_version':1,'kind':'managed_autonomous_update','game_dir':str(root),'prior_state':prior,'next_state':next_state,'bridge_state':bridge}
            pending_validate(root,state_path,pending);verify_game(cfg,root);installer.require_closed()
            need(installer.pair_matches(paths,current),'File cambiati durante preparazione aggiornamento')
            installer.write_state(update_path(state_path),pending)
            try:
                installer.apply_pair(root,bridge_dir,bridge,'after',guard=True)
                need(installer.pair_matches(paths,next_state['after']),'Verifica aggiornamento fallita')
                installer.write_state(state_path,{**next_state,'phase':'installed'})
                update_path(state_path).unlink()
            except BaseException as exc:
                try:
                    installer.rollback(root,state_path,bridge_dir,bridge,'before',prior)
                    update_path(state_path).unlink(missing_ok=True)
                except BaseException as recovery:
                    raise installer.InstallError('Aggiornamento interrotto; backup e journal conservati: '+str(recovery)) from exc
                raise
    return 'Traduzione aggiornata. Il backup originale è conservato; seleziona Español nel gioco.'

def restore(cfg,root):
    installer.require_closed();verify_game(cfg,root);state_path=installer.state_file(root,None)
    with installer.installation_lock(state_path):
        build_adoption.recover(cfg,root,state_path)
        recover_update(root,state_path)
    return installer.restore(root)
def check(cfg,root,data):
    verify_game(cfg,root);state_path=installer.state_file(root,None)
    pending=installer.read_state(update_path(state_path))
    if pending:pending_validate(root,state_path,pending)
    state=installer.read_state(state_path)
    if build_adoption.needed(cfg,root,state):
        if state:installer.validate_state(root,state_path,state)
        return 'La build Steam è aggiornata. Scegli Aggiornare la traduzione per sostituire la patch precedente con un backup della nuova firma originale.'
    if state:installer.validate_state(root,state_path,state)
    before=state['before'] if state else {name:installer.describe(file) for name,file in installer.targets(root).items()}
    with tempfile.TemporaryDirectory(prefix='Aion2AutonomousCheck_') as tmp:
        folder=Path(tmp);pin=bundle_write(folder,data,release_for(cfg,data,before))
        result=installer.status(root,folder,manifest_sha256=pin)
    if pending:result+='\nUna precedente operazione sarà recuperata automaticamente con Installa o Ripristina.'
    return result
