"""Guarded Steam build rollover: fresh native signature backup, old overlay rollback."""
from pathlib import Path
import tempfile
import autonomous_engine as engine
from payload_contract import need,sha

i=engine.installer
def pending_path(state_path):return state_path.with_suffix('.build-update.json')

def recover(cfg,root,state_path):
    path=pending_path(state_path);p=i.read_state(path)
    if p is None:return
    need(set(p)=={'schema_version','kind','game_dir','prior_state','native_state','bridge_state'} and p['schema_version']==1 and p['kind']=='native_build_adoption' and p['game_dir']==str(root),'Journal cambio build non valido')
    stable,bridge=p['native_state'],p['bridge_state']
    stable_dir=i.validate_state(root,state_path,stable);bridge_dir=i.validate_state(root,state_path,bridge)
    need(stable['steam_build']==bridge['steam_build']==cfg['steam_build'],'Build del journal diversa')
    need(stable['before']['dat']=={'exists':False} and stable['before']['signature']['sha256'] in cfg['original_signature_pins'],'Baseline originale della nuova build non provata')
    need(stable['before']['signature']==bridge['before']['signature'] and all(stable['after'][name][key]==bridge['after'][name][key] for name in i.TARGET_PATHS for key in ('exists','size','sha256','mode','mtime_ns')),'Coppia del journal incoerente')
    engine.verify_game(cfg,root);i.require_closed();paths=i.targets(root)
    committed={**stable,'phase':'installed'}
    if i.read_state(state_path)==committed and i.pair_matches(paths,stable['after']):path.unlink();return
    need(all(any(i.matches(file,bridge[side][name]) for side in ('before','after')) for name,file in paths.items()),'File modificati esternamente durante il cambio build')
    i.apply_pair(root,bridge_dir,bridge,'before',guard=True)
    if p['prior_state'] is None:state_path.unlink(missing_ok=True)
    else:i.write_state(state_path,p['prior_state'])
    path.unlink()

def needed(cfg,root,state):
    return bool(state and state['steam_build']!=cfg['steam_build'] or not state and i.targets(root)['dat'].exists())

def install(cfg,root,data,state_path,prior):
    """Caller owns the installation lock; original game archives were pin-checked."""
    need(not i.read_state(engine.update_path(state_path)),'Recupera prima l’aggiornamento precedente')
    if prior:
        need(prior['phase']=='installed','La precedente installazione richiede recupero')
        i.validate_state(root,state_path,prior)
    paths=i.targets(root);current={name:i.describe(file) for name,file in paths.items()}
    need(current['signature']['exists'] and current['signature']['sha256'] in cfg['original_signature_pins'] and current['signature']['size']==cfg['original_signature_size'],'Serve la firma originale della nuova build: verifica i file con Steam')
    allowed=set(cfg.get('adoptable_prior_payload_sha256',[]))
    if prior and prior['after']['dat'].get('exists'):allowed.add(prior['after']['dat']['sha256'])
    need(not current['dat']['exists'] or current['dat']['sha256'] in allowed,'Overlay precedente non riconosciuto: nessuna sostituzione')
    # Native new-build archives have no loose DAT. The recognized old Italian
    # overlay is backed up separately for rollback, never as a new native original.
    native_before={'dat':{'exists':False},'signature':current['signature']}
    with tempfile.TemporaryDirectory(prefix='Aion2BuildAdoption_') as tmp:
        payload=Path(tmp)/'L10NString.dat';payload.write_bytes(data)
        stable,stable_dir=engine.stage(root,state_path,payload,engine.release_for(cfg,data,native_before),native_before,paths)
        bridge,bridge_dir=engine.stage(root,state_path,payload,engine.release_for(cfg,data,current),current,paths,
             {name:i.snapshot_path(stable_dir,'after',name) for name in paths})
        p={'schema_version':1,'kind':'native_build_adoption','game_dir':str(root),'prior_state':prior,'native_state':stable,'bridge_state':bridge}
        engine.verify_game(cfg,root);i.require_closed();need(i.pair_matches(paths,current),'File cambiati durante il backup')
        i.write_state(pending_path(state_path),p)
        try:
            i.apply_pair(root,bridge_dir,bridge,'after',guard=True)
            need(i.pair_matches(paths,stable['after']),'Verifica della nuova patch fallita')
            i.write_state(state_path,{**stable,'phase':'installed'})
            pending_path(state_path).unlink()
        except BaseException:
            recover(cfg,root,state_path)
            raise
    return 'Traduzione aggiornata alla nuova build. Backup precedente conservato; Ripristinare recupera lo spagnolo originale della build attuale.'
