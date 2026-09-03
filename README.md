# Void Status
<img width="141" height="103" alt="image" src="https://github.com/user-attachments/assets/cc1f8eb9-24b8-4bc3-94a2-0f408485947c" /><img width="88" height="95" alt="image" src="https://github.com/user-attachments/assets/d889ba38-6214-42b8-bebb-06871bf75f03" />

pyRevit extension for void approval. Select openings and stamp **Approved by**, **Pending by**, or **Rejected by** with your discipline. There is no extra ribbon tab: settings live on **Add-Ins**, and the status buttons are copied onto **Modify** when something is selected (same idea as MMI).


## Ribbon

| Where | Tools |
| --- | --- |
| **Add-Ins → Void Status** | **Config** — your profile and project settings. **Reset** (split) — clear status fields. **Sync** — merge statuses from a linked model. |
| **Modify → Void Status** | **Approve**, **Pending**, **Reject** — shown when openings are selected |

## Setup

1. Copy `pyVoidStatus.extension` into your pyRevit extensions folder, or add this repo as an extension path.
2. Reload pyRevit (or restart Revit). If the extension lives on OneDrive/SharePoint, right-click **pyRevit Extensions** → **Always keep on this device** so `.xaml` files are actually downloaded.
3. Open a project → **Add-Ins** → **Void Status** → **Config**.
4. Set **Name** (this workstation) and **Discipline** (stored for you in this Revit file). The same person can use STR in one model and FP in another.
5. Optionally edit **this model** settings (discipline codes, bind categories). **Save** writes them into the Revit file, so colleagues share them. Import / Export under **Advanced** is only if you need to copy settings between models.
6. Click **Ensure parameters** if the shared parameters are not already in the project (existing bindings are left unchanged).

## Shared parameters

Bundled in `shared_params/VoidStatus.txt`:

| Parameter | GUID |
| --- | --- |
| Drawn by | `9651d3dd-e420-4a10-8de6-565fc0315f47` |
| Drawn Date | `240a0677-044f-4bb8-9410-486103fbe13b` |
| Drawn Status | `8e164356-e013-4548-b21b-5128466c692c` |
| Approved by | `719a943d-f1a3-4a18-9684-0f813b9d6e5a` |
| Rejected by | `b01b41a7-973e-48fd-8816-163f7a33a7a7` |
| Pending by | `962ca537-282e-42a1-b77c-c959957efb99` |
| Assigned to | `1035d1b3-baff-4446-94c5-312404c3d845` |

Approve / Pending / Reject look up parameters by GUID first, then by name, so they work on openings that already have these parameters.

## Actions

Each action writes your **discipline code** (``STR``, ``ARC``, ``ELEC``, …) into the matching parameter. Combined codes such as ``HVAC & PLBG`` are one list value. Other disciplines already on the element are left in place (multi-approved). The default separator is ``, ``.

| Button | Adds your code to | Removes only your code from |
| --- | --- | --- |
| Approve | Approved by | Pending by, Rejected by |
| Pending | Pending by | Approved by, Rejected by |
| Reject | Rejected by | Approved by, Pending by |

Drawn by / Drawn Date / Drawn Status are **not** this value list: they are the author name, a date, and the drawing state (Created, Changed, Up to Date).

## Sync from a linked model

On **Add-Ins → Void Status**, **Sync**:

1. Pick a loaded Revit or IFC link.
2. The window lists unique discipline codes found in that model’s Approved by / Rejected by / Pending by fields.
3. Choose which codes to import (your own discipline is unchecked by default).
4. **Import** merges those codes into matching openings in *this* model.

Matching compares **MatchKey** (IfcGuid of the reference element, GUID `2e9bc4c8-bf25-4700-b8ee-14294918ffa6`), **ObjectId**, and the element’s built-in IFC GUID by value across those fields. UniqueId is last. Only openings with MatchKey or ObjectId are sync candidates. Only the three status parameters are written.

Example: host opening has `STR` in Approved by, linked opening has `ARC` in Approved by, and you import `ARC` → host becomes `STR, ARC`. Other host codes are left in place. For a selected code, the linked model’s bucket wins (if the link has ARC in Rejected by, ARC moves to Rejected by here and is removed from Approved by / Pending by).


## Project XML vs profile

- **Project settings** — discipline codes, bind categories, parameter mapping, separator. Stored in the `.rvt`. Import / export `*.xml` from Config → Advanced if you need to reuse them in another model.
- **Discipline** — your code for *this* model, stored in the `.rvt` under your Revit username. Colleagues keep their own codes in the same file.
- **Name** — stored in pyRevit user config on this workstation.

Reload the extension in pyRevit after changing files under `lib/` or `startup.py`.

## Logging

Every ribbon action, XML load/save, parameter bind, status write, and Sync match is logged with the prefix `[VoidStatus]`.

1. pyRevit Settings → Reporting Levels → enable **File Debug Logging**.
2. Reload the Void Status extension (required after `lib/` or `startup.py` changes).
3. Reproduce the workflow.
4. Open `%APPDATA%/pyRevit/<RevitVersion>/pyRevit_*_runtime.log` and search for `[VoidStatus]`.

Info lines cover the workflow (who/what/before/after). Debug lines include match keys, GUID vs name lookups, and the stored project XML.
