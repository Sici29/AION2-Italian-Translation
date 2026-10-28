"""Small read-only CLI. New catalog, frozen baseline, pure diff; no apply/network."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from catalog_contract import LOCALES, PRIMARY, make_catalog, validate_catalog, compare_catalogs, validate_diff, baseline_from_project, digest


def file_sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest().upper()


def read_json(path):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=no_duplicates)


def new_output(path, value):
    destination = Path(path).resolve()
    if destination.exists():
        raise ValueError("Output already exists; select a new filename")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Validate/encode completely before opening a new output.
    data = (json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    with destination.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return destination


def ensure_file(path):
    path = Path(path).resolve()
    if not path.is_file() or path.is_symlink():
        raise ValueError("Explicit regular source file required")
    return path


def extract(args, getter=None, profile=None):
    from native_reader import load_profile, steam_identity, decode_manifest, decode_catalog, pak_get, KEY_MANIFEST_ENTRY
    manifest = ensure_file(args.steam_manifest)
    key_archive = ensure_file(args.key_manifest_pak)
    repak = ensure_file(args.repak)
    paks = Path(args.paks).resolve()
    if not paks.is_dir() or paks.is_symlink():
        raise ValueError("Original PAK snapshot directory required")
    output = Path(args.output).resolve()
    if output == manifest or output == key_archive or output == repak or output.is_relative_to(paks):
        raise ValueError("Output must be outside the read-only original PAK snapshot")
    manifest_before = manifest.read_bytes()
    build = steam_identity(manifest_before)
    if args.expected_build and build != args.expected_build:
        raise ValueError("Observed Steam build differs from expected build")
    profile = profile or load_profile(args.tools_dir)
    get = getter or pak_get
    key_archive_before = file_sha(key_archive)
    key_manifest = get(repak, key_archive, KEY_MANIFEST_ENTRY, profile["pak_key"])
    keys = decode_manifest(key_manifest, profile)
    catalogs, evidence, observed_paths = {}, {}, []
    for locale in LOCALES:
        directory = paks / "L10N" / "Text" / locale
        # The input is the original .pak container; loose L10NString.dat is ignored.
        matches = sorted(directory.glob("pakchunk*-Windows_0_P.pak"))
        if not matches:
            if locale in PRIMARY:
                raise ValueError("Required original ES/EN language archive absent")
            continue
        if len(matches) != 1:
            raise ValueError("Ambiguous native locale archive; explicit source selection required")
        archive = ensure_file(matches[0])
        if not archive.is_relative_to(paks):
            raise ValueError("Language archive escapes source snapshot")
        before_hash = file_sha(archive)
        dat_entry = f"Aion2/Content/L10N/Text/{locale}/L10NString.dat"
        raw = get(repak, archive, dat_entry, profile["pak_key"])
        # Loose Italian files are never inspected. Reject only a known override
        # actually returned as the native PAK entry by a mistaken source input.
        if hashlib.sha256(raw).hexdigest().upper() == "4DEDB38859F831E7F92BEB696D5B825AE89F31F3FB4ABED21148745A97EE9710":
            raise ValueError("PAK entry is the installed Italian override, not native source")
        values = decode_catalog(raw, locale, keys, profile)
        after_hash = file_sha(archive)
        if before_hash != after_hash:
            raise ValueError("Original archive changed while reading")
        catalogs[locale] = values
        evidence[locale] = {"archive_name": archive.name, "archive_sha256": before_hash,
                            "dat_sha256": hashlib.sha256(raw).hexdigest().upper(), "dat_bytes": len(raw),
                            "count": len(values), "catalog_hash": digest(values), "format": "aion2_l10n_v2",
                            "origin": "original_pak_native_entry", "archive_checked_before_after": True}
        observed_paths.append((archive, before_hash))
    if manifest.read_bytes() != manifest_before or file_sha(key_archive) != key_archive_before:
        raise ValueError("Steam/key archive identity changed during extraction")
    for path, pin in observed_paths:
        if file_sha(path) != pin:
            raise ValueError("Original archive changed before final catalog output")
    provenance = {"observed_at_utc": datetime.now(timezone.utc).isoformat(), "steam_manifest_sha256": hashlib.sha256(manifest_before).hexdigest().upper(),
                  "steam_app_id": "3393110", "steam_build_id": build, "steam_state_flags": "4",
                  "key_manifest_archive_name": key_archive.name, "key_manifest_archive_sha256": key_archive_before,
                  "key_manifest_sha256": hashlib.sha256(key_manifest).hexdigest().upper(),
                  "key_manifest_read_from_current_original_archive": True, "cached_key_manifest_used": False,
                  "loose_dat_read": False, "installed_italian_used_as_source": False,
                  "source_hashes_copied_from_old_catalog": False, "source_read_only": True,
                  "game_written": False, "runtime_build_certified": False, "authenticity_attested": False,
                  "codec_profile_files": getattr(args, "codec_profile_pins", None) or {name: file_sha(Path(args.tools_dir) / name) for name in ("analyze.py", "encrypt_aion2_pak.py")}}
    catalog = make_catalog(build, catalogs, evidence, provenance)
    destination = new_output(output, catalog)
    return {"catalog": str(destination), "file_sha256": file_sha(destination), "build_id": build,
            "source_catalog_hash": catalog["source_catalog_hash"], "counts": {lang: len(rows) for lang, rows in catalogs.items()},
            "source_approved": False, "game_written": False, "applied": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Estrai fonti originali e prepara anteprima importazione manuale; nessuna applicazione.")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("extract", help="Legge ES/EN e altre lingue da archivi PAK originali.")
    command.add_argument("--steam-manifest", required=True, help="appmanifest_3393110.acf della stessa build")
    command.add_argument("--paks", required=True, help="Cartella Paks di uno snapshot originale, con L10N/Text")
    command.add_argument("--key-manifest-pak", required=True, help="Archivio originale della stessa build contenente key_manifest.dat")
    command.add_argument("--tools-dir", default=r"E:\TRADUZIONI\AION 2\01_LAVORO_ATTIVO\aion2", help="Profilo codec locale del progetto; nessuna chiave viene esportata")
    command.add_argument("--repak", default=r"E:\TRADUZIONI\AION 2\05_TOOLS\repak\repak.exe")
    command.add_argument("--expected-build", help="Build attesa opzionale; deve coincidere con il manifest appena letto")
    command.add_argument("--output", required=True, help="Nome nuovo, fuori dallo snapshot sorgente")
    command = sub.add_parser("baseline", help="Congela solo le fonti storiche ES/EN da un progetto esplicitamente pinnato.")
    command.add_argument("--project", required=True)
    command.add_argument("--project-sha256", required=True)
    command.add_argument("--output", required=True)
    command = sub.add_parser("diff", help="Confronto puro e delta pratico da caricare manualmente nell'anteprima.")
    command.add_argument("--previous", required=True)
    command.add_argument("--current", required=True)
    command.add_argument("--project", help="Facoltativo: conserva IT precedente nella proiezione senza modificarlo")
    command.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "extract":
        result = extract(args)
    elif args.command == "baseline":
        project_path = ensure_file(args.project)
        actual = file_sha(project_path)
        if actual != args.project_sha256.upper():
            raise ValueError("Explicit frozen project SHA mismatch")
        raw = project_path.read_bytes()
        project = read_json(project_path)
        value = baseline_from_project(project, actual)
        if project_path.read_bytes() != raw:
            raise ValueError("Frozen project changed while reading")
        target = new_output(args.output, value)
        result = {"baseline": str(target), "file_sha256": file_sha(target), "from_build": value["build_id"], "source_catalog_hash": value["source_catalog_hash"], "source_approved": False}
    else:
        previous = read_json(ensure_file(args.previous))
        current = read_json(ensure_file(args.current))
        project = read_json(ensure_file(args.project)) if args.project else None
        value = validate_diff(compare_catalogs(previous, current, project))
        target = new_output(args.output, value)
        result = {"diff": str(target), "file_sha256": file_sha(target), "diff_hash": value["diff_hash"], "from_build": value["from_build"], "to_build": value["to_build"], "counts": value["counts"], "italian_replacements": 0, "applied": False}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, TimeoutError) as exc:
        print("Operazione annullata: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
