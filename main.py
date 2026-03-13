#!/usr/bin/env python3
"""
SteamKM2 - Steam Key Management Tool
Main entry point for the application
"""

import sys
import os
import glob

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from src.ui.main_window import MainWindow
from src.core.database_manager import DatabaseManager
from src.core.theme_manager import ThemeManager
from src.core.settings_manager import SettingsManager


def cleanup_old_backup_files():
    """Remove old .bak files from executable directory after successful update."""
    try:
        exe_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
        for bak in glob.glob(os.path.join(exe_dir, '*.bak')):
            try:
                os.remove(bak)
                print(f"[Update Cleanup] Removed: {bak}")
            except Exception as e:
                print(f"[Update Cleanup] Failed to remove {bak}: {e}")
    except Exception as e:
        print(f"[Update Cleanup] Error: {e}")


def main():
    """Main application entry point"""
    # If relaunched by the updater, we pass a special flag so the UI
    # can show an "update installed" notification and bring the window forward.
    if "--post-update" in sys.argv:
        try:
            while "--post-update" in sys.argv:
                sys.argv.remove("--post-update")
            os.environ["SKM2_POST_UPDATE"] = "1"
            
            # Clean up old backup files after successful update
            cleanup_old_backup_files()
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("SteamKM2")
    app.setApplicationVersion("1.9.0")
    
    # Set application icon if available
    icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'Icons', 'app_icon.png')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # Initialize managers
    settings_manager = SettingsManager()
    theme_manager = ThemeManager(settings_manager)
    db_manager = DatabaseManager(settings_manager.get_database_path(), settings_manager)

    # Apply initial theme
    theme_manager.apply_theme(app)
    
    # Initialize database
    db_manager.initialize()
    
    # Create and show main window
    main_window = MainWindow(db_manager, theme_manager, settings_manager)
    main_window.show()
    
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
