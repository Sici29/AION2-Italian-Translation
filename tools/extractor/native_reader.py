"""Read native v2 catalogs from original PAK bytes; never reads a loose Italian DAT.

The decoding layout is the one used by the project's analyze.py. Technical game
constants are read from the existing local source files, not bundled/exported.
"""
from __future__ import annotations
import ast
import hashlib
import re
import struct
import subprocess
from pathlib import Path
from Crypto.Cipher import AES
from blake3 import blake3
import lz4.block

KEY_MANIFEST_ENTRY = "Aion2/Content/StartUpData/Table/key_manifest.dat"
MAX_SOURCE_BYTES = 256 * 1024 * 1024
OODLE_SHA256 = "6F5D41A7892EA6B2DB420F2458DAD2F84A63901C9A93CE9497337B16C195F457"


def file_sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest().upper()


def load_profile(tools):
    """Only literal constants; do not import/run project source modules."""
    tools = Path(tools).resolve()
    def constant(filename, name):
        text = (tools / filename).read_text(encoding="utf-8-sig")
        for node in ast.parse(text).body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                expression = node.value
                if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute) and isinstance(expression.func.value, ast.Name) and expression.func.value.id == "bytes" and expression.func.attr == "fromhex" and len(expression.args) == 1:
                    return bytes.fromhex(ast.literal_eval(expression.args[0]))
                return ast.literal_eval(expression)
        raise ValueError("Required local codec constant missing")
    profile = {"manifest_hash_key": constant("analyze.py", "MANIFEST_HASH_KEY"),
               "header_xor": constant("analyze.py", "HEADER_XOR_CONSTANT"),
               "pak_key": constant("encrypt_aion2_pak.py", "KEY")}
    if len(profile["manifest_hash_key"]) != 32 or len(profile["pak_key"]) != 32 or not isinstance(profile["header_xor"], int):
        raise ValueError("Unsupported local codec profile")
    return profile


def decode_manifest(data, profile):
    if len(data) < 56 or (len(data) - 8) % 48:
        raise ValueError("Invalid freshly extracted key manifest layout")
    plain = AES.new(blake3(profile["manifest_hash_key"]).digest(), AES.MODE_ECB).decrypt(data[8:])
    keys = {}
    for pos in range(0, len(plain), 48):
        seed = struct.unpack_from("<Q", plain, pos)[0]
        key = plain[pos + 8:pos + 40]
        if seed in keys and keys[seed] != key:
            raise ValueError("Conflicting duplicate key manifest seed")
        # The real native manifest repeats a few identical records. Such a
        # repetition has one unambiguous key; differing repeats fail closed.
        keys[seed] = key
    return keys


def u64_hash(data):
    return struct.unpack("<Q", blake3(data).digest()[:8])[0]


def fstring(data, pos):
    if pos + 4 > len(data):
        raise ValueError("Truncated FString length")
    length = struct.unpack_from("<i", data, pos)[0]
    pos += 4
    size = length if length >= 0 else -2 * length
    if size > MAX_SOURCE_BYTES or pos + size > len(data):
        raise ValueError("Invalid FString bounds")
    raw = data[pos:pos + size]
    if length > 0:
        if not raw.endswith(b"\0"):
            raise ValueError("Missing UTF8 FString terminator")
        value = raw[:-1].decode("utf-8", errors="strict")
    elif length < 0:
        if not raw.endswith(b"\0\0"):
            raise ValueError("Missing UTF16 FString terminator")
        value = raw[:-2].decode("utf-16le", errors="strict")
    else:
        value = ""
    return value, pos + size


