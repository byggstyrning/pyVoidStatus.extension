# -*- coding: utf-8 -*-
"""Extensible Storage schema for Void Status project settings."""

from pyrevit import script
from extensible_storage import BaseSchema, simple_field, map_field, ES

logger = script.get_logger()


class VoidStatusSchema(BaseSchema):
    """Project-level Void Status configuration stored in the Revit file."""

    guid = "c8e4f2a1-7b39-4d6e-9a5c-1f8d2e4b6a70"
    read_access_level = ES.AccessLevel.Public
    write_access_level = ES.AccessLevel.Public

    @simple_field(value_type="string")
    def schema_version():
        """Current schema version."""
        return "1.0"

    @simple_field(value_type="string")
    def config_xml():
        """Project XML configuration (parameters, disciplines, options)."""
        return None


class VoidStatusUserSchema(BaseSchema):
    """Per-user discipline codes stored in the Revit file.

    Keyed by Revit username so the same person can use STR in one model and
    FP in another, without changing a colleague's setting.
    """

    guid = "c8e4f2a1-7b39-4d6e-9a5c-1f8d2e4b6a71"
    read_access_level = ES.AccessLevel.Public
    write_access_level = ES.AccessLevel.Public

    @map_field(key_type="string", value_type="string")
    def discipline_by_user():
        """Revit username to discipline code."""
        return None
