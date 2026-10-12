# -*- coding: utf-8 -*-
"""Config window for the workstation name and the project XML."""

import codecs

from pyrevit import forms, revit, HOST_APP

import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
clr.AddReference("System.Data")
from System import DBNull, String
from System.Data import DataTable
from System.Windows.Controls import CheckBox, DataGridEditingUnit
from System.Windows import Thickness

from void_status.contract import (
    DEFAULT_XML,
    CATEGORY_CHOICES,
    categories_for_ensure,
    STATUS_PARAMETERS,
    canonical_discipline_code,
)
from void_status.storage import load_config_xml, save_config_xml
from void_status.config import parse_config_xml, build_config_xml, assert_import_xml
from void_status.profile import load_profile, save_profile
from void_status.binder import ensure_shared_parameters
from void_status.logutil import log_info, log_warning, log_exception
from void_status.paths import local_bundle_file


def _cell(row, column):
    try:
        value = row[column]
    except Exception:
        return ""
    if value is None or value == DBNull.Value:
        return ""
    return str(value).strip()


def _commit_grid(grid):
    if grid is None:
        return
    try:
        grid.CommitEdit(DataGridEditingUnit.Cell, True)
        grid.CommitEdit(DataGridEditingUnit.Row, True)
    except Exception:
        try:
            grid.CommitEdit()
        except Exception:
            pass


