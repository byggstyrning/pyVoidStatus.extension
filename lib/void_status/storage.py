# -*- coding: utf-8 -*-
"""Read and write Void Status settings on the project DataStorage element."""

from Autodesk.Revit.DB import FilteredElementCollector, ExtensibleStorage
from System.Collections.Generic import Dictionary, IDictionary
from pyrevit import revit

from void_status.schema import VoidStatusSchema, VoidStatusUserSchema
from void_status.contract import SCHEMA_VERSION, DEFAULT_XML
from void_status.contract import FIELD_SCHEMA_VERSION, FIELD_CONFIG_XML, FIELD_DISCIPLINE_BY_USER
from void_status.config import parse_config_xml
from void_status.logutil import log_debug, log_info, log_warning, log_error, log_exception

# Session caches. Scanning extensible storage and parsing XML dominate a click.
_STORAGE_IDS = {}
_PARSED = {}
_XML_FALLBACK_ALERTED = set()


def _doc_key(doc):
    try:
        return "{}|{}".format(doc.PathName or "", doc.Title or "")
    except Exception:
        return str(id(doc))


def _invalidate_doc(doc):
    _PARSED.pop(_doc_key(doc), None)


def _entity_matches(element, schema):
    entity = element.GetEntity(schema)
    return entity.IsValid() and entity.Schema.GUID == schema.GUID


def find_storage(doc):
    """Return the existing DataStorage element for Void Status, or None."""
    schema = VoidStatusSchema.schema
    if not schema:
        log_error("Could not get VoidStatusSchema definition.")
        return None

    key = _doc_key(doc)
    cached_id = _STORAGE_IDS.get(key)
    if cached_id is not None:
        try:
            existing = doc.GetElement(cached_id)
            if existing and _entity_matches(existing, schema):
                return existing
        except Exception:
            pass
        _STORAGE_IDS.pop(key, None)

    collector = FilteredElementCollector(doc).OfClass(ExtensibleStorage.DataStorage)
    for storage in collector:
        try:
            if _entity_matches(storage, schema):
                _STORAGE_IDS[key] = storage.Id
                log_debug("Found Void Status storage element {}".format(storage.Id))
                return storage
        except Exception as ex:
            log_debug("Error checking Void Status storage: {}".format(ex))
    log_debug("No existing Void Status DataStorage in this document")
    return None


def get_or_create_storage(doc):
    """Get the existing DataStorage element, or create one with default XML."""
    existing = find_storage(doc)
    if existing:
        log_debug("Using existing Void Status storage {}".format(existing.Id))
        return existing

    schema = VoidStatusSchema.schema
    if not schema:
        log_error("Cannot create storage: schema definition missing")
        return None

    with revit.Transaction("Create Void Status Settings Storage", doc):
        storage = ExtensibleStorage.DataStorage.Create(doc)
        entity = VoidStatusSchema.entity
        entity.Set[str](FIELD_SCHEMA_VERSION, SCHEMA_VERSION)
        entity.Set[str](FIELD_CONFIG_XML, DEFAULT_XML)
        storage.SetEntity(entity)
        user_entity = VoidStatusUserSchema.entity
        user_entity.Set[IDictionary[str, str]](
            FIELD_DISCIPLINE_BY_USER, Dictionary[str, str]()
        )
        storage.SetEntity(user_entity)
        _STORAGE_IDS[_doc_key(doc)] = storage.Id
        log_info("Created Void Status storage (ElementId: {})".format(storage.Id))
        return storage


def _alert_config_fallback(doc, message):
    """Alert once per document when stored settings cannot be used."""
    key = _doc_key(doc)
    if key in _XML_FALLBACK_ALERTED:
        log_warning(message)
        return
    _XML_FALLBACK_ALERTED.add(key)
    log_warning(message)
    try:
        from pyrevit import forms
        forms.alert(
            "{}\n\nDefaults will be used until you save Config. "
            "Saving replaces the stored settings.".format(message),
            title="Void Status",
        )
    except Exception as ex:
        log_debug("Could not show settings alert: {}".format(ex))


