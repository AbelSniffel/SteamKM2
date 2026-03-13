"""Compact notification-style widget for showing selected game count.

Anchored to a viewport (typically the game list view viewport) and stays visible
whenever the selection count is > 0.

Kept separate from the drag overlay.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class SelectionCountNotification(QWidget):
    BORDER_SIZE = 2
    RADIUS = 8

    def __init__(self, parent: QWidget, theme_manager=None):
        super().__init__(parent)
        self._theme_manager = theme_manager
        self._count = 0
        self._alpha = 1.0
        self._size = 36
        self._margin = 4

        for a in (Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                  Qt.WidgetAttribute.WA_NoSystemBackground,
                  Qt.WidgetAttribute.WA_TranslucentBackground):
            self.setAttribute(a, True)

        self.setFixedSize(self._size + self.BORDER_SIZE * 2, self._size + self.BORDER_SIZE * 2)

        # Fade animation on a simple float property (keeps API tiny).
        self._anim = QPropertyAnimation(self, b"fadeAlpha", self)
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)

        self.hide()
        if self._theme_manager and hasattr(self._theme_manager, "theme_changed"):
            try:
                # avoid hard dependency on theme signal
                self._theme_manager.theme_changed.connect(self.update)
            except Exception:
                pass

    def _get_fade_alpha(self) -> float:
        return float(self._alpha)

    def _set_fade_alpha(self, v: float) -> None:
        self._alpha = max(0.0, min(1.0, float(v)))
        self.update()

    fadeAlpha = Property(float, _get_fade_alpha, _set_fade_alpha)

    def _animate_to(self, end: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._alpha)
        self._anim.setEndValue(float(end))
        self._anim.start()

    def set_count(self, count: int) -> None:
        self._count = max(0, int(count))
        if self._count > 0:
            if not self.isVisible():
                self._alpha = 0.0
                self.show()
            self.raise_()
            self._animate_to(1.0)
        elif self.isVisible() or self._alpha > 0.0:
            self._animate_to(0.0)

    def _on_anim_finished(self) -> None:
        if self._alpha <= 0.0:
            self.hide()
            self._alpha = 1.0

    def reposition(self, viewport_rect: QRect) -> None:
        x = viewport_rect.x() + viewport_rect.width() - self.width() - self._margin
        y = viewport_rect.y() + viewport_rect.height() - self.height() - self._margin
        self.move(QPoint(max(0, x), max(0, y)))

    def _palette(self) -> dict:
        if self._theme_manager:
            try:
                return self._theme_manager.get_palette() or {}
            except Exception:
                pass
        return {"notification_bg": "#3a3a3a", "notification_text_color": "#ffffff", "accent_color": "#9C27B0"}

    def paintEvent(self, event):
        # Draw while visible or animating; hide numeric "0" during fade-out.
        if self._count <= 0 and self._alpha <= 0.0:
            return

        pal = self._palette()
        bg = QColor(pal.get("notification_bg", "#3a3a3a"))
        text_col = QColor(pal.get("notification_text_color", "#ffffff"))
        border_col = QColor(pal.get("accent_color", "#5f92ff"))

        w, h = self.width(), self.height()
        bs = self.BORDER_SIZE
        alpha = float(self._alpha)

        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)

        # Background (border thickness follows BORDER_SIZE)
        content = QRect(bs, bs, w - bs * 2, h - bs * 2)
        bg2 = QColor(bg); bg2.setAlpha(int(bg2.alpha() * alpha))
        p.setBrush(bg2)
        if bs > 0:
            border = QColor(border_col); border.setAlpha(int(235 * alpha))
            pen = QPen(border)
            pen.setWidthF(bs)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
        else:
            p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(content, self.RADIUS, self.RADIUS)

        if self._count > 0:
            f = QFont(self.font()); f.setBold(True); f.setPointSize(max(10, f.pointSize() + 1))
            p.setFont(f)
            text_col.setAlpha(int(text_col.alpha() * alpha))
            p.setPen(text_col)
            p.drawText(content, Qt.AlignmentFlag.AlignCenter, str(self._count))

        p.end()
