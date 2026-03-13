"""
Universal Notification System for SteamKM2

Provides toast-style notifications with animations, theming, and progress bar support.
"""

from enum import Enum
from typing import List, Optional
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRectF
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, 
    QGraphicsOpacityEffect, QToolButton, QSizePolicy, QProgressBar
)
from PySide6.QtGui import QFont, QPainter, QColor, QPainterPath

# Default color palette for notifications
DEFAULT_PALETTE = {
    'notification_bg': '#3a3a3a',
    'notification_text_color': '#ffffff',
    'notification_close_button_bg': '#3a3a3a',
    'notification_close_button_hover': '#555555',
    'notification_success_color': '#4CAF50',
    'notification_error_color': '#F44336',
    'notification_warning_color': '#FF9800',
    'notification_info_color': '#2196F3',
    'accent_color': '#9C27B0',
}


class NotificationType(Enum):
    """Notification types with color key and icon"""
    SUCCESS = ("success", "notification_success_color", "✓")
    ERROR = ("error", "notification_error_color", "X") 
    WARNING = ("warning", "notification_warning_color", "⚠")
    INFO = ("info", "notification_info_color", "ℹ")
    UPDATE = ("update", "accent_color", "🎉")
    DOWNLOAD = ("download", "accent_color", "⬇")
    STEAM = ("steam", "notification_info_color", "🎮")


class NotificationPosition(Enum):
    """Notification display positions"""
    TOP_RIGHT = "top_right"
    TOP_LEFT = "top_left"
    BOTTOM_RIGHT = "bottom_right"
    BOTTOM_LEFT = "bottom_left"
    TOP_CENTER = "top_center"
    BOTTOM_CENTER = "bottom_center"


class NotificationAccentSquare(QWidget):
    """Painted accent square with centered icon."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._type_color = QColor("#2196F3")
        self._icon = "ℹ"
        self._text_color = QColor("#ffffff")
        self.setFixedWidth(33)
        self.setMinimumHeight(33)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    
    def set_colors(self, type_color: str, text_color: str):
        """Set the square and text colors."""
        self._type_color = QColor(type_color)
        self._text_color = QColor(text_color)
        self.update()
    
    def set_icon(self, icon: str):
        """Set the icon text."""
        self._icon = icon
        self.update()
    
    def paintEvent(self, event):
        """Paint the accent square with solid color and centered icon."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 3, 3)
        painter.fillPath(path, self._type_color)
        
        painter.setPen(self._text_color)
        font = QFont("Segoe UI Emoji", 14)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._icon)


