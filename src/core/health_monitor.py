"""
Health monitoring system for SteamKM2
Tracks application performance, resource usage, and system health
"""

import os
import psutil
import time
from typing import List, Dict, Any, Optional, Deque
from dataclasses import dataclass, asdict
from collections import deque
from PySide6.QtCore import QObject, Signal, QTimer


@dataclass
class HealthMetrics:
    """Container for health metrics data"""
    ram_usage_mb: float = 0.0
    ram_percent: float = 0.0
    cpu_percent: float = 0.0
    thread_count: int = 0
    response_time_ms: float = 0.0
    error_count: int = 0
    warning_count: int = 0
    theme_change_time_ms: float = 0.0
    uptime_seconds: float = 0.0
    database_size_mb: float = 0.0
    last_update: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        return asdict(self)


@dataclass
class HealthIssue:
    """Represents a health issue/warning"""
    severity: str  # 'info', 'warning', 'error', 'critical'
    message: str
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MetricPoint:
    """Represents a single metric sample."""
    timestamp: float
    value: float


class HealthMonitor(QObject):
    """
    Monitors application health and performance metrics
    """
    
    metrics_updated = Signal(object)  # HealthMetrics
    issue_detected = Signal(object)  # HealthIssue
    status_changed = Signal(str)  # overall status: 'healthy', 'warning', 'error', 'critical'
    
    # Thresholds for warnings
    THRESHOLDS = {
        'ram_warning': 500,
        'ram_critical': 1000,
        'cpu_warning': 50,
        'cpu_critical': 80,
        'response_warning': 100,
        'response_critical': 500,
    }

    HISTORY_LENGTH = 100
    ISSUE_LOG_LENGTH = 200
    DB_SIZE_CACHE_TTL = 5.0  # seconds
    
    def __init__(self, settings_manager=None, db_manager=None, theme_manager=None):
        super().__init__()
        
        self.db_manager = db_manager
        self.current_metrics = HealthMetrics()
        self.start_time = time.time()
        
        # Combined history tracking (keep last HISTORY_LENGTH data points)
        self.history: Dict[str, Deque[MetricPoint]] = {
            'ram': deque(maxlen=self.HISTORY_LENGTH),
            'cpu': deque(maxlen=self.HISTORY_LENGTH),
            'response': deque(maxlen=self.HISTORY_LENGTH),
        }
        
        # Issue tracking
        self.issue_log: Deque[HealthIssue] = deque(maxlen=self.ISSUE_LOG_LENGTH)
        self._issue_counts = {'warning': 0, 'error': 0, 'critical': 0}
        self._threshold_states: Dict[str, HealthIssue] = {}
        self._manual_states: Dict[str, HealthIssue] = {}
        self._current_status = 'healthy'
        
        # Cache process info
        self._process = psutil.Process(os.getpid())
        self._db_path = getattr(db_manager, 'db_path', None) if db_manager else None
        self._db_size_cache = {'value': 0.0, 'expires': 0.0}
        
        # Update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._collect_metrics)
        self.update_interval_ms = 1000
        
        # Theme change tracking
        self.last_theme_change_time = 0.0
        if theme_manager:
            try:
                theme_manager.theme_applied.connect(self._on_theme_applied)
            except Exception:
                pass
        
        # Initial collection
        self._collect_metrics()
    
    def start(self):
        """Start monitoring"""
        if not self.update_timer.isActive():
            self.update_timer.start(self.update_interval_ms)
    
    def stop(self):
        """Stop monitoring"""
        self.update_timer.stop()
    
    def set_update_interval(self, interval_ms: int):
        """Set the update interval in milliseconds"""
        self.update_interval_ms = max(100, interval_ms)  # Minimum 100ms
        if self.update_timer.isActive():
            self.update_timer.stop()
            self.update_timer.start(self.update_interval_ms)
    
    def _collect_metrics(self):
        """Collect current metrics"""
        try:
            start = time.perf_counter()
            
            # Memory and CPU (single call each)
            mem_info = self._process.memory_info()
            self.current_metrics.ram_usage_mb = mem_info.rss / 1048576  # bytes to MB
            self.current_metrics.ram_percent = self._process.memory_percent()
            self.current_metrics.cpu_percent = self._process.cpu_percent(interval=0)
            
            # Thread count (with fallback)
            try:
                self.current_metrics.thread_count = self._process.num_threads()
            except Exception:
                self.current_metrics.thread_count = 0
            
            # Uptime and timestamp
            current_time = time.time()
            self.current_metrics.uptime_seconds = current_time - self.start_time
            self.current_metrics.last_update = current_time
            
            # Database size with lightweight caching
            if self._db_path:
                self.current_metrics.database_size_mb = self._get_database_size_mb(current_time)
            
            # Response time measurement
            self.current_metrics.response_time_ms = (time.perf_counter() - start) * 1000
            
            # Counters and theme time
            self._update_issue_counts_in_metrics()
            self.current_metrics.theme_change_time_ms = self.last_theme_change_time
            
            # Add to history
            self._append_history('ram', current_time, self.current_metrics.ram_usage_mb)
            self._append_history('cpu', current_time, self.current_metrics.cpu_percent)
            self._append_history('response', current_time, self.current_metrics.response_time_ms)
            
            # Check for issues and emit
            self._check_health()
            self.metrics_updated.emit(self.current_metrics)
            
        except Exception as e:
            self._log_error(f"Error collecting metrics: {e}")
    
    def _check_health(self):
        """Check metrics against thresholds and detect issues"""
        m = self.current_metrics
        t = self.THRESHOLDS
        checks = [
            (m.ram_usage_mb, t['ram_critical'], t['ram_warning'], 'memory usage', 'MB'),
            (m.cpu_percent, t['cpu_critical'], t['cpu_warning'], 'CPU usage', '%'),
            (m.response_time_ms, t['response_critical'], t['response_warning'], 'response time', 'ms'),
        ]
        
        new_states: Dict[str, HealthIssue] = {}
        for value, critical, warning, name, unit in checks:
            key = name.replace(' ', '_')
            severity = None
            message = None
            if value > critical:
                severity = 'critical'
                message = f'Critical {name}: {value:.1f}{unit}'
            elif value > warning:
                severity = 'warning'
                message = f'High {name}: {value:.1f}{unit}'
            
            previous_issue = self._threshold_states.get(key)
            if severity:
                issue = HealthIssue(severity, message)
                new_states[key] = issue
                if not previous_issue or previous_issue.severity != severity:
                    self._record_issue(issue)
            elif previous_issue:
                recovery = f'{name.capitalize()} returned to normal ({value:.1f}{unit})'
                self._record_issue(HealthIssue('info', recovery))
        
        self._threshold_states = new_states
        self._update_status_from_active()
    
    def _on_theme_applied(self, duration_ms: float):
        """Track theme change time"""
        self.last_theme_change_time = duration_ms
    
    def _log_error(self, message: str):
        """Log an error"""
        self._record_issue(HealthIssue('error', message))
        self._activate_manual_issue('manual_error', 'error', message, duration_ms=4000)
    
    def log_warning(self, message: str):
        """Log a warning"""
        self._record_issue(HealthIssue('warning', message))
        self._activate_manual_issue('manual_warning', 'warning', message, duration_ms=3000)
    
    def log_info(self, message: str):
        """Log an info message"""
        self._record_issue(HealthIssue('info', message))
    
    def get_current_metrics(self) -> HealthMetrics:
        """Get current metrics snapshot"""
        return self.current_metrics
    
    def get_history(self, metric_type: str) -> List[MetricPoint]:
        """Get history for specified metric type ('ram', 'cpu', or 'response')"""
        return list(self.history.get(metric_type, []))
    
    # Compatibility methods
    def get_ram_history(self) -> List[MetricPoint]:
        return self.get_history('ram')
    
    def get_cpu_history(self) -> List[MetricPoint]:
        return self.get_history('cpu')
    
    def get_response_history(self) -> List[MetricPoint]:
        return self.get_history('response')
    
    def get_current_issues(self) -> List[HealthIssue]:
        """Get the logged issues"""
        return list(self.issue_log)

    def get_issue_log(self) -> List[HealthIssue]:
        """Alias for logged issues to clarify intent."""
        return list(self.issue_log)

    def get_active_issues(self) -> List[HealthIssue]:
        """Return currently active issues detected by monitors."""
        return list(self._threshold_states.values()) + list(self._manual_states.values())
    
    def get_status_summary(self) -> str:
        """Get a human-readable status summary"""
        active = self.get_active_issues()
        if not active:
            return "Application is running normally"
        count = len(active)
        severity_map = {
            'critical': f"Critical issues detected ({count} issues)",
            'error': f"Errors detected ({count} errors)",
            'warning': f"Performance warnings ({count} warnings)"
        }
        return severity_map.get(self._current_status, "Application is running normally")
    
    def clear_issues(self):
        """Clear all current issues"""
        self.issue_log.clear()
        for key in self._issue_counts:
            self._issue_counts[key] = 0
        self._threshold_states.clear()
        self._manual_states.clear()
        self._update_issue_counts_in_metrics()
        self._update_status_from_active()
        self.metrics_updated.emit(self.current_metrics)
    
    def reset_counters(self):
        """Reset error and warning counters (compatibility)"""
        self.clear_issues()

    def get_current_status(self) -> str:
        """Expose the current health status."""
        return self._current_status

    def simulate_issue_sequence(self):
        """Simulate a sequence of issues for testing."""
        sequence = [
            ('warning', 'Simulated memory pressure detected'),
            ('error', 'Simulated database timeout encountered'),
            ('critical', 'Simulated CPU saturation detected'),
            ('info', 'Simulation complete, systems nominal')
        ]
        delay_step = 1500
        for index, (severity, message) in enumerate(sequence):
            QTimer.singleShot(delay_step * index, lambda s=severity, msg=message: self._simulate_issue_entry(s, msg))

    # Internal helpers
    def _record_issue(self, issue: HealthIssue):
        self.issue_log.append(issue)
        if issue.severity in self._issue_counts:
            self._issue_counts[issue.severity] += 1
        self._update_issue_counts_in_metrics()
        self.issue_detected.emit(issue)

    def _update_issue_counts_in_metrics(self):
        self.current_metrics.error_count = self._issue_counts['error'] + self._issue_counts['critical']
        self.current_metrics.warning_count = self._issue_counts['warning']

    def _update_status_from_active(self):
        active = [issue.severity for issue in self._threshold_states.values()]
        active.extend(issue.severity for issue in self._manual_states.values())
        self._set_status(self._determine_status(active))

    def _set_status(self, status: str):
        if status != self._current_status:
            self._current_status = status
            self.status_changed.emit(status)

    @staticmethod
    def _determine_status(severities: List[str]) -> str:
        if not severities:
            return 'healthy'
        if 'critical' in severities:
            return 'critical'
        if 'error' in severities:
            return 'error'
        if 'warning' in severities:
            return 'warning'
        return 'healthy'

    def _activate_manual_issue(self, key: str, severity: str, message: str, duration_ms: int = 3000):
        if severity not in {'warning', 'error', 'critical'}:
            return
        # Allow overlapping manual entries by namespacing key
        unique_key = f"{key}_{time.time_ns()}"
        self._manual_states[unique_key] = HealthIssue(severity, message)
        self._update_status_from_active()

        def clear_manual():
            self._manual_states.pop(unique_key, None)
            self._update_status_from_active()

        QTimer.singleShot(duration_ms, clear_manual)

    def _simulate_issue_entry(self, severity: str, message: str):
        self._record_issue(HealthIssue(severity, message))
        self._activate_manual_issue('simulation', severity, message, duration_ms=4000)

    def _get_database_size_mb(self, current_time: float) -> float:
        """Return cached DB size, refreshing at most every DB_SIZE_CACHE_TTL seconds."""
        cache = self._db_size_cache
        if current_time < cache['expires']:
            return cache['value']

        size_mb = cache['value']
        try:
            path = self._db_path
            if not path:
                cache['value'] = 0.0
                cache['expires'] = current_time + self.DB_SIZE_CACHE_TTL
                return 0.0

            if os.path.exists(path):
                size_mb = os.path.getsize(path) / 1048576
            else:
                size_mb = 0.0
        except Exception:
            # Keep previous cached value on failure
            size_mb = cache['value']

        cache['value'] = size_mb
        cache['expires'] = current_time + self.DB_SIZE_CACHE_TTL
        return size_mb

    def _append_history(self, key: str, timestamp: float, value: float) -> None:
        """Append a metric sample to the requested history deque."""
        history = self.history.get(key)
        if history is None:
            return
        history.append(MetricPoint(timestamp=timestamp, value=value))
