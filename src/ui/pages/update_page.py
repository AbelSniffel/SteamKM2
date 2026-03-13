"""
Update page for SteamKM2
Handles application updates and version management with background downloading
"""

from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QTextEdit, QProgressBar,
    QMessageBox, QApplication, QFrame, QListWidget, QAbstractItemView, QWidget, QSizePolicy
)
from PySide6.QtCore import Signal, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from src.ui.pages.base_page import BasePage
from src.ui.widgets.main_widgets import create_push_button, create_combo_box
from src.ui.ui_factory import UIFactory
from src.core.update_manager import _human_size
from src.ui.widgets.notification_system import NotificationType


class UpdatePage(BasePage):
    """Page for managing application updates with background download support."""
    
    status_message = Signal(str)
    update_available = Signal(bool)
    
    def __init__(self, db_manager, theme_manager, settings_manager):
        app = QApplication.instance()
        self.current_version = getattr(app, 'applicationVersion', lambda: "Unknown")() if app else "Unknown"
        super().__init__(db_manager, theme_manager, settings_manager, title="Update Manager")
        
        self.available_update = None
        self._releases_cache = []
        self._download_in_progress = False
        self._download_completed = False
        self._staged_path = None
        self._checking_notification = None
        self._download_slots = {}
        
        self._setup_ui()
        self.refresh()
    
    def _get_manager(self, attr):
        """Get a manager from main window by attribute name."""
        mw = self.window()
        return getattr(mw, attr, None) if mw else None
    
    def _get_update_manager(self):
        return self._get_manager('update_manager')
    
    def _get_notification_manager(self):
        return self._get_manager('notification_manager')
    
    def _get_health_monitor(self):
        return self._get_manager('health_monitor')
    
    def _disconnect_download_signals(self):
        """Disconnect download signal handlers if connected."""
        um = self._get_update_manager()
        if um:
            for sig_name, slot in self._download_slots.items():
                try:
                    getattr(um, sig_name).disconnect(slot)
                except Exception:
                    pass
        self._download_slots.clear()
    
    def _setup_ui(self):
        """Setup the user interface."""
        # Adjust margins
        try:
            left, _, right, bottom = getattr(self, '_default_main_margins', (10, 10, 10, 5))
            self.main_layout.setContentsMargins(left, 0, right, bottom)
        except Exception:
            pass

        # Auto-check label in header
        self.auto_check_label = QLabel()
        self.auto_check_label.setStyleSheet("color: #666;")
        if self.header_layout:
            self.header_layout.addWidget(self.auto_check_label)

        self._create_version_section()
        self._create_update_section()
        self.body_layout.addStretch()
    
    def _create_version_section(self):
        """Create version info and download progress section."""
        group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager, object_name="version_info_section", title="Version"
        )
        
        # Version info row
        row = QHBoxLayout()
        self.version_label = QLabel(f"SteamKM2 V{self.current_version}")
        self.version_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        row.addWidget(self.version_label)
        row.addStretch()
        
        self.check_btn = create_push_button("Check for Updates")
        self.check_btn.setToolTip("Check GitHub for new releases")
        self.check_btn.clicked.connect(self._check_for_updates)
        row.addWidget(self.check_btn)
        
        self.clear_skipped_btn = create_push_button("Clear Skipped Versions")
        self.clear_skipped_btn.setToolTip("Clear all skipped versions")
        self.clear_skipped_btn.clicked.connect(self._clear_skipped_versions)
        row.addWidget(self.clear_skipped_btn)

        self.unikm_github_btn = create_push_button("UniKM Github")
        self.unikm_github_btn.setToolTip("Open the UniKM GitHub repository")
        self.unikm_github_btn.clicked.connect(self._open_unikm_github)
        row.addWidget(self.unikm_github_btn)
        
        group.content_layout.addLayout(row)
        
        # Health timer
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._update_health_status)
        self._health_timer.start(2000)
        
        self.body_layout.addWidget(group)
        
        # Download progress inner groupbox
        try:
            self.download_progress_groupbox, dl_layout = group._create_inner_groupbox(title=None)
        except Exception:
            dl_layout = group.add_inner_groupbox(title=None)
            self.download_progress_groupbox = None

        self._create_download_progress_widget(dl_layout)
        
        # Action buttons
        actions = QHBoxLayout()
        self.cancel_btn = create_push_button("Cancel Download")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_download)
        actions.addWidget(self.cancel_btn)
        
        self.install_btn = create_push_button("Restart App")
        self.install_btn.setVisible(False)
        self.install_btn.setToolTip("Install the update and restart the application")
        self.install_btn.clicked.connect(self._install_update)
        actions.addWidget(self.install_btn)
        actions.addStretch()
        dl_layout.addLayout(actions)
        
        if self.download_progress_groupbox:
            self.download_progress_groupbox.setVisible(False)
    
    def _create_download_progress_widget(self, parent_layout):
        """Create download progress widget."""
        self.download_section_widget = frame = QFrame(objectName="download_progress_frame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        
        header = QHBoxLayout()
        header.addWidget(QLabel("⬇"))
        self.download_status_label = QLabel("Downloading...")
        header.addWidget(self.download_status_label)
        header.addStretch()
        layout.addLayout(header)
        
        self.download_progress_bar = QProgressBar()
        self.download_progress_bar.setRange(0, 100)
        self.download_progress_bar.setTextVisible(True)
        self.download_progress_bar.setFormat("%p%")
        layout.addWidget(self.download_progress_bar)
        
        self.download_info_label = QLabel("Preparing...")
        self.download_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.download_info_label)
        
        parent_layout.addWidget(frame)
    
    def _create_update_section(self):
        """Create update available and changelog sections."""
        # Update Available section
        update_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager, object_name="update_available_section", title="Update"
        )
        self.update_available_section = update_group
        self.update_available_section.setVisible(False)
        self.update_details_groupbox = update_group.inner_groupbox
        
        header = QHBoxLayout()
        self.update_version_label = QLabel("")
        self.update_version_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(self.update_version_label)
        header.addStretch()
        
        self.update_size_label = QLabel("")
        self.update_size_label.setStyleSheet("color: #666;")
        header.addWidget(self.update_size_label)
        
        self.quick_download_btn = create_push_button("Download")
        self.quick_download_btn.setToolTip("Download the available update")
        self.quick_download_btn.setFixedWidth(80)
        self.quick_download_btn.clicked.connect(self._start_download)
        header.addWidget(self.quick_download_btn)

        self.skip_btn = create_push_button("Skip Version")
        self.skip_btn.setToolTip("Ignore this update")
        self.skip_btn.clicked.connect(self._skip_update)
        header.addWidget(self.skip_btn)
        
        update_group.content_layout.addLayout(header)
        self.body_layout.addWidget(update_group)
        
        # Changelog section
        changelog_group = UIFactory.create_section_groupbox(
            settings_manager=self.settings_manager, object_name="changelog_section", title="Changelog"
        )
        
        split = QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        
        # Left: version list
        left = QWidget(objectName="Transparent")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        
        self.version_list = QListWidget()
        self.version_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.version_list.setToolTip("Select a version to view its changelog")
        self.version_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.version_list.currentTextChanged.connect(self._on_version_selected)
        left_layout.addWidget(self.version_list, 1)
        
        self.download_selected_btn = create_push_button("Download This Version")
        self.download_selected_btn.setStyleSheet("font-weight: bold;")
        self.download_selected_btn.setToolTip("Download and install the selected version")
        self.download_selected_btn.clicked.connect(self._start_selected_version_download)
        self.download_selected_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_layout.addWidget(self.download_selected_btn)
        
        split.addWidget(left, 0)
        
        # Right: changelog
        right = QWidget(objectName="Transparent")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.changelog_text = QTextEdit()
        self.changelog_text.setReadOnly(True)
        self.changelog_text.setPlaceholderText("Select a version to view release notes...")
        right_layout.addWidget(self.changelog_text, 1)
        
        split.addWidget(right, 1)
        changelog_group.content_layout.addLayout(split)
        self.body_layout.addWidget(changelog_group)
        
        self._update_selected_download_button_state()
    
    def refresh(self):
        """Refresh the page data."""
        app = QApplication.instance()
        if app:
            self.current_version = app.applicationVersion() or self.current_version
        self.version_label.setText(f"SteamKM2 V{self.current_version}")
        
        self.update_unikm_button_state()
        self._load_version_history()
        self._update_auto_check_label()
        self._sync_with_update_manager()
        self._update_selected_download_button_state()
        self.status_message.emit("Update manager loaded")

    def update_unikm_button_state(self):
        """Update UniKM button visibility and tooltip from settings."""
        if not getattr(self, 'unikm_github_btn', None):
            return

        repo = str(self.settings_manager.get('unikm_repo', 'AbelSniffel/UniKM') or '').strip()
        visible = self.settings_manager.get_bool('show_unikm_github_button', True)
        url = self._build_github_url(repo)

        self.unikm_github_btn.setVisible(visible)
        self.unikm_github_btn.setEnabled(bool(url))
        if url:
            self.unikm_github_btn.setToolTip(f"Open {repo} on GitHub")
        else:
            self.unikm_github_btn.setToolTip("Set a valid UniKM repository in Settings")

    @staticmethod
    def _build_github_url(repo):
        """Build a GitHub URL from an owner/repo setting."""
        value = str(repo or '').strip().strip('/')
        if not value or '/' not in value:
            return ''
        return f"https://github.com/{value}"

    def _open_unikm_github(self):
        """Open the configured UniKM GitHub repository."""
        repo = self.settings_manager.get('unikm_repo', 'AbelSniffel/UniKM')
        url = self._build_github_url(repo)
        if not url:
            self.notify_warning("Set the UniKM repository in Settings using the format owner/repo")
            return
        if not QDesktopServices.openUrl(QUrl.fromUserInput(url)):
            self.notify_error("Failed to open the UniKM GitHub page")
    
    def _load_version_history(self):
        """Load version history from update manager or local cache."""
        if not self.version_list:
            return
            
        self.version_list.blockSignals(True)
        self.version_list.clear()
        
        um = self._get_update_manager()
        releases = um.get_known_releases() if um else []
        if not releases and um:
            releases = um.load_changelog_from_file()
        
        current = str(self.current_version).lstrip('vV')
        items = []
        has_current = False
        
        for r in releases:
            ver = str(r.get('version', '')).lstrip('vV')
            has_current = has_current or ver == current
            items.append(f"V{ver} (Current)" if ver == current else f"V{ver}")
        
        if not has_current:
            items.insert(0, f"V{current} (Current)")
        if not items:
            items = [f"V{current} (Current)"]
        
        self.version_list.addItems(items)
        self._releases_cache = releases
        
        # Select preferred version
        preferred = f"V{str(self.available_update.get('version')).lstrip('vV')}" if self.available_update else None
        self.version_list.blockSignals(False)
        self._select_version_in_list(preferred or f"V{current} (Current)")
        self._update_selected_download_button_state()
    
    def _update_auto_check_label(self):
        """Update auto-check status label."""
        try:
            enabled = self.settings_manager.get_bool('auto_update_check', True)
            if enabled:
                mins = self.settings_manager.get_int('update_check_interval_min', 5)
                self.auto_check_label.setText(f"Auto-update checks: Enabled (every {mins} min)")
            else:
                self.auto_check_label.setText("Auto-update checks: Disabled")
        except Exception:
            self.auto_check_label.setText("")
    
    def _sync_with_update_manager(self):
        """Sync UI with update manager's current state."""
        um = self._get_update_manager()
        if not um:
            return
        try:
            result = um.get_last_result()
            state = result.get('state', 'unknown')
            if state == 'available' and result.get('info'):
                self._on_update_found(result['info'], silent=True)
            elif state == 'none':
                self._on_no_update(silent=True)
        except Exception:
            pass
    
    def _check_for_updates(self):
        """Manually check for updates."""
        um = self._get_update_manager()
        if not um:
            self.notify_error("Update manager not available")
            return
        
        self.check_btn.setEnabled(False)
        self.check_btn.setText("Checking...")
        self.status_message.emit("Checking for updates...")
        self._show_checking_notification()
        
        handled = [False]
        
        def cleanup():
            for sig, h in [('update_available', on_available), ('no_update', on_none), ('update_error', on_error)]:
                try:
                    getattr(um, sig).disconnect(h)
                except Exception:
                    pass
        
        def on_available(info):
            if not handled[0]:
                handled[0] = True
                cleanup()
                self._on_update_found(info)
        
        def on_none():
            if not handled[0]:
                handled[0] = True
                cleanup()
                self._on_no_update()
        
        def on_error(msg):
            if not handled[0]:
                handled[0] = True
                cleanup()
                self._on_update_error(msg)
        
        um.update_available.connect(on_available)
        um.no_update.connect(on_none)
        um.update_error.connect(on_error)
        um.trigger_check_now()
    
    def _show_checking_notification(self):
        """Show persistent checking notification."""
        self._dismiss_checking_notification()
        nm = self._get_notification_manager()
        if nm:
            self._checking_notification = nm.show_notification(
                "Checking for updates...", NotificationType.INFO, duration=0, closable=True
            )
    
    def _dismiss_checking_notification(self, result_message=None, is_error=False):
        """Dismiss checking notification with optional result."""
        if self._checking_notification:
            try:
                self._checking_notification.close_notification()
            except Exception:
                pass
            self._checking_notification = None
        
        if result_message:
            (self.notify_error if is_error else self.notify_info)(result_message)
    
    def _on_update_found(self, info, silent=False):
        """Handle update available."""
        self._dismiss_checking_notification()
        
        # Skip if same version already downloading/downloaded
        if self.available_update and self.available_update.get('version') == info.get('version'):
            if self._download_completed or self._download_in_progress:
                self._finish_check()
                return
        
        self.available_update = info
        version = info.get('version', 'Unknown')
        
        self.update_version_label.setText(f"Version {version} Available")
        self.update_size_label.setText(f"Size: {info.get('file_size', 'Unknown')}")
        self.update_available_section.setVisible(True)
        self.changelog_text.setPlainText(info.get('changelog', '') or '')
        
        self._set_button_visibility(download=True, skip=True, cancel=False, install=False)
        self.download_section_widget.setVisible(False)
        self._load_version_history()
        self._select_version_in_list(f"V{str(version).lstrip('vV')}")
        self._finish_check()
        
        self.update_available.emit(True)
        self.status_message.emit(f"Update v{version} available")
        if not silent:
            self.notify_update(f"Update v{version} is available!")
    
    def _on_no_update(self, silent=False):
        """Handle no update available."""
        if not silent:
            self._dismiss_checking_notification("You're running the latest version")
        else:
            self._dismiss_checking_notification()
        
        self.available_update = None
        # Clear update UI consistently
        self._clear_update_ui()
        self._handle_download_state_visibility()
        self._load_version_history()
        self._finish_check()
        self.update_available.emit(False)
        self.status_message.emit("You're up to date")
    
    def _on_update_error(self, error_msg, silent=False):
        """Handle update check error."""
        if not silent:
            self._dismiss_checking_notification(f"Update check failed: {error_msg}", is_error=True)
        else:
            self._dismiss_checking_notification()
        
        self.available_update = None
        # Clear update UI consistently
        self._clear_update_ui()
        self._handle_download_state_visibility()
        self._load_version_history()
        self._finish_check()
        self.update_available.emit(False)
        self.status_message.emit("Update check failed")
    
    def _handle_download_state_visibility(self):
        """Handle visibility based on download state."""
        if self._download_in_progress:
            self._set_button_visibility(download=False, skip=False, cancel=True, install=False)
            self.download_section_widget.setVisible(True)
            if self.download_progress_groupbox:
                self.download_progress_groupbox.setVisible(True)
        else:
            self.update_available_section.setVisible(False)
            self._set_button_visibility(download=False, skip=False, cancel=False, install=False)
    
    def _clear_update_ui(self):
        """Clear and hide the Update section UI (labels, changelog, groupbox)."""
        try:
            if getattr(self, 'update_available_section', None):
                self.update_available_section.setVisible(False)
            if getattr(self, 'update_version_label', None):
                self.update_version_label.setText("")
            if getattr(self, 'update_size_label', None):
                self.update_size_label.setText("")
            if getattr(self, 'changelog_text', None):
                self.changelog_text.clear()
        except Exception:
            pass
    
    def _finish_check(self):
        """Reset check button state."""
        self.check_btn.setEnabled(True)
        self.check_btn.setText("Check for Updates")
    
    def _set_button_visibility(self, download=True, skip=True, cancel=False, install=False):
        """Set action button visibility states."""
        for btn, visible in [(self.quick_download_btn, download), (self.skip_btn, skip),
                              (self.cancel_btn, cancel), (self.install_btn, install)]:
            if btn:
                btn.setVisible(visible)
    
    def _start_download(self):
        """Start downloading the available update."""
        if not self.available_update:
            self.notify_warning("No update available")
            return
        self._start_download_for_info(dict(self.available_update))

    def _start_selected_version_download(self):
        """Download the currently selected version."""
        info = self._get_selected_release_info()
        if not info:
            self.notify_warning("Select a version to download")
            return
        if not info.get('download_url'):
            self.notify_error("No download URL for this version. Click 'Check for Updates' first.")
            return
        self._start_download_for_info(dict(info))

    def _start_download_for_info(self, info):
        """Start download for given release info."""
        um = self._get_update_manager()
        if not um:
            self.notify_error("Update manager not available")
            return
        if um.is_downloading():
            self.notify_warning("A download is already in progress")
            return

        # Hide and clear the visible "Update" section while download runs
        self._clear_update_ui()

        if self.download_progress_groupbox:
            self.download_progress_groupbox.setVisible(True)

        has_update = bool(self.available_update)
        self._set_button_visibility(download=has_update, skip=has_update, cancel=True, install=False)
        self.download_section_widget.setVisible(True)
        self.download_progress_bar.setValue(0)
        version = str(info.get('version', 'Unknown')).lstrip('vV')
        self.download_status_label.setText(f"Downloading V{version}")
        self.download_info_label.setText("Starting download...")

        self._download_in_progress = True
        self._download_completed = False

        self._disconnect_download_signals()
        self._connect_download_signals(um)

        if not um.start_download(info):
            self._download_in_progress = False
            self._reset_download_ui()
            self.notify_error("Failed to start download")

    def _get_selected_release_info(self):
        """Return selected release info from cache."""
        if not self.version_list:
            return None
        item = self.version_list.currentItem()
        if not item:
            return None
        
        version = (item.text() or '').split(' ')[0].lstrip('vV')
        if not version:
            return None

        if self.available_update and str(self.available_update.get('version', '')).lstrip('vV') == version:
            return self.available_update

        return next((r for r in self._releases_cache if str(r.get('version', '')).lstrip('vV') == version), None)

    def _update_selected_download_button_state(self):
        """Enable/disable selected-version download button."""
        btn = self.download_selected_btn
        if not btn:
            return

        has_items = self.version_list and self.version_list.count() > 0
        btn.setVisible(has_items)

        info = self._get_selected_release_info()
        btn.setEnabled(bool(info and info.get('download_url')))
        btn.setToolTip("Download and install the selected version" if btn.isEnabled() 
                       else "No download link cached. Click 'Check for Updates' to fetch release assets.")
    
    def _connect_download_signals(self, um):
        """Connect download signal handlers."""
        def on_progress(downloaded, total):
            self._update_download_progress(downloaded, total)
        
        um.download_progress.connect(on_progress)
        um.download_completed.connect(self._on_download_completed)
        um.download_error.connect(self._on_download_error)
        
        self._download_slots = {
            'download_progress': on_progress,
            'download_completed': self._on_download_completed,
            'download_error': self._on_download_error
        }
    
    def _update_download_progress(self, downloaded, total):
        """Update download progress bar."""
        if total > 0:
            self.download_progress_bar.setValue(int((downloaded / total) * 100))
            self.download_info_label.setText(f"{_human_size(downloaded)} / {_human_size(total)}")
        else:
            self.download_progress_bar.setRange(0, 0)
            self.download_info_label.setText(_human_size(downloaded))
        
        # Sync notification
        nm = self._get_notification_manager()
        if nm:
            try:
                notif = nm.get_download_notification()
                if notif:
                    notif.update_progress(downloaded, total)
            except Exception:
                pass
    
    def _on_download_completed(self, path):
        """Handle download completion."""
        self._download_in_progress = False
        self._download_completed = True
        self._staged_path = None
        
        um = self._get_update_manager()
        if um:
            try:
                self._staged_path = um.stage_update(path)
            except Exception as ex:
                self._download_completed = False
                self._on_download_error(f"Failed to stage update: {ex}")
                return
        
        self.download_status_label.setText("Download Complete!")
        self.download_progress_bar.setValue(100)
        self.download_info_label.setText("Ready to install")
        
        self.cancel_btn.setVisible(False)
        self.install_btn.setVisible(True)
        self.download_section_widget.setVisible(True)
        if self.download_progress_groupbox:
            self.download_progress_groupbox.setVisible(True)
        
        self.status_message.emit("Update downloaded successfully")
        self.notify_success("Update downloaded! Click 'Restart App' to apply")
        
        nm = self._get_notification_manager()
        if nm:
            try:
                notif = nm.get_download_notification()
                if notif:
                    notif.restart_requested.connect(self._install_update)
                    notif.set_completed(True, "Ready to install")
            except Exception:
                pass
        
        self._disconnect_download_signals()
    
    def _on_download_error(self, error):
        """Handle download error."""
        self._download_in_progress = False
        self._download_completed = False
        self._reset_download_ui()
        
        self.status_message.emit("Download failed")
        self.notify_error(f"Download failed: {error}")
        
        nm = self._get_notification_manager()
        if nm:
            try:
                notif = nm.get_download_notification()
                if notif:
                    notif.set_completed(False, error)
            except Exception:
                pass
        
        self._disconnect_download_signals()
    
    def _reset_download_ui(self):
        """Reset download UI to initial state."""
        has_update = bool(self.available_update)
        self._set_button_visibility(download=has_update, skip=has_update, cancel=False, install=False)
        self.download_section_widget.setVisible(False)
        if self.download_progress_groupbox:
            self.download_progress_groupbox.setVisible(False)
        self.download_progress_bar.setValue(0)
    
    def _cancel_download(self):
        """Cancel the current download."""
        um = self._get_update_manager()
        if um:
            um.cancel_download()
        
        self._download_in_progress = False
        self._download_completed = False
        self._reset_download_ui()
        self.status_message.emit("Download cancelled")
        self.notify_info("Download cancelled")
        self._disconnect_download_signals()
    
    def _install_update(self):
        """Install the downloaded update."""
        if not self._staged_path:
            self.notify_error("No staged update available")
            return
        
        if QMessageBox.question(
            self, "Install Update",
            "The application will close and restart to complete the update.\n\n"
            "Make sure you have saved your work before proceeding.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        ) != QMessageBox.StandardButton.Yes:
            return
        
        um = self._get_update_manager()
        if um and um.apply_update_on_restart(self._staged_path):
            QApplication.instance().quit()
        else:
            self.notify_error("Failed to launch updater")
    
    def _skip_update(self):
        """Skip the current update."""
        if self.available_update:
            version = self.available_update.get('version', '')
            if version:
                self.settings_manager.add_skipped_version(version)

        # Clear the Update section UI (labels, changelog, groupbox)
        self._clear_update_ui()

        if self._download_in_progress:
            self.available_update = None
            self._set_button_visibility(download=False, skip=False, cancel=True, install=False)
        else:
            self.available_update = None
            self._download_completed = False
            self._staged_path = None
            self._set_button_visibility(download=False, skip=False, cancel=False, install=False)

        um = self._get_update_manager()
        if um and hasattr(um, 'clear_last_result'):
            try:
                um.clear_last_result()
            except Exception:
                pass
        
        self.update_available.emit(False)
        self.status_message.emit("Update skipped")
        self.notify_info("Update skipped")
    
    def _clear_skipped_versions(self):
        """Clear all skipped versions."""
        self.settings_manager.clear_skipped_versions()
        self.status_message.emit("Cleared all skipped versions")
        self.notify_info("Cleared skipped versions list")
    
    def _on_version_selected(self, version_text):
        """Handle version selection in history."""
        if not version_text:
            self.changelog_text.clear()
            self._update_selected_download_button_state()
            return

        version = version_text.split(' ')[0].lstrip('vV')
        
        if self.available_update and str(self.available_update.get('version', '')).lstrip('vV') == version:
            self.changelog_text.setPlainText(self.available_update.get('changelog', '') or '')
        else:
            body = next((r.get('body', '') for r in self._releases_cache 
                        if str(r.get('version', '')).lstrip('vV') == version), "No release notes available.")
            self.changelog_text.setPlainText(body)
        
        self._update_selected_download_button_state()

    def _select_version_in_list(self, display_text):
        """Select an item in the version list by display text."""
        if not self.version_list or not display_text:
            return

        items = self.version_list.findItems(display_text, Qt.MatchFlag.MatchExactly)
        if not items and " (Current)" not in display_text:
            items = self.version_list.findItems(display_text + " (Current)", Qt.MatchFlag.MatchExactly)

        if items:
            self.version_list.setCurrentItem(items[0])
        elif self.version_list.count() > 0:
            self.version_list.setCurrentRow(0)
    
    def _update_health_status(self):
        """Update health status label."""
        hm = self._get_health_monitor()
        if not hm:
            return
        
        try:
            active = getattr(hm, 'get_active_issues', lambda: [])()
            logged = getattr(hm, 'get_issue_log', lambda: [])()
            
            ac = self._count_severities(active)
            lc = self._count_severities(logged)
            text, color = self._get_health_display(ac, lc)
            
            mw = self.window()
            if mw and hasattr(mw, 'page_controller'):
                mw.page_controller.ensure_and_call('Settings', 'update_health_status', text, color)
        except Exception:
            try:
                mw = self.window()
                if mw and hasattr(mw, 'page_controller'):
                    mw.page_controller.ensure_and_call('Settings', 'update_health_status', "● Status Unknown", "#9e9e9e")
            except Exception:
                pass
    
    @staticmethod
    def _count_severities(issues):
        """Count issues by severity level."""
        counts = {'critical': 0, 'error': 0, 'warning': 0}
        for issue in issues:
            sev = getattr(issue, 'severity', None)
            if sev in counts:
                counts[sev] += 1
        return counts
    
    @staticmethod
    def _get_health_display(ac, lc):
        """Get health status display text and color."""
        if ac['critical']:
            return "✖ I'm having a meltdown :/", "#ff0000"
        if ac['error']:
            return f"⚠ {ac['error']} Error(s) Active", "#ff6b35"
        if ac['warning']:
            return f"⚠ {ac['warning']} Warning(s) Active", "#ffbf3f"
        if lc['critical'] or lc['error']:
            return f"● {lc['critical'] + lc['error']} Issue(s) Logged", "#ff9800"
        if lc['warning']:
            return f"● {lc['warning']} Warning(s) Logged", "#ffc107"
        return "● No Issues", "#4caf50"
    
    def showEvent(self, event):
        """Handle page becoming visible."""
        super().showEvent(event)
        self._restore_download_state()
        self._hide_download_notification()
    
    def hideEvent(self, event):
        """Handle page becoming hidden."""
        super().hideEvent(event)
        if self._download_in_progress or self._download_completed:
            self._show_download_notification()
    
    def _restore_download_state(self):
        """Restore download UI state when returning to the page."""
        if not self.available_update:
            return
        
        if self._download_completed and self._staged_path:
            self.update_details_groupbox.setVisible(True)
            self._set_button_visibility(download=False, skip=False, cancel=False, install=True)
            self.download_section_widget.setVisible(True)
            if self.download_progress_groupbox:
                self.download_progress_groupbox.setVisible(True)
            self.download_status_label.setText("Download Complete!")
            self.download_progress_bar.setValue(100)
            self.download_info_label.setText("Ready to install")
        elif self._download_in_progress:
            self.update_details_groupbox.setVisible(True)
            self._set_button_visibility(download=False, skip=False, cancel=True, install=False)
            self.download_section_widget.setVisible(True)
            if self.download_progress_groupbox:
                self.download_progress_groupbox.setVisible(True)
    
    def _hide_download_notification(self):
        """Hide the download progress notification."""
        nm = self._get_notification_manager()
        if nm:
            try:
                notif = nm.get_download_notification()
                if notif:
                    notif.close_notification()
            except Exception:
                pass
    
    def _show_download_notification(self):
        """Show download notification when navigating away."""
        if not (self._download_in_progress or self._download_completed):
            return
        
        nm = self._get_notification_manager()
        if not nm:
            return
        
        try:
            version = self.available_update.get('version', '') if self.available_update else ''
            
            if self._download_completed:
                notif = nm.show_download(f"Update v{version} Ready")
                notif.restart_requested.connect(self._install_update)
                notif.set_completed(True, "Ready to install")
            else:
                notif = nm.show_download(f"Downloading v{version}...")
                notif.cancel_requested.connect(self._cancel_download)
                progress = self.download_progress_bar.value()
                if progress > 0:
                    notif.progress_bar.setValue(progress)
                    notif.info_label.setText(self.download_info_label.text())
        except Exception:
            pass
    
    def get_status_message(self):
        """Get status message for this page."""
        return f"Current version: {self.current_version}"
