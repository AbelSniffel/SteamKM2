from typing import Callable, Dict, Optional
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QStackedWidget, QWidget


class PageManager(QObject):
    """Manage page factories and lazy instantiation into a QStackedWidget.

    Usage:
      pm = PageManager(stacked_widget)
      pm.register('Home', lambda: HomePage(...))
      widget = pm.ensure_page('Home')  # creates + adds to stack if needed
      pm.show_page('Home')  # convenience that sets current widget
    """

    page_created = Signal(str, object)  # name, widget

    def __init__(self, stacked: QStackedWidget):
        super().__init__()
        self._stacked = stacked
        self._factories: Dict[str, Callable[[], QWidget]] = {}
        self._instances: Dict[str, QWidget] = {}

    def register(self, name: str, factory: Callable[[], QWidget]):
        self._factories[name] = factory

    def is_registered(self, name: str) -> bool:
        return name in self._factories

    def get_instance(self, name: str) -> Optional[QWidget]:
        return self._instances.get(name)

    def ensure_page(self, name: str) -> QWidget:
        """Ensure the page instance exists and is added to the stacked widget."""
        if name in self._instances:
            return self._instances[name]
        if name not in self._factories:
            raise KeyError(f"Page not registered: {name}")
        widget = self._factories[name]()
        # add to stack and keep reference
        self._stacked.addWidget(widget)
        self._instances[name] = widget
        # emit created signal
        self.page_created.emit(name, widget)
        return widget

    def show_page(self, name: str) -> QWidget:
        w = self.ensure_page(name)
        self._stacked.setCurrentWidget(w)
        return w

    def prewarm(self, name: str) -> None:
        """Create the page without showing it (useful to reduce first-open latency)."""
        try:
            self.ensure_page(name)
        except KeyError:
            pass
