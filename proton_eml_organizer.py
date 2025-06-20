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
import os
import shutil
import sys
import re
import argparse
from pathlib import Path


def sanitize_folder_name(name):
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


def load_labels_mapping(export_dir, debug=False):
    """
    Load the labels.json file and create ID -> (name, type) mapping
    """
    labels_file = Path(export_dir) / "labels.json"
    
    if not labels_file.exists():
        print(f"Error: labels.json not found in {export_dir}")
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
            print("Error: Unexpected labels.json structure")
            print(f"Expected 'Payload' array, got: {list(labels_data.keys())}")
            return None
        
        print(f"Loaded {len(mapping)} label mappings")
        folders = [k for k, v in mapping.items() if v['type'] == 3]
        tags = [k for k, v in mapping.items() if v['type'] == 1]
        print(f"  Folders (Type 3): {len(folders)}")
        print(f"  Tags (Type 1): {len(tags)}")
        
        if debug:
            print("\nDetailed label mappings:")
            for label_id, info in mapping.items():
                is_system = is_system_folder(label_id)
                type_name = "folder" if info['type'] == 3 else "tag" if info['type'] == 1 else f"type_{info['type']}"
                system_name = "system" if is_system else "user-created"
                print(f"  {label_id} -> {info['name']} ({type_name}, {system_name})")
        
        return mapping
        
    except json.JSONDecodeError as e:
        print(f"Error parsing labels.json: {e}")
        return None
    except Exception as e:
        print(f"Error loading labels.json: {e}")
        return None


def is_system_folder(label_id):
    """
    Determine if a label ID is a system folder (numeric) or user-created (complex string)
    """
    return label_id.isdigit()


def get_email_labels(json_file, labels_mapping, debug=False):
    """
    Extract label IDs from an email JSON file and return single folder name
    Priority: User folders > System folders > Tags
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            email_data = json.load(f)
        
        # Try different possible paths for LabelIDs
        label_ids = None
        if 'Payload' in email_data and 'LabelIDs' in email_data['Payload']:
            label_ids = email_data['Payload']['LabelIDs']
        elif 'LabelIDs' in email_data:
            label_ids = email_data['LabelIDs']
        
        if not label_ids:
            return ['Unlabeled']
        
        # Separate labels by type and system vs user-created
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
                
                if label_info['type'] == 3:  # Folder
                    if is_system:
                        system_folders.append(label_info['name'])
                    else:
                        user_folders.append(label_info['name'])
                elif label_info['type'] == 1:  # Tag
                    if is_system:
                        system_tags.append(label_info['name'])
                    else:
                        user_tags.append(label_info['name'])
                else:
                    unknown.append(f"{label_info['name']}_type{label_info['type']}")
            else:
                if debug:
                    print(f"Warning: Unknown label ID {label_id} in {json_file.name}")
                unknown.append(f"Unknown_Label_{label_id}")
        
        # Priority logic: Pick single best folder
        if user_folders:
            # Priority 1: User-created folders
            chosen = user_folders[0]  # Take first if multiple
            if len(user_folders) > 1 and debug:
                print(f"Debug: {json_file.name} has multiple user folders {user_folders}, choosing '{chosen}'")
            return [chosen]
            
        elif system_folders:
            # Priority 2: System folders
            chosen = system_folders[0]  # Take first if multiple
            if len(system_folders) > 1 and debug:
                print(f"Debug: {json_file.name} has multiple system folders {system_folders}, choosing '{chosen}'")
            return [chosen]
            
        elif user_tags or system_tags:
            # Priority 3: Tags as fallback
            all_tags = user_tags + system_tags
            chosen = all_tags[0]
            # Only log if it's not the common "All Mail" tag
            if chosen != "All Mail":
                print(f"UNUSUAL: {json_file.name} has no folders, falling back to tag '{chosen}' (all tags: {all_tags})")
            return [chosen]
            
        elif unknown:
            # Unknown types
            return [unknown[0]]
        else:
            # Nothing useful found
            return ['Unlabeled']
        
    except json.JSONDecodeError as e:
        print(f"Error parsing {json_file}: {e}")
        return ['Invalid_JSON']
    except Exception as e:
        print(f"Error processing {json_file}: {e}")
        return ['Error']


def organize_emails(export_dir, debug=False):
    """
    Main function to organize emails into folders
    """
    export_path = Path(export_dir)
    
    if not export_path.exists():
        print(f"Error: Directory {export_dir} does not exist")
        return False
    
    # Load labels mapping
    labels_mapping = load_labels_mapping(export_dir, debug)
    if not labels_mapping:
        return False
    
    # Create organized output directory
    organized_dir = export_path / "organized_emails"
    if organized_dir.exists():
        print(f"Error: Output directory '{organized_dir}' already exists!")
        print("Please remove or rename the existing directory before running the script.")
        print("This prevents accidental duplicates of previously organized emails.")
        return False
    
    organized_dir.mkdir()
    
    # Find all metadata JSON files (*.metadata.json)
    metadata_files = list(export_path.glob("*.metadata.json"))
    
    if not metadata_files:
        print("No email metadata files found (*.metadata.json)")
        return False
    
    print(f"\nProcessing {len(metadata_files)} email files...")
    
    processed = 0
    errors = 0
    
    for metadata_file in metadata_files:
        # Get corresponding EML file - remove .metadata.json and add .eml
        base_name = metadata_file.name.replace('.metadata.json', '')
        eml_file = metadata_file.parent / f"{base_name}.eml"
        
        if not eml_file.exists():
            if debug:
                print(f"Warning: EML file not found for {metadata_file.name} (looking for {eml_file.name})")
            errors += 1
            continue
        
        # Get the single target folder for this email (returns list with one item)
        target_folders = get_email_labels(metadata_file, labels_mapping, debug)
        target_folder = target_folders[0]  # Always exactly one folder now
        
        # Create target directory
        target_dir = organized_dir / target_folder
        target_dir.mkdir(exist_ok=True)
        
        # Create unique filename if file already exists
        target_eml = target_dir / eml_file.name
        counter = 1
        while target_eml.exists():
            stem = eml_file.stem
            target_eml = target_dir / f"{stem}_{counter}.eml"
            counter += 1
        
        try:
            shutil.copy2(eml_file, target_eml)
            if debug:
                print(f"Copied {eml_file.name} -> {target_folder}/{target_eml.name}")
        except Exception as e:
            print(f"Error copying {eml_file.name} to {target_folder}: {e}")
            errors += 1
            continue
        
        processed += 1
        
        # Show progress every 1000 files (unless in debug mode)
        if not debug and processed % 1000 == 0:
            print(f"  Processed {processed}/{len(metadata_files)} emails...")
    
    print(f"\nCompleted! Processed {processed} emails with {errors} errors")
    print(f"Organized emails are in: {organized_dir}")
    
    # Show folder summary
    folders = [d for d in organized_dir.iterdir() if d.is_dir()]
    print(f"\nCreated {len(folders)} folders:")
    for folder in sorted(folders):
        email_count = len(list(folder.glob("*.eml")))
        print(f"  {folder.name}: {email_count} emails")
    
    return True


def main():
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
    
    args = parser.parse_args()
    
    print(f"Organizing Proton Mail export in: {os.path.abspath(args.export_dir)}")
    if args.debug:
        print("Debug mode enabled - detailed logging active")
    
    success = organize_emails(args.export_dir, args.debug)
    
    if success:
        print("\n✅ Email organization completed successfully!")
    else:
        print("\n❌ Email organization failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()