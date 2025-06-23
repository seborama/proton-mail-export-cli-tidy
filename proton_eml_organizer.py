#!/usr/bin/env python3
"""
Proton Mail EML Organizer

This script organizes EML files exported from Proton Mail Export Tool
into folders based on the labels.json mapping file.

Usage:
    python organize_emails.py [export_directory]

If no directory is specified, it uses the current directory.
"""

import json
import logging
import os
import shutil
import sys
import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


# Constants
LABEL_TYPE_TAG = 1
LABEL_TYPE_FOLDER = 3
PROGRESS_REPORT_INTERVAL = 1000
ORGANIZED_DIR_NAME = "organized_emails"
LABELS_FILE_NAME = "labels.json"


def sanitize_folder_name(name: str) -> str:
    """
    Sanitize folder name by removing/replacing invalid characters
    """
    # Replace common problematic characters
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Remove leading/trailing spaces and dots
    name = name.strip('. ')
    # Handle empty names
    if not name:
        name = "Unknown"
    return name


def load_labels_mapping(export_dir: Path, debug: bool = False) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Load the labels.json file and create ID -> (name, type) mapping
    """
    labels_file = export_dir / LABELS_FILE_NAME
    
    if not labels_file.exists():
        logging.error(f"labels.json not found in {export_dir}")
        return None
    
    try:
        with open(labels_file, 'r', encoding='utf-8') as f:
            labels_data = json.load(f)
        
        # Create mapping from ID to (name, type)
        mapping = {}
        
        # Handle the actual Proton Mail structure: {"Version": 1, "Payload": [...]}
        if 'Payload' in labels_data and isinstance(labels_data['Payload'], list):
            for label in labels_data['Payload']:
                if 'ID' in label and 'Name' in label and 'Type' in label:
                    mapping[label['ID']] = {
                        'name': sanitize_folder_name(label['Name']),
                        'type': label['Type']
                    }
                else:
                    logging.warning(f"Incomplete label entry found: {label}")
        else:
            logging.error("Unexpected labels.json structure")
            logging.error(f"Expected 'Payload' array, got: {list(labels_data.keys())}")
            return None
        
        if not mapping:
            logging.error("No valid label mappings found in labels.json")
            return None
        
        logging.info(f"Loaded {len(mapping)} label mappings")
        folders = [k for k, v in mapping.items() if v['type'] == LABEL_TYPE_FOLDER]
        tags = [k for k, v in mapping.items() if v['type'] == LABEL_TYPE_TAG]
        logging.info(f"  Folders (Type {LABEL_TYPE_FOLDER}): {len(folders)}")
        logging.info(f"  Tags (Type {LABEL_TYPE_TAG}): {len(tags)}")
        
        if debug:
            logging.debug("\nDetailed label mappings:")
            for label_id, info in mapping.items():
                is_system = is_system_folder(label_id)
                type_name = "folder" if info['type'] == LABEL_TYPE_FOLDER else "tag" if info['type'] == LABEL_TYPE_TAG else f"type_{info['type']}"
                system_name = "system" if is_system else "user-created"
                logging.debug(f"  {label_id} -> {info['name']} ({type_name}, {system_name})")
        
        return mapping
        
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing labels.json: {e}")
        return None
    except FileNotFoundError:
        logging.error(f"labels.json not found in {export_dir}")
        return None
    except PermissionError:
        logging.error(f"Permission denied reading labels.json in {export_dir}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error loading labels.json: {e}")
        return None


def is_system_folder(label_id: str) -> bool:
    """
    Determine if a label ID is a system folder (numeric) or user-created (complex string)
    """
    return label_id.isdigit()


def _extract_label_ids_from_email(email_data: Dict[str, Any]) -> Optional[List[Any]]:
    """Extract label IDs from email JSON data."""
    if 'Payload' in email_data and 'LabelIDs' in email_data['Payload']:
        return email_data['Payload']['LabelIDs']
    elif 'LabelIDs' in email_data:
        return email_data['LabelIDs']
    return None


def _categorize_labels(label_ids: List[Any], labels_mapping: Dict[str, Dict[str, Any]], debug: bool = False, json_file: Optional[Path] = None) -> Tuple[List[str], List[str], List[str], List[str], List[str]]:
    """Categorize labels into user/system folders and tags."""
    user_folders = []     # Type 3, complex ID
    system_folders = []   # Type 3, numeric ID
    user_tags = []        # Type 1, complex ID  
    system_tags = []      # Type 1, numeric ID
    unknown = []          # Unknown/other types
    
    for label_id in label_ids:
        label_id_str = str(label_id)
        if label_id_str in labels_mapping:
            label_info = labels_mapping[label_id_str]
            is_system = is_system_folder(label_id_str)
            
            if label_info['type'] == LABEL_TYPE_FOLDER:  # Folder
                if is_system:
                    system_folders.append(label_info['name'])
                else:
                    user_folders.append(label_info['name'])
            elif label_info['type'] == LABEL_TYPE_TAG:  # Tag
                if is_system:
                    system_tags.append(label_info['name'])
                else:
                    user_tags.append(label_info['name'])
            else:
                unknown.append(f"{label_info['name']}_type{label_info['type']}")
        else:
            if debug and json_file:
                logging.warning(f"Unknown label ID {label_id} in {json_file.name}")
            unknown.append(f"Unknown_Label_{label_id}")
    
    return user_folders, system_folders, user_tags, system_tags, unknown


def _select_target_folder(user_folders: List[str], system_folders: List[str], user_tags: List[str], system_tags: List[str], unknown: List[str], debug: bool = False, json_file: Optional[Path] = None) -> str:
    """Select the target folder based on priority rules."""
    # Priority 1: User-created folders
    if user_folders:
        chosen = user_folders[0]  # Take first if multiple
        if len(user_folders) > 1 and debug and json_file:
            logging.debug(f"{json_file.name} has multiple user folders {user_folders}, choosing '{chosen}'")
        return chosen
        
    # Priority 2: System folders
    elif system_folders:
        chosen = system_folders[0]  # Take first if multiple
        if len(system_folders) > 1 and debug and json_file:
            logging.debug(f"{json_file.name} has multiple system folders {system_folders}, choosing '{chosen}'")
        return chosen
        
    # Priority 3: Tags as fallback
    elif user_tags or system_tags:
        all_tags = user_tags + system_tags
        chosen = all_tags[0]
        # Only log if it's not the common "All Mail" tag
        if chosen != "All Mail" and json_file:
            logging.warning(f"UNUSUAL: {json_file.name} has no folders, falling back to tag '{chosen}' (all tags: {all_tags})")
        return chosen
        
    # Unknown types
    elif unknown:
        return unknown[0]
    else:
        # Nothing useful found
        return 'Unlabeled'


def get_email_labels(json_file: Path, labels_mapping: Dict[str, Dict[str, Any]], debug: bool = False) -> List[str]:
    """
    Extract label IDs from an email JSON file and return single folder name
    Priority: User folders > System folders > Tags
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            email_data = json.load(f)
        
        label_ids = _extract_label_ids_from_email(email_data)
        if not label_ids:
            return ['Unlabeled']
        
        user_folders, system_folders, user_tags, system_tags, unknown = _categorize_labels(
            label_ids, labels_mapping, debug, json_file
        )
        
        target_folder = _select_target_folder(
            user_folders, system_folders, user_tags, system_tags, unknown, debug, json_file
        )
        
        return [target_folder]
        
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing {json_file}: {e}")
        return ['Invalid_JSON']
    except Exception as e:
        logging.error(f"Error processing {json_file}: {e}")
        return ['Error']


