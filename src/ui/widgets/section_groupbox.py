from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QSizePolicy, QWidget, QHBoxLayout
from src.ui.config import WIDGET_SPACING
import weakref


TITLE_COLUMN_MIN_WIDTH = 105
TITLE_ALIGNMENT_MAP = {
    "top": Qt.AlignTop,
    "center": Qt.AlignVCenter,
    "bottom": Qt.AlignBottom,
}


class SectionGroupBox(QGroupBox):
    """A simple group box with an optional header label and an inner content area.

        Key behavior preserved:
        - Group header label uses objectName "SectionOuterGroupLabel" for styling.
        - Inner group boxes use objectName "SectionGroupBox" and optional
            top-left label "SectionInnerGroupLabel" for styling.
        - When add_inner_box=True (default), the first call to add_inner_groupbox()
            returns the initial inner box to avoid creating an extra empty one.
        - When add_inner_box=False, content_layout is a plain QVBoxLayout attached
            directly to the outer layout (used by tag helpers).

        Enhancements:
        - `title_location="left"` places the section label in a dedicated left column
            to optimize horizontal space usage while keeping the content area flexible.
        - `title_width` can fix the left column width when using the horizontal layout.
        - `title_vertical_alignment` lets callers keep the title pinned to the top
            or center it vertically when using the horizontal layout.
    """

    _instances = weakref.WeakSet()

    def __init__(
        self,
        object_name: str | None = None,
        title: str | None = None,
        size_policy=None,
        add_title: bool = True,
        add_inner_box: bool = True,
        parent=None,
        margins: tuple[int, int, int, int] | None = None,
        inner_orientation=Qt.Vertical,
        title_location: str = "left",
        title_width: int | None = None,
        title_vertical_alignment: str = "center",
    ) -> None:
        super().__init__("", parent)
        SectionGroupBox._instances.add(self)
        if object_name:
            self.setObjectName(object_name)

        # Default to expanding horizontally while only taking the vertical
        # space required unless an explicit policy was provided.
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum))
        if size_policy:
            self.setSizePolicy(size_policy)

        self._title_location = title_location if title_location in {"left", "top"} else "left"
        self._title_vertical_alignment = self._normalize_title_alignment(title_vertical_alignment)
        self._title_width = title_width if title_location == "left" else None
        self._title_layout: QVBoxLayout | None = None
        self._margins = margins if margins is not None else (5, 5, 5, 5)

        # Outer layout (title + content)
        self._create_outer_layout()

        # Optional title label (styled via #SectionOuterGroupLabel)
        self.title_label: QLabel | None = None
        self.title_container: QWidget | None = None
        if add_title and title:
            self._create_title_widgets(title)

        # Single container for inner groupboxes (created on demand)
        self._container_widget: QWidget | None = None
        self._container_layout: QVBoxLayout | QHBoxLayout | None = None
        self._container_orientation = inner_orientation

        # Track inner boxes and initial reuse behavior
        self.inner_boxes: list[tuple[QGroupBox, QVBoxLayout]] = []
        self._initial_inner_reused = False
        self.inner_groupbox: QGroupBox | None = None

        # Public content layout reference
        if add_inner_box:
            self._ensure_container()
            gb, content = self._create_inner_groupbox()
            self.inner_groupbox = gb
            self.content_layout = content  # backward compatibility
        else:
            self.inner_groupbox = None
            # Use a container widget for consistency and movability
            self._container_widget = QWidget(self, objectName="Transparent")
            self.content_layout = QVBoxLayout(self._container_widget)
            self.content_layout.setContentsMargins(0, 0, 0, 0)
            self.content_layout.setSpacing(WIDGET_SPACING)
            
            if isinstance(self.outer_layout, QHBoxLayout):
                self.outer_layout.addWidget(self._container_widget, 1)
            else:
                self.outer_layout.addWidget(self._container_widget)

    @classmethod
    def update_all_instances(cls, location: str):
        """Update title location for all active instances."""
        for instance in cls._instances:
            instance.set_title_location(location)

    def set_title_location(self, location: str):
        """Dynamically update the title location."""
        if location not in ("left", "top"):
            return
        if self._title_location == location:
            return
            
        self._title_location = location
        
        # 1. Preserve Title Label Text
        saved_title_text = None
        if self.title_label:
            saved_title_text = self.title_label.text()
            # Clean up old title widgets
            self.title_label.deleteLater()
            self.title_label = None
            
        if self.title_container:
            self.title_container.deleteLater()
            self.title_container = None
            self._title_layout = None

        # 2. Preserve Content
        saved_container_widget = self._container_widget
        
        # 3. Delete old outer layout
        if self.outer_layout:
            if saved_container_widget:
                self.outer_layout.removeWidget(saved_container_widget)
            QWidget().setLayout(self.outer_layout)
            self.outer_layout = None

        # 4. Create new outer layout (using shared helper)
        self._create_outer_layout()

        # 5. Recreate Title (using shared helper)
        if saved_title_text:
            self._create_title_widgets(saved_title_text)

        # 6. Restore Content
        if saved_container_widget:
            alignment = Qt.AlignTop if self.inner_groupbox is not None else Qt.Alignment()
            
            if isinstance(self.outer_layout, QHBoxLayout):
                self.outer_layout.addWidget(saved_container_widget, 1, alignment)
                self.outer_layout.setStretchFactor(saved_container_widget, 1)
            else:
                self.outer_layout.addWidget(saved_container_widget, 0, alignment)

    # --- helpers ---------------------------------------------------------
    def _ensure_container(self):
        if self._container_layout is not None:
            return
        cont = QWidget(self, objectName="Transparent")
        if self._container_orientation == Qt.Horizontal:
            layout = QHBoxLayout(cont)
        else:
            layout = QVBoxLayout(cont)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(WIDGET_SPACING)
        # Keep the collection of inner boxes aligned to the top
        layout.setAlignment(Qt.AlignTop)
        cont.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum))
        if isinstance(self.outer_layout, QHBoxLayout):
            self.outer_layout.addWidget(cont, 1, Qt.AlignTop)
            self.outer_layout.setStretchFactor(cont, 1)
        else:
            self.outer_layout.addWidget(cont, 0, Qt.AlignTop)
        self._container_widget = cont
        self._container_layout = layout

    def _apply_title_width(self):
        if not self.title_container:
            return
        # Use a single fixed width for the title column. If a width was
        # provided use it; otherwise fall back to TITLE_COLUMN_MIN_WIDTH.
        width = TITLE_COLUMN_MIN_WIDTH if self._title_width is None else max(0, self._title_width)
        # setFixedWidth is simpler and communicates intent: this column is fixed.
        self.title_container.setFixedWidth(width)

    def _label_alignment_flags(self) -> Qt.Alignment:
        vertical_flag = Qt.AlignTop
        if self._title_vertical_alignment == Qt.AlignVCenter:
            vertical_flag = Qt.AlignVCenter
        elif self._title_vertical_alignment == Qt.AlignBottom:
            vertical_flag = Qt.AlignBottom
        return Qt.AlignCenter | vertical_flag

    @staticmethod
    def _normalize_title_alignment(option: str) -> Qt.Alignment:
        if not isinstance(option, str):
            return Qt.AlignTop
        return TITLE_ALIGNMENT_MAP.get(option.lower(), Qt.AlignTop)

    def _create_outer_layout(self):
        """Create the outer layout based on title location."""
        if self._title_location == "left":
            self.outer_layout = QHBoxLayout(self)
        else:
            self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(*self._margins)
        self.outer_layout.setSpacing(WIDGET_SPACING)
    
    def _create_title_widgets(self, title_text: str):
        """Create title label and container based on title location.
        
        This is the shared logic used by both __init__ and set_title_location.
        """
        if self._title_location == "left":
            self.title_container = QWidget(self)
            self.title_container.setObjectName("Transparent")
            self.title_container.setProperty("sectionTitleArea", True)
            title_layout = QVBoxLayout(self.title_container)
            title_layout.setContentsMargins(0, 5, 0, 5)
            title_layout.setSpacing(4)
            title_layout.setAlignment(self._title_vertical_alignment)
            self._title_layout = title_layout

            self.title_label = QLabel(title_text, self.title_container)
            self.title_label.setObjectName("SectionOuterGroupLabel")
            self.title_label.setWordWrap(True)
            self.title_label.setAlignment(self._label_alignment_flags())
            self.title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            title_layout.addWidget(self.title_label)

            self._apply_title_width()
            self.title_container.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
            self.outer_layout.addWidget(self.title_container, 0, Qt.AlignLeft | self._title_vertical_alignment)
        else:
            self.title_label = QLabel(title_text, self)
            self.title_label.setObjectName("SectionOuterGroupLabel")
            self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.title_label.setAlignment(Qt.AlignCenter)
            self.outer_layout.addSpacing(5)
            self.outer_layout.addWidget(self.title_label)

    def _add_inner_title(self, content_layout: QVBoxLayout, text: str, parent: QWidget):
        """Insert a standard inner title label at the top of a card."""
        title_label = QLabel(text, parent)
        title_label.setObjectName("SectionInnerGroupLabel")
        title_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        content_layout.insertWidget(0, title_label, alignment=Qt.AlignLeft)

    def _build_group_card(
        self,
        parent_layout: QVBoxLayout | QHBoxLayout,
        *,
        title: str | None = None,
        margins: tuple[int, int, int, int] = (12, 12, 12, 12),
    ) -> tuple[QGroupBox, QVBoxLayout]:
        """Create a Section-style inner card (QGroupBox + VBox content) and add it to parent_layout."""
        gb = QGroupBox("", self)
        gb.setObjectName("SectionGroupBox")
        gb.setContentsMargins(0, 0, 0, 0)
        
        # If the container layout is horizontal (side-by-side), use Expanding vertical policy
        # so all inner boxes stretch to the same height
        if isinstance(self._container_layout, QHBoxLayout):
            gb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            gb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        
        parent_layout.addWidget(gb)

        content_layout = QVBoxLayout(gb)
        content_layout.setContentsMargins(*margins)
        content_layout.setSpacing(WIDGET_SPACING)
        content_layout.setAlignment(Qt.AlignTop)

        if title:
            self._add_inner_title(content_layout, title, gb)

        return gb, content_layout

    def _create_inner_groupbox(
        self,
        title: str | None = None,
        margins: tuple[int, int, int, int] = (12, 12, 12, 12),
    ) -> tuple[QGroupBox, QVBoxLayout]:
        """Create an inner QGroupBox with a VBox content layout."""
        self._ensure_container()
        gb, content_layout = self._build_group_card(self._container_layout, title=title, margins=margins)
        self.inner_boxes.append((gb, content_layout))
        return gb, content_layout

    def add_inner_column_stack(self, titles: list[str]) -> list[QVBoxLayout]:
        """Create a single column (one horizontal slot) containing multiple
        stacked inner groupboxes.

        Returns a list of content layouts for each created inner groupbox,
        in the same order as `titles`.
        """
        # Ensure container exists
        self._ensure_container()

        # If an initial inner_groupbox was created during __init__ and has
        # not been reused, it's an unused placeholder sitting as the first
        # child of the container. Remove it so our column occupies the
        # left-most slot instead of leaving a blank card.
        if (
            len(self.inner_boxes) == 1
            and getattr(self, "inner_groupbox", None) is not None
            and not self._initial_inner_reused
        ):
            try:
                gb0, content0 = self.inner_boxes.pop(0)
                # Remove widget from layout and detach
                try:
                    self._container_layout.removeWidget(gb0)
                except Exception:
                    pass
                gb0.setParent(None)
            except Exception:
                pass
            # Clear the public aliases if they pointed to the removed box
            if getattr(self, "content_layout", None) is content0:
                self.content_layout = None
            self.inner_groupbox = None
        # Create a transparent widget that will be the single column
        column = QWidget(self, objectName="Transparent")
        col_layout = QVBoxLayout(column)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(WIDGET_SPACING)
        col_layout.setAlignment(Qt.AlignTop)

        # Insert the column widget at the end of the container (left-to-right)
        self._container_layout.addWidget(column)

        created: list[QVBoxLayout] = []
        # For each requested title, create a QGroupBox inside the column
        for title in titles:
            gb, content_layout = self._build_group_card(col_layout, title=title, margins=(12, 12, 12, 12))
            self.inner_boxes.append((gb, content_layout))
            created.append(content_layout)

        return created

    def insert_inner_groupbox_at(
        self,
        index: int,
        title: str | None = None,
        margins: tuple[int, int, int, int] = (12, 12, 12, 12),
    ) -> QVBoxLayout:
        """Insert a new inner groupbox at a specific index in the container.

        This keeps the public API small: callers can create multiple stacked
        inner boxes by inserting one after the other (e.g. index 0 then index 1).
        Returns the new content layout.
        """
        # Ensure container exists
        self._ensure_container()

        # Build card at the end, then reposition to requested index
        gb, content_layout = self._build_group_card(self._container_layout, title=title, margins=margins)
        count = self._container_layout.count()
        insert_at = max(0, min(index, count - 1)) if count > 0 else 0
        self._container_layout.removeWidget(gb)
        self._container_layout.insertWidget(insert_at, gb)

        # Track order similarly in inner_boxes
        try:
            self.inner_boxes.remove((gb, content_layout))
        except ValueError:
            pass
        self.inner_boxes.insert(insert_at, (gb, content_layout))
        return content_layout

    # --- public API ------------------------------------------------------
    def add_inner_groupbox(
        self,
        title: str | None = None,
        margins: tuple[int, int, int, int] = (12, 12, 12, 12),
    ) -> QVBoxLayout:
        """Return a content layout of an inner box.

        First call reuses the initial inner box (created when add_inner_box=True)
        to avoid an unused placeholder box. Subsequent calls create new boxes.
        """
        # Reuse the initial inner box once
        if len(self.inner_boxes) == 1 and self.inner_groupbox is not None and not self._initial_inner_reused:
            gb, content = self.inner_boxes[0]
            if title:
                # Update or create the inner title label
                lbl = gb.findChild(QLabel, "SectionInnerGroupLabel")
                if lbl is not None:
                    lbl.setText(title)
                else:
                    self._add_inner_title(content, title, gb)
            # Ensure public alias
            self.content_layout = content
            self._initial_inner_reused = True
            return content

        # Otherwise create a new inner group box
        _gb, content = self._create_inner_groupbox(title=title, margins=margins)
        if not hasattr(self, "content_layout") or getattr(self, "content_layout", None) is None:
            self.content_layout = content
        return content

    def add_widget(self, widget):
        """Add a widget to the primary content layout."""
        self.content_layout.addWidget(widget)

    def set_title_vertical_alignment(self, alignment: str):
        """Adjust the vertical placement of the left-column title."""
        if self._title_location != "left":
            return
        flag = self._normalize_title_alignment(alignment)
        if flag == self._title_vertical_alignment:
            return
        self._title_vertical_alignment = flag
        if self._title_layout is not None:
            self._title_layout.setAlignment(flag)
        if self.title_label is not None:
            self.title_label.setAlignment(self._label_alignment_flags())
        if isinstance(self.outer_layout, QHBoxLayout) and self.title_container is not None:
            self.outer_layout.setAlignment(self.title_container, Qt.AlignCenter | flag)

    def set_title_width(self, width: int | None):
        """Set a fixed width for the title column; pass None to restore the default."""
        if self._title_location != "left":
            return
        self._title_width = width
        self._apply_title_width()
