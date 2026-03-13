import weakref
from typing import Dict, Type, Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QCursor

from .classic_toggle import ClassicToggle
from .dot_toggle import DotToggle
from .toggle_base import ToggleBase


class ToggleStyleRegistry:
    """Simple registry so new toggle styles can be plugged in easily."""

    def __init__(self):
        self._styles: Dict[str, Type[ToggleBase]] = {}

    def register(self, name: str, toggle_cls: Type[ToggleBase]):
        self._styles[name.lower()] = toggle_cls

    def resolve(self, name: str) -> Type[ToggleBase]:
        if not name:
            return ClassicToggle
        return self._styles.get(name.lower(), ClassicToggle)

    def names(self):
        return tuple(sorted(self._styles.keys()))


STYLE_REGISTRY = ToggleStyleRegistry()
STYLE_REGISTRY.register("classic", ClassicToggle)
STYLE_REGISTRY.register("dot", DotToggle)


class StyleableToggle(QWidget):
    """Wrap a toggle so the visual style can be swapped dynamically."""

    toggled = Signal(bool)
    _instances = weakref.WeakSet()

    def __init__(
        self,
        settings_manager,
        theme_manager,
        label_text="",
        parent=None,
        checked=False,
        animation_duration=120,
        setting_key=None,
        default_checked=True,
        style_name=None,
        **toggle_kwargs,
    ):
        super().__init__(parent)
        StyleableToggle._instances.add(self)

        self._settings_manager = settings_manager
        self._theme_manager = theme_manager
        self._label_text = label_text
        self._animation_duration = animation_duration
        self._setting_key = setting_key
        self._checked = checked
        self._style_override = style_name
        self._toggle_kwargs = dict(toggle_kwargs)

        if setting_key and settings_manager:
            self._checked = settings_manager.get_bool(setting_key, default_checked)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._current_toggle: Optional[ToggleBase] = None
        self.update_style()

    @classmethod
    def update_all_instances(cls):
        for instance in cls._instances:
            instance.update_style()

    @classmethod
    def register_style(cls, name: str, toggle_cls: Type[ToggleBase]):
        STYLE_REGISTRY.register(name, toggle_cls)

    def _resolve_style(self) -> Type[ToggleBase]:
        if self._style_override:
            return STYLE_REGISTRY.resolve(self._style_override)
        style_name = "regular"
        if self._settings_manager:
            style_name = self._settings_manager.get("toggle_style", "regular")
        return STYLE_REGISTRY.resolve(style_name)

    def update_style(self):
        if self._current_toggle:
            self._checked = self._current_toggle.isChecked()
            self._current_toggle.deleteLater()
            self._current_toggle = None

        toggle_cls = self._resolve_style()
        self._current_toggle = toggle_cls(
            parent=self,
            checked=self._checked,
            animation_duration=self._animation_duration,
            theme_manager=self._theme_manager,
            **self._toggle_kwargs,
        )
        self._current_toggle.toggled.connect(self._emit_toggled)

        self._layout.addWidget(self._current_toggle)
        self.setSizePolicy(self._current_toggle.sizePolicy())

    def _emit_toggled(self, checked):
        self._checked = checked
        if self._setting_key and self._settings_manager:
            self._settings_manager.set(self._setting_key, checked)
        self.toggled.emit(checked)

    def setChecked(self, checked):
        if self._current_toggle:
            self._current_toggle.setChecked(checked)
        self._checked = checked

    def isChecked(self):
        if self._current_toggle:
            return self._current_toggle.isChecked()
        return self._checked

    def toggle(self):
        if self._current_toggle:
            self._current_toggle.toggle()

    def setCheckedNoAnimation(self, checked):
        if self._current_toggle:
            getattr(self._current_toggle, "setCheckedNoAnimation", self._current_toggle.setChecked)(checked)
        else:
            self.setChecked(checked)

    def setCheckedAnimated(self, checked):
        if self._current_toggle:
            getattr(self._current_toggle, "setCheckedAnimated", self._current_toggle.setChecked)(checked)
        else:
            self.setChecked(checked)

    def get_position(self):
        return 1 if self.isChecked() else 0

    def set_position(self, index, animated=True):
        if animated:
            self.setCheckedAnimated(bool(index))
        else:
            self.setCheckedNoAnimation(bool(index))


class StyleableLabel(QLabel):
    """Clickable label that toggles the associated StyleableToggle."""

    _instances = weakref.WeakSet()

    def __init__(self, text, settings_manager, toggle_widget, parent=None):
        super().__init__(text, parent)
        StyleableLabel._instances.add(self)
        self._settings_manager = settings_manager
        self._toggle_widget = toggle_widget

        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.update_style()

    @classmethod
    def update_all_instances(cls):
        for instance in cls._instances:
            instance.update_style()

    def update_style(self):
        if not self.parent():
            return
        self.show()

    def mouseReleaseEvent(self, event):
        if self._toggle_widget:
            try:
                self._toggle_widget.toggle()
            except Exception:
                pass
        super().mouseReleaseEvent(event)
