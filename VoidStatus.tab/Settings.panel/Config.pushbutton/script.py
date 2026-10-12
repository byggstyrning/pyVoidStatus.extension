# -*- coding: utf-8 -*-
"""Void Status profile and project configuration."""

from __future__ import print_function

__title__ = "Config"
__author__ = "Byggstyrning AB"
__doc__ = "Set your discipline for this model and edit shared project settings."

import os.path as op

from void_status.settings_ui import show_settings

show_settings(op.join(op.dirname(__file__), "SettingsWindow.xaml"))
