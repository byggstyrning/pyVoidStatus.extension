# -*- coding: utf-8 -*-
"""Path helpers for the Void Status extension."""

import os
import os.path as op

from void_status.logutil import log_debug, log_info, log_warning


def find_extension_dir(start_path):
    """Walk parents until a folder ending with ``.extension`` is found."""
    current = op.abspath(start_path)
    if op.isfile(current):
        current = op.dirname(current)
    while current:
        if current.lower().endswith(".extension"):
            return current
        parent = op.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def shared_parameter_file(start_path):
    """Return the bundled shared-parameter file path."""
    ext_dir = find_extension_dir(start_path)
    if not ext_dir:
        return None
    return op.join(ext_dir, "shared_params", "VoidStatus.txt")


def _cache_dir():
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    path = op.join(root, "VoidStatus", "cache")
    if not op.isdir(path):
        os.makedirs(path)
    return path


def _read_bytes(path):
    handle = open(path, "rb")
    try:
        return handle.read()
    finally:
        handle.close()


def _pin_onedrive(path):
    """Ask OneDrive to keep the file on this device, then retry a read."""
    try:
        import subprocess
        subprocess.call(["attrib", "+P", "-U", path])
        log_debug("Pinned OneDrive file {}".format(path))
    except Exception as ex:
        log_debug("Could not pin OneDrive file: {}".format(ex))


def local_bundle_file(src_path):
    """Copy a bundle file to a local cache so WPF can read it.

    OneDrive Files On-Demand often leaves ``.xaml`` as a cloud placeholder.
    XmlReader then fails with 'The cloud operation is invalid' (errno 380).
    A sequential read into ``%LOCALAPPDATA%\\VoidStatus\\cache`` hydrates it.
    """
    if not src_path:
        raise IOError("Missing bundle file path.")
    src_path = op.abspath(src_path)
    dest = op.join(_cache_dir(), op.basename(src_path))

    data = None
    last_error = None
    for attempt, pin_first in ((1, False), (2, True)):
        try:
            if pin_first:
                _pin_onedrive(src_path)
            data = _read_bytes(src_path)
            if data:
                break
            last_error = IOError("File is empty: {}".format(src_path))
        except Exception as ex:
            last_error = ex
            log_warning(
                "Could not read bundle file (attempt {}): {}".format(attempt, ex)
            )
            data = None

    if not data:
        raise IOError(
            "OneDrive has not downloaded this file yet:\n{}\n\n"
            "Right-click the folder 'pyRevit Extensions' → "
            "Always keep on this device.\n"
            "Wait for the green tick, then try again.\n\n"
            "({} )".format(src_path, last_error)
        )

    out = open(dest, "wb")
    try:
        out.write(data)
    finally:
        out.close()
    log_info("Cached bundle file {} ({} bytes)".format(dest, len(data)))
    return dest
