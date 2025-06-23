#!/usr/bin/env python3
"""
Unit tests for proton_eml_organizer.py

Test coverage for core logic components including:
- Label categorization and priority selection
- Email metadata parsing
- File path utilities
- Folder name sanitization
"""

import unittest
import tempfile
import json
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch, mock_open

from proton_eml_organizer import (
    sanitize_folder_name,
    is_system_folder,
    _extract_label_ids_from_email,
    _categorize_labels,
    _select_target_folder,
    _get_corresponding_eml_file,
    _generate_unique_filename,
    load_labels_mapping,
    LABEL_TYPE_TAG,
    LABEL_TYPE_FOLDER
)


class TestSanitizeFolderName(unittest.TestCase):
    """Test folder name sanitization."""
    
    def test_valid_folder_names(self):
        """Test that valid folder names are unchanged."""
        self.assertEqual(sanitize_folder_name("Inbox"), "Inbox")
        self.assertEqual(sanitize_folder_name("My Documents"), "My Documents")
        self.assertEqual(sanitize_folder_name("2023_Archive"), "2023_Archive")
    
    def test_invalid_characters_replaced(self):
        """Test that invalid characters are replaced with underscores."""
        self.assertEqual(sanitize_folder_name("My<Files>"), "My_Files_")
        self.assertEqual(sanitize_folder_name("Test:Folder"), "Test_Folder")
        self.assertEqual(sanitize_folder_name('File"With"Quotes'), "File_With_Quotes")
        self.assertEqual(sanitize_folder_name("Path\\With\\Backslashes"), "Path_With_Backslashes")
    
    def test_whitespace_handling(self):
        """Test handling of leading/trailing whitespace and dots."""
        self.assertEqual(sanitize_folder_name("  Folder  "), "Folder")
        self.assertEqual(sanitize_folder_name("..Hidden.."), "Hidden")
        self.assertEqual(sanitize_folder_name(" . Mixed . "), "Mixed")
    
    def test_empty_names(self):
        """Test handling of empty or whitespace-only names."""
        self.assertEqual(sanitize_folder_name(""), "Unknown")
        self.assertEqual(sanitize_folder_name("   "), "Unknown")
        self.assertEqual(sanitize_folder_name("..."), "Unknown")


class TestIsSystemFolder(unittest.TestCase):
    """Test system folder identification."""
    
    def test_numeric_ids_are_system(self):
        """Test that numeric IDs are identified as system folders."""
        self.assertTrue(is_system_folder("1"))
        self.assertTrue(is_system_folder("123"))
        self.assertTrue(is_system_folder("0"))
    
    def test_complex_ids_are_user_created(self):
        """Test that complex IDs are identified as user-created."""
        self.assertFalse(is_system_folder("abc123"))
        self.assertFalse(is_system_folder("user_folder_id"))
        self.assertFalse(is_system_folder("aBc123DeF"))
        self.assertFalse(is_system_folder(""))


class TestExtractLabelIdsFromEmail(unittest.TestCase):
    """Test email label ID extraction."""
    
    def test_extract_from_payload(self):
        """Test extraction from Payload structure."""
        email_data = {
            "Payload": {
                "LabelIDs": ["1", "2", "user_folder_123"]
            }
        }
        result = _extract_label_ids_from_email(email_data)
        self.assertEqual(result, ["1", "2", "user_folder_123"])
    
    def test_extract_from_root(self):
        """Test extraction from root level."""
        email_data = {
            "LabelIDs": ["3", "4", "another_label"]
        }
        result = _extract_label_ids_from_email(email_data)
        self.assertEqual(result, ["3", "4", "another_label"])
    
    def test_no_label_ids(self):
        """Test handling when no LabelIDs present."""
        email_data = {"SomeOtherField": "value"}
        result = _extract_label_ids_from_email(email_data)
        self.assertIsNone(result)
    
    def test_empty_label_ids(self):
        """Test handling of empty LabelIDs array."""
        email_data = {"Payload": {"LabelIDs": []}}
        result = _extract_label_ids_from_email(email_data)
        self.assertEqual(result, [])