def load_config_xml(doc):
    """Load the project XML string. Missing storage returns the default quietly.

    A read error or XML that will not parse alerts once, so Save does not
    overwrite it unnoticed.
    """
    storage = find_storage(doc)
    if not storage:
        log_info("No project XML stored — using default ({} chars)".format(len(DEFAULT_XML)))
        return DEFAULT_XML

    try:
        entity = storage.GetEntity(VoidStatusSchema.schema)
        if not entity.IsValid():
            _alert_config_fallback(
                doc,
                "Void Status settings in this model could not be read (invalid storage).",
            )
            return DEFAULT_XML
        xml_text = entity.Get[str](FIELD_CONFIG_XML)
        if not xml_text or not xml_text.strip():
            log_warning("Stored XML empty — using default")
            return DEFAULT_XML
        try:
            parse_config_xml(xml_text)
        except ValueError as ex:
            _alert_config_fallback(
                doc,
                "Void Status settings in this model could not be read.\n\n{}".format(ex),
            )
            return DEFAULT_XML
        log_debug(
            "Loaded project XML ({} chars) from storage {}".format(len(xml_text), storage.Id)
        )
        return xml_text
    except Exception as ex:
        log_exception("Error loading Void Status XML", ex)
        _alert_config_fallback(
            doc,
            "Void Status settings in this model could not be read.\n\n{}".format(ex),
        )
    return DEFAULT_XML


def save_config_xml(doc, xml_text):
    """Persist XML configuration on the project DataStorage element."""
    storage = get_or_create_storage(doc)
    if not storage:
        log_error("Could not create Void Status project storage")
        raise RuntimeError("Could not create Void Status project storage.")

    log_info(
        "Saving project XML ({} chars) to storage {}".format(len(xml_text or ""), storage.Id)
    )
    with revit.Transaction("Save Void Status Settings", doc):
        entity = storage.GetEntity(VoidStatusSchema.schema)
        if not entity.IsValid():
            log_debug("Replacing invalid storage entity")
            entity = VoidStatusSchema.entity
        entity.Set[str](FIELD_SCHEMA_VERSION, SCHEMA_VERSION)
        entity.Set[str](FIELD_CONFIG_XML, xml_text)
        storage.SetEntity(entity)
    _invalidate_doc(doc)
    log_info("Project XML saved")
    return True


def load_config(doc):
    """Parsed project config, cached for the rest of the Revit session."""
    key = _doc_key(doc)
    hit = _PARSED.get(key)
    if hit is not None:
        return hit[1]
    xml_text = load_config_xml(doc)
    config = parse_config_xml(xml_text)
    _PARSED[key] = (xml_text, config)
    return config


def _read_discipline_map(storage):
    """Return username -> discipline from the user schema."""
    schema = VoidStatusUserSchema.schema
    if not schema or not storage:
        return {}
    try:
        entity = storage.GetEntity(schema)
        if not entity.IsValid():
            return {}
        mapping = entity.Get[IDictionary[str, str]](FIELD_DISCIPLINE_BY_USER)
        if not mapping:
            return {}
        result = {}
        for key in mapping.Keys:
            result[str(key)] = str(mapping[key] or "")
        return result
    except Exception as ex:
        log_debug("Could not read user discipline map: {}".format(ex))
        return {}


def load_user_discipline(doc, username):
    """Discipline code for this Revit user in this model, or an empty string."""
    if not doc or not username:
        return ""
    storage = find_storage(doc)
    if not storage:
        return ""
    return (_read_discipline_map(storage).get(username) or "").strip()


def save_user_discipline(doc, username, discipline):
    """Store this Revit user's discipline in the model. Other users stay."""
    if not doc or not username:
        log_warning("Cannot save user discipline without a document and username")
        return False
    storage = get_or_create_storage(doc)
    if not storage:
        log_error("Could not create Void Status project storage")
        return False

    mapping = _read_discipline_map(storage)
    mapping[username] = discipline or ""
    stored = Dictionary[str, str]()
    for key, value in mapping.items():
        stored[key] = value or ""

    log_info(
        "Saving discipline {!r} for user {!r} in this model ({} users)".format(
            discipline or "", username, stored.Count
        )
    )
    with revit.Transaction("Save Void Status user discipline", doc):
        schema = VoidStatusUserSchema.schema
        entity = storage.GetEntity(schema)
        if not entity.IsValid():
            entity = VoidStatusUserSchema.entity
        entity.Set[IDictionary[str, str]](FIELD_DISCIPLINE_BY_USER, stored)
        storage.SetEntity(entity)
    log_info("User discipline saved")
    return True
