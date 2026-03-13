"""
Color Picker Button Demo

Demonstrates the ColorPickerButton, SwapButton, and LinkedColorPickerPair widgets.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from src.ui.widgets.color_picker_button import ColorPickerButton, LinkedColorPickerPair


class ColorPickerDemo(QMainWindow):
    """Demo window for color picker buttons"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Color Picker Button Demo")
        self.setMinimumSize(600, 400)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Color Picker Button Widgets")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # Individual buttons section
        layout.addWidget(QLabel("Individual Color Picker Buttons:"))
        
        individual_layout = QHBoxLayout()
        
        self.button1 = ColorPickerButton("#ff7f3f", "Primary")
        self.button1.color_changed.connect(lambda c: print(f"Button 1 color changed to: {c}"))
        individual_layout.addWidget(self.button1)
        
        self.button2 = ColorPickerButton("#2d1b1b", "Background")
        self.button2.color_changed.connect(lambda c: print(f"Button 2 color changed to: {c}"))
        individual_layout.addWidget(self.button2)
        
        individual_layout.addStretch()
        layout.addLayout(individual_layout)
        
        # Linked pair section
        layout.addWidget(QLabel("Linked Color Picker Pair (with swap button):"))
        
        linked_layout = QHBoxLayout()
        
        self.linked_pair = LinkedColorPickerPair(
            color1="#ff7f3f",
            color2="#ff9f3f",
            label1="Gradient Start",
            label2="Gradient End"
        )
        self.linked_pair.color1_changed.connect(lambda c: print(f"Linked pair color 1 changed to: {c}"))
        self.linked_pair.color2_changed.connect(lambda c: print(f"Linked pair color 2 changed to: {c}"))
        self.linked_pair.colors_swapped.connect(lambda: print("Linked pair colors swapped!"))
        
        linked_layout.addWidget(self.linked_pair)
        linked_layout.addStretch()
        layout.addLayout(linked_layout)
        
        # Manual linking section
        layout.addWidget(QLabel("Manually Linked Buttons (link after creation):"))
        
        manual_layout = QHBoxLayout()
        
        self.button3 = ColorPickerButton("#0078d4", "Color A")
        self.button4 = ColorPickerButton("#00a4ef", "Color B")
        
        # Link them together
        self.button3.link_to(self.button4)
        
        manual_layout.addWidget(self.button3)
        manual_layout.addWidget(self.button4)
        manual_layout.addStretch()
        layout.addLayout(manual_layout)
        
        # Status label
        layout.addStretch()
        self.status_label = QLabel("Click any color button to change its color. Click swap button to swap colors.")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.status_label)
        
        # Apply dark theme styling
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
        """)


def main():
    app = QApplication(sys.argv)
    window = ColorPickerDemo()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