class TestCategorizeLabels(unittest.TestCase):
    """Test label categorization logic."""
    
    def setUp(self):
        """Set up test labels mapping."""
        self.labels_mapping = {
            "1": {"name": "Inbox", "type": LABEL_TYPE_FOLDER},           # System folder
            "2": {"name": "Sent", "type": LABEL_TYPE_FOLDER},            # System folder
            "3": {"name": "All Mail", "type": LABEL_TYPE_TAG},           # System tag
            "user123": {"name": "Personal", "type": LABEL_TYPE_FOLDER},  # User folder
            "user456": {"name": "Work", "type": LABEL_TYPE_FOLDER},      # User folder
            "tag789": {"name": "Important", "type": LABEL_TYPE_TAG},     # User tag
        }
    
    def test_categorize_mixed_labels(self):
        """Test categorization of mixed label types."""
        label_ids = ["1", "user123", "3", "tag789"]
        
        user_folders, system_folders, user_tags, system_tags, unknown = _categorize_labels(
            label_ids, self.labels_mapping
        )
        
        self.assertEqual(user_folders, ["Personal"])
        self.assertEqual(system_folders, ["Inbox"])
        self.assertEqual(user_tags, ["Important"])
        self.assertEqual(system_tags, ["All Mail"])
        self.assertEqual(unknown, [])
    
    def test_unknown_labels(self):
        """Test handling of unknown label IDs."""
        label_ids = ["1", "unknown_label", "999"]
        
        user_folders, system_folders, user_tags, system_tags, unknown = _categorize_labels(
            label_ids, self.labels_mapping
        )
        
        self.assertEqual(system_folders, ["Inbox"])
        self.assertEqual(len(unknown), 2)
        self.assertIn("Unknown_Label_unknown_label", unknown)
        self.assertIn("Unknown_Label_999", unknown)
    
    def test_empty_label_ids(self):
        """Test handling of empty label IDs list."""
        user_folders, system_folders, user_tags, system_tags, unknown = _categorize_labels(
            [], self.labels_mapping
        )
        
        self.assertEqual(user_folders, [])
        self.assertEqual(system_folders, [])
        self.assertEqual(user_tags, [])
        self.assertEqual(system_tags, [])
        self.assertEqual(unknown, [])


class TestSelectTargetFolder(unittest.TestCase):
    """Test target folder selection logic."""
    
    def test_priority_user_folders_first(self):
        """Test that user folders have highest priority."""
        result = _select_target_folder(
            user_folders=["Personal", "Work"],
            system_folders=["Inbox", "Sent"],
            user_tags=["Important"],
            system_tags=["All Mail"],
            unknown=[]
        )
        self.assertEqual(result, "Personal")  # First user folder
    
    def test_priority_system_folders_second(self):
        """Test that system folders have second priority."""
        result = _select_target_folder(
            user_folders=[],
            system_folders=["Inbox", "Sent"],
            user_tags=["Important"],
            system_tags=["All Mail"],
            unknown=[]
        )
        self.assertEqual(result, "Inbox")  # First system folder
    
    def test_priority_tags_third(self):
        """Test that tags are used as fallback."""
        result = _select_target_folder(
            user_folders=[],
            system_folders=[],
            user_tags=["Important"],
            system_tags=["All Mail"],
            unknown=[]
        )
        self.assertEqual(result, "Important")  # First available tag
    
    def test_priority_unknown_fourth(self):
        """Test that unknown types are used when nothing else available."""
        result = _select_target_folder(
            user_folders=[],
            system_folders=[],
            user_tags=[],
            system_tags=[],
            unknown=["Unknown_Label_123"]
        )
        self.assertEqual(result, "Unknown_Label_123")
    
    def test_unlabeled_fallback(self):
        """Test fallback to 'Unlabeled' when nothing is available."""
        result = _select_target_folder(
            user_folders=[],
            system_folders=[],
            user_tags=[],
            system_tags=[],
            unknown=[]
        )
        self.assertEqual(result, "Unlabeled")


