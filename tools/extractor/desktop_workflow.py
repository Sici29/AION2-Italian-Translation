"""Local desktop workflow. Original PAK reads; new output directory only."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
import re
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from catalog_contract import validate_catalog, compare_catalogs, validate_diff, digest
from estrai_build import extract, read_json, file_sha, new_output, ensure_file
from native_reader import steam_identity, pak_has_entry, KEY_MANIFEST_ENTRY

HERE = Path(__file__).resolve().parent


def resource_root():
    return Path(getattr(sys, "_MEIPASS", HERE)) / "bundle_data"


def resources():
    folder = resource_root()
    pins = read_json(folder / "resource_pins.json")
    for name, expected in pins["files"].items():
        if Path(name).name != name or file_sha(folder / name) != expected:
            raise ValueError("Una risorsa del programma non corrisponde al rilascio verificato.")
    baseline = validate_catalog(json.loads(gzip.decompress((folder / "baseline.json.gz").read_bytes()).decode("utf-8")))
    if baseline["source_catalog_hash"] != pins["baseline_source_catalog_hash"] or baseline["build_id"] != pins["baseline_build"]:
        raise ValueError("Il catalogo precedente incluso non corrisponde al rilascio.")
    raw = (folder / "codec_profile.bin").read_bytes()
    if len(raw) != 80 or raw[:8] != b"A2SRCV1\0":
        raise ValueError("Profilo codec non valido.")
    profile = {"manifest_hash_key": raw[8:40], "pak_key": raw[40:72], "header_xor": struct.unpack_from("<Q", raw, 72)[0]}
    return baseline, profile, folder / "repak.exe", pins


def locate_steam_source(selected):
    """Accept game, library, steamapps or Paks directory; no registry/accounts."""
    selected = Path(selected).resolve()
    if not selected.is_dir() or selected.is_symlink():
        raise ValueError("Scegli la cartella Steam o AION 2.")
    search = {selected, *list(selected.parents)[:5]}
    candidates = set()
    for root in search:
        for path in (root / "appmanifest_3393110.acf", root / "steamapps" / "appmanifest_3393110.acf"):
            if path.is_file():
                candidates.add(path.resolve())
    valid = []
    for manifest in sorted(candidates):
        raw = manifest.read_bytes()
        build = steam_identity(raw)
        names = re.findall(r'"installdir"\s+"([^"\r\n]+)"', raw.decode("utf-8-sig"), flags=re.I)
        if len(names) != 1 or names[0] in (".", "..") or Path(names[0]).name != names[0] or any(c in names[0] for c in ("/", "\\", ":")):
            raise ValueError("Percorso del gioco nel manifest Steam non valido.")
        game = (manifest.parent / "common" / names[0]).resolve()
        paks = game / "Aion2" / "Content" / "Paks"
        if not paks.is_dir() or paks.is_symlink():
            continue
        library_choices = {manifest.parent, manifest.parent.parent}
        if selected in library_choices or selected == game or selected.is_relative_to(game) or game.is_relative_to(selected):
            valid.append((manifest, paks.resolve(), build))
    if len(valid) != 1:
        raise ValueError("Non trovo un’unica installazione Steam AION 2 completa. Scegli la sua cartella o la libreria corretta.")
    return valid[0]


def find_key_archive(paks, repak, profile, progress=lambda message: None, checker=pak_has_entry):
    # Search indexes of non-language PAKs. No loose key manifest or old cache.
    candidates = sorted(path for path in paks.rglob("*.pak") if "L10N" not in path.relative_to(paks).parts)
    if not candidates or len(candidates) > 4096:
        raise ValueError("Gli archivi originali del gioco sono assenti o ambigui.")
    found = []
    for index, archive in enumerate(candidates, 1):
        if archive.is_symlink() or not archive.resolve().is_relative_to(paks):
            raise ValueError("Un archivio esce dalla cartella del gioco.")
        progress(f"Cerco l’indice delle chiavi negli archivi originali ({index}/{len(candidates)})…")
        try:
            present = checker(repak, archive, KEY_MANIFEST_ENTRY, profile["pak_key"])
        except ValueError:
            # A non-readable optional archive cannot be silently used as proof.
            # Once all candidates have been inspected, require a unique source.
            continue
        if present:
            found.append(archive)
    if len(found) != 1:
        raise ValueError("Indice delle chiavi originale assente o presente in più archivi: nessuna fonte viene inventata.")
    return found[0]


def run_workflow(selected, output_parent, previous_path=None, progress=lambda message: None,
                 resource_loader=resources, locator=locate_steam_source, finder=find_key_archive, getter=None):
    previous, profile, repak, pins = resource_loader()
    if previous_path:
        previous = validate_catalog(read_json(ensure_file(previous_path)))
    manifest, paks, build = locator(selected)
    output_parent = Path(output_parent).resolve()
    game = paks.parents[2]
    if output_parent == game or output_parent.is_relative_to(game):
        raise ValueError("Scegli una destinazione esterna alla cartella del gioco.")
    progress("Verifico gli archivi originali della build Steam…")
    key_archive = finder(paks, repak, profile, progress)
    output_parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = output_parent / f"AION2_build_{build}_{stamp}"
    target.mkdir(exist_ok=False)
    archive=target / "ARCHIVIO"
    archive.mkdir()
    args = argparse.Namespace(steam_manifest=manifest, paks=paks, key_manifest_pak=key_archive, repak=repak,
                              tools_dir=HERE, codec_profile_pins=pins["codec_source_files"], expected_build=build,
                              output=archive / "source_catalog.json")
    progress("Leggo ES, EN e le altre lingue presenti nei PAK; il DAT italiano viene ignorato…")
    result = extract(args, getter=getter, profile=profile)
    current = read_json(result["catalog"])
    progress("Preparo aggiunte, modifiche e rimozioni senza cambiare l’italiano…")
    diff = validate_diff(compare_catalogs(previous, current))
    diff_file = new_output(target / "IMPORTA_NEL_LABORATORIO.json", diff)
    summary = {"schema": 1, "from_build": previous["build_id"], "to_build": build,
               "catalog": str(Path(result["catalog"]).name), "catalog_file_sha256": result["file_sha256"],
               "diff": diff_file.name, "diff_file_sha256": file_sha(diff_file), "diff_hash": diff["diff_hash"],
               "counts": diff["counts"], "current_languages": diff["current_languages"], "warnings": diff["warnings"],
               "game_written": False, "source_approved": False, "server_registered": False,
               "human_review_complete": False, "runtime_verified": False, "applied": False,
               "same_build": build == previous["build_id"]}
    new_output(archive / "riepilogo.json", summary)
    (target / "LEGGIMI.txt").write_text("FILE DA IMPORTARE NEL LABORATORIO: IMPORTA_NEL_LABORATORIO.json\n\nApri Importa build nel laboratorio e seleziona questo file. Contiene le differenze EN e ES.\nARCHIVIO/source_catalog.json: conserva questo catalogo per il confronto con la prossima build.\nARCHIVIO/riepilogo.json: conteggi e controlli tecnici; non va importato.\n" + ("\nLa build non è cambiata: non serve importare un aggiornamento.\n" if summary["same_build"] else ""), encoding="utf-8")
    return {**summary, "output_directory": str(target)}
