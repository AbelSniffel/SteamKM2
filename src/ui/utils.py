"""Small UI utilities.

Currently contains clear_layout used by various pages/dialogs.
"""
from PySide6.QtWidgets import QLayout


def clear_layout(layout: QLayout):
    """Remove all widgets/items from a layout and delete their widgets.

    Safe for both standard and custom layouts (e.g., FlowLayout) that expose
    count(), takeAt(index), and return QLayoutItem with optional widget().
    """
    try:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget() if hasattr(item, 'widget') else None
            if w is not None:
                try:
                    w.deleteLater()
                except Exception:
                    pass
    except Exception:
        # Be permissive; callers shouldn't crash if layout is custom
        pass
