# -*- coding: utf-8 -*-
"""Read and write Void Status XML into the Revit project (DataStorage)."""

from Autodesk.Revit.DB import FilteredElementCollector, ExtensibleStorage
from System.Collections.Generic import Dictionary, IDictionary
from pyrevit import revit, script

from void_status.schema import VoidStatusSchema, VoidStatusUserSchema
from void_status.constants import SCHEMA_VERSION, DEFAULT_XML
from void_status.config_xml import parse_config_xml
from void_status.logutil import log_debug, log_info, log_warning, log_error, log_exception

logger = script.get_logger()

# Session caches: Extensible Storage scan and XML parse dominate a single click.
_STORAGE_IDS = {}
_PARSED = {}


def _doc_key(doc):
    try:
        return "{}|{}".format(doc.PathName or "", doc.Title or "")
    except Exception:
        return str(id(doc))


def _invalidate_doc(doc):
    key = _doc_key(doc)
    _PARSED.pop(key, None)


def find_storage(doc):
    """Return the existing DataStorage element for Void Status, or None."""
    schema = VoidStatusSchema.schema
    if not schema:
        log_error("Could not get VoidStatusSchema definition.")
        logger.error("Could not get VoidStatusSchema definition.")
        return None

    key = _doc_key(doc)
    cached_id = _STORAGE_IDS.get(key)
    if cached_id is not None:
        try:
            existing = doc.GetElement(cached_id)
            if existing:
                entity = existing.GetEntity(schema)
                if entity.IsValid() and entity.Schema.GUID == schema.GUID:
                    return existing
        except Exception:
            pass
        _STORAGE_IDS.pop(key, None)

    collector = FilteredElementCollector(doc).OfClass(ExtensibleStorage.DataStorage)
    for ds in collector:
        try:
            entity = ds.GetEntity(schema)
            if entity.IsValid() and entity.Schema.GUID == schema.GUID:
                _STORAGE_IDS[key] = ds.Id
                log_debug("Found Void Status storage element {}".format(ds.Id))
                return ds
        except Exception as ex:
            log_debug("Error checking Void Status storage: {}".format(ex))
            continue
    log_debug("No existing Void Status DataStorage in this document")
    return None


def get_or_create_storage(doc):
    """Get existing or create new Void Status DataStorage in the document."""
    existing = find_storage(doc)
    if existing:
        log_debug("Using existing Void Status storage {}".format(existing.Id))
        return existing

    schema = VoidStatusSchema.schema
    if not schema:
        log_error("Cannot create storage: schema definition missing")
        return None

    with revit.Transaction("Create Void Status Settings Storage", doc):
        new_storage = ExtensibleStorage.DataStorage.Create(doc)
        entity = VoidStatusSchema.entity
        entity.Set[str]("schema_version", SCHEMA_VERSION)
        entity.Set[str]("config_xml", DEFAULT_XML)
        new_storage.SetEntity(entity)
        user_entity = VoidStatusUserSchema.entity
        user_entity.Set[IDictionary[str, str]](
            "discipline_by_user", Dictionary[str, str]()
        )
        new_storage.SetEntity(user_entity)
        _STORAGE_IDS[_doc_key(doc)] = new_storage.Id
        log_info("Created Void Status storage (ElementId: {})".format(new_storage.Id))
        logger.debug("Created Void Status storage (ElementId: {})".format(new_storage.Id))
        return new_storage


def load_config_xml(doc):
    """Load the project XML string. Returns the default XML if none is stored."""
    storage = find_storage(doc)
    if not storage:
        log_info("No project XML stored — using default ({} chars)".format(len(DEFAULT_XML)))
        return DEFAULT_XML

    try:
        entity = storage.GetEntity(VoidStatusSchema.schema)
        if not entity.IsValid():
            log_warning("Storage entity invalid — using default XML")
            return DEFAULT_XML
        xml_text = entity.Get[str]("config_xml")
        if xml_text and xml_text.strip():
            log_debug(
                "Loaded project XML ({} chars) from storage {}".format(
                    len(xml_text), storage.Id
                )
            )
            return xml_text
        log_warning("Stored XML empty — using default")
    except Exception as ex:
        log_exception("Error loading Void Status XML", ex)
        logger.error("Error loading Void Status XML: {}".format(ex))
    return DEFAULT_XML


def save_config_xml(doc, xml_text):
    """Persist XML configuration on the project DataStorage element."""
    storage = get_or_create_storage(doc)
    if not storage:
        log_error("Could not create Void Status project storage")
        raise RuntimeError("Could not create Void Status project storage.")

    log_info("Saving project XML ({} chars) to storage {}".format(
        len(xml_text or ""), storage.Id
    ))
    with revit.Transaction("Save Void Status Settings", doc):
        entity = storage.GetEntity(VoidStatusSchema.schema)
        if not entity.IsValid():
            log_debug("Replacing invalid storage entity")
            entity = VoidStatusSchema.entity
        entity.Set[str]("schema_version", SCHEMA_VERSION)
        entity.Set[str]("config_xml", xml_text)
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
    """Return a Python dict of username -> discipline from the user schema."""
    schema = VoidStatusUserSchema.schema
    if not schema or not storage:
        return {}
    try:
        entity = storage.GetEntity(schema)
        if not entity.IsValid():
            return {}
        mapping = entity.Get[IDictionary[str, str]]("discipline_by_user")
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
    """Discipline code for this Revit user in this model, or empty string."""
    if not doc or not username:
        return ""
    storage = find_storage(doc)
    if not storage:
        return ""
    return (_read_discipline_map(storage).get(username) or "").strip()


def save_user_discipline(doc, username, discipline):
    """Store this Revit user's discipline in the model. Does not change others."""
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
        entity.Set[IDictionary[str, str]]("discipline_by_user", stored)
        storage.SetEntity(entity)
    log_info("User discipline saved")
    return True