class NotificationWidget(QFrame):
    """Individual notification widget with animations and styling"""
    
    closed = Signal()
    GLOW_SIZE = 3
    RADIUS = 6
    
    def __init__(self, message: str, notification_type: NotificationType = NotificationType.INFO,
                 duration: int = 4000, closable: bool = True, parent=None):
        super().__init__(parent)
        
        self.message = message
        self.notification_type = notification_type
        self.duration = duration
        self.closable = closable
        self._glow_color = QColor("#2196F3")
        self._bg_color = QColor("#3a3a3a")
        self._fade_connected = False
        
        self._setup_ui()
        self._setup_animations()
        self._setup_timer()
    
    def paintEvent(self, event):
        """Paint the notification with outer glow effect."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        gs = self.GLOW_SIZE
        
        # Draw glow layers with decreasing alpha
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(gs, 0, -1):
            alpha = int(60 * (i / gs) ** 2)
            glow_color = QColor(self._glow_color)
            glow_color.setAlpha(alpha)
            
            offset = gs - i
            glow_rect = QRectF(gs - offset - 1, gs - offset - 1,
                               w - (gs - offset - 1) * 2, h - (gs - offset - 1) * 2)
            
            path = QPainterPath()
            path.addRoundedRect(glow_rect, self.RADIUS + offset, self.RADIUS + offset)
            painter.setBrush(glow_color)
            painter.drawPath(path)
        
        # Draw main background
        content_rect = QRectF(gs, gs, w - gs * 2, h - gs * 2)
        content_path = QPainterPath()
        content_path.addRoundedRect(content_rect, self.RADIUS, self.RADIUS)
        painter.fillPath(content_path, self._bg_color)
        
    def _setup_ui(self):
        """Setup the notification UI"""
        self.setObjectName("NotificationWidget")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(300)
        self.setMaximumWidth(550)
        
        margin = 6 + self.GLOW_SIZE
        layout = QHBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin + 6, margin)
        layout.setSpacing(10)
        
        self.accent_square = NotificationAccentSquare()
        layout.addWidget(self.accent_square)
        
        self.message_label = QLabel(self.message)
        self.message_label.setWordWrap(True)
        self.message_label.setFont(QFont("Arial", 10))
        self.message_label.setMinimumWidth(200)
        self.message_label.setMaximumWidth(450)
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.message_label, 1)
        
        if self.closable:
            self.close_button = QToolButton()
            self.close_button.setText("×")
            self.close_button.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            self.close_button.setFixedSize(20, 20)
            self.close_button.clicked.connect(self.close_notification)
            layout.addWidget(self.close_button)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self._apply_styling()
        
    def _apply_styling(self):
        """Apply themed styling with type-specific accent square and glow"""
        _, type_color_key, icon = self.notification_type.value
        palette = self._get_palette()
        
        bg_color = palette.get('notification_bg', '#3a3a3a')
        text_color = palette.get('notification_text_color', palette.get('text_color', '#ffffff'))
        type_color = palette.get(type_color_key, '#2196F3')
        close_btn_bg = palette.get('notification_close_button_bg', bg_color)
        close_btn_hover = palette.get('notification_close_button_hover', '#555555')
        
        self._bg_color = QColor(bg_color)
        self._glow_color = QColor(type_color)
        
        self.accent_square.set_colors(type_color, text_color)
        self.accent_square.set_icon(icon)

        self.setStyleSheet(f"""
            QFrame#NotificationWidget {{ background: transparent; border: none; border-radius: 6px; }}
            QLabel {{ color: {text_color}; background: transparent; }}
            QToolButton {{ background: {close_btn_bg}; border: none; border-radius: 10px; color: {text_color}; }}
            QToolButton:hover {{ background: {close_btn_hover}; }}
        """)
        self.update()
    
    def _get_palette(self) -> dict:
        """Get color palette from theme manager or return defaults."""
        try:
            tm = getattr(self, 'theme_manager', None) or getattr(self.parent(), 'theme_manager', None)
            if tm:
                return tm.get_palette()
        except Exception:
            pass
        return DEFAULT_PALETTE
        
    def _setup_animations(self):
        """Setup entrance and exit animations"""
        self.opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity_effect)
        
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(200)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        self.slide_animation = QPropertyAnimation(self, b"pos")
        self.slide_animation.setDuration(300)
        self.slide_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.reposition_animation = QPropertyAnimation(self, b"pos")
        self.reposition_animation.setDuration(200)
        self.reposition_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
    def _setup_timer(self):
        """Setup auto-hide timer"""
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.close_notification)
        
    def show_notification(self, slide_from_right: bool = True):
        """Show the notification with animation"""
        self.show()
        
        offset = 300 if slide_from_right else -300
        start_pos = QPoint(self.pos().x() + offset, self.pos().y())
        end_pos = self.pos()
        
        self.slide_animation.setStartValue(start_pos)
        self.slide_animation.setEndValue(end_pos)
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        
        self.slide_animation.start()
        self.fade_animation.start()
        
        if self.duration > 0:
            self.hide_timer.start(self.duration)
            
    def close_notification(self):
        """Close the notification with animation"""
        if not self.isVisible():
            return
            
        self.hide_timer.stop()
        self.reposition_animation.stop()
        
        # Disconnect previous fade connection if exists
        if self._fade_connected:
            try:
                self.fade_animation.finished.disconnect(self._on_fade_out_finished)
            except (RuntimeError, TypeError):
                pass
            self._fade_connected = False

        try:
            self.fade_animation.finished.connect(self._on_fade_out_finished)
            self._fade_connected = True
        except Exception:
            pass
            
        self.fade_animation.setStartValue(self.opacity_effect.opacity())
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.start()
        
    def animate_to_position(self, target_pos: QPoint):
        """Smoothly animate to a new position"""
        if not self.isVisible() or self.pos() == target_pos:
            return
            
        self.reposition_animation.stop()
        self.reposition_animation.setStartValue(self.pos())
        self.reposition_animation.setEndValue(target_pos)
        self.reposition_animation.start()

    def mousePressEvent(self, event):
        """Close on click if closable"""
        if self.closable:
            self.close_notification()
        super().mousePressEvent(event)
        
    def _on_fade_out_finished(self):
        """Called when fade out animation completes"""
        self.hide()
        self.closed.emit()
        self.deleteLater()
        
    def _cleanup(self):
        """Stop all timers and animations"""
        self.hide_timer.stop()
        if self._fade_connected:
            try:
                self.fade_animation.finished.disconnect(self._on_fade_out_finished)
            except Exception:
                pass
        self.fade_animation.stop()
        self.slide_animation.stop()
        self.reposition_animation.stop()


class DownloadNotificationWidget(NotificationWidget):
    """Notification widget with a progress bar for download progress."""
    
    cancel_requested = Signal()
    restart_requested = Signal()
    
    def __init__(self, message: str, parent=None):
        # Initialize base class attributes without calling parent __init__
        QFrame.__init__(self, parent)
        
        self.message = message
        self.notification_type = NotificationType.DOWNLOAD
        self.duration = 0
        self.closable = True
        self._glow_color = QColor("#2196F3")
        self._bg_color = QColor("#3a3a3a")
        self._fade_connected = False
        self._download_active = True
        
        self._setup_download_ui()
        self._setup_animations()
        self._setup_timer()
        
    def _setup_download_ui(self):
        """Setup the download notification UI with progress bar"""
        self.setObjectName("NotificationWidget")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)
        
        margin = 6 + self.GLOW_SIZE
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(margin, margin, margin + 6, margin)
        outer_layout.setSpacing(10)
        
        self.accent_square = NotificationAccentSquare()
        outer_layout.addWidget(self.accent_square)
        
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        
        # Top row: message + close button
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)
        
        self.message_label = QLabel(self.message)
        self.message_label.setFont(QFont("Arial", 10))
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top_layout.addWidget(self.message_label, 1)
        
        self.close_button = QToolButton()
        self.close_button.setText("×")
        self.close_button.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.close_button.setFixedSize(20, 20)
        self.close_button.clicked.connect(self.close_notification)
        top_layout.addWidget(self.close_button)
        
        content_layout.addLayout(top_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedHeight(16)
        content_layout.addWidget(self.progress_bar)
        
        # Bottom row: Info label + spacer + cancel button
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)
        
        self.info_label = QLabel("Preparing...")
        self.info_label.setFont(QFont("Arial", 9))
        bottom_layout.addWidget(self.info_label)
        
        bottom_layout.addStretch(1)
        
        self.cancel_button = QToolButton()
        self.cancel_button.setText("Cancel")
        self.cancel_button.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        self.cancel_button.setFixedHeight(20)
        self.cancel_button.setToolTip("Cancel download")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        bottom_layout.addWidget(self.cancel_button)
        
        self.restart_button = QToolButton()
        self.restart_button.setText("Restart")
        self.restart_button.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        self.restart_button.setFixedHeight(20)
        self.restart_button.setToolTip("Restart app to apply update")
        self.restart_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restart_button.clicked.connect(self._on_restart_clicked)
        self.restart_button.setVisible(False)
        bottom_layout.addWidget(self.restart_button)
        
        content_layout.addLayout(bottom_layout)
        
        outer_layout.addLayout(content_layout, 1)
        self._apply_styling()
    
    def _on_cancel_clicked(self):
        """Handle cancel button click."""
        self.cancel_requested.emit()
        self.close_notification()
    
    def _on_restart_clicked(self):
        """Handle restart button click."""
        self.restart_requested.emit()
    
    def _apply_styling(self):
        """Apply themed styling with transparent cancel button."""
        _, type_color_key, icon = self.notification_type.value
        palette = self._get_palette()
        
        bg_color = palette.get('notification_bg', '#3a3a3a')
        text_color = palette.get('notification_text_color', palette.get('text_color', '#ffffff'))
        type_color = palette.get(type_color_key, '#2196F3')
        close_btn_hover = palette.get('notification_close_button_hover', '#555555')
        
        self._bg_color = QColor(bg_color)
        self._glow_color = QColor(type_color)
        
        self.accent_square.set_colors(type_color, text_color)
        self.accent_square.set_icon(icon)

        self.setStyleSheet(f"""
            QFrame#NotificationWidget {{ background: transparent; border: none; border-radius: 6px; }}
            QLabel {{ color: {text_color}; background: transparent; }}
            QToolButton {{ background: transparent; border: none; border-radius: 10px; color: {text_color}; }}
            QToolButton:hover {{ background: {close_btn_hover}; }}
        """)
        self.update()
    
    def update_progress(self, downloaded: int, total: int):
        """Update the progress bar and info label."""
        if total > 0:
            self.progress_bar.setValue(int((downloaded / total) * 100))
            self.info_label.setText(f"{self._format_size(downloaded)} / {self._format_size(total)}")
        else:
            self.progress_bar.setRange(0, 0)  # Indeterminate
            self.info_label.setText(self._format_size(downloaded))
    
    def set_completed(self, success: bool = True, message: str = ""):
        """Mark download as completed."""
        self._download_active = False
        self.cancel_button.setVisible(False)
        
        if success:
            self.progress_bar.setValue(100)
            self.info_label.setText(message or "Download complete!")
            self.restart_button.setVisible(True)
        else:
            self.info_label.setText(message or "Download failed")
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format bytes to human-readable string."""
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size_bytes < 1024 or unit == 'GB':
                return f"{int(size_bytes)} {unit}" if unit == 'B' else f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} GB"


