# -*- coding: utf-8 -*-
"""Extensible Storage schemas for Void Status project settings.

Field names and GUIDs come from ``void_status.contract``. The method names
below are the stored field names; do not rename them.
"""

from extensible_storage import BaseSchema, simple_field, map_field, ES

from void_status.contract import (
    PROJECT_SCHEMA_GUID,
    USER_SCHEMA_GUID,
    SCHEMA_VERSION,
)


class VoidStatusSchema(BaseSchema):
    """Project XML stored on a DataStorage element in the Revit file."""

    guid = PROJECT_SCHEMA_GUID
    read_access_level = ES.AccessLevel.Public
    write_access_level = ES.AccessLevel.Public

    @simple_field(value_type="string")
    def schema_version():
        """Current schema version."""
        return SCHEMA_VERSION

    @simple_field(value_type="string")
    def config_xml():
        """Project XML configuration (parameters, disciplines, options)."""
        return None


class VoidStatusUserSchema(BaseSchema):
    """Per-user discipline codes stored in the Revit file.

    Keyed by Revit username so one person can use STR in one model and FP
    in another, without changing a colleague's setting.
    """

    guid = USER_SCHEMA_GUID
    read_access_level = ES.AccessLevel.Public
    write_access_level = ES.AccessLevel.Public

    @map_field(key_type="string", value_type="string")
    def discipline_by_user():
        """Revit username to discipline code."""
        return None