def _validate_export_directory(export_path: Path) -> bool:
    """Validate that the export directory exists and is accessible."""
    if not export_path.exists():
        logging.error(f"Directory {export_path} does not exist")
        return False
    return True


def _setup_output_directory(export_path: Path, dry_run: bool = False) -> Optional[Path]:
    """Create and validate the organized output directory."""
    organized_dir = export_path / ORGANIZED_DIR_NAME
    if organized_dir.exists() and not dry_run:
        logging.error(f"Output directory '{organized_dir}' already exists!")
        logging.error("Please remove or rename the existing directory before running the script.")
        logging.error("This prevents accidental duplicates of previously organized emails.")
        return None
    
    if dry_run:
        logging.info(f"[DRY RUN] Would create output directory: {organized_dir}")
        return organized_dir
    
    try:
        organized_dir.mkdir()
        return organized_dir
    except Exception as e:
        logging.error(f"Failed to create output directory {organized_dir}: {e}")
        return None


def _find_metadata_files(export_path: Path) -> List[Path]:
    """Find all metadata JSON files in the export directory."""
    metadata_files = list(export_path.glob("*.metadata.json"))
    if not metadata_files:
        logging.error("No email metadata files found (*.metadata.json)")
    return metadata_files


def _get_corresponding_eml_file(metadata_file: Path) -> Path:
    """Get the corresponding EML file for a metadata file."""
    base_name = metadata_file.name.replace('.metadata.json', '')
    return metadata_file.parent / f"{base_name}.eml"


