"""
Toggle Widgets Showcase

Combined demo that shows both the MultiStepToggle (multi-option) widgets
and the ClassicToggle (binary) widgets in a single window.
"""
import sys
from _bootstrap import ensure_project_root_on_path

# Ensure project root is on sys.path so `src` package imports resolve.
ensure_project_root_on_path(__file__)

from PySide6.QtWidgets import ( QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QLabel, QHBoxLayout, QComboBox, QScrollArea, QSizePolicy )
from PySide6.QtCore import Qt

from src.core.theme_manager import ThemeManager
from src.core.settings_manager import SettingsManager
from src.ui.widgets.toggles import MultiStepToggle, ClassicToggle, DotToggle


class ToggleShowcaseWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Toggle Widgets Showcase")
        self.setMinimumSize(900, 850)

        # Theme and settings
        self.settings_manager = SettingsManager()
        self.theme_manager = ThemeManager(self.settings_manager)
        self.theme_manager.apply_theme(QApplication.instance())

        # Setup UI
        self._setup_ui()

    def _setup_ui(self):
        """Initialize and configure the UI layout."""
        # Central widget with scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        central = QWidget()
        scroll.setWidget(central)
        self.setCentralWidget(scroll)

        # Main layout
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 10, 20, 10)

        # Header with theme selector and title
        self._create_header(layout)

        # Description
        layout.addWidget(self._create_label("This demo shows all custom toggles in a single place.", 
                                            center=True))

        # Binary toggles section
        layout.addSpacing(6)
        self._create_binary_toggles_section(layout)
        layout.addSpacing(12)

        # Multi-step toggles section
        self._create_multistep_toggles_section(layout)

        # Status label
        self.status_label = QLabel("Click on any toggle to see the selection")
        self.status_label.setStyleSheet("font-size: 14px; padding: 10px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch(1)

    def _create_header(self, parent_layout):
        """Create header with theme selector and centered title."""
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # Theme selector
        theme_container = self._create_theme_selector()
        header_layout.addWidget(theme_container)

        # Centered title
        title = QLabel("Toggle Widgets Showcase")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title, 1)

        # Right placeholder for centering
        right_placeholder = QWidget()
        right_placeholder.setFixedWidth(theme_container.sizeHint().width() or 120)
        header_layout.addWidget(right_placeholder)

        parent_layout.addWidget(header)

    def _create_theme_selector(self):
        """Create and configure the theme selector widget."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Theme:"))
        
        self.theme_selector = QComboBox()
        themes = self.theme_manager.get_available_themes()
        if themes:
            self.theme_selector.addItems(themes)
            current = self.settings_manager.get("current_theme", None)
            if current and current in themes:
                self.theme_selector.setCurrentText(current)
        self.theme_selector.currentTextChanged.connect(self.theme_manager.set_theme)
        layout.addWidget(self.theme_selector)
        
        return container

    def _create_label(self, text, font_size=None, bold=False, center=False):
        """Helper to create styled labels."""
        label = QLabel(text)
        styles = []
        if font_size:
            styles.append(f"font-size: {font_size}px")
        if bold:
            styles.append("font-weight: bold")
        if styles:
            label.setStyleSheet("; ".join(styles))
        if center:
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _create_binary_toggles_section(self, parent_layout):
        """Create the binary toggles demo section."""
        parent_layout.addWidget(self._create_label("Binary Toggles — ClassicToggle", 18, bold=True))
        
        # Classic style toggles
        self._create_simple_toggle_demo(parent_layout)


    def _create_multistep_toggles_section(self, parent_layout):
        """Create the multi-step toggles demo section."""
        parent_layout.addWidget(self._create_label("Multi-Option Toggles — MultiStepToggle", 18, bold=True))
        
        # Define multi-step toggle configurations
        configs = [
            ("Long to Short Text", ["Oh, hello Mark", "I"], 0),
            ("Multi-Options", ["Very Low", "Low", "Normal", "High", "Critical"], 1),
        ]
        
        for title, options, initial_index in configs:
            self._add_demo_section(parent_layout, title, options, initial_index)

    def _add_demo_section(self, parent_layout, title, options, initial_index):
        """Add a demo section with a title and toggle."""
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setSpacing(10)

        # Title
        section_layout.addWidget(self._create_label(title, 16, bold=True))

        # Toggle (left-aligned with stretch)
        toggle = MultiStepToggle(options=options, current_index=initial_index, parent=self)
        toggle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toggle.position_changed.connect(
            lambda idx: self._on_multistep_changed(toggle, title, options, idx)
        )

        toggle_layout = QHBoxLayout()
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.addWidget(toggle)
        toggle_layout.addStretch()
        section_layout.addLayout(toggle_layout)

        # Result label
        result_label = QLabel(f"Selected: {options[initial_index]}")
        result_label.setStyleSheet("font-size: 12px;")
        section_layout.addWidget(result_label)

        # Store reference for updating
        toggle._result_label = result_label

        parent_layout.addWidget(section)

    def _on_multistep_changed(self, toggle, title, options, index):
        """Handle multi-step toggle position change."""
        selected = options[index]
        self.status_label.setText(f"{title}: {selected} (index {index})")
        if hasattr(toggle, "_result_label"):
            toggle._result_label.setText(f"Selected: {selected}")

    def _on_binary_toggled(self, label_text, checked):
        """Update status label for binary toggles."""
        state = "On" if checked else "Off"
        self.status_label.setText(f"{label_text}: {state}")

    def _connect_toggle(self, toggle_widget, label_text):
        """Connect toggle signal to status update."""
        try:
            toggle_widget.toggled.connect(lambda checked: self._on_binary_toggled(label_text, checked))
        except AttributeError:
            # If container doesn't expose .toggled, try inner toggle
            if hasattr(toggle_widget, 'toggle'):
                toggle_widget.toggle.toggled.connect(lambda checked: self._on_binary_toggled(label_text, checked))

    def _create_simple_toggle_demo(self, parent_layout):
        """Create simple toggle demo.

        This now contains two separate rows so the user can compare styles:
        - Classic on its own row
        - DotToggle (dot style) on its own row
        """
        # Classic style row (ClassicToggle)
        # Classic style row (ClassicToggle)
        classic = ClassicToggle.with_label(
            "Regular Toggle",
            parent=self,
            checked=False,
            theme_manager=self.theme_manager,
        )
        self._connect_toggle(classic, "Regular Toggle")

        row_classic = QHBoxLayout()
        row_classic.setSpacing(10)
        row_classic.addWidget(classic)
        row_classic.addStretch()
        parent_layout.addLayout(row_classic)

        # dot style row (DotToggle) — use the same labelled factory for parity
        # dot style row (DotToggle)
        dot = DotToggle.with_label(
            "Dot Toggle",
            parent=self,
            checked=True,
            theme_manager=self.theme_manager,
        )
        self._connect_toggle(dot, "Dot Toggle")

        row_dot = QHBoxLayout()
        row_dot.setSpacing(10)
        row_dot.addWidget(dot)
        row_dot.addStretch()
        parent_layout.addLayout(row_dot)

def main():
    app = QApplication(sys.argv)
    window = ToggleShowcaseWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
