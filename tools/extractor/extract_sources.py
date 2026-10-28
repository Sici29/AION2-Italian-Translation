"""Read installed original PAKs. Does not distribute or upload native texts."""
from pathlib import Path
import argparse,json,struct,sys
from datetime import datetime,timezone
from desktop_workflow import locate_steam_source,find_key_archive
from steam_discovery import discover_installations
from estrai_build import extract,read_json,new_output,file_sha
from catalog_contract import validate_catalog,compare_catalogs,validate_diff
from native_reader import OODLE_SHA256

def main():
 p=argparse.ArgumentParser(description='Estrai ES/EN e le altre lingue dagli archivi originali della tua copia Steam.');p.add_argument('--game',type=Path);p.add_argument('--output',type=Path,default=Path.home()/'Documents/AION2 Cataloghi');p.add_argument('--previous',type=Path);p.add_argument('--repak',type=Path,default=Path(__file__).parent/'bundle_data/repak.exe');a=p.parse_args()
 if not a.game:
  found=discover_installations()
  if len(found)!=1:p.error('Indica --game con la cartella AION2 della tua libreria Steam.')
  a.game=Path(found[0]['path'])
 dll=a.repak.with_name('oo2core_9_win64.dll')
 if not dll.is_file() or file_sha(dll)!=OODLE_SHA256:p.error('Serve la libreria di decompressione locale verificata oo2core_9_win64.dll accanto a repak.exe. Non viene scaricata o distribuita da questo repository.')
 folder=Path(__file__).parent/'bundle_data';raw=(folder/'codec_profile.bin').read_bytes();assert len(raw)==80 and raw[:8]==b'A2SRCV1\0'
 profile={'manifest_hash_key':raw[8:40],'pak_key':raw[40:72],'header_xor':struct.unpack_from('<Q',raw,72)[0]};pins=read_json(folder/'resource_pins.json')
 for name,pin in pins['files'].items():
  if file_sha(folder/name)!=pin:raise ValueError('Risorsa estrattore modificata: '+name)
 manifest,paks,build=locate_steam_source(a.game);game=paks.parents[2];dest=a.output.resolve()
 if dest==game or dest.is_relative_to(game):raise ValueError('Salva il catalogo fuori dalla cartella del gioco.')
 dest=dest/f'AION2_build_{build}_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}';dest.mkdir(parents=True,exist_ok=False);archive=dest/'ARCHIVIO';archive.mkdir()
 key_archive=find_key_archive(paks,a.repak,profile,print)
 args=argparse.Namespace(steam_manifest=manifest,paks=paks,key_manifest_pak=key_archive,repak=a.repak,tools_dir=folder,codec_profile_pins=pins['codec_source_files'],expected_build=build,output=archive/'source_catalog.json')
 result=extract(args,profile=profile);current=validate_catalog(read_json(Path(result['catalog'])))
 if a.previous:
  diff=validate_diff(compare_catalogs(validate_catalog(read_json(a.previous)),current));new_output(dest/'IMPORTA_NEL_LABORATORIO.json',diff);message='Differenze: IMPORTA_NEL_LABORATORIO.json. Catalogo da conservare: ARCHIVIO/source_catalog.json.'
 else:message='Prima estrazione: usa ARCHIVIO/source_catalog.json nel laboratorio offline e conservalo per --previous alla prossima build. Nessun confronto precedente è stato inventato.'
 (dest/'LEGGIMI.txt').write_text(message+'\nNessun file del gioco è stato modificato o caricato online.\n','utf8');print(message);print(dest)
if __name__=='__main__':main()
