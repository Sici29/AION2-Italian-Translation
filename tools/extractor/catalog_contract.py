"""Pure source catalogue validation, hashing and comparison. No I/O mutations."""
from __future__ import annotations
import hashlib
import json
from copy import deepcopy

PROJECT = "aion2-steam-25650019-lpi"
APP_ID = "3393110"
LOCALES = ("es-ES", "en-US", "ko-KR", "ja-JP", "fr-FR", "de-DE", "pt-BR", "ru-RU")
PRIMARY = ("es-ES", "en-US")
GROUPS = ("settings_character_creation", "menus_interface_messages", "skills_items_equipment", "quests_achievements", "dialogue", "world_other")


def classify_key(key):
    """Exact category/priority rules already used by the project's tracker."""
    family = key.split("_", 1)[0]
    category = family
    if family == "String":
        if key.startswith("String_STR_ITEM_TITLE_"):
            category = "titles_item_description" if "_DESC_" in key else "titles_item_name"
        elif key.startswith("String_STR_ITEM_"):
            category = "items_description" if "_DESC_" in key else "items_name"
        elif key.startswith("String_UI_"):
            category = "interface"
        else:
            category = "world_and_other_strings"
    if key.startswith(("String_UI_CUSTOMIZE", "String_UI_SETTING", "String_UI_CAMERASETTING", "PCCreationInfo_")):
        return GROUPS[0]
    if category in ("interface", "InputKeyMapping", "InputKeyText", "InventoryFilter", "TradeTab", "Message", "PcSocialAction", "CurrencyInfo"):
        return GROUPS[1]
    if category in ("items_name", "items_description", "SkillString", "SkillAbnormalString", "SkillCondString", "GatherSkill", "Skin", "SkinSet", "SkinMaterial", "SkinPattern", "Wing", "Title", "TitleCategory"):
        return GROUPS[2]
    if category in ("QuestString", "QuestPart", "AchievementString", "EventContentsString", "NoteData", "Post"):
        return GROUPS[3]
    if category in ("NpcTalk", "CutsceneSubtitle"):
        return GROUPS[4]
    return GROUPS[5]


