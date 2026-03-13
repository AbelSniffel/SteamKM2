"""
Improved Badge System Demo - Showcases the simplified badge API

This demo demonstrates the new simplified badge system with:
1. One-liner badge addition with custom text
2. Automatic text width adjustment
3. Easy badge updates
4. Support for count, text, and dot badges
"""

import sys
from _bootstrap import ensure_project_root_on_path

ensure_project_root_on_path(__file__)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
    QWidget, QPushButton, QLabel, QLineEdit, QSpinBox
)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont

# Import the new simplified badge API
from src.ui.widgets.badge import Badge, BadgePosition, add_badge, get_badge
from src.ui.ui_factory import UIFactory
from src.core.theme_manager import ThemeManager
from src.core.settings_manager import SettingsManager


class ImprovedBadgeDemoWindow(QMainWindow):
    """Demo window showcasing the improved badge system"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Improved Badge System Demo")
        self.setGeometry(100, 100, 800, 600)
        
        # Initialize theme
        self.settings_manager = SettingsManager()
        self.theme_manager = ThemeManager(self.settings_manager)
        self.theme_manager.apply_theme(QApplication.instance())
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the demo UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Title
        title = QLabel("Improved Badge System Demo")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Section 1: One-liner badge addition
        layout.addWidget(QLabel("\n1. One-Liner Badge Addition:"))
        self._create_one_liner_demo(layout)
        
        # Section 2: Custom text with auto-width
        layout.addWidget(QLabel("\n2. Custom Text with Auto-Width:"))
        self._create_custom_text_demo(layout)
        
        # Section 3: Count badges
        layout.addWidget(QLabel("\n3. Count Badges:"))
        self._create_count_demo(layout)
        
        # Section 4: Dot notifications
        layout.addWidget(QLabel("\n4. Notification Dots:"))
        self._create_dot_demo(layout)
        
        # Section 5: UIFactory integration
        layout.addWidget(QLabel("\n5. UIFactory Integration:"))
        self._create_factory_demo(layout)
        
        # Section 6: Different positions
        layout.addWidget(QLabel("\n6. Badge Positions:"))
        self._create_position_demo(layout)
        
        layout.addStretch()
    
    def _create_one_liner_demo(self, parent_layout):
        """Demonstrate one-liner badge addition"""
        row = QHBoxLayout()
        
        # Create buttons with badges using one-liners
        btn1 = QPushButton("Feature 1")
        btn1.setFixedSize(100, 40)
        add_badge(btn1, text="NEW", theme_manager=self.theme_manager)
        
        btn2 = QPushButton("Feature 2")
        btn2.setFixedSize(100, 40)
        add_badge(btn2, text="BETA", theme_manager=self.theme_manager)
        
        btn3 = QPushButton("Updates")
        btn3.setFixedSize(100, 40)
        add_badge(btn3, count=5, theme_manager=self.theme_manager)
        
        row.addWidget(btn1)
        row.addWidget(btn2)
        row.addWidget(btn3)
        row.addWidget(QLabel("← Added with one-liner: add_badge(widget, text='NEW')"))
        row.addStretch()
        
        parent_layout.addLayout(row)
    
    def _create_custom_text_demo(self, parent_layout):
        """Demonstrate custom text with automatic width adjustment"""
        row = QHBoxLayout()
        
        self.custom_text_button = QPushButton("Feature")
        self.custom_text_button.setFixedSize(100, 40)
        add_badge(self.custom_text_button, text="NEW", theme_manager=self.theme_manager)
        
        text_input = QLineEdit()
        text_input.setPlaceholderText("Enter custom badge text...")
        text_input.setMaximumWidth(200)
        text_input.textChanged.connect(self._update_custom_badge_text)
        
        row.addWidget(self.custom_text_button)
        row.addWidget(QLabel("Custom text:"))
        row.addWidget(text_input)
        row.addWidget(QLabel("← Badge width auto-adjusts!"))
        row.addStretch()
        
        parent_layout.addLayout(row)
    
    def _create_count_demo(self, parent_layout):
        """Demonstrate count badges"""
        row = QHBoxLayout()
        
        self.count_button = QPushButton("Messages")
        self.count_button.setFixedSize(100, 40)
        add_badge(self.count_button, count=0, theme_manager=self.theme_manager)
        
        count_spinner = QSpinBox()
        count_spinner.setRange(0, 150)
        count_spinner.setValue(0)
        count_spinner.valueChanged.connect(self._update_count_badge)
        
        row.addWidget(self.count_button)
        row.addWidget(QLabel("Count:"))
        row.addWidget(count_spinner)
        row.addWidget(QLabel("← Shows '99+' for counts > 99"))
        row.addStretch()
        
        parent_layout.addLayout(row)
    
    def _create_dot_demo(self, parent_layout):
        """Demonstrate notification dots"""
        row = QHBoxLayout()
        
        self.dot_button = QPushButton("Notifications")
        self.dot_button.setFixedSize(120, 40)
        add_badge(self.dot_button, show_dot=False, theme_manager=self.theme_manager)
        
        show_btn = QPushButton("Show Dot")
        hide_btn = QPushButton("Hide Dot")
        
        show_btn.clicked.connect(lambda: self._set_dot_visible(True))
        hide_btn.clicked.connect(lambda: self._set_dot_visible(False))
        
        row.addWidget(self.dot_button)
        row.addWidget(show_btn)
        row.addWidget(hide_btn)
        row.addStretch()
        
        parent_layout.addLayout(row)
    
    def _create_factory_demo(self, parent_layout):
        """Demonstrate UIFactory integration"""
        row = QHBoxLayout()
        
        # Create button with badge using UIFactory
        factory_button = UIFactory.create_button_with_badge(
            parent=self,
            text="Settings",
            badge_text="NEW",
            theme_manager=self.theme_manager
        )
        factory_button.setFixedSize(100, 40)
        
        # Create another one
        factory_button2 = UIFactory.create_button_with_badge(
            parent=self,
            text="Updates",
            badge_count=3,
            theme_manager=self.theme_manager
        )
        factory_button2.setFixedSize(100, 40)
        
        row.addWidget(factory_button)
        row.addWidget(factory_button2)
        row.addWidget(QLabel("← Created with UIFactory.create_button_with_badge()"))
        row.addStretch()
        
        parent_layout.addLayout(row)
    
    def _create_position_demo(self, parent_layout):
        """Demonstrate different badge positions"""
        row = QHBoxLayout()
        
        positions = [
            (BadgePosition.TOP_LEFT, "Top Left"),
            (BadgePosition.TOP_RIGHT, "Top Right"),
            (BadgePosition.BOTTOM_LEFT, "Bottom Left"),
            (BadgePosition.BOTTOM_RIGHT, "Bottom Right"),
            (BadgePosition.CENTER_RIGHT, "Center Right")
        ]
        
        for position, label in positions:
            button = QPushButton(label)
            button.setFixedSize(100, 50)
            add_badge(button, count=1, position=position, theme_manager=self.theme_manager)
            row.addWidget(button)
        
        row.addStretch()
        parent_layout.addLayout(row)
    
    def _update_custom_badge_text(self, text):
        """Update custom badge text"""
        badge = get_badge(self.custom_text_button)
        if badge:
            badge.set_text(text if text else "")
    
    def _update_count_badge(self, count):
        """Update count badge"""
        badge = get_badge(self.count_button)
        if badge:
            badge.set_count(count)
    
    def _set_dot_visible(self, visible):
        """Set dot visibility"""
        badge = get_badge(self.dot_button)
        if badge:
            badge.set_dot(visible)


def main():
    """Run the improved badge demo"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = ImprovedBadgeDemoWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
