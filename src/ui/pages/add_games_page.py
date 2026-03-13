"""
Add Games page - Simplified version

A streamlined interface for adding multiple games at once.
Features batch text input and individual entry forms with:
- Game cover images
- Title, key, and platform
- Tags, notes, and game status toggles
- Auto-detect platform from game keys
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QDateTime, QTimer
from PySide6.QtWidgets import (
	QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
	QFileDialog, QTextEdit, QDialog, QDialogButtonBox, QSizePolicy, QMenu
)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QAction, QKeySequence, QShortcut, QPainterPath

from src.ui.pages.base_page import BasePage
from src.ui.config import WIDGET_SPACING, TOGGLE_SPACING
from src.ui.ui_factory import UIFactory
from src.ui.widgets.main_widgets import (
	create_push_button,
	create_line_edit,
	create_combo_box,
	create_tags_section,
	create_date_selector,
	create_scroll_area,
	create_toggle_button,
	create_fetching_placeholder,
)
from src.ui.widgets.sidebar import Sidebar
from src.core.platform_detector import PlatformDetector
from src.core.database_manager import DatabaseLockedError
from src.core.steam_integration import SteamIntegration, SteamFetchWorker, DatabaseSaveWorker
from src.ui.utils import clear_layout

if TYPE_CHECKING:
	from typing import Iterable

# Check for Qt threading support
try:
	from PySide6.QtCore import QThread
	HAS_QTHREAD = True
except ImportError:
	HAS_QTHREAD = False


class NotesDialog(QDialog):
	"""Simple modal dialog to edit notes for an entry."""
	
	__slots__ = ('edit',)

	def __init__(self, text: str = "", parent: QWidget | None = None):
		super().__init__(parent)
		self.setWindowTitle("Edit Notes")
		self.setModal(True)
		self.setMinimumWidth(380)
		
		layout = QVBoxLayout(self)
		self.edit = QTextEdit()
		self.edit.setPlainText(text or "")
		layout.addWidget(self.edit)
		
		buttons = QDialogButtonBox(
			QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
		)
		buttons.accepted.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)

	@classmethod
	def get_text(cls, parent: QWidget | None, initial: str = "") -> str | None:
		"""Show dialog and return edited text, or None if cancelled."""
		dialog = cls(initial, parent)
		if dialog.exec() == QDialog.DialogCode.Accepted:
			return dialog.edit.toPlainText()
		return None


class CoverPicker(QWidget):
	"""Image picker with dashed border and preview inside."""
	
	__slots__ = ('_theme_manager', '_pixmap', '_path', '_hovered')
	
	# Default border colors
	_DEFAULT_COLOR = '#666'
	_HOVER_COLOR = '#00aaff'

	def __init__(self, parent=None, theme_manager=None, size=(180, 120)):
		super().__init__(parent)
		self._theme_manager = theme_manager
		self._pixmap: QPixmap | None = None
		self._path: str | None = None
		self._hovered = False
		self.setFixedSize(*size)
		self.setCursor(Qt.CursorShape.PointingHandCursor)
		self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
		self.setToolTip("Click to add a cover image")

	def enterEvent(self, event):
		"""Handle mouse enter for hover effect."""
		self._hovered = True
		self.update()
		super().enterEvent(event)

	def leaveEvent(self, event):
		"""Handle mouse leave for hover effect."""
		self._hovered = False
		self.update()
		super().leaveEvent(event)

	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		rect = self.rect().adjusted(3, 3, -3, -3)
		# Fill background with theme bg_color (or default)
		palette = None
		if self._theme_manager and hasattr(self._theme_manager, 'get_palette'):
			try:
				palette = self._theme_manager.get_palette()
			except Exception:
				palette = None

		bg = None
		if palette:
			bg = palette.get('bg_color')
		else:
			# fallback to current_theme or default
			if self._theme_manager and hasattr(self._theme_manager, 'current_theme'):
				t = self._theme_manager.current_theme or {}
				bg = t.get('bg_color')
			else:
				bg = None

		bg_color = QColor(bg) if bg else None
		# Use a rounded rect fill so the widget blends in and avoids sharp corners
		if bg_color:
			path = QPainterPath()
			radius = 8
			path.addRoundedRect(rect, radius, radius)
			painter.fillPath(path, bg_color)

		# Determine border color and width; use primary_color for hover like GameCard
		if palette:
			primary = palette.get('primary_color')
			fallback_border = palette.get('deselected_color', self._DEFAULT_COLOR)
		else:
			primary = (self._theme_manager.current_theme.get('base_primary')
				if (self._theme_manager and hasattr(self._theme_manager, 'current_theme')) else None)
			fallback_border = self._DEFAULT_COLOR

		border_color = QColor(primary) if (self._hovered and primary) else QColor(fallback_border)
		border_width = 3 if self._hovered else 2

		# If hovered, slightly increase alpha for a glowy look
		if self._hovered:
			border_color.setAlpha(220)

		# Draw single rounded border
		pen = QPen(border_color, border_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
		painter.setPen(pen)
		painter.setBrush(Qt.NoBrush)
		painter.drawRoundedRect(rect, 8, 8)

		# Draw image or placeholder, clipped to a slightly inset rounded area so corners are smooth
		inner = rect.adjusted(8, 8, -8, -8)
		inner_path = QPainterPath()
		inner_radius = max(radius - 2, 4)
		inner_path.addRoundedRect(inner, inner_radius, inner_radius)
		painter.save()
		painter.setClipPath(inner_path)
		if self._pixmap and not self._pixmap.isNull():
			scaled = self._pixmap.scaled(
				inner.size(), 
				Qt.AspectRatioMode.KeepAspectRatio, 
				Qt.TransformationMode.SmoothTransformation
			)
			x = inner.x() + (inner.width() - scaled.width()) // 2
			y = inner.y() + (inner.height() - scaled.height()) // 2
			painter.drawPixmap(x, y, scaled)
		else:
			# Placeholder text using theme text color when possible
			text_color = None
			if palette:
				text_color = palette.get('text_color')
			elif self._theme_manager and hasattr(self._theme_manager, 'current_theme'):
				text_color = (self._theme_manager.current_theme or {}).get('text_color')
			pen_col = QColor(text_color) if text_color else QColor(200, 160, 140)
			painter.setPen(QPen(pen_col))
			painter.drawText(inner, Qt.AlignmentFlag.AlignCenter, '📷\nClick to add picture')
		painter.restore()
		painter.end()

	def _get_border_color(self) -> str:
		"""Get the appropriate border color based on hover state and theme."""
		if self._theme_manager and hasattr(self._theme_manager, 'current_theme'):
			theme = self._theme_manager.current_theme
			key = 'accent_primary' if self._hovered else 'accent_secondary'
			return theme.get(key, self._HOVER_COLOR if self._hovered else self._DEFAULT_COLOR)
		return self._HOVER_COLOR if self._hovered else self._DEFAULT_COLOR

	def _draw_corner_dashed_border(self, painter, rect, radius, color, width):
		"""Draw rounded border with solid corners and dashed straight edges."""
		adj = width // 2
		r = rect.adjusted(adj, adj, -adj, -adj)
		pen_color = QColor(color)
		radius2 = radius * 2
		
		# Solid corners - draw all arcs with same pen
		painter.setPen(QPen(pen_color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
		# Arc angles in 1/16th degrees: top-left, top-right, bottom-right, bottom-left
		corners = [
			(r.left(), r.top(), 90 * 16, 90 * 16),
			(r.right() - radius2, r.top(), 0, 90 * 16),
			(r.right() - radius2, r.bottom() - radius2, 270 * 16, 90 * 16),
			(r.left(), r.bottom() - radius2, 180 * 16, 90 * 16),
		]
		for x, y, start, span in corners:
			painter.drawArc(x, y, radius2, radius2, start, span)
		
		# (Dashed styling removed — replaced by a single rounded border above.)

	def mousePressEvent(self, event):
		if event.button() == Qt.MouseButton.LeftButton:
			self._pick_image()

	def contextMenuEvent(self, event):
		"""Right-click menu to act on the current image (clear only when an image exists)."""
		if not (self._pixmap or self._path):
			# No image — no menu required
			return

		menu = QMenu(self)
		clear_action = QAction("Clear Image", self)
		clear_action.triggered.connect(self._clear_image)
		menu.addAction(clear_action)
		menu.exec(event.globalPos())

	def _pick_image(self):
		"""Open file dialog to select a cover image."""
		path, _ = QFileDialog.getOpenFileName(
			self, 'Select Image', '', 
			'Images (*.png *.jpg *.jpeg *.webp);;All files (*.*)'
		)
		if not path:
			return
		
		pixmap = QPixmap(path)
		if not pixmap.isNull():
			self._pixmap = pixmap
			self._path = path
			self.setToolTip(path)
			self.update()

	def path(self) -> str | None:
		"""Return the path to the selected image, or None."""
		return self._path

	def set_path(self, path: str | None):
		"""Set the image path programmatically (e.g., from Steam fetch)."""
		if not path:
			self._clear_image()
			return
		pixmap = QPixmap(path)
		if not pixmap.isNull():
			self._pixmap = pixmap
			self._path = path
			self.setToolTip(path)
			self.update()

	def _clear_image(self):
		"""Clear the currently selected image and update UI."""
		self._pixmap = None
		self._path = None
		self.setToolTip("Click to add a cover image")
		self.update()


class AddEntryWidget(QGroupBox):
	"""One add-game row with fields and tag toggles."""
	
	# Compiled regex for batch line parsing - shared across instances
	_BATCH_SEPARATORS = re.compile(r'\t| \| | ; | , | - ')

	def __init__(self, db_manager, theme_manager, settings_manager, tag_index: dict[str, int], platforms: Iterable[str] | None = None):
		super().__init__("")
		self.db_manager = db_manager
		self.theme_manager = theme_manager
		self.settings_manager = settings_manager
		self.tag_index = tag_index  # name -> id
		self._selected_tags: set[str] = set()
		self.notes_text = ""
		# Steam review data (fetched via Steam Data button)
		self._steam_review_score: int | None = None
		self._steam_review_count: int | None = None
		# DLC status (controlled by Steam fetch)
		self._is_dlc: bool = False
		# Track last fetched title to detect title changes
		self._last_fetched_title: str = ""
		
		self.setObjectName("AddEntryGroup")
		self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

		outer = QVBoxLayout(self)
		outer.setContentsMargins(WIDGET_SPACING, WIDGET_SPACING, WIDGET_SPACING, WIDGET_SPACING)
		outer.setSpacing(WIDGET_SPACING)

		# Top row: left picture, right column with 3 rows (Title, Key+Platform, Toggles)
		top_row = QHBoxLayout()
		top_row.setSpacing(WIDGET_SPACING)

		# Picture (left)
		self.cover = CoverPicker(theme_manager=self.theme_manager)
		self.cover.setToolTip("Click to add a cover image")

		# Right column
		right_box = QWidget(objectName="Transparent")
		right_v = QVBoxLayout(right_box)
		right_v.setContentsMargins(0, 0, 0, 0)
		right_v.setSpacing(WIDGET_SPACING)

		# Row 1: Title + Remove button aligned right
		row1 = QHBoxLayout()
		row1.setContentsMargins(0, 0, 0, 0)
		row1.setSpacing(WIDGET_SPACING)
		self.title_edit = create_line_edit()
		self.title_edit.setPlaceholderText("Title")
		row1.addWidget(self.title_edit, 1)
		self.remove_btn = create_push_button("✕")
		self.remove_btn.setFixedWidth(36)
		self.remove_btn.setToolTip("Remove this entry card")
		row1.addWidget(self.remove_btn)
		right_v.addLayout(row1)

		# Row 2: Key + Steam AppID + Platform combo on the right
		row2 = QHBoxLayout()
		row2.setContentsMargins(0, 0, 0, 0)
		row2.setSpacing(WIDGET_SPACING)
		self.key_edit = create_line_edit()
		self.key_edit.setPlaceholderText("Key")
		row2.addWidget(self.key_edit, 2)
		# Steam AppID container (visible only when Steam is selected)
		self.steam_app_id_container = QWidget(objectName="Transparent")
		steam_app_id_layout = QHBoxLayout(self.steam_app_id_container)
		steam_app_id_layout.setContentsMargins(0, 0, 0, 0)
		steam_app_id_layout.setSpacing(WIDGET_SPACING)
		self.steam_app_id_label = QLabel("Steam AppID:")
		self.steam_app_id_edit = create_line_edit()
		self.steam_app_id_edit.setPlaceholderText("480")
		self.steam_app_id_edit.setFixedWidth(80)
		steam_app_id_layout.addWidget(self.steam_app_id_label)
		steam_app_id_layout.addWidget(self.steam_app_id_edit)
		row2.addWidget(self.steam_app_id_container, 0)
		self.platform_combo = create_combo_box(width=130)
		row2.addWidget(self.platform_combo, 0)
		right_v.addLayout(row2)

		# Row 3: Toggles (Notes, Tags, Auto Tag button, Used, DLC, Deadline + date)
		toggles_row = QHBoxLayout()
		toggles_row.setSpacing(TOGGLE_SPACING)
		
		# Create toggles using helper method
		# Place these labeled switches on the LEFT side of the row
		# Move Notes and Tags to the LEFT side of the row
		self.notes_btn = create_push_button("Notes")
		self.notes_btn.setToolTip("Open notes for this entry")
		toggles_row.addWidget(self.notes_btn)

		# Tags toggle button (show/hide tags section)
		self.tags_toggle_btn = create_toggle_button(
			"Tags",
			force_unchecked=True,
			object_name="toggle_button",
			tooltip="Show/hide tags for this entry",
		)
		toggles_row.addWidget(self.tags_toggle_btn)

		# Auto Tag button (only visible for Steam platform) - positioned before toggles
		self.auto_tag_btn = create_push_button("Use Cached Data")
		self.auto_tag_btn.setToolTip("Fetch data from local cache if available, or Steam if missing")
		toggles_row.addWidget(self.auto_tag_btn)
		
		# Fetch New Data button (force fresh)
		self.fetch_new_btn = create_push_button("Fetch New Data")
		self.fetch_new_btn.setToolTip("Force a fresh search from Steam (ignores cache)")
		self.fetch_new_btn.clicked.connect(self._on_fetch_new_clicked)
		self.fetch_new_btn.setVisible(False)  # Initially hidden, shown for Steam
		toggles_row.addWidget(self.fetch_new_btn)
		
		# DLC emoji label (visible only for Steam games when DLC)
		self.dlc_label = QLabel("📦 DLC")
		self.dlc_label.setToolTip("This is downloadable content (DLC status controlled by Steam fetch)")
		self.dlc_label.setVisible(False)  # Hidden by default, shown only when Steam + DLC
		toggles_row.addWidget(self.dlc_label)
		
		# DLC toggle (for non-Steam platforms)
		self.dlc_toggle = self._create_labeled_toggle(
			toggles_row, "DLC", "Flag this entry as downloadable content"
		)
		
		# Create toggles using helper method
		# Place these labeled switches after the Auto Tag button
		self.used_toggle = self._create_labeled_toggle(
			toggles_row, "Used", "Mark the key as already redeemed"
		)
		
		self.deadline_toggle = self._create_labeled_toggle(
			toggles_row, "Deadline", "Turn on a redeem-by deadline for this key"
		)
		
		self.deadline_label = QLabel("Redeem By:")
		self.deadline_label.setVisible(False)
		self.deadline_input = create_date_selector(self)
		self.deadline_input.setToolTip("Choose the redeem-by date once the deadline is enabled")
		
		# Deadline label and date input follow the labeled toggles
		toggles_row.addWidget(self.deadline_label)
		toggles_row.addWidget(self.deadline_input)
		# Add stretch after all items so the row is left aligned
		toggles_row.addStretch()
		right_v.addLayout(toggles_row)
		
		# Wire the deadline toggle
		self.deadline_toggle.toggled.connect(self._on_deadline_toggled)

		# Add picture and right column to top row
		top_row.addWidget(self.cover, 0)
		top_row.addWidget(right_box, 1)
		outer.addLayout(top_row)

		# Tags section (collapsible via tags_toggle_btn)
		self.tags_widget, self.tags_flow = self._create_tags_section(outer)
		self.tags_widget.setVisible(False)  # Start collapsed

		# Wire up buttons
		self.notes_btn.clicked.connect(self._on_notes_clicked)
		self.tags_toggle_btn.toggled.connect(self._on_tags_toggled)

		# Set up platforms and build tag buttons
		self.set_platforms(platforms)
		self._setup_platform_detection()
		self._update_tags_buttons()
		
		# Connect platform change to update AppID and Auto Tag visibility
		self.platform_combo.currentTextChanged.connect(self._on_platform_changed)
		# Connect auto tag button to immediately fetch Steam data
		self.auto_tag_btn.clicked.connect(self._on_auto_tag_clicked)
		# Initialize visibility based on default platform
		self._on_platform_changed(self.platform_combo.currentText())

	# ---- UI helpers -------------------------------------------------
	def _create_tags_section(self, parent_layout: QVBoxLayout):
		"""Create the collapsible tags section widget with dual layouts for Steam and custom tags."""
		from src.ui.widgets.flow_layout import FlowLayout
		from PySide6.QtWidgets import QGroupBox
		
		# Container for both tag groups
		tag_widget = QWidget()
		tag_widget.setObjectName("Transparent")
		tag_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
		
		container_layout = QHBoxLayout(tag_widget)
		container_layout.setContentsMargins(0, 0, 0, 0)
		container_layout.setSpacing(10)
		
		# Left groupbox: Steam Tags (read-only, only shows active/assigned tags)
		steam_tags_group = QGroupBox("Steam Tags")
		steam_tags_group.setObjectName("TagBox")
		steam_tags_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
		steam_tags_layout = QVBoxLayout(steam_tags_group)
		steam_tags_layout.setContentsMargins(5, 5, 5, 5)
		self.steam_tags_flow = FlowLayout(margin=0, spacing=WIDGET_SPACING)
		steam_tags_layout.addLayout(self.steam_tags_flow)
		container_layout.addWidget(steam_tags_group)
		
		# Right groupbox: Custom Tags (interactive, can be toggled on/off)
		custom_tags_group = QGroupBox("Custom Tags")
		custom_tags_group.setObjectName("TagBox")
		custom_tags_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
		custom_tags_layout = QVBoxLayout(custom_tags_group)
		custom_tags_layout.setContentsMargins(5, 5, 5, 5)
		self.custom_tags_flow = FlowLayout(margin=0, spacing=WIDGET_SPACING)
		custom_tags_layout.addLayout(self.custom_tags_flow)
		container_layout.addWidget(custom_tags_group)
		
		parent_layout.addWidget(tag_widget)
		
		# Keep backwards compatibility - point tags_flow to custom_tags_flow
		self.tags_flow = self.custom_tags_flow
		return tag_widget, self.custom_tags_flow

	def _on_tags_toggled(self, checked: bool):
		"""Show or hide the tags section."""
		self.tags_widget.setVisible(checked)

	def _create_labeled_toggle(self, layout: QHBoxLayout, label: str, tooltip: str):
		"""Create a toggle with label, add to layout, and return the toggle widget."""
		container = UIFactory.create_toggle_with_label(
			label_text=label,
			parent=self,
			checked=False,
			theme_manager=self.theme_manager,
			settings_manager=self.settings_manager
		)
		container.setToolTip(tooltip)
		layout.addWidget(container)
		# Extract toggle widget (handle both container and direct widget patterns)
		return container.toggle if (hasattr(container, 'toggle') and not callable(container.toggle)) else container

	def _setup_platform_detection(self):
		"""Set up debounced platform detection from key input."""
		self._detect_timer = QTimer(self)
		self._detect_timer.setSingleShot(True)
		self._detect_timer.setInterval(200)
		self._detect_timer.timeout.connect(self._on_detect_timeout)
		self.key_edit.textChanged.connect(self._on_key_changed)

	def _on_detect_timeout(self):
		"""Handle platform detection timer timeout."""
		self.detect_and_set_platform(self.key_edit.text().strip())

	def _on_key_changed(self, text: str):
		"""Handle key text changes - debounce platform detection."""
		if text.strip():
			self._detect_timer.start()
		else:
			self.detect_and_set_platform("")

	def set_platforms(self, platforms: Iterable[str] | None):
		"""Set available platforms in the combo box."""
		items = list(dict.fromkeys(platforms)) if platforms else PlatformDetector.get_all_platforms()
		self.platform_combo.clear()
		self.platform_combo.addItems(sorted(items))

	def _on_platform_changed(self, platform: str):
		"""Handle platform change - show/hide Steam-specific fields."""
		is_steam = platform.lower() == 'steam'
		self.steam_app_id_container.setVisible(is_steam)
		self.auto_tag_btn.setVisible(is_steam)
		# For Steam: show DLC emoji if DLC, hide toggle; For others: hide emoji, show toggle
		self.dlc_label.setVisible(is_steam and self._is_dlc)
		self.dlc_toggle.parent().setVisible(not is_steam)
		self.fetch_new_btn.setVisible(is_steam)  # Show new button for Steam too
	
	def _on_fetch_new_clicked(self):
		"""Handle Fetch New Data button - force fresh search."""
		self._handle_steam_fetch_request(force_fresh=True)
	
	def _on_auto_tag_clicked(self):
		"""Handle Use Cached Data button - standard fetch."""
		self._handle_steam_fetch_request(force_fresh=False)
		
	def _handle_steam_fetch_request(self, force_fresh: bool):
		"""Common handler for Steam fetch requests."""
		# Only proceed if platform is Steam and we have a title
		platform = self.platform_combo.currentText()
		if platform.lower() != 'steam':
			return
		
		title = self.title_edit.text().strip()
		if not title:
			print("[Steam] Fetch clicked but no title entered yet")
			return
		
		# Get settings manager from parent
		settings_manager = self.settings_manager
		if not settings_manager:
			return
		
		# Check if title changed since last fetch - clear all Steam data if so
		if self._last_fetched_title and title.lower() != self._last_fetched_title.lower():
			print(f"[Steam] Title changed from '{self._last_fetched_title}' to '{title}' - clearing Steam data")
			self._clear_steam_data()
		
		# Remember this title for next time
		self._last_fetched_title = title
		
		print(f"[Steam] Fetch triggered for '{title}' (force_fresh={force_fresh})")
		
		# Show fetching placeholder immediately
		self._show_fetching_placeholder()
		
		# Perform threaded fetch
		self._start_steam_fetch(title, force_fresh_search=force_fresh, force_image=force_fresh)
	
	def _clear_steam_data(self):
		"""Clear all Steam-related data when title changes."""
		# Clear AppID
		self.steam_app_id_edit.clear()
		# Clear image
		self.cover._clear_image()
		# Clear Steam-provided tags from selection
		all_tags = self.db_manager.get_tags()
		steam_tag_names = {t['name'] for t in all_tags if t.get('is_builtin', False)}
		self._selected_tags -= steam_tag_names
		# Clear review data
		self._steam_review_score = None
		self._steam_review_count = None
		# Reset DLC status
		self._is_dlc = False
		self.dlc_label.setVisible(False)
		# Clear Steam tags display
		clear_layout(self.steam_tags_flow)
		# Show placeholder
		from src.ui.widgets.main_widgets import create_no_tags_placeholder
		create_no_tags_placeholder(self.steam_tags_flow)
	
	def _show_fetching_placeholder(self):
		"""Clear steam tags and show fetching placeholder."""
		# Clear existing Steam tag buttons
		clear_layout(self.steam_tags_flow)
		# Add fetching placeholder
		create_fetching_placeholder(self.steam_tags_flow)
		# Make sure tags section is visible
		if not self.tags_widget.isVisible():
			self.tags_toggle_btn.setChecked(True)
	
	def _show_not_found_tag(self):
		"""Show a 'Couldn't find that game' tag when Steam search fails."""
		# Clear existing Steam tag buttons
		clear_layout(self.steam_tags_flow)
		# Create a warning-style button
		btn = create_push_button("⚠️ Couldn't find that game", object_name="warning_tag_button")
		btn.setEnabled(False)
		btn.setToolTip("Steam couldn't find a game matching this title. Try a different title or manually enter the AppID.")
		btn.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold;")
		self.steam_tags_flow.addWidget(btn)
		# Make sure tags section is visible
		if not self.tags_widget.isVisible():
			self.tags_toggle_btn.setChecked(True)
	
	def _start_steam_fetch(self, title: str, force_fresh_search: bool = False, force_image: bool = False):
		"""Start a threaded Steam data fetch."""
		if not HAS_QTHREAD:
			# Fallback to synchronous fetch
			self._sync_steam_fetch(title, force_fresh_search, force_image)
			return
		
		try:
			steam = SteamIntegration(self.settings_manager.get_app_data_dir())
		except Exception as e:
			print(f"[Steam] Failed to initialize: {e}")
			return
		
		# Get current values
		current_app_id = self.steam_app_id_edit.text().strip() or None
		# If forcing fresh search, ignore current AppID to ensure we search by title
		if force_fresh_search:
			current_app_id = None
			
		current_image = self.cover.path()
		current_tags = list(self._selected_tags)
		
		# Get list of custom (non-Steam) tags to preserve
		all_tags = self.db_manager.get_tags()
		ignored_tags = SteamIntegration.IGNORED_TAGS
		custom_tags = [
			t['name'] for t in all_tags 
			if not t.get('is_builtin', False) and t['name'].lower() not in ignored_tags
		]
		
		# Create worker
		self._fetch_thread = QThread()
		self._fetch_worker = steam.create_fetch_worker(
			title=title,
			current_app_id=current_app_id,
			current_tags=current_tags,
			current_image_path=current_image,
			fetch_appid=True,
			fetch_tags=True,
			fetch_image=True,
			force_tags=True,  # Force replace Steam tags
			custom_tags=custom_tags,  # Preserve custom tags
			force_fresh_search=force_fresh_search,
			force_image=force_image
		)
		
		# Move worker to thread
		self._fetch_worker.moveToThread(self._fetch_thread)
		
		# Connect signals
		self._fetch_thread.started.connect(self._fetch_worker.run)
		self._fetch_worker.finished.connect(self._on_steam_fetch_complete)
		self._fetch_worker.finished.connect(self._fetch_thread.quit)
		self._fetch_worker.error.connect(self._on_steam_fetch_error)
		self._fetch_worker.error.connect(self._fetch_thread.quit)
		self._fetch_thread.finished.connect(self._cleanup_fetch_thread)
		
		# Start the thread
		self._fetch_thread.start()
		print(f"[Steam] Started background fetch for '{title}' (force_fresh={force_fresh_search})")
	
	def _sync_steam_fetch(self, title: str, force_fresh_search: bool = False, force_image: bool = False):
		"""Synchronous Steam data fetch (fallback when threading unavailable)."""
		try:
			steam = SteamIntegration(self.settings_manager.get_app_data_dir())
			
			current_app_id = self.steam_app_id_edit.text().strip() or None
			# If forcing fresh search, ignore current AppID to ensure we search by title
			if force_fresh_search:
				current_app_id = None
				
			current_image = self.cover.path()
			current_tags = list(self._selected_tags)
			
			# Get list of custom (non-Steam) tags to preserve
			all_tags = self.db_manager.get_tags()
			ignored_tags = SteamIntegration.IGNORED_TAGS
			custom_tags = [
				t['name'] for t in all_tags 
				if not t.get('is_builtin', False) and t['name'].lower() not in ignored_tags
			]
			
			result = steam.fetch_missing_data(
				title=title,
				current_app_id=current_app_id,
				current_tags=current_tags,
				current_image_path=current_image,
				fetch_appid=True,
				fetch_tags=True,
				fetch_image=True,
				force_tags=True,
				custom_tags=custom_tags,
				force_fresh_search=force_fresh_search,
				force_image=force_image
			)
			
			self._on_steam_fetch_complete(result)
		except Exception as e:
			print(f"[Steam] Sync fetch error: {e}")
	
	def _on_steam_fetch_error(self, error_msg: str):
		"""Handle Steam data fetch error."""
		print(f"[Steam] Fetch error: {error_msg}")
		# Clear fetching placeholder and show error
		clear_layout(self.steam_tags_flow)
		error_lbl = QLabel(f"Fetch failed: {error_msg}")
		error_lbl.setStyleSheet("color: #d9534f; font-style: italic;") 
		error_lbl.setWordWrap(True)
		self.steam_tags_flow.addWidget(error_lbl)

	def _on_steam_fetch_complete(self, result: dict):
		"""Handle completed Steam data fetch."""
		print(f"[Steam] Fetch complete: {result}")
		
		fetched = result.get('fetched', {})
		
		# Handle "not found" case - show special tag
		if result.get('not_found'):
			self._show_not_found_tag()
			return
		
		# Update AppID
		if fetched.get('app_id') and result.get('app_id'):
			self.steam_app_id_edit.setText(str(result['app_id']))
		
		# Update image
		if fetched.get('image') and result.get('image_path'):
			self.cover.set_path(result['image_path'])
		
		# Update DLC status
		if fetched.get('is_dlc'):
			is_dlc = result.get('is_dlc', False)
			self._is_dlc = is_dlc
			# For Steam: show emoji label and sync toggle state
			self.dlc_label.setVisible(is_dlc)
			self.dlc_toggle.setCheckedNoAnimation(is_dlc)
			if is_dlc:
				print(f"[Steam] DLC status: This is a DLC")
		
		# Update review data
		if fetched.get('reviews'):
			self._steam_review_score = result.get('review_score')
			self._steam_review_count = result.get('review_count')
			print(f"[Steam] Review data: {self._steam_review_score}% from {self._steam_review_count} reviews")
		
		# Update tags
		if fetched.get('tags') and result.get('tags'):
			new_tags = result['tags']
			
			# Ensure all fetched tags exist in database as Steam-provided tags and update tag_index
			new_tag_mapping = self.db_manager.get_or_create_tags(new_tags, is_builtin=True)
			self.tag_index.update(new_tag_mapping)
			
			# Get the set of Steam-provided tag names for UI display purposes
			all_tags = self.db_manager.get_tags()
			steam_tag_names = {t['name'] for t in all_tags if t.get('is_builtin', False)}
			
			# Add all fetched tags to selected tags
			for tag_name in new_tags:
				self._selected_tags.add(tag_name)
			
			# Rebuild Steam tags flow (shows only active Steam-provided tags)
			while self.steam_tags_flow.count():
				item = self.steam_tags_flow.takeAt(0)
				widget = item.widget()
				if widget:
					widget.deleteLater()
			
			for name in sorted(self._selected_tags):
				if name in steam_tag_names:
					btn = create_push_button(name, object_name="toggle_tag_button")
					btn.setCheckable(True)
					btn.setChecked(True)
					btn.setEnabled(False)  # Non-interactable
					btn.setToolTip(f"Steam tag '{name}' (auto-managed)")
					self.steam_tags_flow.addWidget(btn)
			
			# Update custom tags flow to reflect any newly checked custom tags
			for i in range(self.custom_tags_flow.count()):
				item = self.custom_tags_flow.itemAt(i)
				if item and item.widget():
					btn = item.widget()
					tag_name = btn.text()
					if tag_name in new_tags and tag_name not in steam_tag_names:
						btn.blockSignals(True)
						btn.setChecked(True)
						btn.blockSignals(False)
			
			self.steam_tags_flow.invalidate()
			self.custom_tags_flow.invalidate()
			self.updateGeometry()
	
	def _cleanup_fetch_thread(self):
		"""Clean up the fetch thread after completion."""
		if hasattr(self, '_fetch_worker'):
			self._fetch_worker.deleteLater()
			del self._fetch_worker
		if hasattr(self, '_fetch_thread'):
			self._fetch_thread.deleteLater()
			del self._fetch_thread

	# image picking handled by CoverPicker

	def _edit_notes(self):
		"""Open notes dialog for editing."""
		result = NotesDialog.get_text(self, self.notes_text)
		if result is not None:
			# Save edited notes. The Notes button is not a toggle anymore,
			# so simply persist user changes.
			self.notes_text = result
		return result

	def _on_notes_clicked(self):
		"""Open the notes edit dialog when the Notes button is clicked."""
		# Simply open the notes editor; no toggle state to manage.
		self._edit_notes()

	def _on_deadline_toggled(self, checked: bool):
		"""Toggle deadline input visibility and set default date."""
		self.deadline_input.setEnabled(checked)
		self.deadline_input.setVisible(checked)
		self.deadline_label.setVisible(checked)
		if checked and not self.deadline_input.dateTime().isValid():
			self.deadline_input.setDateTime(QDateTime.currentDateTime())

	# ---- Tags -------------------------------------------------------
	def _update_tags_buttons(self):
		"""Rebuild tag buttons for dual layouts: Steam tags (read-only, active only) and custom tags (interactive)."""
		# Get all tags from database and determine which are Steam-provided
		all_tags_list = self.db_manager.get_tags()
		steam_tag_names = {t['name'] for t in all_tags_list if t.get('is_builtin', False)}
		ignored_tags = SteamIntegration.IGNORED_TAGS
		
		# Clear existing Steam tag buttons
		while self.steam_tags_flow.count():
			item = self.steam_tags_flow.takeAt(0)
			widget = item.widget()
			if widget:
				widget.deleteLater()
		
		# Clear existing custom tag buttons
		while self.custom_tags_flow.count():
			item = self.custom_tags_flow.takeAt(0)
			widget = item.widget()
			if widget:
				widget.deleteLater()

		# Reset selected tags
		self._selected_tags.clear()
		
		# Steam Tags (left side): Only show ACTIVE Steam-provided tags - non-interactable
		# (Steam tags are populated when fetched via auto-tag, initially empty for new games)
		for name in sorted(self._selected_tags):
			if name in steam_tag_names:
				btn = create_push_button(name, object_name="toggle_tag_button")
				btn.setCheckable(True)
				btn.setChecked(True)
				btn.setEnabled(False)  # Non-interactable - controlled by auto-tagging
				btn.setToolTip(f"Steam tag '{name}' (auto-managed)")
				self.steam_tags_flow.addWidget(btn)
		
		# Custom Tags (right side): Show ALL custom (non-Steam) tags from tag_index - fully interactable
		# (also filter out ignored Steam feature tags)
		for name in sorted(self.tag_index):
			if name not in steam_tag_names and name.lower() not in ignored_tags:
				btn = create_push_button(name, object_name="toggle_tag_button")
				btn.setCheckable(True)
				btn.setChecked(name in self._selected_tags)
				btn.toggled.connect(lambda checked, n=name: self._on_tag_toggled(n, checked))
				btn.setToolTip(f"Toggle the '{name}' tag for this game")
				self.custom_tags_flow.addWidget(btn)

		# If both flows are empty, show the disabled "None" placeholder for clarity
		try:
			from src.ui.widgets.main_widgets import create_no_tags_placeholder
			if getattr(self.steam_tags_flow, 'count', lambda: 0)() == 0:
				create_no_tags_placeholder(self.steam_tags_flow)
			if getattr(self.custom_tags_flow, 'count', lambda: 0)() == 0:
				create_no_tags_placeholder(self.custom_tags_flow)
		except Exception:
			pass
		self.steam_tags_flow.invalidate()
		self.custom_tags_flow.invalidate()
		self.updateGeometry()

	def set_tag_index(self, tag_index: dict[str, int]):
		"""Update tag buttons only if keys changed."""
		if set(self.tag_index) != set(tag_index):
			self.tag_index = tag_index
			self._update_tags_buttons()
		else:
			self.tag_index = tag_index

	def _on_tag_toggled(self, name: str, checked: bool):
		if checked:
			self._selected_tags.add(name)
		else:
			self._selected_tags.discard(name)

	# ---- Data API ---------------------------------------------------
	def is_empty(self) -> bool:
		"""Check if both title and key are empty."""
		return not (self.title_edit.text().strip() or self.key_edit.text().strip())

	def get_payload(self) -> dict:
		"""Return a dict ready for DatabaseManager.add_game."""
		deadline_enabled = self.deadline_toggle.isChecked()
		deadline_at = None
		
		if deadline_enabled:
			dt = self.deadline_input.dateTime()
			if dt.isValid():
				deadline_at = dt.toString(Qt.DateFormat.ISODate)
		
		platform = self.platform_combo.currentText() or "Steam"
		
		return {
			"title": self.title_edit.text().strip(),
			"game_key": self.key_edit.text().strip(),
			"platform_type": platform,
			"notes": self.notes_text or "",
			"tag_ids": [self.tag_index[n] for n in sorted(self._selected_tags) if n in self.tag_index],
			"image_path": self.cover.path(),
			"is_used": self.used_toggle.isChecked(),
			"deadline_enabled": deadline_enabled,
			"deadline_at": deadline_at,
			"dlc_enabled": self._is_dlc if platform.lower() == 'steam' else self.dlc_toggle.isChecked(),
			"steam_app_id": self.steam_app_id_edit.text().strip() or None,
			"steam_review_score": self._steam_review_score,
			"steam_review_count": self._steam_review_count,
		}

	# ---- Platform detection helpers ---------------------------------

	def detect_and_set_platform(self, key: str):
		"""Detect platform from key and select it in the combo box."""
		detected = (PlatformDetector.detect_platform(key) if key else "Unknown").lower()
		
		# Find matching platform in combo box
		combo = self.platform_combo
		for i in range(combo.count()):
			if combo.itemText(i).lower() == detected:
				combo.setCurrentIndex(i)
				return
		
		# Fallback to Unknown
		for i in range(combo.count()):
			if combo.itemText(i).lower() == "unknown":
				combo.setCurrentIndex(i)
				return