def canonical(value):
    """Match JS recursively sorted object keys (UTF16), UTF8 JSON, no whitespace."""
    def order(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("Only string JSON keys are allowed")
            return {key: order(item[key]) for key in sorted(item, key=lambda key: key.encode("utf-16-be"))}
        if isinstance(item, list):
            return [order(child) for child in item]
        if item is None or isinstance(item, (str, bool)):
            return item
        if isinstance(item, int) and abs(item) <= 9007199254740991:
            return item
        raise ValueError("Unsupported JSON type/unsafe integer")
    return json.dumps(order(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def source_hash(key, sources):
    return digest([key, sources.get("es-ES") or "", sources["en-US"]])


def make_catalog(build_id, catalogs, evidence, provenance):
    document = {
        "schema_version": 1, "kind": "source_catalog", "project_id": PROJECT,
        "build_id": str(build_id), "app_id": APP_ID, "key_universe_locale": "en-US",
        "catalogs": catalogs, "evidence": evidence, "provenance": provenance,
        "source_catalog_hash": digest(catalogs),
        "local_verified_bytes": True, "source_approved": False, "server_registered": False,
        "human_review_complete": False, "runtime_verified": False,
    }
    return validate_catalog(document)


def validate_catalog(document):
    if document.get("schema_version") != 1 or document.get("kind") not in ("source_catalog", "source_catalog_baseline") or document.get("project_id") != PROJECT or document.get("app_id") != APP_ID or document.get("key_universe_locale") != "en-US":
        raise ValueError("Invalid source catalog schema/project/app/key universe")
    if not isinstance(document.get("build_id"), str) or not document["build_id"].isdigit():
        raise ValueError("Numeric Steam build string required")
    catalogs = document.get("catalogs")
    if not isinstance(catalogs, dict) or not set(PRIMARY) <= set(catalogs) or set(catalogs) - set(LOCALES):
        raise ValueError("ES/EN required; only the eight native locales accepted")
    baseline = document.get("kind") == "source_catalog_baseline"
    if (document.get("local_verified_bytes") is not True and not baseline) or document.get("source_approved") is not False or document.get("server_registered") is not False:
        raise ValueError("Local measurement required; file must not claim approval/registration")
    if document.get("human_review_complete") is not False or document.get("runtime_verified") is not False:
        raise ValueError("No human/runtime approval may be exported")
    for locale, values in catalogs.items():
        if not isinstance(values, dict) or not values or any(not isinstance(key, str) or not key or not isinstance(value, str) for key, value in values.items()):
            raise ValueError("Invalid native text map: " + locale)
        proof = document.get("evidence", {}).get(locale, {})
        if proof.get("catalog_hash") != digest(values) or proof.get("count") != len(values) or proof.get("format") != "aion2_l10n_v2":
            raise ValueError("Catalog hash/count/format mismatch: " + locale)
        for field in ("archive_sha256", "dat_sha256"):
            value = proof.get(field)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdefABCDEF" for c in value):
                raise ValueError("Missing measured source file pin: " + locale + "/" + field)
    if document.get("source_catalog_hash") != digest(catalogs):
        raise ValueError("Full native source catalog fingerprint mismatch")
    return document


def compare_catalogs(previous, current, project=None):
    """Preview only. Every Italian string is copied verbatim; never applies changes."""
    validate_catalog(previous)
    validate_catalog(current)
    before, after = previous["catalogs"], current["catalogs"]
    old_keys, new_keys = set(before["en-US"]), set(after["en-US"])
    comparable = sorted(PRIMARY)
    current_languages = sorted(after)
    entries = {}
    if project is not None:
        if project.get("project_id") != PROJECT or str(project.get("build_id")) != previous["build_id"]:
            raise ValueError("Italian workspace project/build differs from previous catalog")
        for entry in project.get("entries", []):
            key = entry.get("key")
            if key in entries or not isinstance(entry.get("it"), str):
                raise ValueError("Invalid/duplicate Italian workspace key")
            if key not in old_keys or entry.get("es") != before["es-ES"].get(key, "") or entry.get("en") != before["en-US"].get(key):
                raise ValueError("Italian workspace source does not match previous native catalog")
            entries[key] = entry
        if set(entries) != old_keys:
            raise ValueError("Italian workspace coverage differs from previous catalog")
    changes, removed, warnings = [], [], []
    if set(before) - set(after):
        warnings.append({"code": "languages_unavailable_current", "locales": sorted(set(before) - set(after)), "effect": "not_compared_not_removed"})
    if set(after) - set(before):
        warnings.append({"code": "languages_without_historical_comparison", "locales": sorted(set(after) - set(before)), "effect": "new_evidence_not_assumed_changed"})
    changed_count = 0
    for key in sorted(new_keys):
        old = key in old_keys
        old_sources = {lang: before[lang].get(key) for lang in comparable} if old else None
        new_sources = {lang: after[lang].get(key) for lang in current_languages}
        differences = [{"locale": lang, "previous": before[lang].get(key), "current": after[lang].get(key)} for lang in comparable if old and before[lang].get(key) != after[lang].get(key)]
        if new_sources.get("es-ES") is None:
            warnings.append({"code": "spanish_key_absent", "key": key, "effect": "retain_true_absence_no_synthetic_source"})
        if old and not differences:
            continue
        operation = "changed" if old else "added"
        changed_count += int(old)
        event = {"key": key, "operation": operation, "before_sources": old_sources, "after_sources": new_sources,
                 "changed_sources": differences, "source_hash": source_hash(key, new_sources),
                 "current_fingerprint": digest({lang: new_sources[lang] for lang in comparable}), "recheck_required": old, "translation_required": not old,
                 "italian_action": "preserve_exact" if old else "new_empty_after_explicit_import"}
        event.update(group=entries[key].get("group") if key in entries else previous.get("groups_by_key", {}).get(key, classify_key(key)),
                     previous_source_hash=source_hash(key, old_sources) if old else None,
                     before_en=old_sources.get("en-US") if old else None,
                     before_es=old_sources.get("es-ES") if old else None)
        if event["group"] not in GROUPS:
            raise ValueError("Unknown group for import key")
        if key in entries:
            event["previous_it"] = entries[key]["it"]
        changes.append(event)
    for key in sorted(old_keys - new_keys):
        old_sources = {lang: before[lang].get(key) for lang in comparable}
        event = {"key": key, "operation": "removed", "before_sources": old_sources, "italian_action": "archive_preserve_exact", "recheck_required": False,
                 "group": entries[key].get("group") if key in entries else previous.get("groups_by_key", {}).get(key, classify_key(key)),
                 "previous_source_hash": source_hash(key, old_sources), "before_en": old_sources["en-US"], "before_es": old_sources.get("es-ES")}
        if key in entries:
            event["previous_it"] = entries[key]["it"]
        removed.append(event)
    report = {
        "schema_version": 1, "kind": "source_catalog_diff", "project_id": PROJECT,
        "from_build": previous["build_id"], "to_build": current["build_id"],
        "from_catalog_hash": previous["source_catalog_hash"], "to_catalog_hash": current["source_catalog_hash"],
        "counts": {"old_total": len(old_keys), "new_total": len(new_keys), "added": len(new_keys - old_keys),
                   "changed": changed_count, "removed": len(old_keys - new_keys), "unchanged": len(old_keys & new_keys) - changed_count},
        "compared_languages": comparable, "comparison_languages": comparable, "current_languages": current_languages,
        "native_consult_languages": sorted(set(after) - set(PRIMARY)),
        "native_historical_online_comparison": False,
        "source_only_keys": {locale: len(set(values) - new_keys) for locale, values in after.items()},
        "changes": changes, "removed_entries": removed, "warnings": warnings,
        "evidence": {"previous": deepcopy(previous["evidence"]), "current": deepcopy(current["evidence"])},
        "current_provenance": deepcopy(current["provenance"]),
        "italian_projection_included": project is not None,
        "italian_replacements": 0, "source_approved": False, "server_registered": False,
        "human_review_complete": False, "runtime_verified": False, "applied": False,
    }
    report["diff_hash"] = digest(report)
    return report


def baseline_from_project(project, project_file_sha256):
    """Only the attested previous ES/EN subset; never claims new source extraction."""
    if project.get("project_id") != PROJECT or not str(project.get("build_id", "")).isdigit():
        raise ValueError("Frozen project identity invalid")
    native = {lang: {} for lang in PRIMARY}
    groups = {}
    for entry in project.get("entries", []):
        key = entry.get("key")
        if key in groups or not isinstance(key, str) or not key or entry.get("group") not in GROUPS:
            raise ValueError("Invalid/duplicate frozen project key/group")
        for locale, field in (("es-ES", "es"), ("en-US", "en")):
            if not isinstance(entry.get(field), str):
                raise ValueError("Missing frozen native source")
            native[locale][key] = entry[field]
        groups[key] = entry["group"]
        if entry.get("source_hash") != source_hash(key, {lang: native[lang][key] for lang in PRIMARY}):
            raise ValueError("Frozen project source_hash mismatch")
    historical = project.get("translation_tracking", {}).get("current_evidence", {})
    proof = {}
    for locale in PRIMARY:
        old = historical.get(locale, {})
        measured = digest(native[locale])
        if old.get("workspace_catalog_hash") != measured:
            raise ValueError("Frozen historical workspace catalog pin missing/mismatched")
        proof[locale] = {"catalog_hash": measured, "count": len(native[locale]), "archive_sha256": old.get("installed_archive_sha256",old.get("archive_sha256")),
                         "dat_sha256": old.get("dat_sha256"), "format": "aion2_l10n_v2", "origin": "frozen_project_native_subset"}
    return validate_catalog({"schema_version": 1, "kind": "source_catalog_baseline", "project_id": PROJECT,
                            "build_id": str(project["build_id"]), "app_id": APP_ID, "key_universe_locale": "en-US", "catalogs": native,
                            "evidence": proof, "provenance": {"origin": "frozen_project", "frozen_project_sha256": project_file_sha256},
                            "groups_by_key": groups, "source_catalog_hash": digest(native), "local_verified_bytes": False,
                            "source_approved": False, "server_registered": False, "human_review_complete": False, "runtime_verified": False})


def validate_diff(report):
    if report.get("schema_version") != 1 or report.get("kind") != "source_catalog_diff" or report.get("project_id") != PROJECT:
        raise ValueError("Invalid source diff schema")
    payload = {key: value for key, value in report.items() if key != "diff_hash"}
    if digest(payload) != report.get("diff_hash"):
        raise ValueError("Diff fingerprint mismatch")
    if any(report.get(field) is not False for field in ("source_approved", "server_registered", "human_review_complete", "runtime_verified", "applied")) or report.get("italian_replacements") != 0:
        raise ValueError("Source diff cannot claim approval, application or Italian replacement")
    if report.get("comparison_languages") != ["en-US", "es-ES"] or report.get("compared_languages") != ["en-US", "es-ES"] or report.get("native_historical_online_comparison") is not False:
        raise ValueError("Historical comparison must be explicitly EN/ES only")
    if any(not isinstance(report.get(field), str) or not report[field].isdigit() for field in ("from_build", "to_build")):
        raise ValueError("Source diff build IDs invalid")
    if not isinstance(report.get("changes"), list) or not isinstance(report.get("removed_entries"), list):
        raise ValueError("Source diff arrays invalid")
    removed_ids = {id(event) for event in report["removed_entries"]}
    for event in report["changes"] + report["removed_entries"]:
        key, operation = event.get("key"), event.get("operation")
        if not isinstance(key, str) or not key or event.get("group") not in GROUPS or "expected_version" in event:
            raise ValueError("Invalid event key/group or client-supplied version")
        if operation not in ("added", "changed", "removed"):
            raise ValueError("Invalid source operation")
        if (operation == "removed") != (id(event) in removed_ids):
            raise ValueError("Operation is in the wrong event array")
        before = event.get("before_sources")
        if operation == "added":
            if any(event.get(field) is not None for field in ("before_sources", "previous_source_hash", "before_en", "before_es")):
                raise ValueError("Added key cannot invent a previous source")
        else:
            if not isinstance(before, dict) or set(before) != set(PRIMARY) or not isinstance(before.get("en-US"), str) or (before.get("es-ES") is not None and not isinstance(before["es-ES"], str)):
                raise ValueError("Previous native source missing")
            if event.get("before_en") != before["en-US"] or event.get("before_es") != before["es-ES"] or event.get("previous_source_hash") != source_hash(key, before):
                raise ValueError("Previous source text/hash differs")
        if operation != "removed":
            after = event.get("after_sources")
            if not isinstance(after, dict) or not set(PRIMARY) <= set(after) or set(after) - set(LOCALES) or not isinstance(after["en-US"], str) or any(value is not None and not isinstance(value, str) for value in after.values()):
                raise ValueError("Current native source invalid")
            if event.get("source_hash") != source_hash(key, after) or event.get("current_fingerprint") != digest({lang: after[lang] for lang in sorted(PRIMARY)}):
                raise ValueError("Current source text/hash differs")
            expected_changes = [{"locale": lang, "previous": before[lang], "current": after[lang]} for lang in sorted(PRIMARY) if operation == "changed" and before[lang] != after[lang]]
            if event.get("changed_sources") != expected_changes or (operation == "changed" and not expected_changes):
                raise ValueError("Changed source details differ")
            if event.get("recheck_required") is not (operation == "changed") or event.get("translation_required") is not (operation == "added"):
                raise ValueError("Editorial action flags differ")
            if event.get("italian_action") != ("preserve_exact" if operation == "changed" else "new_empty_after_explicit_import"):
                raise ValueError("Italian preservation action differs")
        elif event.get("italian_action") != "archive_preserve_exact":
            raise ValueError("Removed key preservation action differs")
    keys = [row["key"] for row in report.get("changes", []) + report.get("removed_entries", [])]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate diff key")
    counts = report["counts"]
    if set(counts) != {"old_total", "new_total", "added", "changed", "removed", "unchanged"} or any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError("Invalid source diff counts")
    if sum(row["operation"] == "added" for row in report["changes"]) != counts["added"] or sum(row["operation"] == "changed" for row in report["changes"]) != counts["changed"] or len(report["removed_entries"]) != counts["removed"]:
        raise ValueError("Diff event counts differ")
    if counts["old_total"] != counts["changed"] + counts["unchanged"] + counts["removed"] or counts["new_total"] != counts["changed"] + counts["unchanged"] + counts["added"]:
        raise ValueError("Diff coverage counts differ")
    return report