class TestFileUtilities(unittest.TestCase):
    """Test file-related utility functions."""
    
    def test_get_corresponding_eml_file(self):
        """Test EML file name generation from metadata file."""
        metadata_file = Path("/test/email123.metadata.json")
        result = _get_corresponding_eml_file(metadata_file)
        expected = Path("/test/email123.eml")
        self.assertEqual(result, expected)
    
    def test_generate_unique_filename_no_conflict(self):
        """Test unique filename generation when no conflict exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            eml_file = Path("test.eml")
            
            result = _generate_unique_filename(target_dir, eml_file)
            expected = target_dir / "test.eml"
            self.assertEqual(result, expected)
    
    def test_generate_unique_filename_with_conflict(self):
        """Test unique filename generation when conflicts exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            eml_file = Path("test.eml")
            
            # Create conflicting files
            (target_dir / "test.eml").touch()
            (target_dir / "test_1.eml").touch()
            
            result = _generate_unique_filename(target_dir, eml_file)
            expected = target_dir / "test_2.eml"
            self.assertEqual(result, expected)


class TestLoadLabelsMapping(unittest.TestCase):
    """Test labels mapping loading functionality."""
    
    def test_load_valid_labels_json(self):
        """Test loading valid labels.json structure."""
        labels_data = {
            "Version": 1,
            "Payload": [
                {"ID": "1", "Name": "Inbox", "Type": 3},
                {"ID": "2", "Name": "Sent", "Type": 3},
                {"ID": "tag1", "Name": "Important", "Type": 1}
            ]
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)
            labels_file = export_dir / "labels.json"
            
            with open(labels_file, 'w') as f:
                json.dump(labels_data, f)
            
            result = load_labels_mapping(export_dir)
            
            self.assertIsNotNone(result)
            self.assertEqual(len(result), 3)
            self.assertEqual(result["1"]["name"], "Inbox")
            self.assertEqual(result["1"]["type"], 3)
            self.assertEqual(result["tag1"]["name"], "Important")
            self.assertEqual(result["tag1"]["type"], 1)
    
    def test_load_labels_json_missing_file(self):
        """Test handling when labels.json is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)
            result = load_labels_mapping(export_dir)
            self.assertIsNone(result)
    
    def test_load_labels_json_invalid_structure(self):
        """Test handling of invalid JSON structure."""
        invalid_data = {"WrongStructure": "data"}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)
            labels_file = export_dir / "labels.json"
            
            with open(labels_file, 'w') as f:
                json.dump(invalid_data, f)
            
            result = load_labels_mapping(export_dir)
            self.assertIsNone(result)
    
    def test_load_labels_json_incomplete_entries(self):
        """Test handling of incomplete label entries."""
        labels_data = {
            "Version": 1,
            "Payload": [
                {"ID": "1", "Name": "Inbox", "Type": 3},
                {"ID": "2", "Name": "Incomplete"},  # Missing Type
                {"Name": "No ID", "Type": 1},       # Missing ID
                {"ID": "3", "Name": "Valid", "Type": 1}
            ]
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)
            labels_file = export_dir / "labels.json"
            
            with open(labels_file, 'w') as f:
                json.dump(labels_data, f)
            
            result = load_labels_mapping(export_dir)
            
            # Should only include valid entries
            self.assertIsNotNone(result)
            self.assertEqual(len(result), 2)  # Only "1" and "3" are valid
            self.assertIn("1", result)
            self.assertIn("3", result)
            self.assertNotIn("2", result)


if __name__ == '__main__':
    # Configure logging to suppress output during tests
    import logging
    logging.disable(logging.CRITICAL)
    
    # Run the tests
    unittest.main(verbosity=2)