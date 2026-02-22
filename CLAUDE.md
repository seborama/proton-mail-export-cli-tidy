# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python script (`proton_eml_organizer.py`) that organizes EML files exported from Proton Mail into folders based on label assignments. Each email is placed in exactly one folder using a priority system.

## Commands

```bash
# Organize emails in an export directory
python3 proton_eml_organizer.py /path/to/proton/export

# Preview without copying files
python3 proton_eml_organizer.py /path/to/proton/export --dry-run

# Detailed logging for troubleshooting
python3 proton_eml_organizer.py /path/to/proton/export --debug

# Run all tests
python3 test_proton_eml_organizer.py -v

# Run a single test class
python3 -m unittest test_proton_eml_organizer.TestSelectTargetFolder -v
```

## Architecture

The script is structured as a pipeline: validate → load labels → setup output dir → find metadata files → process each email → copy EML.

**Public functions** (no underscore prefix) form the API:
- `load_labels_mapping()` — reads `labels.json`, returns `{label_id: {name, type}}`
- `get_email_labels()` — given a `*.metadata.json` file, returns a single-element list with the chosen folder name
- `organize_emails()` — top-level orchestration

**Private helpers** (underscore prefix) are decomposed from `organize_emails` and `get_email_labels`:
- `_extract_label_ids_from_email()` — handles two metadata structures: `{"Payload": {"LabelIDs": [...]}}` and `{"LabelIDs": [...]}`
- `_categorize_labels()` — splits label IDs into `user_folders`, `system_folders`, `user_tags`, `system_tags`, `unknown`
- `_select_target_folder()` — applies the priority order to pick one folder name

## Data Model

**`labels.json`** structure:
```json
{"Version": 1, "Payload": [{"ID": "...", "Name": "...", "Type": 1|3}]}
```
- `Type 1` = Tag, `Type 3` = Folder
- Numeric IDs (e.g. `"1"`, `"5"`) = system labels (Inbox, Sent, Trash…)
- Complex string IDs (base64-like) = user-created labels

**Folder selection priority** (highest to lowest):
1. User-created folders (complex ID, Type 3)
2. System folders (numeric ID, Type 3)
3. Tags (Type 1) — unusual fallback, logged as a warning unless "All Mail"
4. Unknown label types
5. `"Unlabeled"` — final fallback

## Output

Creates `organized_emails/` inside the export directory. The script refuses to run if this directory already exists to prevent duplicate processing. Filename collisions within a folder are resolved with `_1`, `_2`, … suffixes.
