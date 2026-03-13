"""
Search and animation handler for Settings Page.
Handles search functionality, highlighting, and fade animations.
"""

from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QComboBox, QLineEdit, QListWidget
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtGui import QColor
from src.ui.widgets.toggles import MultiStepToggle


class SearchAnimationHandler:
    """Handles search, highlighting, and animations for settings page"""
    
    def __init__(self, settings_page):
        """
        Initialize handler with reference to parent SettingsPage
        
        Args:
            settings_page: The parent SettingsPage instance
        """
        self.page = settings_page
        self.theme_manager = settings_page.theme_manager
        
        # Track active blink animations for search matches
        self._active_blink_animations = []
        
        # Track animation sequence to stagger start times
        self._animation_sequence_counter = 0
        
        # Track pending animation timers (for QTimer.singleShot delays)
        self._pending_animation_timers = []
        
        # Cache for search text to avoid repeated findChildren calls
        self._widget_text_cache = {}
    
    def cache_widget_text(self, record):
        """Pre-cache all searchable text from a section widget"""
        widget = record.widget
        if widget is None:
            return
        
        widget_id = id(widget)
        fragments = []
        
        # Include title if present
        title_label = getattr(widget, 'title_label', None)
        if title_label:
            text = title_label.text()
            if text:
                fragments.append(text.strip())
        
        # Collect all searchable text
        fragments.extend(self.collect_widget_text(widget))
        
        # Store as lowercase for case-insensitive search
        self._widget_text_cache[widget_id] = ' '.join(fragments).lower()
    
    def collect_widget_text(self, widget) -> list[str]:
        """Collect all searchable text from a widget and its children"""
        fragments = []
        
        # Collect text from various widget types
        for lbl in widget.findChildren(QLabel):
            if text := lbl.text():
                fragments.append(text.strip())
        
        for btn in widget.findChildren(QPushButton):
            if text := btn.text():
                fragments.append(text.strip())
        
        for combo in widget.findChildren(QComboBox):
            if current := combo.currentText():
                fragments.append(current.strip())
            fragments.extend(combo.itemText(i).strip() for i in range(combo.count()) if combo.itemText(i))
        
        for edit in widget.findChildren(QLineEdit):
            if text := edit.text():
                fragments.append(text.strip())
            if placeholder := edit.placeholderText():
                fragments.append(placeholder.strip())
        
        for list_widget in widget.findChildren(QListWidget):
            for i in range(list_widget.count()):
                if (item := list_widget.item(i)) and (text := item.text()):
                    fragments.append(text.strip())
        
        # Collect text from MultiStepToggle widgets
        for toggle in widget.findChildren(MultiStepToggle):
            if options := getattr(toggle, '_options', None):
                fragments.extend(opt.strip() for opt in options if opt)
        
        return [f for f in fragments if f]
    
    def section_matches(self, record, query: str) -> bool:
        """Check if section matches query using cached text"""
        widget = record.widget
        if widget is None:
            return False
        
        widget_id = id(widget)
        haystack = self._widget_text_cache.get(widget_id, '')
        
        # If cache is empty (shouldn't happen), fall back to collection
        if not haystack:
            fragments = []
            title_label = getattr(widget, 'title_label', None)
            if title_label:
                text = title_label.text()
                if text:
                    fragments.append(text.strip())
            fragments.extend(self.collect_widget_text(widget))
            haystack = ' '.join(fragments).lower()
            self._widget_text_cache[widget_id] = haystack
        
        return query in haystack
    
    def find_matching_widgets(self, widget: QWidget, query: str) -> list[QWidget]:
        """Find specific widgets that match the search query, preferring inner groupboxes."""
        if widget is None:
            return []
        
        matching_widgets = []
        
        # First check if there are inner groupboxes (QGroupBox with objectName "SectionGroupBox")
        from PySide6.QtWidgets import QGroupBox
        
        inner_groupboxes = []
        # Find all QGroupBox children with objectName "SectionGroupBox"
        all_groupboxes = widget.findChildren(QGroupBox)
        for groupbox in all_groupboxes:
            if groupbox.objectName() == "SectionGroupBox":
                inner_groupboxes.append(groupbox)
        
        # If we have inner groupboxes, check which ones contain the matching text
        if inner_groupboxes:
            for groupbox in inner_groupboxes:
                if self.widget_contains_query(groupbox, query):
                    matching_widgets.append(groupbox)
        
        return matching_widgets
    
    def widget_contains_query(self, widget: QWidget, query: str) -> bool:
        """Check if a widget or its children contain the query text."""
        if widget is None:
            return False
        
        # Try to use cache first for efficiency
        widget_id = id(widget)
        haystack = self._widget_text_cache.get(widget_id)
        
        # If not cached (inner groupboxes), collect on-demand
        if haystack is None:
            fragments = self.collect_widget_text(widget)
            haystack = ' '.join(fragments).lower()
        
        return query in haystack
    
    def cleanup_all_animations(self):
        """Stop all active animations and restore original styles"""
        # Stop all pending animation timers
        for timer in self._pending_animation_timers:
            try:
                if timer and timer.isActive():
                    timer.stop()
            except RuntimeError:
                pass
        self._pending_animation_timers.clear()
        
        # Stop all active animations and restore styles
        for anim_data in self._active_blink_animations:
            try:
                widget = anim_data.get('widget')
                original_style = anim_data.get('original_style', '')
                
                # Stop animations
                for anim in anim_data.get('animations', []):
                    if anim and anim.state() == QPropertyAnimation.State.Running:
                        anim.stop()
                
                # Stop timers
                for timer in anim_data.get('timers', []):
                    if timer and timer.isActive():
                        timer.stop()
                
                # Restore original stylesheet and remove graphics effect
                if widget:
                    widget.setStyleSheet(original_style)
                    if widget.graphicsEffect():
                        widget.setGraphicsEffect(None)
                
                # Clean up dummy widget
                if dummy := anim_data.get('dummy'):
                    dummy.deleteLater()
                    
            except (RuntimeError, AttributeError):
                pass
        
        self._active_blink_animations.clear()
    
    def apply_fade_highlight(self, widget: QWidget):
        """Apply a smooth fade highlight animation with staggered timing and persistent highlight."""
        if widget is None or not widget.isVisible():
            return

        # Calculate staggered delay (100ms between each widget, max 1500ms)
        stagger_delay = min(self._animation_sequence_counter * 100, 1500)
        
        # Create a timer for the staggered delay and track it
        delay_timer = QTimer()
        delay_timer.setSingleShot(True)
        delay_timer.setInterval(stagger_delay)
        self._pending_animation_timers.append(delay_timer)
        
        # Function to start the animation (called after delay)
        def start_animation():
            # Remove this timer from pending list
            if delay_timer in self._pending_animation_timers:
                self._pending_animation_timers.remove(delay_timer)
            
            # Double-check widget is still valid and visible
            if widget is None or not widget.isVisible():
                return
            
            try:
                # Store original stylesheet
                original_style = widget.styleSheet()
                
                # Get the search highlight color and base background color from palette
                palette = self.theme_manager.get_palette()
                
                # Use the dedicated search highlight color
                highlight_color_str = palette.get('search_highlight_color', palette.get('base_accent', '#4a9eff'))
                base_bg_color_str = palette.get('inner_groupbox_background', palette.get('groupbox_background', '#2a2a2a'))
                
                # Parse colors
                highlight_qcolor = QColor(highlight_color_str)
                base_bg_qcolor = QColor(base_bg_color_str)
                
                # Get widget's object name for specific styling
                obj_name = widget.objectName()
                
                # Animation phases: fade in -> stay highlighted -> fade back
                phase = [0]  # Use list to allow modification in nested function
                
                def interpolate_color(color_from: QColor, color_to: QColor, progress: float) -> str:
                    """Smoothly interpolate between two colors"""
                    r = int(color_from.red() + (color_to.red() - color_from.red()) * progress)
                    g = int(color_from.green() + (color_to.green() - color_from.green()) * progress)
                    b = int(color_from.blue() + (color_to.blue() - color_from.blue()) * progress)
                    a = int(color_from.alpha() + (color_to.alpha() - color_from.alpha()) * progress)
                    return f"rgba({r}, {g}, {b}, {a})"
                
                def update_style(progress):
                    """Update style based on animation progress"""
                    try:
                        if not widget or not widget.isVisible():
                            return
                        
                        if phase[0] == 0:  # Fade in phase (base -> highlight)
                            current_color = interpolate_color(base_bg_qcolor, highlight_qcolor, progress)
                            
                            if obj_name == "SectionGroupBox":
                                style = f"""
                                    QGroupBox#SectionGroupBox {{
                                        background-color: {current_color};
                                    }}
                                """
                                widget.setStyleSheet(style)
                            else:
                                widget.setStyleSheet(f"background-color: {current_color};")
                            
                            if progress >= 1.0:
                                phase[0] = 1
                        
                        elif phase[0] == 1:  # Hold phase - keep highlighted
                            pass
                        
                        elif phase[0] == 2:  # Fade out phase (highlight -> base)
                            current_color = interpolate_color(highlight_qcolor, base_bg_qcolor, progress)
                            
                            if obj_name == "SectionGroupBox":
                                style = f"""
                                    QGroupBox#SectionGroupBox {{
                                        background-color: {current_color};
                                    }}
                                """
                                widget.setStyleSheet(style)
                            else:
                                widget.setStyleSheet(f"background-color: {current_color};")
                            
                            if progress >= 1.0:
                                # Restore original style completely
                                widget.setStyleSheet(original_style)
                    except RuntimeError:
                        # Widget was deleted
                        pass
                
                # Create a graphics opacity effect for smooth property animation
                opacity_effect = QGraphicsOpacityEffect()
                opacity_effect.setOpacity(1.0)
                
                # Create a dummy widget to hold the effect
                dummy = QWidget()
                dummy.setParent(widget)
                dummy.hide()
                dummy.setGraphicsEffect(opacity_effect)
                
                # Phase 1: Fade in
                fade_in_anim = QPropertyAnimation(opacity_effect, b"opacity")
                fade_in_anim.setDuration(700)
                fade_in_anim.setStartValue(0.0)
                fade_in_anim.setEndValue(1.0)
                fade_in_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                
                def on_fade_in_progress(value):
                    progress = float(value)
                    update_style(progress)
                
                fade_in_anim.valueChanged.connect(on_fade_in_progress)
                
                # Phase 2: Hold timer
                hold_timer = QTimer()
                hold_timer.setSingleShot(True)
                hold_timer.setInterval(1000)
                
                # Phase 3: Fade out
                fade_out_anim = QPropertyAnimation(opacity_effect, b"opacity")
                fade_out_anim.setDuration(700)
                fade_out_anim.setStartValue(1.0)
                fade_out_anim.setEndValue(0.0)
                fade_out_anim.setEasingCurve(QEasingCurve.Type.InCubic)
                
                def on_fade_out_progress(value):
                    progress = 1.0 - float(value)
                    update_style(progress)
                
                fade_out_anim.valueChanged.connect(on_fade_out_progress)
                
                # Connect phases
                def start_hold():
                    phase[0] = 1
                    hold_timer.start()
                
                def start_fade_out():
                    phase[0] = 2
                    fade_out_anim.start()
                
                fade_in_anim.finished.connect(start_hold)
                hold_timer.timeout.connect(start_fade_out)
                
                # Clean up after animation finishes
                def cleanup():
                    try:
                        if widget:
                            widget.setStyleSheet(original_style)
                        if opacity_effect:
                            opacity_effect.deleteLater()
                        if dummy:
                            dummy.deleteLater()
                        # Remove from active animations list
                        for anim_data in self._active_blink_animations[:]:
                            if anim_data.get('widget') == widget:
                                self._active_blink_animations.remove(anim_data)
                                break
                    except RuntimeError:
                        pass
                
                fade_out_anim.finished.connect(cleanup)
                
                # Store animation data for cleanup
                anim_data = {
                    'animation': fade_in_anim,
                    'widget': widget,
                    'original_style': original_style,
                    'dummy': dummy,
                    'timers': [hold_timer],
                    'animations': [fade_in_anim, fade_out_anim]
                }
                self._active_blink_animations.append(anim_data)
                
                # Start the fade-in animation
                fade_in_anim.start()
                
            except Exception:
                # Silently handle any errors to prevent crashes
                pass
        
        # Connect and start the delay timer
        delay_timer.timeout.connect(start_animation)
        delay_timer.start()
    
    def reset_animation_counter(self):
        """Reset the animation sequence counter"""
        self._animation_sequence_counter = 0
    
    def increment_animation_counter(self):
        """Increment the animation sequence counter"""
        self._animation_sequence_counter += 1