def _generate_unique_filename(target_dir: Path, eml_file: Path) -> Path:
    """Generate a unique filename if the target file already exists."""
    target_eml = target_dir / eml_file.name
    counter = 1
    while target_eml.exists():
        stem = eml_file.stem
        target_eml = target_dir / f"{stem}_{counter}.eml"
        counter += 1
    return target_eml


def _copy_email_file(eml_file: Path, target_eml: Path, target_folder: str, debug: bool, dry_run: bool = False) -> bool:
    """Copy an email file to its target location."""
    if dry_run:
        if debug:
            logging.debug(f"[DRY RUN] Would copy {eml_file.name} -> {target_folder}/{target_eml.name}")
        return True
    
    try:
        shutil.copy2(eml_file, target_eml)
        if debug:
            logging.debug(f"Copied {eml_file.name} -> {target_folder}/{target_eml.name}")
        return True
    except Exception as e:
        logging.error(f"Error copying {eml_file.name} to {target_folder}: {e}")
        return False


def _print_folder_summary(organized_dir: Path, dry_run: bool = False, metadata_files: List[Path] = None, labels_mapping: Dict[str, Dict[str, Any]] = None, debug: bool = False) -> None:
    """Print a summary of created folders and email counts."""
    if dry_run and metadata_files and labels_mapping:
        # Simulate folder structure for dry run
        folder_counts = {}
        for metadata_file in metadata_files:
            eml_file = _get_corresponding_eml_file(metadata_file)
            if eml_file.exists():
                target_folders = get_email_labels(metadata_file, labels_mapping, debug)
                target_folder = target_folders[0]
                folder_counts[target_folder] = folder_counts.get(target_folder, 0) + 1
        
        print(f"\nWould create {len(folder_counts)} folders:")
        for folder_name in sorted(folder_counts.keys()):
            email_count = folder_counts[folder_name]
            print(f"  {folder_name}: {email_count} emails")
    else:
        # Normal mode - read actual directories
        folders = [d for d in organized_dir.iterdir() if d.is_dir()]
        print(f"\nCreated {len(folders)} folders:")
        for folder in sorted(folders):
            email_count = len(list(folder.glob("*.eml")))
            print(f"  {folder.name}: {email_count} emails")


