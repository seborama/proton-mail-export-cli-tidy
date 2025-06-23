# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based utility that organizes EML files exported from Proton Mail Export Tool into structured folders based on email labels. The tool processes Proton Mail's export format and creates a single-copy organization system where each email is placed in exactly one folder based on a priority system.

## Core Architecture

The project consists of a single Python script (`proton_eml_organizer.py`) that:

1. **Label Processing**: Reads `labels.json` from Proton Mail export to build ID-to-name mappings
2. **Email Metadata Processing**: Processes `*.metadata.json` files to extract label assignments for each email
3. **Folder Prioritization**: Implements a priority system for folder selection:
   - Priority 1: User-created folders (complex ID, Type 3)
   - Priority 2: System folders (numeric ID, Type 3) 
   - Priority 3: Tags as fallback (Type 1)
4. **File Organization**: Copies corresponding `.eml` files into organized folder structure

## Key Components

- `load_labels_mapping()`: Parses Proton's labels.json structure (`{"Version": 1, "Payload": [...]}`)
- `get_email_labels()`: Extracts and prioritizes labels from email metadata
- `organize_emails()`: Main orchestration function that processes all emails
- `sanitize_folder_name()`: Handles filesystem-safe folder naming
- `is_system_folder()`: Distinguishes between system (numeric ID) and user-created (complex ID) labels

## Usage Commands

```bash
# Basic usage - organize emails in current directory
python3 proton_eml_organizer.py .

# Organize emails in specific directory
python3 proton_eml_organizer.py /path/to/proton/export

# Debug mode with detailed logging
python3 proton_eml_organizer.py /path/to/export --debug
```

## Data Structure Understanding

- **Labels.json**: Contains label definitions with ID, Name, and Type fields
- **Type 1**: Tags 
- **Type 3**: Folders
- **System labels**: Numeric IDs (e.g., "1", "2", "3")
- **User labels**: Complex string IDs (base64-like strings)
- **Email metadata**: JSON files with LabelIDs arrays referencing label mappings

## Output Structure

The script creates an `organized_emails` directory with:
- One subdirectory per email label/folder
- EML files copied (not moved) to appropriate folders  
- Duplicate filename handling with counter suffixes
- Single-copy guarantee (each email in exactly one folder)

## Error Handling

- Validates existence of required files (labels.json, *.metadata.json, *.eml)
- Prevents accidental overwrites by checking for existing organized_emails directory
- Handles missing label mappings gracefully
- Provides detailed error reporting and progress indicators