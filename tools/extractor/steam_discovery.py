"""Find AION 2 through Steam installation metadata only."""
from pathlib import Path
import os
import re

def steam_roots():
    candidates=[]
    try:
        import winreg
        for hive,key,name in [(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam','SteamPath'),(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\WOW6432Node\Valve\Steam','InstallPath'),(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Valve\Steam','InstallPath')]:
            try:
                with winreg.OpenKey(hive,key) as handle:
                    value,_=winreg.QueryValueEx(handle,name)
                    if isinstance(value,str):candidates.append(Path(value))
            except OSError:pass
    except ImportError:pass
    for name in ['ProgramFiles(x86)','ProgramFiles']:
        value=os.environ.get(name)
        if value:candidates.append(Path(value)/'Steam')
    return candidates

def discover_installations(roots=None):
    from desktop_workflow import locate_steam_source
    libraries={}
    for candidate in steam_roots() if roots is None else roots:
        path=Path(candidate).expanduser()
        if path.is_dir() and not path.is_symlink():libraries[str(path.resolve()).casefold()]=path.resolve()
    for steam in list(libraries.values()):
        for file in [steam/'steamapps'/'libraryfolders.vdf',steam/'config'/'libraryfolders.vdf']:
            try:
                if file.is_symlink() or file.stat().st_size>2*1024*1024:continue
                source=file.read_text('utf-8-sig')
            except (OSError,UnicodeError):continue
            for value in re.findall(r'"(?:path|\d+)"\s*"([^"\r\n]+)"',source,flags=re.I):
                path=Path(value.replace('\\\\','\\'))
                if path.is_absolute() and path.is_dir() and not path.is_symlink():libraries[str(path.resolve()).casefold()]=path.resolve()
    found={}
    for library in libraries.values():
        try:manifest,paks,build=locate_steam_source(library)
        except (ValueError,OSError,UnicodeError):continue
        game=paks.parents[2]
        found[str(game).casefold()]={'path':str(game),'build':build,'manifest':str(manifest)}
    return sorted(found.values(),key=lambda row:row['path'].casefold())
