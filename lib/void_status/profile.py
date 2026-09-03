# -*- coding: utf-8 -*-
"""Per-user Void Status profile.

Name stays on this workstation (pyRevit user config).
Discipline is stored in the Revit file, keyed by Revit username, so it is
user + model specific.
"""

from pyrevit import script, HOST_APP
from pyrevit.userconfig import user_config
from void_status.constants import canonical_discipline_code
from void_status.storage import _doc_key, load_user_discipline, save_user_discipline
from void_status.logutil import log_debug, log_info, log_exception

logger = script.get_logger()

CONFIG_SECTION = "VoidStatus"
KEY_NAME = "profile_name"
KEY_DISCIPLINE = "profile_discipline"

_profile_cache = {}


def current_user_key():
    """Stable Revit username used as the model-side map key."""
    try:
        name = (HOST_APP.username or "").strip()
        if name:
            return name
    except Exception:
        pass
    return ""


def _section():
    if not hasattr(user_config, CONFIG_SECTION):
        log_info("Creating user_config section {!r}".format(CONFIG_SECTION))
        user_config.add_section(CONFIG_SECTION)
    return getattr(user_config, CONFIG_SECTION)


def _load_local_name_and_legacy_discipline():
    """Workstation name, plus leftover machine-wide discipline for migration."""
    try:
        section = _section()
        name = section.get_option(KEY_NAME, default_value="") or ""
        raw = section.get_option(KEY_DISCIPLINE, default_value="") or ""
        return name, canonical_discipline_code(raw)
    except Exception as ex:
        log_exception("Error loading Void Status workstation profile", ex)
        logger.error("Error loading Void Status workstation profile: {}".format(ex))
        return "", ""


def load_profile(doc=None):
    """Return ``{'name': str, 'discipline': str}``.

    Discipline comes from this model for the current Revit user. If this
    model has no entry yet, a leftover workstation value is used so existing
    setups keep working until Config is saved once.
    """
    user = current_user_key()
    cache_key = (_doc_key(doc) if doc else "", user)
    hit = _profile_cache.get(cache_key)
    if hit is not None:
        return hit

    name, legacy_discipline = _load_local_name_and_legacy_discipline()
    discipline = ""
    if doc and user:
        discipline = canonical_discipline_code(load_user_discipline(doc, user))
    if not discipline:
        discipline = legacy_discipline

    log_debug(
        "Loaded profile user={!r} name={!r} discipline={!r} (model={})".format(
            user, name, discipline, bool(doc)
        )
    )
    profile = {"name": name, "discipline": discipline}
    _profile_cache[cache_key] = profile
    return profile


def save_profile(name, discipline, doc=None):
    """Save name on this workstation and discipline for this user in this model."""
    global _profile_cache
    try:
        canon = canonical_discipline_code(discipline)
        section = _section()
        section.set_option(KEY_NAME, name or "")
        if hasattr(section, "remove_option"):
            try:
                section.remove_option(KEY_DISCIPLINE)
            except Exception:
                section.set_option(KEY_DISCIPLINE, "")
        else:
            section.set_option(KEY_DISCIPLINE, "")
        user_config.save_changes()

        user = current_user_key()
        if doc and user:
            if not save_user_discipline(doc, user, canon):
                return False
        elif doc and not user:
            log_warning("Cannot store model discipline: Revit username is empty")
            return False

        profile = {"name": name or "", "discipline": canon}
        _profile_cache.clear()
        if doc:
            _profile_cache[(_doc_key(doc), user)] = profile
        log_info(
            "Saved profile name={!r} discipline={!r} user={!r} in-model={}".format(
                name or "", canon, user, bool(doc)
            )
        )
        return True
    except Exception as ex:
        log_exception("Error saving Void Status profile", ex)
        logger.error("Error saving Void Status profile: {}".format(ex))
        return False


def require_discipline(doc=None):
    """Return the configured discipline or None if missing."""
    profile = load_profile(doc)
    discipline = (profile.get("discipline") or "").strip()
    if not discipline:
        log_debug("require_discipline: no discipline for this user in this model")
        return None
    return discipline
