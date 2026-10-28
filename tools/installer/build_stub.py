"""Compile only this new private CWD stub. Does not change final KIT or installed game."""
from pathlib import Path
import hashlib,json,subprocess,sys
BASE=Path(__file__).resolve().parent
source_files=['autonomous_installer.py','autonomous_engine.py','build_adoption.py','payload_contract.py','aion2_it_installer.py','dat_codec.py','protected_text.py','private_resources/autonomous_config.json','private_resources/base_v69.dat','aion2_visual_theme.py',*[str(p.relative_to(BASE)).replace('\\','/') for p in (BASE/'visual_assets').iterdir()]]
source_pins={name:hashlib.sha256((BASE/name).read_bytes()).hexdigest().upper() for name in source_files}
args=[sys.executable,'-B','-X','utf8','-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--name','AION2_Italian_Installer_Stub_v2',
      '--distpath',str(BASE/'dist'),'--workpath',str(BASE/'build'),'--specpath',str(BASE),
      '--paths',str(BASE),'--icon',str(BASE/'visual_assets/aion2-italiano.ico'),'--add-data',str(BASE/'visual_assets')+';visual_assets','--add-data',str(BASE/'private_resources/autonomous_config.json')+';private_resources',
      '--add-data',str(BASE/'private_resources/base_v69.dat')+';private_resources',
      '--hidden-import','Crypto.Cipher._raw_ecb','--hidden-import','Crypto.Cipher._raw_aes',str(BASE/'autonomous_installer.py')]
done=subprocess.run(args,cwd=BASE,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
(BASE/'pyinstaller_build.log').write_bytes(done.stdout+done.stderr)
if done.returncode:raise SystemExit(done.returncode)
if source_pins!={name:hashlib.sha256((BASE/name).read_bytes()).hexdigest().upper() for name in source_files}:raise RuntimeError('Source changed during compilation; EXE ineligible')
file=BASE/'dist/AION2_Italian_Installer_Stub_v2.exe'
pin={'schema_version':1,'stub_filename':file.name,'stub_path':str(file),'stub_bytes':file.stat().st_size,
     'stub_sha256':hashlib.sha256(file.read_bytes()).hexdigest().upper(),'footer_bytes':328,'footer_magic':'A2EXEFOOTERv1___',
     'source_pins':source_pins,'human_review_complete':False,'runtime_verified':False,'root_read_complete':False}
(BASE/'stub_pin.json').write_bytes((json.dumps(pin,indent=2)+'\n').encode())
print(json.dumps(pin))
