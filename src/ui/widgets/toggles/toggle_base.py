from PySide6.QtWidgets import QAbstractButton, QWidget, QHBoxLayout, QLabel, QSizePolicy, QLayout
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QCursor

from src.ui.config import WIDGET_SPACING


class ToggleBase(QAbstractButton):
    """Common behavior shared by all binary toggles."""

    def __init__(self, parent=None, checked=False, animation_duration=120, theme_manager=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self._handle_position = 1.0 if checked else 0.0

        self._anim = QPropertyAnimation(self, b"handle_position")
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.setDuration(animation_duration)

        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.toggled.connect(self._on_toggled)

        self.theme_manager = theme_manager if theme_manager is not None else getattr(parent, "theme_manager", None)
        self._connect_theme_manager()

    # Shared animation plumbing -------------------------------------------------
    def _on_toggled(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._handle_position)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def get_handle_position(self) -> float:
        return self._handle_position

    def set_handle_position(self, value: float):
        self._handle_position = value
        self.update()

    handle_position = Property(float, get_handle_position, set_handle_position)

    def setCheckedNoAnimation(self, checked: bool):
        old = self.blockSignals(True)
        self.setChecked(checked)
        self._handle_position = 1.0 if checked else 0.0
        self.update()
        self.blockSignals(old)

    def setCheckedAnimated(self, checked: bool):
        old = self.blockSignals(True)
        try:
            self.setChecked(checked)
        finally:
            self.blockSignals(old)

        self._anim.stop()
        self._anim.setStartValue(self._handle_position)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def set_animation_duration(self, ms: int):
        self._anim.setDuration(ms)

    # Theme plumbing ------------------------------------------------------------
    def _connect_theme_manager(self):
        if not self.theme_manager or not hasattr(self.theme_manager, "theme_changed"):
            return

        try:
            self.theme_manager.theme_changed.connect(self._apply_theme, Qt.ConnectionType.UniqueConnection)
        except Exception:
            pass

    def _apply_theme(self):
        """Override in subclasses to pull colors from the theme manager."""
        return None

    # Convenience helpers -------------------------------------------------------
    @staticmethod
    def interpolate_color(color1: QColor, color2: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        r = int(color1.red() + (color2.red() - color1.red()) * t)
        g = int(color1.green() + (color2.green() - color1.green()) * t)
        b = int(color1.blue() + (color2.blue() - color1.blue()) * t)
        a = int(color1.alpha() + (color2.alpha() - color1.alpha()) * t)
        return QColor(r, g, b, a)

    @classmethod
    def with_label(
        cls,
        label_text: str,
        parent=None,
        checked=False,
        animation_duration=120,
        theme_manager=None,
        **toggle_kwargs,
    ):
        """Return a QWidget that combines a label and the toggle class."""
        container = QWidget(parent, objectName="Transparent")
        container.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(WIDGET_SPACING)
        try:
            layout.setSizeConstraint(QLayout.SetFixedSize)
        except Exception:
            pass

        label = QLabel(label_text)
        label.setCursor(QCursor(Qt.PointingHandCursor))
        label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        toggle = cls(
            parent=container,
            checked=checked,
            animation_duration=animation_duration,
            theme_manager=theme_manager,
            **toggle_kwargs,
        )
        toggle.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        def _label_clicked(event=None):
            try:
                toggle.toggle()
            except Exception:
                try:
                    toggle.setCheckedNoAnimation(not toggle.isChecked())
                except Exception:
                    pass

        label.mouseReleaseEvent = _label_clicked

        layout.addWidget(label)
        layout.addWidget(toggle)

        container.toggle = toggle
        container.toggled = toggle.toggled
        return container
