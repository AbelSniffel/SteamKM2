"""
Health monitor dialog for SteamKM2.
This dialog wraps the UI elements from the previous health monitor "window" and
belongs in the dialogs package so it follows the same layout as other modal/utility
windows in the application.
"""

from typing import Optional
import time
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QGridLayout, QScrollArea, QSizePolicy, QToolTip, QGroupBox
)
from PySide6.QtCore import Qt
from src.ui.config import HEALTH_MONITOR_GRAPH_HEIGHT
from src.ui.widgets.health_monitor_widgets import GraphWidget, MetricCard
from src.ui.widgets.main_widgets import create_scroll_area


class HealthMonitorDialog(QWidget):
    """Dialog wrapper for the health monitor window.

    For backwards compatibility the class name differs from the original window
    wrapper; callers should import this from `src.ui.dialogs`.
    """

    STATUS_CONFIG = {
        'healthy': {'color': '#1db954', 'message': 'Application is running normally'},
        'warning': {'color': '#ffbf3f', 'message': 'Performance warnings detected'},
        'error': {'color': '#ff6b35', 'message': 'Errors detected'},
        'critical': {'color': '#ff0000', 'message': 'Critical issues detected'}
    }

    def __init__(self, health_monitor, parent=None):
        super().__init__(parent)
        self.health_monitor = health_monitor
        self.parent_window = parent
        # Keep as top-level floating window; no minimize/maximize
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)

        self.setWindowTitle("Health Monitor")
        self.setFixedSize(580, 700)

        self._setup_ui()
        self._connect_signals()
        if self.health_monitor and hasattr(self.health_monitor, 'get_current_status'):
            self._on_status_changed(self.health_monitor.get_current_status())
        else:
            self._on_status_changed('healthy')

        initial_metrics = self.health_monitor.get_current_metrics() if self.health_monitor else None
        self._update_display(initial_metrics)
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        header_frame = QFrame()
        header_frame.setObjectName("page_navigation_bar")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setSpacing(8)
        header_layout.setContentsMargins(8, 4, 8, 4)

        title_label = QLabel("SKM2 Health Monitor")
        title_label.setObjectName("page_title")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        status_container = QWidget()
        status_container.setObjectName("Transparent")
        status_container.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(4)

        self.status_icon = QLabel("●")
        self.status_icon.setStyleSheet("font-size: 16px;")
        status_layout.addWidget(self.status_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self.status_label = QLabel("Application is running normally")
        self.status_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        status_layout.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignVCenter)

        header_layout.addWidget(status_container, 0, Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(header_frame)

        scroll_area = create_scroll_area(
            object_name="Health_Monitor",
            widget_resizable=True,
            frame_shape=QFrame.Shape.NoFrame,
        )

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self._setup_metrics_grid(content_layout)

        self.ram_graph = GraphWidget("Memory Usage", " MB", "#5f92ff")
        self.cpu_graph = GraphWidget("CPU Usage", "%", "#ff6b35")
        self.cpu_graph.set_range(0, 100)
        self.response_graph = GraphWidget("Response Time", " ms", "#1db954")

        for graph in [self.ram_graph, self.cpu_graph, self.response_graph]:
            graph.setFixedHeight(HEALTH_MONITOR_GRAPH_HEIGHT)
            content_layout.addWidget(graph)

        self._setup_issues_section(content_layout)
        content_layout.addStretch()
        scroll_area.setWidget(content_widget)

        content_outer = QWidget()
        content_outer_layout = QVBoxLayout(content_outer)
        content_outer_layout.setContentsMargins(8, 8, 8, 8)
        content_outer_layout.setSpacing(0)
        content_outer_layout.addWidget(scroll_area)
        main_layout.addWidget(content_outer)
        main_layout.setSpacing(0)
        self._setup_navigation_bar(main_layout)
        main_layout.setContentsMargins(0, 0, 0, 0)

    def _setup_metrics_grid(self, parent_layout):
        grid_layout = QGridLayout()
        grid_layout.setSpacing(5)

        cards = {
            'uptime': MetricCard("Uptime"),
            'threads': MetricCard("Threads"),
            'db_size': MetricCard("Database Size"),
            'theme_time': MetricCard("Last Theme Change"),
            'errors': MetricCard("Errors"),
            'warnings': MetricCard("Warnings")
        }

        self.uptime_card = cards['uptime']
        self.thread_count_card = cards['threads']
        self.db_size_card = cards['db_size']
        self.theme_time_card = cards['theme_time']
        self.errors_card = cards['errors']
        self.warnings_card = cards['warnings']

        positions = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
        for card, pos in zip(cards.values(), positions):
            grid_layout.addWidget(card, *pos)

        parent_layout.addLayout(grid_layout)

    def _create_quick_action_groupboxes(self):
        util_group = QGroupBox()
        util_group.setTitle("")
        util_group.setFlat(True)
        util_layout = QHBoxLayout(util_group)
        util_layout.setContentsMargins(5, 5, 5, 5)
        util_layout.setSpacing(6)
        from src.ui.widgets.main_widgets import create_push_button
        for text, handler in [
            ("🗑️ Clear Issues", self._clear_issues),
            ("♻️ Run GC", self._run_gc),
            ("📤 Export Log", self._export_issue_log),
        ]:
            btn = create_push_button(text)
            btn.clicked.connect(handler)
            util_layout.addWidget(btn)
        util_layout.addStretch()

        debug_group = QGroupBox()
        debug_group.setTitle("")
        debug_group.setFlat(True)
        debug_layout = QHBoxLayout(debug_group)
        debug_layout.setContentsMargins(5, 5, 5, 5)
        debug_layout.setSpacing(6)
        for text, handler in [
            ("🔄 Dev Update", self._trigger_test_update),
            ("🧪 Simulate Issues", self._simulate_issues)
        ]:
            btn = create_push_button(text)
            btn.clicked.connect(handler)
            debug_layout.addWidget(btn)
        debug_layout.addStretch()

        return util_group, debug_group

    def set_debug_controls_visible(self, visible: bool):
        """Show or hide the debug action button group (dev update / simulate issues)."""
        try:
            if hasattr(self, 'debug_group') and self.debug_group is not None:
                self.debug_group.setVisible(bool(visible))
                # Force a geometry/layout refresh in case the change affects sizing
                try:
                    self.updateGeometry()
                except Exception:
                    pass
        except Exception:
            pass

    def _setup_navigation_bar(self, parent_layout):
        nav_frame = QFrame()
        nav_frame.setObjectName("page_navigation_bar")
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setSpacing(0)
        nav_layout.setContentsMargins(4, 4, 4, 4)

        util_group, debug_group = self._create_quick_action_groupboxes()
        # Keep references so we can toggle the debug action group dynamically
        self.util_group = util_group
        self.debug_group = debug_group
        util_group.setObjectName("page_navigation_button_groupbox")
        debug_group.setObjectName("page_navigation_button_groupbox")
        nav_layout.addWidget(util_group)
        nav_layout.addStretch()
        nav_layout.addWidget(debug_group)

        parent_layout.addWidget(nav_frame)

        # Apply initial visibility preference for debug buttons from settings (default True)
        try:
            # Use the new global debug_mode flag only
            visible = self.parent_window.settings_manager.get_bool(
                'debug_mode', True
            ) if (self.parent_window and hasattr(self.parent_window, 'settings_manager')) else True
            self.set_debug_controls_visible(visible)
        except Exception:
            pass

    def _setup_issues_section(self, parent_layout):
        issues_frame = QFrame()
        issues_frame.setFrameStyle(QFrame.Shape.Box)
        issues_layout = QVBoxLayout(issues_frame)
        issues_layout.setContentsMargins(5, 5, 5, 5)
        issues_layout.setSpacing(3)

        label = QLabel("Issue Log")
        label.setStyleSheet("font-weight: bold; font-size: 11px;")
        issues_layout.addWidget(label)

        self.issue_log_label = QLabel("No logged issues")
        self.issue_log_label.setStyleSheet("font-size: 11px;")
        self.issue_log_label.setWordWrap(True)
        issues_layout.addWidget(self.issue_log_label)

        parent_layout.addWidget(issues_frame)

    def _connect_signals(self):
        if self.health_monitor:
            try:
                self.health_monitor.metrics_updated.connect(self._update_display, Qt.ConnectionType.UniqueConnection)
            except Exception:
                self.health_monitor.metrics_updated.connect(self._update_display)
            try:
                self.health_monitor.status_changed.connect(self._on_status_changed, Qt.ConnectionType.UniqueConnection)
            except Exception:
                self.health_monitor.status_changed.connect(self._on_status_changed)

    def _disconnect_signals(self):
        if not self.health_monitor:
            return
        try:
            self.health_monitor.metrics_updated.disconnect(self._update_display)
        except (RuntimeError, TypeError):
            pass
        try:
            self.health_monitor.status_changed.disconnect(self._on_status_changed)
        except (RuntimeError, TypeError):
            pass

    def _update_display(self, metrics=None):
        if not self.health_monitor:
            return
        if metrics is None:
            metrics = self.health_monitor.get_current_metrics()
        if metrics is None:
            return

        uptime = int(metrics.uptime_seconds)
        self.uptime_card.set_value(f"{uptime//3600:02d}:{(uptime%3600)//60:02d}:{uptime%60:02d}")
        self.thread_count_card.set_value(str(metrics.thread_count))
        self.db_size_card.set_value(f"{metrics.database_size_mb:.1f} MB")
        self.theme_time_card.set_value(f"{metrics.theme_change_time_ms:.1f} ms" if metrics.theme_change_time_ms > 0 else "N/A")
        self.errors_card.set_value(str(metrics.error_count))
        self.warnings_card.set_value(str(metrics.warning_count))

        self.ram_graph.set_data(self.health_monitor.get_ram_history())
        self.cpu_graph.set_data(self.health_monitor.get_cpu_history())
        self.response_graph.set_data(self.health_monitor.get_response_history())

        issues = self.health_monitor.get_current_issues()
        if issues:
            snippets = []
            for issue in issues[-10:]:
                timestamp = time.strftime("%H:%M:%S", time.localtime(issue.timestamp))
                snippets.append(f"{timestamp} • [{issue.severity.upper()}] {issue.message}")
            self.issue_log_label.setText("\n".join(snippets))
        else:
            self.issue_log_label.setText("No logged issues")

    def _on_status_changed(self, status: str):
        config = self.STATUS_CONFIG.get(status, {'color': '#888888', 'message': 'Unknown status'})
        self.status_icon.setStyleSheet(f"color: {config['color']}; font-size: 16px;")
        self.status_label.setText(config['message'])

    def _trigger_test_update(self):
        if self.parent_window:
            try:
                if hasattr(self.parent_window, 'update_coordinator'):
                    self.parent_window.update_coordinator.trigger_test_update()
                elif hasattr(self.parent_window, 'update_manager'):
                    self.parent_window.update_manager.trigger_test_update()
            except Exception:
                pass

    def _clear_issues(self):
        if self.health_monitor:
            self.health_monitor.clear_issues()
        self._update_display()

    def _run_gc(self):
        import gc
        before = len(gc.get_objects())
        gc.collect()
        after = len(gc.get_objects())
        if self.health_monitor:
            self.health_monitor.log_info(f"GC completed: cleaned {before - after} objects")

    def _simulate_issues(self):
        if self.health_monitor:
            self.health_monitor.simulate_issue_sequence()

    def _export_issue_log(self):
        if not self.health_monitor:
            return
        issues = self.health_monitor.get_issue_log()
        export_time = datetime.now()
        export_dir = Path.cwd() / "output"
        try:
            export_dir.mkdir(parents=True, exist_ok=True)
            filename = f"health_log_{export_time:%Y%m%d_%H%M%S}.txt"
            export_path = export_dir / filename

            header = f"SteamKM2 Health Monitor Export – {export_time:%Y-%m-%d %H:%M:%S}"
            lines = [header, "=" * len(header), ""]

            if not issues:
                lines.append("No issues recorded.")
            else:
                for issue in issues:
                    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(issue.timestamp))
                    lines.append(f"[{ts}] [{issue.severity.upper()}] {issue.message}")

            export_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.health_monitor.log_info(f"Health log exported to {export_path}")
        except Exception as exc:
            if self.health_monitor:
                self.health_monitor.log_warning(f"Failed to export health log: {exc}")

    def closeEvent(self, event):
        self._disconnect_signals()
        if self.parent_window and hasattr(self.parent_window, 'health_monitor_window'):
            self.parent_window.health_monitor_window = None
        event.accept()
        # Expose the same public API expected by the main window (isVisible/close) by
        # implementing the default QWidget methods; callers can show this as a
        # floating dialog.
