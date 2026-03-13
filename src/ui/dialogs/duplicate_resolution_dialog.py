"""Duplicate Resolution Dialog for SteamKM2.

Provides a simple UI for handling duplicate game keys during import.
Shows a list of games with their titles and keys, with options to
keep existing or overwrite all duplicates.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QWidget
)
from PySide6.QtCore import Qt

from src.ui.widgets.section_groupbox import SectionGroupBox
from src.ui.ui_factory import UIFactory


class DuplicateResolutionDialog(QDialog):
    """Dialog for resolving duplicate game keys during import."""
    
    def __init__(self, parent, duplicates: list[tuple[dict, dict]], settings_manager=None):
        """Initialize the duplicate resolution dialog.
        
        Args:
            parent: Parent widget
            duplicates: List of (existing_game, new_game) tuples
            settings_manager: Optional settings manager for theming
        """
        super().__init__(parent)
        self.duplicates = duplicates
        self.settings_manager = settings_manager or (parent.settings_manager if hasattr(parent, 'settings_manager') else None)
        
        # Default: skip all duplicates (keep existing)
        self._skip_all = True
        
        self.setWindowTitle("Duplicate Games Found")
        self.setMinimumWidth(550)
        self.setMinimumHeight(350)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Title and info
        title = QLabel(f"{len(self.duplicates)} Duplicate Game(s) Found")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        info = QLabel(
            "The following games already exist in your database. "
            "Choose whether to keep the existing entries or overwrite them with the new data."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: gray; margin-bottom: 8px;")
        layout.addWidget(info)
        
        # Action buttons at top
        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        
        self.keep_btn = QPushButton("Keep Existing")
        self.keep_btn.setToolTip("Keep all existing games, skip importing duplicates")
        self.keep_btn.clicked.connect(self._on_keep_existing)
        self.keep_btn.setMinimumHeight(32)
        button_row.addWidget(self.keep_btn)
        
        self.overwrite_btn = QPushButton("Overwrite All")
        self.overwrite_btn.setToolTip("Replace all existing games with the new data")
        self.overwrite_btn.clicked.connect(self._on_overwrite_all)
        self.overwrite_btn.setMinimumHeight(32)
        button_row.addWidget(self.overwrite_btn)
        
        button_row.addStretch()
        layout.addLayout(button_row)
        
        # Duplicates list
        list_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager,
            title="Duplicates"
        ) if self.settings_manager else SectionGroupBox(title="Duplicates")
        
        self.duplicates_list = QListWidget()
        self.duplicates_list.setAlternatingRowColors(True)
        self.duplicates_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.duplicates_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        # Populate the list with "Title - Key" format
        for existing, new in self.duplicates:
            title = new.get('title', existing.get('title', 'Unknown'))
            key = new.get('key', existing.get('key', ''))
            
            item_text = f"{title} - {key}"
            item = QListWidgetItem(item_text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.duplicates_list.addItem(item)
        
        list_group.content_layout.addWidget(self.duplicates_list)
        layout.addWidget(list_group, 1)  # Stretch factor 1 to expand
        
        # Bottom cancel button
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(cancel_btn)
        
        layout.addLayout(bottom_row)
    
    def _on_keep_existing(self):
        """Handle Keep Existing button - skip all duplicates."""
        self._skip_all = True
        self.accept()
    
    def _on_overwrite_all(self):
        """Handle Overwrite All button - overwrite all duplicates."""
        self._skip_all = False
        self.accept()
    
    def get_games_to_skip(self) -> set[str]:
        """Get set of game keys to skip (keep existing).
        
        Returns:
            Set of game keys that should be skipped during import
        """
        if self._skip_all:
            return {new.get('key', '') for _, new in self.duplicates if new.get('key')}
        return set()
    
    def get_games_to_overwrite(self) -> set[str]:
        """Get set of game keys to overwrite.
        
        Returns:
            Set of game keys that should overwrite existing entries
        """
        if not self._skip_all:
            return {new.get('key', '') for _, new in self.duplicates if new.get('key')}
        return set()
