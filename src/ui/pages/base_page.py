from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Signal
from src.ui.config import WIDGET_SPACING

class BasePage(QWidget):
    """
    Base page widget providing a consistent layout with universal margins and spacing.
    Subclass this for all pages to ensure a unified look and feel.
    """
    status_message = Signal(str)

    def __init__(self, db_manager, theme_manager, settings_manager, title: str = "", parent=None):
        super().__init__(parent)
        # Store common managers
        self.db_manager = db_manager
        self.theme_manager = theme_manager
        self.settings_manager = settings_manager
        self._page_title_text = title or ""

        # Main vertical layout with universal margins and spacing
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 5) # Left, Top, Right, Bottom
        self.main_layout.setSpacing(WIDGET_SPACING)
        margins = self.main_layout.contentsMargins()
        self._default_main_margins = (margins.left(), margins.top(), margins.right(), margins.bottom())

        # Content container: pages should add their main content into `self.body_layout`.
        # We keep a dedicated content body container that holds the header/body
        # (everything except the sidebar). The sidebar is held in
        # `sidebar_container` so it can be placed edge-to-edge while the rest
        # of the content retains the page margins.
        self.content_container = QWidget()
        self.content_layout = QHBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self._default_content_spacing = self.content_layout.spacing()

        # Sidebar container will hold the sidebar widget when attached.
        # Keeping the sidebar inside its own container makes it easy to place
        # it edge-to-edge while the rest of the content keeps page margins.
        self.sidebar_container = QWidget()
        self.sidebar_layout = QVBoxLayout(self.sidebar_container)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)

        # Content body container (everything except the sidebar) — this will
        # hold the page header and the body and preserve the page margins.
        self.content_body_container = QWidget()
        self.content_body_layout = QVBoxLayout(self.content_body_container)
        margins = self.main_layout.contentsMargins()
        self.content_body_layout.setContentsMargins(0, 0, 0, 0)
        self.content_body_layout.setSpacing(WIDGET_SPACING)

        # Body area where page-specific widgets/layouts should be added.
        # This body_widget will be placed inside the inner container so it
        # doesn't touch window edges when the sidebar prefers edge-to-edge.
        self.body_widget = QWidget()
        self.body_layout = QVBoxLayout(self.body_widget)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(WIDGET_SPACING)

        self.header_widget = QWidget()
        self.header_widget.setObjectName("page_header")
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        if title:
            self.header_label = QLabel(title)
            self.header_label.setObjectName("page_title")
            self.header_layout.addWidget(self.header_label)
        else:
            self.header_label = None
        self.header_layout.addStretch()
        self.body_layout.addWidget(self.header_widget)

        # By default the content area contains only the inner container with
        # the body. The sidebar (if present) will be added to content_layout
        # to the left of the inner container so it remains outside of the
        # inner margins.
        # Place the page body inside the content body container (not the
        # sidebar). The content_body_container will always be kept in the
        # content_layout; the sidebar_container is inserted/removed when a
        # sidebar is attached/removed.
        self.content_body_layout.addWidget(self.body_widget, 1)
        self.content_layout.addWidget(self.content_body_container, 1)
        self.main_layout.addWidget(self.content_container)

        # Sidebar bookkeeping
        self._current_sidebar = None
        self._header_embedded_in_sidebar = False

        self._update_header_widget_visibility()

    def set_status(self, message: str):
        """
        Emit a status message signal.
        """
        self.status_message.emit(message)

    # Unified notification helpers that delegate to MainWindow's NotificationManager
    def _notify(self, kind: str, message: str, duration: int | None = None):
        """Internal helper to dispatch notifications via the MainWindow if available.

        kind: one of 'success', 'error', 'warning', 'info', 'update'
        duration: milliseconds; if None, use sensible default per kind
        """
        mw = self.window()
        if not mw:
            # Fallback to status bar message
            self.set_status(message)
            return
        try:
            if kind == 'success' and hasattr(mw, 'show_success'):
                mw.show_success(message, 4000 if duration is None else duration)
            elif kind == 'error' and hasattr(mw, 'show_error'):
                mw.show_error(message, 6000 if duration is None else duration)
            elif kind == 'warning' and hasattr(mw, 'show_warning'):
                mw.show_warning(message, 5000 if duration is None else duration)
            elif kind == 'info' and hasattr(mw, 'show_info'):
                mw.show_info(message, 4000 if duration is None else duration)
            elif kind == 'update' and hasattr(mw, 'show_update_notification'):
                # Default to persistent for updates
                mw.show_update_notification(message, 0 if duration is None else duration)
            else:
                # Final fallback
                self.set_status(message)
        except Exception:
            self.set_status(message)

    # Public convenience wrappers
    def notify_success(self, message: str, duration: int | None = None):
        self._notify('success', message, duration)

    def notify_error(self, message: str, duration: int | None = None):
        self._notify('error', message, duration)

    def notify_warning(self, message: str, duration: int | None = None):
        self._notify('warning', message, duration)

    def notify_info(self, message: str, duration: int | None = None):
        self._notify('info', message, duration)

    def notify_update(self, message: str, duration: int | None = None):
        self._notify('update', message, duration)

    def set_sidebar(self, sidebar: QWidget | None, width: int | None = 175) -> None:
        """Attach (or remove) a sidebar widget to the left of the page body."""

        if sidebar is None:
            self._detach_sidebar()
            return

        try:
            if width:
                sidebar.setFixedWidth(width)
        except Exception:
            pass

        if not sidebar.objectName():
            sidebar.setObjectName("page_sidebar")

        if self._current_sidebar and self._current_sidebar is not sidebar:
            if self._header_embedded_in_sidebar:
                self._restore_header_label()
            try:
                # Remove the current sidebar from the sidebar container layout
                try:
                    self.sidebar_layout.removeWidget(self._current_sidebar)
                except Exception:
                    # Fallback: if the widget somehow ended in the content layout
                    # remove it from there.
                    self.content_layout.removeWidget(self._current_sidebar)
            except Exception:
                pass
            try:
                self._current_sidebar.setParent(None)
            except Exception:
                pass
            self._current_sidebar = None

        # Older layout variants placed widgets directly in content_layout —
        # ensure we don't leave the requested sidebar or the old body widget
        # dangling in the layout.
        try:
            if self.content_layout.indexOf(sidebar) != -1:
                self.content_layout.removeWidget(sidebar)
        except Exception:
            pass

        supports_header = bool(getattr(sidebar, "supports_page_header", False))
        if supports_header and hasattr(sidebar, "embed_page_header"):
            label = getattr(self, "header_label", None)
            if label is not None:
                if self.header_layout.indexOf(label) != -1:
                    self.header_layout.removeWidget(label)
                label.setParent(None)
                try:
                    self._page_title_text = label.text()
                except Exception:
                    pass
            sidebar.embed_page_header(label, title=self._page_title_text)
            self._header_embedded_in_sidebar = True
        else:
            self._restore_header_label()

        if getattr(sidebar, "prefers_edge_to_edge", False):
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            self.content_body_layout.setContentsMargins(10, 0, 10, 5)
            self.content_layout.setSpacing(self._default_content_spacing)
        else:
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            self.content_body_layout.setContentsMargins(10, 0, 10, 5)
            self.content_layout.setSpacing(self._default_content_spacing)

        try:
            policy = sidebar.sizePolicy()
            sidebar.setSizePolicy(policy.horizontalPolicy(), QSizePolicy.Expanding)
        except Exception:
            pass

        # Insert the sidebar into the dedicated sidebar container layout
        # and ensure the sidebar container is present at the left of the
        # content_layout so it sits outside the content body margins.
        try:
            # remove any existing widgets inside sidebar_container
            for i in reversed(range(self.sidebar_layout.count())):
                item = self.sidebar_layout.takeAt(i)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
        except Exception:
            pass

        try:
            sidebar.setParent(self.sidebar_container)
            self.sidebar_layout.addWidget(sidebar)
        except Exception:
            pass

        # Ensure the sidebar_container is present as the left-most child
        # of the content_layout.
        if self.content_layout.indexOf(self.sidebar_container) == -1:
            self.content_layout.insertWidget(0, self.sidebar_container, 0)
        self._current_sidebar = sidebar
        self._update_header_widget_visibility()

    def _detach_sidebar(self) -> None:
        if self._current_sidebar is not None:
            try:
                # Remove from the sidebar layout
                self.sidebar_layout.removeWidget(self._current_sidebar)
            except Exception:
                pass
            try:
                self._current_sidebar.setParent(None)
            except Exception:
                pass
            self._current_sidebar = None
        self._restore_header_label()
        left, top, right, bottom = self._default_main_margins
        # Restore main layout margins and ensure inner container also has
        # the default page margins.
        self.main_layout.setContentsMargins(left, top, right, bottom)
        self.content_body_layout.setContentsMargins(left, top, right, bottom)
        self.content_layout.setSpacing(self._default_content_spacing)
        # Ensure the content_body_container still contains the body.
        if self.content_layout.indexOf(self.content_body_container) == -1:
            self.content_layout.addWidget(self.content_body_container, 1)

    def _restore_header_label(self) -> None:
        label = getattr(self, "header_label", None)
        if not label:
            self._header_embedded_in_sidebar = False
            return
        if label.parent() is not self.header_widget:
            label.setParent(self.header_widget)
        if self.header_layout.indexOf(label) == -1:
            self.header_layout.insertWidget(0, label)
        try:
            self._page_title_text = label.text()
        except Exception:
            pass
        label.show()
        self._header_embedded_in_sidebar = False
        self._update_header_widget_visibility()

    def _header_layout_has_content(self) -> bool:
        if self.header_layout is None:
            return False
        for idx in range(self.header_layout.count()):
            item = self.header_layout.itemAt(idx)
            if item is None:
                continue
            widget = item.widget()
            if widget is None:
                continue
            if widget is self.header_label and self._header_embedded_in_sidebar:
                continue
            if widget.isHidden():
                continue
            return True
        return False

    def _update_header_widget_visibility(self) -> None:
        if getattr(self, "header_widget", None) is None:
            return
        if self._header_embedded_in_sidebar and not self._header_layout_has_content():
            self.header_widget.setVisible(False)
        else:
            self.header_widget.setVisible(True)