def decode_catalog(cipher, locale, keys, profile):
    if len(cipher) < 52 or len(cipher) > MAX_SOURCE_BYTES or struct.unpack_from("<I", cipher)[0] != 2:
        raise ValueError("Unsupported native DAT version/size")
    seed = u64_hash(f"L10NString_{locale}".encode())
    if seed not in keys:
        raise ValueError("Fresh key manifest has no locale seed")
    root = u64_hash(struct.pack("<Q", profile["header_xor"]))
    header_key = blake3(struct.pack("<QQII", root, seed, 3, 0)).digest()
    header = bytes(a ^ b for a, b in zip(cipher[4:20], header_key))
    packed, encryption, aligned, raw_size = struct.unpack("<4I", header)
    if encryption != 2 or aligned % 16 or len(cipher) != 20 + aligned or raw_size > MAX_SOURCE_BYTES or packed > aligned - 32:
        raise ValueError("Invalid native v2 DAT header")
    decrypted = AES.new(keys[seed], AES.MODE_ECB).decrypt(cipher[20:])
    data = lz4.block.decompress(decrypted[32:32 + packed], uncompressed_size=raw_size)
    if len(data) != raw_size or len(data) < 12 or struct.unpack_from("<I", data)[0] != 1:
        raise ValueError("Invalid native DAT payload version/size")
    namespace, pos = fstring(data, 4)
    if namespace != "AION2" or pos + 4 > len(data):
        raise ValueError("Native DAT namespace invalid")
    count = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    if count > 2000000:
        raise ValueError("Implausible catalog count")
    entries = {}
    for _ in range(count):
        key, pos = fstring(data, pos)
        value, pos = fstring(data, pos)
        if not key or key in entries:
            raise ValueError("Invalid or duplicate native key")
        entries[key] = value
    if len(data) - pos != 4:
        raise ValueError("Unexpected native DAT suffix")
    return entries


def steam_identity(raw):
    # Do not export raw ACF: it may contain an unrelated LastOwner Steam ID.
    text = raw.decode("utf-8-sig", errors="strict")
    def field(name):
        found = re.findall(r'"' + name + r'"\s+"([^"\r\n]+)"', text, flags=re.I)
        if len(found) != 1:
            raise ValueError("Missing/ambiguous Steam identity field")
        return found[0]
    if field("appid") != "3393110" or field("StateFlags") != "4":
        raise ValueError("Wrong Steam app or update not complete")
    build = field("buildid")
    if not build.isdigit():
        raise ValueError("Invalid Steam build")
    return build


def pak_get(repak, archive, entry, key):
    """Read one known native entry to private memory. No unpack/write/game changes."""
    actual_entry = pak_find_entry(repak, archive, entry, key)
    if actual_entry is None:
        raise ValueError("Requested native entry is absent in original archive")
    # repak's Oodle loader otherwise attempts a download. The existing project
    # library is bundled and measured; never request/install it at runtime.
    oodle = Path(repak).resolve().with_name("oo2core_9_win64.dll")
    if not oodle.is_file() or file_sha(oodle) != OODLE_SHA256:
        raise ValueError("Pinned local Oodle library required; runtime downloads disabled")
    try:
        result = subprocess.run([str(repak), "-a", key.hex(), "get", str(archive), actual_entry], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise ValueError("Original archive read timed out after 120s") from None
    # Never print command, stderr or raw bytes: they could contain game keys/data.
    if result.returncode:
        raise ValueError("Original archive cannot provide requested native entry")
    if not result.stdout or len(result.stdout) > MAX_SOURCE_BYTES:
        raise ValueError("Invalid original native entry size")
    return result.stdout


def pak_find_entry(repak, archive, entry, key):
    """Read the archive index without extracting files; bounded, hidden child."""
    try:
        result = subprocess.run([str(repak), "-a", key.hex(), "list", str(archive)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise ValueError("Original archive index read timed out after 20s") from None
    if result.returncode or len(result.stdout) > MAX_SOURCE_BYTES:
        raise ValueError("Original archive index unreadable")
    lines = result.stdout.decode("utf-8", errors="strict").splitlines()
    matches = [line.strip() for line in lines if line.strip().replace("\\", "/").lstrip("/").casefold() == entry.casefold()]
    if len(matches) > 1:
        raise ValueError("Ambiguous case variants of original native entry")
    return matches[0] if matches else None


def pak_has_entry(repak, archive, entry, key):
    return pak_find_entry(repak, archive, entry, key) is not None