class AddGamesPage(BasePage):
	"""Add new games page with multiple entry rows."""

	game_added = Signal(list)  # emit list of inserted IDs

	def __init__(self, db_manager, theme_manager, settings_manager):
		super().__init__(db_manager, theme_manager, settings_manager, title="Add New Games")
		self._tag_index: dict[str, int] = {}
		self.entries: list[AddEntryWidget] = []
		self._platform_items: list[str] = PlatformDetector.get_all_platforms()
		self._setup_ui()
		self.refresh()

	# UI setup methods
	def _setup_ui(self):
		layout = self.body_layout

		# Add button, Save button, Clear All, and Import Games button in header
		self.add_row_btn = create_push_button("Add Card", object_name="page_header_button")
		self.add_row_btn.setToolTip("Add another entry row")
		self.add_row_btn.clicked.connect(self._add_entry)
		self.header_layout.addWidget(self.add_row_btn)

		# Save button right next to add button
		self.save_btn = create_push_button("Save Games", object_name="page_header_button")
		self.save_btn.clicked.connect(self._save_all)
		self.save_btn.setToolTip("Save all filled game cards to the database")
		self.header_layout.addWidget(self.save_btn)

		# Clear All button
		self.clear_all_btn = create_push_button("Clear All", object_name="page_header_button")
		self.clear_all_btn.clicked.connect(self._clear_all_entries)
		self.clear_all_btn.setToolTip("Clear all game cards and start fresh")
		self.header_layout.addWidget(self.clear_all_btn)

		# Import Games button
		self.import_games_btn = create_push_button("Import Games", object_name="page_header_button")
		self.import_games_btn.clicked.connect(self._import_games)
		self.import_games_btn.setToolTip("Import games from supported sources or backups")
		self.header_layout.addWidget(self.import_games_btn)

		# Sidebar with quick batch import
		batch_section = self._create_batch_sidebar_section()
		self.sidebar = Sidebar()
		self.sidebar.set_search_visible(False)
		self.sidebar.clear_sections()
		# Don't stretch the batch section so it only takes the space it needs
		self.sidebar.add_section(batch_section, stretch=False)
		try:
			self.set_sidebar(self.sidebar, width=340)
		except Exception:
			pass

		# Scrollable list of entries (main content)
		self.content_widget = QWidget()
		self.content_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
		self.content_layout = QVBoxLayout(self.content_widget)
		self.content_layout.setContentsMargins(WIDGET_SPACING, WIDGET_SPACING, WIDGET_SPACING, WIDGET_SPACING)
		self.content_layout.setSpacing(WIDGET_SPACING)

		self.scroll = create_scroll_area(
			widget=self.content_widget,
			widget_resizable=True,
			horizontal_policy=Qt.ScrollBarPolicy.ScrollBarAsNeeded,
			vertical_policy=Qt.ScrollBarPolicy.ScrollBarAsNeeded,
			alignment=Qt.AlignTop,
		)
		layout.addWidget(self.scroll, 1)

		# Keyboard shortcuts for batch creation
		QShortcut(QKeySequence("Ctrl+Return"), self.batch_edit, self._create_entries_from_batch)
		QShortcut(QKeySequence("Ctrl+Enter"), self.batch_edit, self._create_entries_from_batch)
		self.batch_create_btn.clicked.connect(self._create_entries_from_batch)

		# Create initial blank row
		self._add_entry()

	def _create_batch_sidebar_section(self) -> QWidget:
		# Create a plain widget container for the quick batch import area so it can
		# stretch edge-to-edge in the sidebar (no QGroupBox borders or extra margins).
		self.batch_section = QWidget()
		self.batch_section.setObjectName("sidebar_batch_section")
		# Use a Fixed vertical policy so the section height is controlled by its content
		self.batch_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
		batch_layout = QVBoxLayout(self.batch_section)
		batch_layout.setContentsMargins(WIDGET_SPACING, WIDGET_SPACING, WIDGET_SPACING, WIDGET_SPACING)
		batch_layout.setSpacing(WIDGET_SPACING)

		# Section label
		batch_label = QLabel("Add Multiple Games at Once")
		batch_label.setStyleSheet("font-weight: bold;")
		batch_label.setAlignment(Qt.AlignCenter)
		batch_layout.addWidget(batch_label, 0)

		# Multi-line input (expands to fill available space)
		self.batch_edit = QTextEdit()
		self.batch_edit.setPlaceholderText(
			"Cyberpunk 2077\tABCDE-FGHIJ-KLMNO\n"
			"The Witcher 3 | WT3GA-ME123-45ABC\n"
			"Tropico 3 - Steam Special Edition: 7786N-GGVKX-423IV"
		)
		# Fixed height to make the input larger and consistent; allow horizontal expansion
		self.batch_edit.setFixedHeight(320)
		self.batch_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
		batch_layout.addWidget(self.batch_edit, 0)

		# Action buttons (kept at the bottom) - make the button expand to full width
		batch_buttons = QHBoxLayout()
		self.batch_create_btn = create_push_button("Create Game Cards")
		self.batch_create_btn.setToolTip("Convert the text above into entry cards")
		# Allow the button to expand to fill the sidebar width
		self.batch_create_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
		batch_buttons.addWidget(self.batch_create_btn)
		batch_layout.addLayout(batch_buttons)

		# Lock the batch section's height to its contents so it doesn't stretch
		# when the window is maximized; the QTextEdit controls the visible height.
		self.batch_section.setMaximumHeight(self.batch_section.sizeHint().height())

		return self.batch_section

	# Regex to detect game keys: alphanumeric segments separated by dashes (at least 2 segments)
	# Examples: 7786N-GGVKX-423IV, ABCDE-FGHIJ-KLMNO-PQRST, ABC12-DEF34
	_GAME_KEY_PATTERN = re.compile(r'[A-Za-z0-9]{4,6}(?:-[A-Za-z0-9]{4,6}){1,5}')
	
	# Characters to strip from end of title (but preserve !, ?, etc.)
	_TITLE_TRAILING_CHARS = re.compile(r'[\s:;\-,|]+$')

	# Data parsing methods
	def _parse_batch_lines(self, text: str) -> list[tuple[str, str]]:
		"""Parse multiline text into (title, key) pairs.
		
		Handles various formats:
		- Tab-separated: "Title\tKEY-CODE-HERE"
		- Pipe-separated: "Title | KEY-CODE-HERE"
		- Colon-separated: "Title: KEY-CODE-HERE"
		- Smart detection: "Tropico 3 - Steam Special Edition: 7786N-GGVKX-423IV"
		  (detects multi-dash key pattern and treats everything before as title)
		"""
		if not text:
			return []
		
		pairs = []
		for line in text.splitlines():
			line = line.strip()
			if not line:
				continue
			
			result = self._parse_single_line(line)
			if result:
				pairs.append(result)
		
		return pairs
	
	def _parse_single_line(self, line: str) -> tuple[str, str] | None:
		"""Parse a single line into (title, key) tuple or None if invalid."""
		# Strategy 1: Look for a game key pattern (multi-segment dashed code)
		# This handles cases like "Tropico 3 - Steam Special Edition: 7786N-GGVKX-423IV"
		key_match = self._GAME_KEY_PATTERN.search(line)
		if key_match:
			key = key_match.group()
			# Everything before the key is the title
			title_part = line[:key_match.start()]
			# Clean up the title: remove trailing separators/punctuation (but keep !, ?, etc.)
			title = self._TITLE_TRAILING_CHARS.sub('', title_part).strip()
			if title and key:
				return (title, key)
		
		# Strategy 2: Tab separator (explicit delimiter)
		if '\t' in line:
			parts = line.split('\t', 1)
			if len(parts) == 2:
				title = parts[0].strip()
				key = parts[1].strip()
				if title and key:
					return (title, key)
		
		# Strategy 3: Pipe separator " | "
		if ' | ' in line:
			parts = line.split(' | ', 1)
			if len(parts) == 2:
				title = parts[0].strip()
				key = parts[1].strip()
				if title and key:
					return (title, key)
		
		# Strategy 4: Fallback - split on last whitespace (for simple "Title KEY" format)
		parts = line.rsplit(None, 1)
		if len(parts) == 2:
			title = self._TITLE_TRAILING_CHARS.sub('', parts[0]).strip()
			key = parts[1].strip()
			if title and key:
				return (title, key)
		
		return None
		
		return pairs

	def _create_entries_from_batch(self):
		"""Create entries from batch text input."""
		text = self.batch_edit.toPlainText()
		pairs = self._parse_batch_lines(text)
		
		if not pairs:
			self.notify_error("No valid entries found. Use format: Title TAB Key")
			return
		
		# Create entries for each parsed pair
		for title, key in pairs:
			# Find empty entry or create new one
			entry = next((e for e in self.entries if e.is_empty()), None)
			if entry is None:
				self._add_entry()
				entry = self.entries[-1]
			
			# Populate fields
			entry.title_edit.setText(title)
			entry.key_edit.setText(key)
			entry.detect_and_set_platform(key)
		
		self.batch_edit.clear()
		self.notify_success(f"Created {len(pairs)} entries")
	def refresh(self):
		"""Reload tags list and update all entries."""
		if not self._database_ready(show_message=True):
			return
		try:
			tags = self.db_manager.get_tags()
		except DatabaseLockedError:
			self._database_ready(show_message=True)
			return
		except Exception as exc:
			self.notify_error(f"Failed to load tags: {exc}")
			return
		self._tag_index = {t["name"]: int(t["id"]) for t in tags}
		
		for entry in self.entries:
			entry.set_tag_index(self._tag_index)
		self._set_inputs_enabled(True)

	def _set_inputs_enabled(self, enabled: bool):
		for widget in [
			getattr(self, 'add_row_btn', None),
			getattr(self, 'save_btn', None),
			getattr(self, 'clear_all_btn', None),
			getattr(self, 'batch_edit', None),
			getattr(self, 'batch_create_btn', None),
		]:
			if widget is not None:
				widget.setEnabled(enabled)
		for entry in self.entries:
			entry.setEnabled(enabled)

	def _database_ready(self, *, show_message: bool = False) -> bool:
		locked = getattr(self.db_manager, 'requires_password', None) and self.db_manager.requires_password()
		if locked:
			self._set_inputs_enabled(False)
			if show_message:
				self.notify_warning("Unlock the database on the Home page to add games.")
			return False
		self._set_inputs_enabled(True)
		return True

	def on_encryption_status_changed(self, enabled: bool):
		self.refresh()

	def _add_entry(self):
		"""Add a new entry widget."""
		entry = AddEntryWidget(self.db_manager, self.theme_manager, self.settings_manager, self._tag_index, self._platform_items)
		self.entries.append(entry)
		
		# Remove existing stretch and add entry
		if self.content_layout.count() > 0:
			last_item = self.content_layout.itemAt(self.content_layout.count() - 1)
			if last_item and hasattr(last_item, 'spacerItem') and last_item.spacerItem():
				self.content_layout.removeItem(last_item)
		
		self.content_layout.addWidget(entry)
		self.content_layout.addStretch(1)
		
		# Wire remove button
		entry.remove_btn.clicked.connect(lambda: self._remove_entry(entry))
		self._update_remove_buttons()

	def _remove_entry(self, entry: AddEntryWidget):
		"""Remove an entry widget."""
		if entry in self.entries and len(self.entries) > 1:
			self.entries.remove(entry)
			entry.setParent(None)
			entry.deleteLater()
		self._update_remove_buttons()

	def _update_remove_buttons(self):
		"""Enable/disable remove buttons based on entry count."""
		can_remove = len(self.entries) > 1
		for entry in self.entries:
			entry.remove_btn.setEnabled(can_remove)

	# Removed local notification wrapper; use BasePage.notify_* helpers

	def _clear_all_entries(self):
		"""Clear all entry cards and start fresh with one empty card."""
		# Fast bulk removal - remove all entries at once
		for entry in self.entries:
			entry.setParent(None)
			entry.deleteLater()
		self.entries.clear()
		
		# Add one fresh entry
		self._add_entry()

	def _clear_successful_entries(self, successful_entries: list[AddEntryWidget]):
		"""Clear entries that were successfully saved - fast version."""
		# Fast removal: detach all at once, then clean up
		for entry in successful_entries:
			if entry in self.entries:
				self.entries.remove(entry)
				entry.setParent(None)
				entry.deleteLater()
		
		# Ensure we always have at least one entry
		if not self.entries:
			self._add_entry()
		else:
			self._update_remove_buttons()

	def _save_all(self):
		"""Save all valid entries to the database instantly without blocking.
		
		Games are added to the database immediately. Steam data fetching
		only happens if the user has manually toggled Auto Tag on the entry card,
		which triggers a background fetch for that specific entry.
		"""
		if not self._database_ready(show_message=True):
			return
		
		# Collect valid entries with their payloads
		valid_entries = []
		for entry in self.entries:
			if entry.is_empty():
				continue
			payload = entry.get_payload()
			if payload["title"] and payload["game_key"]:
				# Remove auto_tag flag - fetching is done separately when user toggles it
				payload.pop('auto_tag', None)
				valid_entries.append((entry, payload))

		if not valid_entries:
			self.notify_error("Nothing to save. Fill in the Title and the Key.")
			return

		# Check for duplicates before saving
		game_keys = [p["game_key"] for _, p in valid_entries]
		existing_games = self.db_manager.get_games_by_keys(game_keys)
		
		keys_to_skip = set()
		keys_to_overwrite = set()
		
		if existing_games:
			# Build list of duplicates for the resolution dialog
			duplicates = []
			for entry, payload in valid_entries:
				key = payload["game_key"]
				if key in existing_games:
					# Create a new_game dict in the format expected by the dialog
					new_game = {
						'title': payload.get('title', ''),
						'key': key,
						'platform': payload.get('platform_type', 'Steam'),
						'tags': payload.get('tags', []),
					}
					duplicates.append((existing_games[key], new_game))
			
			if duplicates:
				from src.ui.dialogs.duplicate_resolution_dialog import DuplicateResolutionDialog
				dialog = DuplicateResolutionDialog(self, duplicates, self.settings_manager)
				if dialog.exec() != QDialog.DialogCode.Accepted:
					return
				
				keys_to_skip = dialog.get_games_to_skip()
				keys_to_overwrite = dialog.get_games_to_overwrite()

		# Filter entries based on duplicate resolution
		final_entries = []
		entries_to_update = []
		
		for entry, payload in valid_entries:
			key = payload["game_key"]
			if key in keys_to_skip:
				continue  # Skip this entry
			elif key in keys_to_overwrite:
				# Need to update existing game instead of adding new
				existing = existing_games.get(key)
				if existing:
					entries_to_update.append((entry, payload, existing['id']))
			else:
				final_entries.append((entry, payload))

		# Update existing games
		updated_ids = []
		for entry, payload, game_id in entries_to_update:
			try:
				self.db_manager.update_game(
					game_id=game_id,
					title=payload.get('title', ''),
					game_key=payload.get('game_key', ''),
					platform_type=payload.get('platform_type', 'Steam'),
					notes=payload.get('notes', ''),
					tag_ids=payload.get('tag_ids'),
					image_path=payload.get('image_path'),
					is_used=payload.get('is_used', False),
					deadline_enabled=payload.get('deadline_enabled', False),
					deadline_at=payload.get('deadline_at'),
					dlc_enabled=payload.get('dlc_enabled', False),
					steam_app_id=payload.get('steam_app_id'),
					steam_review_score=payload.get('steam_review_score'),
					steam_review_count=payload.get('steam_review_count'),
				)
				updated_ids.append(game_id)
			except Exception as e:
				print(f"Error updating game {game_id}: {e}")

		# Add new games using batch insert
		new_ids = []
		if final_entries:
			try:
				payloads = [p for _, p in final_entries]
				new_ids = self.db_manager.add_games_batch(payloads)
				
				# Verify games were added to database
				verified_count = self._verify_games_in_database(new_ids, payloads)
				
				if verified_count != len(new_ids):
					self.notify_warning(f"Saved {len(new_ids)} games, but only {verified_count} verified")
					
			except DatabaseLockedError:
				self.notify_error("Database locked — unlock before saving games.")
				return
			except Exception as e:
				print(f"Error saving games: {e}")
				self.notify_error(f"Failed to save games: {e}")
				return

		# Build result message
		all_ids = new_ids + updated_ids
		if not all_ids:
			if keys_to_skip:
				self.notify_info(f"Skipped {len(keys_to_skip)} duplicate(s), nothing to save.")
			else:
				self.notify_error("No games were saved.")
			return
		
		msg_parts = []
		if new_ids:
			msg_parts.append(f"{len(new_ids)} new game(s)")
		if updated_ids:
			msg_parts.append(f"{len(updated_ids)} updated")
		if keys_to_skip:
			msg_parts.append(f"{len(keys_to_skip)} skipped")
		
		self.notify_success(f"Saved: {', '.join(msg_parts)}")
		
		# Clear successful entries (both new and updated)
		successful_entries = [e for e, _ in final_entries] + [e for e, _, _ in entries_to_update]
		self._clear_successful_entries(successful_entries)
		
		# Emit signal for all affected games
		if all_ids:
			self.game_added.emit(all_ids)

	def _verify_games_in_database(self, game_ids: list[int], payloads: list[dict]) -> int:
		"""Verify that games were properly added to the database.
		
		Performs data integrity check by fetching each game and comparing
		key fields (title, game_key, platform_type).
		
		Returns the count of successfully verified games.
		"""
		if not game_ids or len(game_ids) != len(payloads):
			return 0
		
		verified = 0
		for game_id, payload in zip(game_ids, payloads):
			try:
				game = self.db_manager.get_game_by_id(game_id)
				if not game:
					print(f"[Verify] Game ID {game_id} not found in database")
					continue
				
				# Check key fields match
				if (game.get('title') == payload.get('title') and
					game.get('game_key') == payload.get('game_key') and
					game.get('platform_type') == payload.get('platform_type')):
					verified += 1
				else:
					print(f"[Verify] Game ID {game_id} data mismatch:")
					print(f"  Expected: {payload.get('title')} / {payload.get('game_key')}")
					print(f"  Got: {game.get('title')} / {game.get('game_key')}")
			except Exception as e:
				print(f"[Verify] Error checking game ID {game_id}: {e}")
		
		return verified

	def _import_games(self):
		"""Import games from various sources using the import dialog."""
		from src.ui.dialogs import ImportDialog
		
		dialog = ImportDialog(self, self.db_manager)
		
		if dialog.exec() == QDialog.DialogCode.Accepted:
			# Refresh the page after successful import
			self.refresh()
			self.status_message.emit("Games imported successfully")
			self.notify_success("Games imported successfully")
			
			# Emit signal with added game IDs to refresh other pages
			added_ids = getattr(dialog, 'added_game_ids', [])
			self.game_added.emit(added_ids or [])

