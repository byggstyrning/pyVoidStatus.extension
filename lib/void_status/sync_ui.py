# -*- coding: utf-8 -*-
"""WPF window for syncing approval statuses from a linked model."""

import os.path as op

from pyrevit import forms, revit, script

import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

from System.Windows import Thickness
from System.Windows.Controls import CheckBox

from void_status.storage import load_config_xml
from void_status.config import parse_config_xml
from void_status.profile import load_profile
from void_status.contract import canonical_discipline_code
from void_status.sync import (
    list_loaded_links,
    collect_link_disciplines,
    synchronize_from_link,
)
from void_status.logutil import log_info, log_warning, log_exception
from void_status.paths import local_bundle_file

logger = script.get_logger()


class LinkItem(object):
    def __init__(self, info):
        self.name = info["name"]
        self.info = info

    def ToString(self):
        return self.name


class SyncApprovalsWindow(forms.WPFWindow):
    def __init__(self, doc, fixed_link=None):
        self._doc = doc
        self._fixed_link = fixed_link
        log_info("Sync window opening")
        xaml_file = local_bundle_file(
            op.join(op.dirname(__file__), "SyncWindow.xaml")
        )
        forms.WPFWindow.__init__(self, xaml_file)
        self._config = parse_config_xml(load_config_xml(doc))
        self._separator = self._config.value_separator
        self._own = canonical_discipline_code(load_profile(doc).get("discipline"))
        log_info(
            "Sync profile discipline={!r} separator={!r}".format(
                self._own, self._separator
            )
        )
        self._checkboxes = []
        if fixed_link:
            self.Title = "Void Status — Link reloaded"
            self.introTitle.Text = "Link reloaded"
            self.introText.Text = (
                "{} was reloaded. Import approval statuses into this model?".format(
                    fixed_link.get("name") or "A linked model"
                )
            )
            self.closeButton.Content = "Not now"
            self.linkCombo.IsEnabled = False
        self._load_links()

    def _load_links(self):
        self.linkCombo.Items.Clear()
        if self._fixed_link:
            links = [self._fixed_link]
        else:
            links = list_loaded_links(self._doc)
        if not links:
            log_warning("Sync: no loaded Revit/IFC links")
            self.statusText.Text = "No loaded Revit or IFC links found."
            self.importButton.IsEnabled = False
            return
        for info in links:
            self.linkCombo.Items.Add(LinkItem(info))
        self.linkCombo.SelectedIndex = 0
        log_info("Sync UI listed {} link(s)".format(len(links)))

    def _selected_link(self):
        item = self.linkCombo.SelectedItem
        if item is None:
            return None
        return item.info

    def link_changed(self, sender, args):
        self._refresh_disciplines()

    def _refresh_disciplines(self):
        self.disciplinesPanel.Children.Clear()
        self._checkboxes = []
        link = self._selected_link()
        if not link:
            self.statusText.Text = "Select a linked model."
            return
        log_info("Scanning linked model '{}' for status codes".format(link["name"]))
        rows, opening_count = collect_link_disciplines(
            link["document"], self._config, self._separator
        )
        if not rows:
            self.statusText.Text = (
                "No Approved by / Rejected by / Pending by values found in {} "
                "({} openings with MatchKey or ObjectId).".format(
                    link["name"], opening_count
                )
            )
            return

        for row in rows:
            parts = []
            if row["approved"]:
                parts.append("Approved {}".format(row["approved"]))
            if row["rejected"]:
                parts.append("Rejected {}".format(row["rejected"]))
            if row["pending"]:
                parts.append("Pending {}".format(row["pending"]))
            label = row["code"]
            if parts:
                label = "{}  ({})".format(row["code"], ", ".join(parts))
            box = CheckBox()
            box.Content = label
            box.Tag = row["code"]
            is_own = self._own and row["code"].lower() == self._own.lower()
            box.IsChecked = not is_own
            box.Margin = Thickness(0, 4, 0, 4)
            self.disciplinesPanel.Children.Add(box)
            self._checkboxes.append(box)

        self.statusText.Text = "{} — {} openings, {} unique status code(s).".format(
            link["name"], opening_count, len(rows)
        )

    def _selected_codes(self):
        codes = []
        for box in self._checkboxes:
            if box.IsChecked == True:
                codes.append(box.Tag)
        return codes

    def import_click(self, sender, args):
        link = self._selected_link()
        if not link:
            log_warning("Import clicked with no link selected")
            forms.alert("Select a linked model.", title="Void Status")
            return
        codes = self._selected_codes()
        log_info("Import clicked link={!r} codes={}".format(link.get("name"), codes))
        if not codes:
            log_warning("Import clicked with no codes selected")
            forms.alert("Select at least one status code to import.", title="Void Status")
            return

        try:
            with revit.Transaction(
                "Void Status: Sync approvals from {}".format(link["name"]),
                self._doc,
            ):
                result = synchronize_from_link(
                    self._doc, link, self._config, codes, self._separator
                )
        except Exception as ex:
            log_exception("Sync failed", ex)
            logger.error("Sync failed: {}".format(ex))
            forms.alert("Sync failed:\n{}".format(ex), title="Void Status")
            return

        log_info(
            "Sync UI result updated={} unchanged={} unmatched={} skipped={}".format(
                result["updated"],
                result["unchanged"],
                result["unmatched"],
                result["skipped"],
            )
        )

        self.statusText.Text = (
            "Imported {}: {} updated, {} already in sync, {} unmatched, {} skipped.".format(
                ", ".join(result["selected"]),
                result["updated"],
                result["unchanged"],
                result["unmatched"],
                result["skipped"],
            )
        )
        if self._fixed_link:
            self.Close()

    def close_click(self, sender, args):
        self.Close()


def show_sync_window(doc, fixed_link=None):
    """Open the Sync dialog. Returns after the window is closed."""
    if doc is None:
        log_warning("Sync aborted: no document")
        forms.alert("Open a project before synchronizing Void Status.", title="Void Status")
        return
    try:
        parse_config_xml(load_config_xml(doc))
    except ValueError as ex:
        log_exception("Sync aborted: invalid project XML", ex)
        forms.alert(
            "Project Void Status XML is invalid.\nOpen Config and fix it.\n\n{}".format(ex),
            title="Void Status",
        )
        return
    try:
        SyncApprovalsWindow(doc, fixed_link=fixed_link).ShowDialog()
    except IOError as ex:
        log_exception("Sync could not load XAML", ex)
        forms.alert(str(ex), title="Void Status")