class SteamFetchNotificationWidget(NotificationWidget):
    """Notification widget with progress for Steam data fetching."""
    
    cancel_requested = Signal()
    
    def __init__(self, message: str, total_games: int = 0, parent=None):
        # Initialize base class attributes without calling parent __init__
        QFrame.__init__(self, parent)
        
        self.message = message
        self.notification_type = NotificationType.STEAM
        self.duration = 0  # No auto-hide
        self.closable = False  # Can't close with X during fetch
        self._glow_color = QColor("#2196F3")
        self._bg_color = QColor("#3a3a3a")
        self._fade_connected = False
        self._fetch_active = True
        self._total_games = total_games
        self._current_game = 0
        self._current_title = ""
        
        self._setup_steam_ui()
        self._setup_animations()
        self._setup_timer()
        
    def _setup_steam_ui(self):
        """Setup the Steam fetch notification UI."""
        self.setObjectName("NotificationWidget")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)
        
        margin = 6 + self.GLOW_SIZE
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(margin, margin, margin + 6, margin)
        outer_layout.setSpacing(10)
        
        self.accent_square = NotificationAccentSquare()
        outer_layout.addWidget(self.accent_square)
        
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        
        # Top row: message
        self.message_label = QLabel(self.message)
        self.message_label.setFont(QFont("Arial", 10))
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        content_layout.addWidget(self.message_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        if self._total_games > 0:
            self.progress_bar.setRange(0, self._total_games)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%v / %m")
        else:
            self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(14)
        content_layout.addWidget(self.progress_bar)
        
        # Bottom row: Info label + cancel button
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)
        
        self.info_label = QLabel("Starting...")
        self.info_label.setFont(QFont("Arial", 9))
        bottom_layout.addWidget(self.info_label, 1)
        
        self.cancel_button = QToolButton()
        self.cancel_button.setText("Cancel")
        self.cancel_button.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        self.cancel_button.setFixedHeight(20)
        self.cancel_button.setToolTip("Cancel fetch operation")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        bottom_layout.addWidget(self.cancel_button)
        
        content_layout.addLayout(bottom_layout)
        outer_layout.addLayout(content_layout, 1)
        self._apply_styling()
    
    def _on_cancel_clicked(self):
        """Handle cancel button click."""
        self._fetch_active = False
        self.cancel_requested.emit()
        self.set_cancelled()
    
    def _apply_styling(self):
        """Apply themed styling."""
        _, type_color_key, icon = self.notification_type.value
        palette = self._get_palette()
        
        bg_color = palette.get('notification_bg', '#3a3a3a')
        text_color = palette.get('notification_text_color', palette.get('text_color', '#ffffff'))
        type_color = palette.get(type_color_key, '#2196F3')
        close_btn_hover = palette.get('notification_close_button_hover', '#555555')
        
        self._bg_color = QColor(bg_color)
        self._glow_color = QColor(type_color)
        
        self.accent_square.set_colors(type_color, text_color)
        self.accent_square.set_icon(icon)

        self.setStyleSheet(f"""
            QFrame#NotificationWidget {{ background: transparent; border: none; border-radius: 6px; }}
            QLabel {{ color: {text_color}; background: transparent; }}
            QToolButton {{ background: transparent; border: none; border-radius: 10px; color: {text_color}; }}
            QToolButton:hover {{ background: {close_btn_hover}; }}
        """)
        self.update()
    
    def update_progress(self, current: int, total: int, current_title: str = ""):
        """Update the progress bar and info label."""
        self._current_game = current
        self._total_games = total
        self._current_title = current_title
        
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"%v / %m")
        
        if current_title:
            # Truncate long titles
            display_title = current_title[:30] + "..." if len(current_title) > 30 else current_title
            self.info_label.setText(f"Fetching: {display_title}")
        else:
            self.info_label.setText(f"Processing {current} of {total}...")
    
    def set_completed(self, fetched_count: int, failed_count: int = 0):
        """Mark fetch as completed."""
        self._fetch_active = False
        self.cancel_button.setVisible(False)
        self.closable = True
        
        # Make clickable to close
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.progress_bar.setValue(self.progress_bar.maximum())
        
        if fetched_count > 0 and failed_count == 0:
            self.info_label.setText(f"✓ Updated {fetched_count} game{'s' if fetched_count != 1 else ''}")
            self._glow_color = QColor("#4CAF50")  # Success green
        elif fetched_count > 0 and failed_count > 0:
            self.info_label.setText(f"✓ {fetched_count} updated, {failed_count} failed")
            self._glow_color = QColor("#FF9800")  # Warning orange
        elif failed_count > 0:
            self.info_label.setText(f"✗ Failed to fetch {failed_count} game{'s' if failed_count != 1 else ''}")
            self._glow_color = QColor("#F44336")  # Error red
        else:
            self.info_label.setText("No new data to fetch")
        
        self.update()
        
        # Auto-close after 4 seconds
        self.duration = 4000
        self.hide_timer.start(self.duration)
    
    def set_cancelled(self):
        """Mark fetch as cancelled."""
        self._fetch_active = False
        self.cancel_button.setVisible(False)
        self.closable = True
        
        # Make clickable to close
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.info_label.setText("Cancelled")
        self._glow_color = QColor("#FF9800")  # Warning orange
        self.update()
        
        # Auto-close after 2 seconds
        self.duration = 2000
        self.hide_timer.start(self.duration)
    
    @property
    def is_active(self) -> bool:
        """Check if fetch is still active."""
        return self._fetch_active