class VoidStatusSettingsWindow(forms.WPFWindow):
    """WPF window for the profile and the shared project settings."""

    def __init__(self, xaml_path):
        log_info("Config window opening")
        self._is_initializing = True
        self._category_checks = []
        self._disc_table = None
        self._param_table = None
        forms.WPFWindow.__init__(self, local_bundle_file(xaml_path))
        self._load_ui()
        self._is_initializing = False
        log_info("Config window loaded")

    def _load_ui(self):
        profile = load_profile(revit.doc)
        name = (profile.get("name") or "").strip()
        if not name:
            try:
                name = HOST_APP.username or ""
            except Exception:
                name = ""
        self.nameBox.Text = name
        try:
            config = parse_config_xml(load_config_xml(revit.doc))
        except ValueError as ex:
            log_exception("Could not parse project settings", ex)
            forms.alert(
                "Project settings could not be read.\nRestoring defaults.\n\n{}".format(ex),
                title="Void Status",
            )
            config = parse_config_xml(DEFAULT_XML)
        self._apply_config(
            config, select=canonical_discipline_code(profile.get("discipline") or "")
        )

    def _apply_config(self, config, select=None):
        self._fill_disciplines(config)
        self._fill_categories(config)
        self._fill_parameters(config)
        self.separatorBox.Text = (
            config.value_separator if config.value_separator is not None else ", "
        )
        self._refresh_discipline_combo(select=select)

    def _fill_disciplines(self, config):
        table = DataTable()
        table.Columns.Add("Code", String)
        table.Columns.Add("Name", String)
        for item in config.disciplines:
            if isinstance(item, dict):
                code = (item.get("code") or "").strip()
                label = (item.get("label") or "").strip()
            else:
                code = (item or "").strip()
                label = ""
            if not code:
                continue
            row = table.NewRow()
            row["Code"] = code
            row["Name"] = label
            table.Rows.Add(row)
        self._disc_table = table
        self.disciplineGrid.ItemsSource = table.DefaultView

    def _fill_parameters(self, config):
        table = DataTable()
        table.Columns.Add("Key", String)
        table.Columns.Add("Name", String)
        table.Columns.Add("Guid", String)
        for item in STATUS_PARAMETERS:
            mapped = config.parameter(item["key"]) or item
            row = table.NewRow()
            row["Key"] = item["key"]
            row["Name"] = mapped.get("name") or item["name"]
            row["Guid"] = mapped.get("guid") or item["guid"]
            table.Rows.Add(row)
        self._param_table = table
        self.parameterGrid.ItemsSource = table.DefaultView

    def _fill_categories(self, config):
        self.categoriesPanel.Children.Clear()
        self._category_checks = []
        selected = set(config.categories or [])
        known = []
        for ost_name, label in CATEGORY_CHOICES:
            known.append(ost_name)
            self._add_category_check(ost_name, label, ost_name in selected)
        for ost_name in [name for name in (config.categories or []) if name not in known]:
            self._add_category_check(ost_name, ost_name, True)

    def _add_category_check(self, ost_name, label, checked):
        box = CheckBox()
        box.Content = label
        box.Tag = ost_name
        box.IsChecked = bool(checked)
        box.Margin = Thickness(0, 0, 16, 6)
        box.FontSize = 12
        self.categoriesPanel.Children.Add(box)
        self._category_checks.append(box)

    def _refresh_discipline_combo(self, select=None):
        current = self.disciplineCombo.Text if select is None else select
        codes = self._discipline_codes_from_grid()
        self.disciplineCombo.Items.Clear()
        for code in codes:
            self.disciplineCombo.Items.Add(code)
        self.disciplineCombo.Text = current or ""

    def _discipline_codes_from_grid(self):
        codes = []
        _commit_grid(self.disciplineGrid)
        if self._disc_table is None:
            return codes
        for row in self._disc_table.Rows:
            code = canonical_discipline_code(_cell(row, "Code"))
            if code:
                codes.append(code)
        return codes

    def _config_from_ui(self):
        _commit_grid(self.disciplineGrid)
        _commit_grid(self.parameterGrid)

        config = parse_config_xml(DEFAULT_XML)
        config.disciplines = []
        if self._disc_table is not None:
            for row in self._disc_table.Rows:
                code = canonical_discipline_code(_cell(row, "Code"))
                label = _cell(row, "Name")
                if code:
                    config.add_discipline(code, label)

        config.categories = []
        for box in self._category_checks:
            if box.IsChecked:
                name = box.Tag
                if name:
                    config.categories.append(str(name))

        separator = self.separatorBox.Text
        config.value_separator = ", " if separator is None else separator

        if self._param_table is not None:
            for row in self._param_table.Rows:
                key = _cell(row, "Key")
                guid = _cell(row, "Guid")
                name = _cell(row, "Name")
                if key and guid and name:
                    config.parameters[key] = {"guid": guid, "name": name}
        return config

    def import_click(self, sender, args):
        path = forms.pick_file(file_ext="xml")
        if not path:
            log_info("Settings import cancelled")
            return
        log_info("Importing settings from {}".format(path))
        try:
            with codecs.open(path, "r", "utf-8") as handle:
                text = handle.read()
            text = assert_import_xml(text)
            self._apply_config(parse_config_xml(text))
            log_info("Settings import succeeded")
        except Exception as ex:
            log_exception("Settings import failed", ex)
            forms.alert("Could not import settings:\n{}".format(ex), title="Void Status")

    def export_click(self, sender, args):
        path = forms.save_file(file_ext="xml")
        if not path:
            log_info("Settings export cancelled")
            return
        log_info("Exporting settings to {}".format(path))
        try:
            text = build_config_xml(self._config_from_ui())
            with codecs.open(path, "w", "utf-8") as handle:
                handle.write(text)
            log_info("Settings export succeeded ({} chars)".format(len(text)))
        except Exception as ex:
            log_exception("Settings export failed", ex)
            forms.alert("Could not export settings:\n{}".format(ex), title="Void Status")

    def reset_click(self, sender, args):
        if not forms.alert(
            "Restore the default disciplines, categories and parameter mapping for this window?",
            yes=True,
            no=True,
            title="Void Status",
        ):
            log_info("Restore defaults cancelled")
            return
        log_info("Restoring default project settings in the editor")
        current = self.disciplineCombo.Text
        self._apply_config(parse_config_xml(DEFAULT_XML), select=current)

    def ensure_params_click(self, sender, args):
        try:
            config = self._config_from_ui()
        except Exception as ex:
            log_warning("Bind aborted: {}".format(ex))
            forms.alert("Could not read the form:\n{}".format(ex), title="Void Status")
            return
        if not config.categories:
            forms.alert(
                "Select at least one category before adding parameters.",
                title="Void Status",
            )
            return
        bind_categories = categories_for_ensure(config.categories)
        log_info("Binding status parameters for categories {}".format(bind_categories))
        added, already, error = ensure_shared_parameters(
            revit.doc, bind_categories, __file__
        )
        if error:
            log_warning("Bind failed: {}".format(error))
            forms.alert("Could not bind parameters:\n{}".format(error), title="Void Status")
            return
        log_info("Bind UI result added={} already={}".format(added, already))
        forms.alert(
            "Added or repaired {} parameter(s). {} already fully bound.".format(added, already),
            title="Void Status",
        )

    def save_click(self, sender, args):
        try:
            config = self._config_from_ui()
        except Exception as ex:
            log_warning("Save aborted: {}".format(ex))
            forms.alert("Could not read the form:\n{}".format(ex), title="Void Status")
            return
        if not config.discipline_codes():
            forms.alert("Add at least one discipline code.", title="Void Status")
            return

        discipline = canonical_discipline_code(self.disciplineCombo.Text)
        name = (self.nameBox.Text or "").strip()
        log_info("Save config name={!r} discipline={!r}".format(name, discipline))
        if discipline and discipline not in config.discipline_codes():
            log_info("Adding custom discipline {} to project settings".format(discipline))
            config.add_discipline(discipline)
            self._fill_disciplines(config)
            self._refresh_discipline_combo(select=discipline)

        try:
            save_config_xml(revit.doc, build_config_xml(config))
        except Exception as ex:
            log_exception("Could not save project settings", ex)
            forms.alert(
                "Could not save to the project file:\n{}".format(ex), title="Void Status"
            )
            return

        if not save_profile(name, discipline, revit.doc):
            log_warning("Project settings saved but profile save failed")
            forms.alert(
                "Project settings were saved, but the profile could not be stored.",
                title="Void Status",
            )
            return

        log_info("Config save complete")
        forms.alert(
            "Saved.\n\n"
            "Your discipline is stored for you in this Revit file.\n"
            "Name stays on this workstation.\n"
            "Project settings are shared with colleagues.",
            title="Void Status",
        )

    def close_click(self, sender, args):
        self.Close()


def show_settings(xaml_path):
    """Open the Config dialog. Returns after the window is closed."""
    if revit.doc is None:
        log_warning("Config aborted: no document")
        forms.alert("Open a project before configuring Void Status.", title="Void Status")
        return
    log_info("Ribbon: Config clicked")
    try:
        VoidStatusSettingsWindow(xaml_path).ShowDialog()
    except IOError as ex:
        log_exception("Config could not load XAML", ex)
        forms.alert(str(ex), title="Void Status")