def organize_emails(export_dir: str, debug: bool = False, dry_run: bool = False) -> bool:
    """
    Main function to organize emails into folders
    """
    export_path = Path(export_dir)
    
    # Validation phase
    if not _validate_export_directory(export_path):
        return False
    
    # Load labels mapping
    labels_mapping = load_labels_mapping(export_path, debug)
    if not labels_mapping:
        return False
    
    # Setup output directory
    organized_dir = _setup_output_directory(export_path, dry_run)
    if not organized_dir:
        return False
    
    # Find metadata files
    metadata_files = _find_metadata_files(export_path)
    if not metadata_files:
        return False
    
    mode_text = "[DRY RUN] Analyzing" if dry_run else "Processing"
    print(f"\n{mode_text} {len(metadata_files)} email files...")
    
    processed = 0
    errors = 0
    
    for metadata_file in metadata_files:
        # Get corresponding EML file
        eml_file = _get_corresponding_eml_file(metadata_file)
        
        if not eml_file.exists():
            if debug:
                logging.warning(f"EML file not found for {metadata_file.name} (looking for {eml_file.name})")
            errors += 1
            continue
        
        # Get the single target folder for this email
        target_folders = get_email_labels(metadata_file, labels_mapping, debug)
        target_folder = target_folders[0]  # Always exactly one folder now
        
        # Create target directory
        target_dir = organized_dir / target_folder
        if not dry_run:
            target_dir.mkdir(exist_ok=True)
        elif debug:
            logging.debug(f"[DRY RUN] Would create directory: {target_dir}")
        
        # Generate unique filename if needed
        target_eml = _generate_unique_filename(target_dir, eml_file)
        
        # Copy the file
        if _copy_email_file(eml_file, target_eml, target_folder, debug, dry_run):
            processed += 1
        else:
            errors += 1
            continue
        
        # Show progress every N files (unless in debug mode)
        if not debug and processed % PROGRESS_REPORT_INTERVAL == 0:
            print(f"  Processed {processed}/{len(metadata_files)} emails...")
    
    completion_text = "Analysis completed!" if dry_run else "Completed!"
    action_text = "Would process" if dry_run else "Processed"
    location_text = "Would organize emails in:" if dry_run else "Organized emails are in:"
    
    print(f"\n{completion_text} {action_text} {processed} emails with {errors} errors")
    print(f"{location_text} {organized_dir}")
    
    _print_folder_summary(organized_dir, dry_run, metadata_files, labels_mapping, debug)
    
    return True


def _setup_logging(debug: bool) -> None:
    """Configure logging based on debug mode."""
    level = logging.DEBUG if debug else logging.INFO
    format_str = '%(asctime)s - %(levelname)s - %(message)s' if debug else '%(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def main() -> None:
    """
    Main entry point with argument parsing
    """
    parser = argparse.ArgumentParser(
        description="Organize Proton Mail exported EML files into folders based on labels.json mapping",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python organize_emails.py .                 # Organize emails in current directory
  python organize_emails.py /path/to/export   # Organize emails in specified directory
  python organize_emails.py . --debug         # Run with detailed logging
  
Priority order for folder selection:
  1. User-created folders (complex ID, Type 3)
  2. System folders (numeric ID, Type 3) 
  3. Tags as fallback (Type 1) - unusual case

The script creates an 'organized_emails' directory with your emails sorted into 
the appropriate folder structure, with each email appearing in exactly one folder.
        """.strip()
    )
    
    parser.add_argument(
        'export_dir', 
        help='Directory containing Proton Mail export files'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable detailed logging including file copy operations and decision details'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview the organization without actually copying files'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    _setup_logging(args.debug)
    
    logging.info(f"Organizing Proton Mail export in: {os.path.abspath(args.export_dir)}")
    if args.debug:
        logging.info("Debug mode enabled - detailed logging active")
    if args.dry_run:
        logging.info("Dry run mode enabled - no files will be copied")
    
    try:
        success = organize_emails(args.export_dir, args.debug, args.dry_run)
        
        if success:
            print("\n✅ Email organization completed successfully!")
        else:
            print("\n❌ Email organization failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        logging.error("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        if args.debug:
            logging.exception("Full traceback:")
        sys.exit(1)


if __name__ == "__main__":
    main()