class NotificationManager(QWidget):
    """Central manager for displaying and positioning notifications"""
    
    def __init__(self, parent=None, position: NotificationPosition = NotificationPosition.TOP_RIGHT, 
                 max_notifications: int = 5):
        super().__init__(parent)
        
        self.position = position
        self.notifications: List[NotificationWidget] = []
        self.spacing = 0 # Spacing between notifications
        self.max_notifications = max_notifications
        self._is_repositioning = False
        self.theme_manager = getattr(parent, 'theme_manager', None) if parent else None
        
        self.setFixedSize(0, 0)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            
    def show_notification(self, message: str, notification_type: NotificationType = NotificationType.INFO,
                         duration: int = 4000, closable: bool = True, 
                         prevent_duplicates: bool = True) -> NotificationWidget:
        """Show a new notification. Returns existing one if duplicate found."""
        # Check for duplicates
        if prevent_duplicates:
            for notif in self.notifications:
                if notif.message == message and notif.notification_type == notification_type:
                    if duration > 0 and notif.duration > 0:
                        notif.hide_timer.start(duration)
                    return notif
        
        # Remove oldest if at capacity
        if len(self.notifications) >= self.max_notifications:
            for notif in self.notifications:
                if notif.duration > 0:
                    notif.close_notification()
                    break
        
        # Create and configure notification
        parent_widget = self.parent() or self
        notification = NotificationWidget(message, notification_type, duration, closable, parent_widget)
        
        if self.theme_manager:
            notification.theme_manager = self.theme_manager
            try:
                self.theme_manager.theme_changed.connect(notification._apply_styling, Qt.ConnectionType.UniqueConnection)
            except Exception:
                pass
            notification._apply_styling()
        
        notification.closed.connect(lambda: self._remove_notification(notification))
        notification.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        notification.raise_()
        
        self.notifications.append(notification)
        notification.adjustSize()
        notification.updateGeometry()
        
        QTimer.singleShot(0, lambda: self._show_notification_delayed(notification))
        return notification
        
    def _show_notification_delayed(self, notification: NotificationWidget):
        """Position and show notification after sizing is complete"""
        if notification not in self.notifications:
            return
        notification.move(self._calculate_position(notification))
        notification.show_notification(slide_from_right=self.position.value.endswith("right"))
        
    def _calculate_position(self, notification: NotificationWidget) -> QPoint:
        """Calculate position for a notification"""
        if not self.parent():
            return QPoint(20, 20)
            
        parent_rect = self.parent().rect()
        size = notification.size() if notification.size().width() > 0 else notification.sizeHint()
        
        try:
            index = self.notifications.index(notification)
        except ValueError:
            index = 0
        
        # Calculate cumulative offset for stacking
        offset = sum(
            (n.size().height() if n.size().height() > 0 else n.sizeHint().height()) + self.spacing
            for n in self.notifications[:index]
        )
        
        pos = self.position
        is_right = "right" in pos.value
        is_bottom = "bottom" in pos.value
        is_center = "center" in pos.value
        
        # X position
        if is_center:
            x = (parent_rect.width() - size.width()) // 2
        elif is_right:
            x = parent_rect.width() - size.width() - 20
        else:
            x = 20
        
        # Y position
        if is_bottom:
            total_height = sum(
                n.size().height() if n.size().height() > 0 else n.sizeHint().height() 
                for n in self.notifications[:index + 1]
            ) + self.spacing * index
            y = parent_rect.height() - 20 - total_height
        else:
            y = 20 + offset
            
        return QPoint(x, y)
        
    def _remove_notification(self, notification: NotificationWidget):
        """Remove notification and reposition remaining ones"""
        if notification in self.notifications:
            self.notifications.remove(notification)
            self._reposition_notifications()
            
    def _reposition_notifications(self):
        """Animate remaining notifications to new positions"""
        if self._is_repositioning:
            return
            
        self._is_repositioning = True
        for notif in self.notifications:
            if notif.isVisible():
                notif.adjustSize()
                notif.animate_to_position(self._calculate_position(notif))
        
        QTimer.singleShot(300, lambda: setattr(self, '_is_repositioning', False))
            
    def clear_all(self):
        """Clear all notifications immediately"""
        for notif in self.notifications:
            notif.hide_timer.stop()
            notif.deleteLater()
        self.notifications.clear()
            
    def handle_parent_resize(self):
        """Reposition notifications on parent resize"""
        if not self._is_repositioning and self.notifications:
            self._reposition_notifications()
            
    # Convenience methods
    def show_success(self, message: str, duration: int = 4000) -> NotificationWidget:
        return self.show_notification(message, NotificationType.SUCCESS, duration)
        
    def show_error(self, message: str, duration: int = 6000) -> NotificationWidget:
        return self.show_notification(message, NotificationType.ERROR, duration)
        
    def show_warning(self, message: str, duration: int = 5000) -> NotificationWidget:
        return self.show_notification(message, NotificationType.WARNING, duration)
        
    def show_info(self, message: str, duration: int = 4000) -> NotificationWidget:
        return self.show_notification(message, NotificationType.INFO, duration)
        
    def show_update(self, message: str, duration: int = 0) -> NotificationWidget:
        return self.show_notification(message, NotificationType.UPDATE, duration)
    
    def show_download(self, message: str = "Downloading update...") -> DownloadNotificationWidget:
        """Show a download progress notification."""
        # Remove existing download notifications
        for notif in self.notifications[:]:
            if isinstance(notif, DownloadNotificationWidget):
                notif.close_notification()
        
        parent_widget = self.parent() or self
        notification = DownloadNotificationWidget(message, parent_widget)
        
        if self.theme_manager:
            notification.theme_manager = self.theme_manager
            try:
                self.theme_manager.theme_changed.connect(notification._apply_styling, Qt.ConnectionType.UniqueConnection)
            except Exception:
                pass
            notification._apply_styling()
        
        notification.closed.connect(lambda: self._remove_notification(notification))
        notification.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        notification.raise_()
        
        self.notifications.append(notification)
        notification.adjustSize()
        notification.updateGeometry()
        
        QTimer.singleShot(0, lambda: self._show_notification_delayed(notification))
        return notification
    
    def get_download_notification(self) -> Optional[DownloadNotificationWidget]:
        """Get the active download notification if one exists."""
        return next((n for n in self.notifications if isinstance(n, DownloadNotificationWidget)), None)
    
    def show_steam_fetch(self, message: str = "Fetching Steam data...", 
                         total_games: int = 0) -> SteamFetchNotificationWidget:
        """Show a Steam fetch progress notification."""
        # Remove existing Steam fetch notifications
        for notif in self.notifications[:]:
            if isinstance(notif, SteamFetchNotificationWidget):
                notif.close_notification()
        
        parent_widget = self.parent() or self
        notification = SteamFetchNotificationWidget(message, total_games, parent_widget)
        
        if self.theme_manager:
            notification.theme_manager = self.theme_manager
            try:
                self.theme_manager.theme_changed.connect(notification._apply_styling, Qt.ConnectionType.UniqueConnection)
            except Exception:
                pass
            notification._apply_styling()
        
        notification.closed.connect(lambda: self._remove_notification(notification))
        notification.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        notification.raise_()
        
        self.notifications.append(notification)
        notification.adjustSize()
        notification.updateGeometry()
        
        QTimer.singleShot(0, lambda: self._show_notification_delayed(notification))
        return notification
    
    def get_steam_fetch_notification(self) -> Optional[SteamFetchNotificationWidget]:
        """Get the active Steam fetch notification if one exists."""
        return next((n for n in self.notifications if isinstance(n, SteamFetchNotificationWidget)), None)
