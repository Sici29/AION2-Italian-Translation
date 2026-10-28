#!/usr/bin/env python3
"""Candidate: reversible es-ES loose DAT installation, with pinned input.

No payload is bundled. A trusted manifest SHA256 must be supplied separately.
The empty signature is a test artifact, never an authentic signature. Each
replacement is atomic; the durable journal permits recovery of the file pair.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

APP_ID = "3393110"
GAME_EXE = Path("Aion2/Binaries/Win64/AION2.exe")
PAKS_DIR = Path("Aion2/Content/Paks")
DAT_PATH = "Aion2/Content/L10N/Text/es-ES/L10NString.dat"
SIGNATURE_PATH = "Aion2/Content/Paks/L10N/Text/es-ES/pakchunk508000-Windows_0_P.sig"
TARGET_PATHS = {"dat": DAT_PATH, "signature": SIGNATURE_PATH}
PACKAGE_NAME = "release.json"
PAYLOAD_NAME = "L10NString.dat"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest().upper()
SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
TRUSTED_MANIFEST_SHA256: str | None = None  # Root supplies the pin at packaging.


class InstallError(Exception):
    pass


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest().upper()


def steam_libraries() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam = Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except (OSError, FileNotFoundError):
        return []
    libraries = [steam]
    vdf = steam / "steamapps/libraryfolders.vdf"
    if vdf.is_file():
        source = vdf.read_text(encoding="utf-8-sig", errors="replace")
        for match in re.finditer(r'"path"\s+"([^"]+)"', source):
            libraries.append(Path(match.group(1).replace("\\\\", "\\")))
    return list(dict.fromkeys(libraries))


def find_game(explicit: Path | None) -> Path:
    candidates = [explicit] if explicit else [Path.cwd(), *(
        library / "steamapps/common/AION2" for library in steam_libraries()
    )]
    for candidate in candidates:
        if candidate is not None:
            root = candidate.resolve()
            if (root / GAME_EXE).is_file() and (root / PAKS_DIR).is_dir():
                return root
    raise InstallError("AION 2 non trovato. Indica la cartella del gioco con --game-dir.")


def steam_build(root: Path) -> str:
    manifest = root.parent.parent / f"appmanifest_{APP_ID}.acf"
    if not manifest.is_file():
        raise InstallError("Manifest Steam non trovato: impossibile verificare la versione del gioco.")
    content = manifest.read_text(encoding="utf-8-sig", errors="replace")
    app = re.search(r'"appid"\s+"(\d+)"', content)
    build = re.search(r'"buildid"\s+"(\d+)"', content)
    installed = re.search(r'"installdir"\s+"([^"]+)"', content)
    if not app or app.group(1) != APP_ID or not build or not installed:
        raise InstallError("Manifest Steam non valido o non appartenente ad AION 2.")
    if root.name.casefold() != installed.group(1).casefold():
        raise InstallError("La cartella del gioco non corrisponde al manifest Steam.")
    return build.group(1)


def game_running() -> bool:
    if os.name != "nt":
        raise InstallError("Il controllo del processo AION2.exe richiede Windows.")
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq AION2.exe", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).decode("mbcs", errors="replace")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InstallError("Impossibile controllare se AION 2 è aperto.") from exc
    return any(row and row[0].casefold() == "aion2.exe" for row in csv.reader(output.splitlines()))


def require_closed() -> None:
    if game_running():
        raise InstallError("Chiudi AION 2 prima di installare o ripristinare la traduzione.")


def unsafe_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def safe_path(path: Path) -> None:
    for component in [*reversed(path.parents), path]:
        if unsafe_link(component):
            raise InstallError(f"Collegamento o reparse point non ammesso: {component}")


def targets(root: Path) -> dict[str, Path]:
    result = {name: root / relative for name, relative in TARGET_PATHS.items()}
    for path in result.values():
        safe_path(path)
        if path.exists() and not path.is_file():
            raise InstallError(f"Destinazione non valida: {path}")
    return result


def state_file(root: Path, state_dir: Path | None) -> Path:
    base = state_dir if state_dir is not None else (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Aion2ItalianTranslation"
    )
    base = base.absolute()
    identity = hashlib.sha256(str(root).casefold().encode("utf-8")).hexdigest()[:24]
    path = base / "installations" / f"{identity}.json"
    safe_path(path)
    if path.is_relative_to(root):
        raise InstallError("La cartella dei backup deve essere esterna alla cartella del gioco.")
    return path


@contextmanager
def installation_lock(state_path: Path):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(".lock")
    safe_path(lock_path)
    stream = lock_path.open("a+b")
    locked = False
    try:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise InstallError("Un'altra operazione su questa installazione è in corso.") from exc
        yield
    finally:
        if locked:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def read_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("not an object")
        return value
    except (OSError, ValueError) as exc:
        raise InstallError("Dati di ripristino non leggibili; operazione bloccata.") from exc


def write_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_path(path)
    temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def remove_state(path: Path) -> None:
    path.unlink()


def valid_description(value: object, metadata: bool = False) -> bool:
    if not isinstance(value, dict) or type(value.get("exists")) is not bool:
        return False
    if not value["exists"]:
        return set(value) == {"exists"}
    if not (
        isinstance(value.get("sha256"), str) and SHA256_RE.fullmatch(value["sha256"])
        and type(value.get("size")) is int and value["size"] >= 0
    ):
        return False
    keys = {"exists", "sha256", "size"}
    if metadata:
        keys.update(("mode", "mtime_ns", "atime_ns"))
    return set(value) == keys and (not metadata or all(
        type(value.get(key)) is int for key in ("mode", "mtime_ns", "atime_ns")
    ))


def describe(path: Path) -> dict:
    safe_path(path)
    if not path.exists():
        return {"exists": False}
    if not path.is_file():
        raise InstallError(f"File non regolare: {path}")
    info = path.stat()
    return {"exists": True, "sha256": digest(path), "size": info.st_size,
            "mode": stat.S_IMODE(info.st_mode), "mtime_ns": info.st_mtime_ns,
            "atime_ns": info.st_atime_ns}


def matches(path: Path, expected: dict, metadata: bool = True) -> bool:
    current = describe(path)
    if current["exists"] != expected["exists"]:
        return False
    if not current["exists"]:
        return True
    keys = ["sha256", "size", *( ["mode", "mtime_ns"] if metadata else [])]
    return all(current[key] == (expected[key].upper() if key == "sha256" else expected[key]) for key in keys)


def validate_release(release: object) -> dict:
    signature = {"mode": "empty_reversible_test", "authentic_signature": False,
                 "size": 0, "sha256": EMPTY_SHA256}
    if not isinstance(release, dict) or not (
        release.get("schema_version") == 2
        and release.get("status") == "approved_for_reversible_test"
        and isinstance(release.get("steam_build"), str)
        and re.fullmatch(r"\d+", release["steam_build"])
        and release.get("working_method") == "loose_localization_dat"
        and release.get("runtime_locale") == "es-ES"
        and release.get("payload_encoding_locale") == "es-ES"
        and release.get("source_locale") == "es-ES"
        and release.get("comparison_locale") == "en-US"
        and release.get("language_to_select") == "Español"
        and release.get("payload_file") == PAYLOAD_NAME
        and release.get("dat_relative_path") == DAT_PATH
        and release.get("signature_relative_path") == SIGNATURE_PATH
        and release.get("signature") == signature
        and isinstance(release.get("dat_sha256"), str)
        and SHA256_RE.fullmatch(release["dat_sha256"])
        and type(release.get("dat_size")) is int and release["dat_size"] > 0
        and isinstance(release.get("pre_install"), dict)
        and set(release["pre_install"]) == set(TARGET_PATHS)
        and all(valid_description(value) for value in release["pre_install"].values())
    ):
        raise InstallError("Manifest privo del contratto es-ES approvato per la prova reversibile.")
    return release


def release_package(bundle: Path, manifest_sha256: str | None) -> tuple[dict, Path, bytes]:
    if not isinstance(manifest_sha256, str) or not SHA256_RE.fullmatch(manifest_sha256):
        raise InstallError("Serve il pin SHA256 del manifest approvato, fornito separatamente.")
    manifest_path = bundle / PACKAGE_NAME
    payload = bundle / PAYLOAD_NAME
    safe_path(manifest_path)
    safe_path(payload)
    if not manifest_path.is_file():
        raise InstallError("Pacchetto approvato assente.")
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest().upper() != manifest_sha256.upper():
        raise InstallError("Hash del manifest diverso dal pin approvato.")
    try:
        release = validate_release(json.loads(raw.decode("utf-8")))
    except (UnicodeError, ValueError) as exc:
        raise InstallError("Il manifest della traduzione non è leggibile.") from exc
    if not payload.is_file() or payload.stat().st_size != release["dat_size"] or digest(payload) != release["dat_sha256"].upper():
        raise InstallError("Il DAT non corrisponde al manifest pinato.")
    return release, payload, raw


def copy_verified(source: Path, destination: Path, expected: dict) -> None:
    safe_path(source)
    safe_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, destination.open("xb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    if not matches(destination, expected, metadata=False):
        raise InstallError("Copia non riuscita: verifica del file fallita.")
    os.chmod(destination, expected["mode"])
    os.utime(destination, ns=(expected["atime_ns"], expected["mtime_ns"]))
    if not matches(destination, expected):
        raise InstallError("Metadati della copia non verificabili.")


def atomic_copy(source: Path, target: Path, expected: dict) -> None:
    safe_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Keep the temporary basename independent of the long signature filename.
    temp = target.with_name(f".a2-{uuid.uuid4().hex}.tmp")
    try:
        copy_verified(source, temp, expected)
        safe_path(target)
        os.replace(temp, target)
        if not matches(target, expected):
            raise InstallError("Verifica dopo la sostituzione fallita.")
    finally:
        temp.unlink(missing_ok=True)


def snapshot_path(directory: Path, side: str, name: str) -> Path:
    return directory / f"{side}_{name}.bin"


def verify_snapshots(directory: Path, states: dict) -> None:
    for side in ("before", "after"):
        for name, description in states[side].items():
            path = snapshot_path(directory, side, name)
            if description["exists"] and not matches(path, description):
                raise InstallError("Backup o staging cambiato: operazione bloccata.")
            if not description["exists"] and path.exists():
                raise InstallError("Backup incoerente con l'assenza originale del file.")


def validate_state(root: Path, state_path: Path, state: dict) -> Path:
    if not (
        state.get("schema_version") == 2 and state.get("game_dir") == str(root)
        and state.get("target_paths") == TARGET_PATHS
        and state.get("phase") in {"installing", "installed", "restoring"}
        and isinstance(state.get("transaction_id"), str)
        and re.fullmatch(r"[0-9a-f]{32}", state["transaction_id"])
        and isinstance(state.get("manifest_sha256"), str)
        and SHA256_RE.fullmatch(state["manifest_sha256"])
        and all(isinstance(state.get(side), dict) and set(state[side]) == set(TARGET_PATHS)
                and all(valid_description(item, True) for item in state[side].values())
                for side in ("before", "after"))
    ):
        raise InstallError("Dati di ripristino non validi o riferiti al vecchio metodo .pak.")
    directory = state_path.parent / state_path.stem / state["transaction_id"]
    safe_path(directory)
    manifest_path = directory / PACKAGE_NAME
    safe_path(manifest_path)
    if not manifest_path.is_file() or digest(manifest_path) != state["manifest_sha256"].upper():
        raise InstallError("Copia del manifest approvato mancante o cambiata.")
    try:
        release = validate_release(json.loads(manifest_path.read_text(encoding="utf-8")))
    except (ValueError, UnicodeError) as exc:
        raise InstallError("Copia del manifest non leggibile.") from exc
    if state.get("steam_build") != release["steam_build"]:
        raise InstallError("Build dei dati di ripristino incoerente.")
    for name in TARGET_PATHS:
        if not all(state["before"][name].get(key) == (value.upper() if key == "sha256" else value)
                   for key, value in release["pre_install"][name].items()):
            raise InstallError("Backup non coerente con lo stato iniziale pinato.")
    if not (state["after"]["dat"]["exists"] and state["after"]["signature"]["exists"]
            and state["after"]["dat"]["sha256"] == release["dat_sha256"].upper()
            and state["after"]["dat"]["size"] == release["dat_size"]
            and state["after"]["signature"]["sha256"] == EMPTY_SHA256
            and state["after"]["signature"]["size"] == 0):
        raise InstallError("Staging non coerente con DAT/firma vuota dichiarati.")
    verify_snapshots(directory, state)
    return directory


def pair_matches(paths: dict[str, Path], descriptions: dict) -> bool:
    return all(matches(paths[name], descriptions[name]) for name in TARGET_PATHS)


def apply_selection(root: Path, directory: Path, state: dict, selection: dict[str, str], guard: bool) -> None:
    paths = targets(root)
    # Check both files before changing either; accept only the two pinned states.
    for name, path in paths.items():
        if not any(matches(path, state[side][name]) for side in ("before", "after")):
            raise InstallError(f"Il file {name} è cambiato esternamente; nessuna sovrascrittura consentita.")
    for name, path in paths.items():
        if guard:
            require_closed()
            if steam_build(root) != state["steam_build"]:
                raise InstallError("Build Steam cambiata durante l'operazione.")
        desired = selection[name]
        if matches(path, state[desired][name]):
            continue
        # Recheck immediately before mutation, including the path components.
        safe_path(path)
        if not any(matches(path, state[side][name]) for side in ("before", "after")):
            raise InstallError(f"Il file {name} è cambiato durante l'operazione.")
        expected = state[desired][name]
        if expected["exists"]:
            atomic_copy(snapshot_path(directory, desired, name), path, expected)
        else:
            path.unlink(missing_ok=True)
    if not all(matches(paths[name], state[selection[name]][name]) for name in TARGET_PATHS):
        raise InstallError("Verifica finale della coppia DAT/firma fallita.")


def apply_pair(root: Path, directory: Path, state: dict, desired: str, guard: bool) -> None:
    apply_selection(root, directory, state, {name: desired for name in TARGET_PATHS}, guard)


def rollback(root: Path, state_path: Path, directory: Path, state: dict, side: str, prior: dict | None) -> None:
    # Rollback must proceed even if the game was launched after the first guard.
    apply_pair(root, directory, state, side, guard=False)
    if prior is None:
        if state_path.exists():
            remove_state(state_path)
    else:
        write_state(state_path, prior)


def install(root: Path, bundle: Path, state_dir: Path | None = None,
            manifest_sha256: str | None = None) -> str:
    root = root.resolve()
    require_closed()
    release, payload, raw = release_package(bundle, manifest_sha256)
    build = steam_build(root)
    if release["steam_build"] != build:
        raise InstallError(f"Gioco aggiornato alla build {build}; il pacchetto richiede {release['steam_build']}.")
    state_path = state_file(root, state_dir)
    with installation_lock(state_path):
        paths = targets(root)
        existing = read_state(state_path)
        if existing:
            validate_state(root, state_path, existing)
            if existing["phase"] == "installed" and pair_matches(paths, existing["after"]):
                if existing["manifest_sha256"] == manifest_sha256.upper():
                    return "Traduzione già installata e integra. Seleziona Español nel gioco."
                raise InstallError("È installata un'altra versione: ripristinala prima di aggiornare.")
            raise InstallError("Installazione interrotta o cambiata: usa restore per il recupero verificato.")
        before = {name: describe(path) for name, path in paths.items()}
        if any(not matches(paths[name], release["pre_install"][name], metadata=False) for name in TARGET_PATHS):
            raise InstallError("DAT o firma iniziali diversi dai pin del manifest; nessun file è stato sostituito.")
        transaction = uuid.uuid4().hex
        directory = state_path.parent / state_path.stem / transaction
        safe_path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        for name, path in paths.items():
            if before[name]["exists"]:
                copy_verified(path, snapshot_path(directory, "before", name), before[name])
        manifest_copy = directory / PACKAGE_NAME
        with manifest_copy.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        payload_description = describe(payload)
        if payload_description["sha256"] != release["dat_sha256"].upper() or payload_description["size"] != release["dat_size"]:
            raise InstallError("Il payload è cambiato durante la preparazione.")
        copy_verified(payload, snapshot_path(directory, "after", "dat"), payload_description)
        empty = snapshot_path(directory, "after", "signature")
        with empty.open("xb") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        after = {name: describe(snapshot_path(directory, "after", name)) for name in TARGET_PATHS}
        state = {"schema_version": 2, "phase": "installing", "game_dir": str(root),
                 "steam_build": build, "target_paths": TARGET_PATHS,
                 "manifest_sha256": manifest_sha256.upper(), "transaction_id": transaction,
                 "before": before, "after": after}
        verify_snapshots(directory, state)
        if not pair_matches(paths, before):
            raise InstallError("I file precedenti sono cambiati durante il backup; operazione bloccata.")
        require_closed()
        if steam_build(root) != build:
            raise InstallError("Build Steam cambiata durante la preparazione; operazione bloccata.")
        try:
            write_state(state_path, state)  # Durable recovery record BEFORE any replacement.
            apply_pair(root, directory, state, "after", guard=True)
            installed = {**state, "phase": "installed"}
            write_state(state_path, installed)
        except BaseException as exc:
            try:
                rollback(root, state_path, directory, state, "before", None)
            except BaseException as recovery:
                raise InstallError(f"Installazione interrotta; backup e journal conservati. Recupero necessario: {recovery}") from exc
            raise
    return "Traduzione installata per prova reversibile. Seleziona Español nel gioco. Firma vuota di test, non autentica."


def restore(root: Path, state_dir: Path | None = None) -> str:
    root = root.resolve()
    require_closed()
    state_path = state_file(root, state_dir)
    with installation_lock(state_path):
        state = read_state(state_path)
        if state is None:
            raise InstallError("Nessuna installazione gestita da questo programma da ripristinare.")
        directory = validate_state(root, state_path, state)
        if steam_build(root) != state["steam_build"]:
            raise InstallError("Build Steam cambiata: ripristino della vecchia build bloccato.")
        paths = targets(root)
        if state["phase"] == "installed" and not pair_matches(paths, state["after"]):
            raise InstallError("DAT o firma cambiati dopo l'installazione; ripristino automatico bloccato.")
        if state["phase"] != "installed":
            selection = {}
            for name, path in paths.items():
                selection[name] = next((side for side in ("before", "after")
                                        if matches(path, state[side][name])), None)
                if selection[name] is None:
                    raise InstallError("File cambiati esternamente: recupero automatico bloccato.")
            try:
                apply_pair(root, directory, state, "before", guard=True)
                remove_state(state_path)
            except BaseException as exc:
                try:
                    apply_selection(root, directory, state, selection, guard=False)
                    write_state(state_path, state)
                except BaseException as recovery:
                    raise InstallError(f"Recupero interrotto; backup e journal conservati: {recovery}") from exc
                raise
            return "Operazione interrotta recuperata: DAT e firma tornati allo stato precedente verificato."
        require_closed()
        try:
            write_state(state_path, {**state, "phase": "restoring"})
            apply_pair(root, directory, state, "before", guard=True)
            remove_state(state_path)
        except BaseException as exc:
            try:
                rollback(root, state_path, directory, state, "after", state)
            except BaseException as recovery:
                raise InstallError(f"Ripristino interrotto; backup e journal conservati. Recupero necessario: {recovery}") from exc
            raise
    return "Stato precedente ripristinato: DAT e firma, comprese le assenze. Backup verificati conservati."


def status(root: Path, bundle: Path, state_dir: Path | None = None,
           manifest_sha256: str | None = None) -> str:
    root = root.resolve()
    build = steam_build(root)
    paths = targets(root)
    state_path = state_file(root, state_dir)
    state = read_state(state_path)
    lines = [f"AION 2 Steam — build {build}", "Slot: es-ES — seleziona Español"]
    if state:
        try:
            validate_state(root, state_path, state)
            if state["phase"] != "installed":
                lines.append("Traduzione: operazione interrotta, recupero con restore")
            elif build != state["steam_build"]:
                lines.append("Traduzione: build cambiata, intervento da verificare")
            elif pair_matches(paths, state["after"]):
                lines.append("Traduzione: installata e integra (DAT e firma vuota di test non autentica)")
            else:
                lines.append("Traduzione: DAT o firma cambiati, ripristino automatico bloccato")
        except InstallError as exc:
            lines.append(f"Traduzione: dati di recupero da controllare — {exc}")
    else:
        lines.append("Traduzione: nessuna installazione gestita")
    try:
        release, _, _ = release_package(bundle, manifest_sha256)
        lines.append("Pacchetto: pin e DAT validi" if release["steam_build"] == build else "Pacchetto: build diversa")
    except InstallError as exc:
        lines.append(f"Pacchetto: bloccato — {exc}")
    lines.append("Questo controllo non prova caricamento, font o resa in gioco.")
    return "\n".join(lines)


def interactive(bundle: Path, state_dir: Path | None = None, manifest_sha256: str | None = None) -> int:
    selected: Path | None = None
    while True:
        print("\nAION 2 — Traduzione italiana (prova reversibile es-ES)\n")
        try:
            root = find_game(selected)
            print(status(root, bundle, state_dir, manifest_sha256))
        except (InstallError, OSError) as exc:
            root = None
            print(exc)
        print("\n1. Installa la traduzione\n2. Ripristina il gioco\n3. Scegli la cartella del gioco\n4. Esci")
        try:
            choice = input("\nScelta: ").strip()
            if choice == "4":
                return 0
            if choice == "3":
                selected = Path(input("Cartella AION2: ").strip().strip('"'))
                continue
            if choice not in {"1", "2"}:
                print("Scegli 1, 2, 3 oppure 4.")
                continue
            if root is None:
                print("Scegli prima la cartella di AION 2.")
                continue
            try:
                print(install(root, bundle, state_dir, manifest_sha256) if choice == "1" else restore(root, state_dir))
            except (InstallError, OSError) as exc:
                print(f"Operazione interrotta: {exc}")
            input("\nPremi Invio per continuare...")
        except (EOFError, KeyboardInterrupt):
            return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Installer candidato: prova reversibile italiana nello slot es-ES")
    parser.add_argument("command", nargs="?", choices=("check", "status", "install", "restore"))
    parser.add_argument("--game-dir", type=Path, help="cartella AION2 della versione Steam")
    parser.add_argument("--bundle-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--state-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--manifest-sha256", help="pin SHA256 approvato del manifest, fornito separatamente")
    args = parser.parse_args(argv)
    bundle = args.bundle_dir or Path(__file__).resolve().parents[1] / "payload"
    pin = args.manifest_sha256 or TRUSTED_MANIFEST_SHA256
    if args.command is None and sys.stdin.isatty():
        return interactive(bundle, args.state_dir, pin)
    try:
        root = find_game(args.game_dir)
        if args.command == "install":
            print(install(root, bundle, args.state_dir, pin))
        elif args.command == "restore":
            print(restore(root, args.state_dir))
        else:
            print(status(root, bundle, args.state_dir, pin))
        return 0
    except (InstallError, OSError) as exc:
        print(f"Operazione interrotta: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
