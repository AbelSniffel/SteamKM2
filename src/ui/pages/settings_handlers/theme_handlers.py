"""
Theme-related handlers for Settings Page.
Contains theme customization, color picking, and radius adjustment handlers.
"""

from PySide6.QtWidgets import QColorDialog, QMessageBox, QApplication
from PySide6.QtGui import QColor


class ThemeHandlers:
    """Mixin class containing theme-related handlers for SettingsPage."""
    
    # =========================================================================
    # Color Handlers
    # =========================================================================
    
    def _get_effective_color(self, key):
        """Get the effective color for a theme key, handling gradient fallbacks."""
        theme = self.theme_manager.current_theme
        if key == 'gradient_color1':
            return theme.get('gradient_color1', theme.get('base_primary', '#000000'))
        elif key == 'gradient_color2':
            return theme.get('gradient_color2', theme.get('base_accent', '#000000'))
        return theme.get(key, '#000000')
    
    def _pick_theme_color(self, key: str):
        """Pick a color for a theme element and apply efficiently."""
        initial = self._get_effective_color(key)
        color = QColorDialog.getColor(QColor(initial), self)
        if not color.isValid():
            return
        
        hexval = color.name()
        
        if key in ('base_background', 'base_primary', 'base_accent'):
            bg = hexval if key == 'base_background' else None
            pr = hexval if key == 'base_primary' else None
            ac = hexval if key == 'base_accent' else None
            self.theme_manager.set_base_colors(background=bg, primary=pr, accent=ac)
        else:
            self.theme_manager.current_theme[key] = hexval
            self.theme_manager.invalidate_cache()
            if app := QApplication.instance():
                self.theme_manager.apply_theme(app)
            self._safe_theme_changed()
        
        if btn := self.theme_color_buttons.get(key):
            self._set_primary_color(btn, hexval)
        
        self.status_message.emit(f"{key.replace('_', ' ').title()} set to {hexval}")
    
    def _on_gradient_color_changed(self, color_key: str, hex_color: str):
        """Handle gradient color change from the gradient color picker widget."""
        self.theme_manager.current_theme[color_key] = hex_color
        self.theme_manager.invalidate_cache()
        
        if app := QApplication.instance():
            self.theme_manager.apply_theme(app)
        
        self._safe_theme_changed()
        
        if mw := self._get_active_window():
            if gb := getattr(mw, 'gradient_bar', None):
                gb.refresh_colors()
        
        self.status_message.emit(f"{color_key.replace('_', ' ').title()} updated to {hex_color}")
    
    def _on_base_color_changed(self, color_key: str, hex_color: str):
        """Handle base color change from the color picker widgets."""
        if color_key in ('base_background', 'base_primary', 'base_accent'):
            bg = hex_color if color_key == 'base_background' else None
            pr = hex_color if color_key == 'base_primary' else None
            ac = hex_color if color_key == 'base_accent' else None
            self.theme_manager.set_base_colors(background=bg, primary=pr, accent=ac)
        
        self.status_message.emit(f"{color_key.replace('_', ' ').title()} updated to {hex_color}")
    
    def _on_base_colors_swapped(self):
        """Handle swap of primary and accent base colors."""
        primary, accent = self.base_color_picker_pair.get_colors()
        self.theme_manager.set_base_colors(primary=primary, accent=accent)
        self.status_message.emit("Primary and Accent colors swapped")
    
    def _on_gradient_colors_swapped(self):
        """Handle gradient colors swap from the gradient color picker widget."""
        color1, color2 = self.gradient_color_picker.get_colors()
        
        self.theme_manager.current_theme['gradient_color1'] = color1
        self.theme_manager.current_theme['gradient_color2'] = color2
        self.theme_manager.invalidate_cache()
        
        if app := QApplication.instance():
            self.theme_manager.apply_theme(app)
        
        self._safe_theme_changed()
        
        if mw := self._get_active_window():
            if gb := getattr(mw, 'gradient_bar', None):
                gb.refresh_colors()
        
        self.status_message.emit("Gradient colors swapped")
    
    def _swap_gradient_colors(self):
        """Swap the two gradient colors (legacy method)."""
        color1 = self._get_effective_color('gradient_color1')
        color2 = self._get_effective_color('gradient_color2')
        
        theme = self.theme_manager.current_theme
        theme['gradient_color1'], theme['gradient_color2'] = color2, color1
        
        self.theme_manager.apply_theme(QApplication.instance())
        self._safe_theme_changed()
        self._update_color_buttons()
        self.status_message.emit("Gradient colors swapped")
    
    # =========================================================================
    # Radius Handlers
    # =========================================================================
    
    def _on_radius_preview(self, value, radius_type='corner'):
        """Unified radius preview handler with immediate visual feedback + debounced regeneration."""
        timer_data = self._radius_timers[radius_type]
        timer_data['active'] = True
        
        self.theme_manager.current_theme[timer_data['theme_key']] = value
        
        if timer_data['preview_callback']:
            timer_data['preview_callback'](value)
        
        timer_data['timer'].start()
    
    def _regenerate_radius_stylesheet(self, radius_type):
        """Regenerate and apply stylesheet after debounce period."""
        timer_data = self._radius_timers[radius_type]
        if not timer_data['active']:
            return
        
        self.theme_manager.invalidate_cache()
        
        if mw := self._get_active_window():
            mw.setStyleSheet(self.theme_manager.get_stylesheet())

    def _on_radius_commit(self, radius_type='corner'):
        """User released slider / finished editing: apply to whole app."""
        timer_data = self._radius_timers[radius_type]
        
        timer_data['timer'].stop()
        timer_data['active'] = False
        
        if not (app := QApplication.instance()):
            return
        
        value = self.theme_manager.current_theme.get(timer_data['theme_key'], 4)
        timer_data['apply_method'](value)
        
        if mw := self._get_active_window():
            mw.setStyleSheet("")
        
        self.theme_manager.apply_theme(app)
        self.status_message.emit(f"{timer_data['theme_key'].replace('_', ' ').title()} set to {value}px")
    
    # =========================================================================
    # Theme Save/Delete Handlers
    # =========================================================================
    
    def _save_theme(self):
        """Save the customized theme file."""
        name = self.new_theme_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Input", "Please enter a theme name.")
            return
        
        theme_data = self.theme_manager.current_theme.copy()
        existed_before = name in (self.theme_manager.get_available_themes() or [])
        
        if self.theme_manager.save_theme(name, theme_data):
            self.theme_manager.set_theme(name)
            self._populate_delete_combo()
            self.status_message.emit(f"Theme '{name}' saved and applied")
            
            if not existed_before:
                self.notify_success(f"Saved new theme '{name}'")
            else:
                self.notify_success(f"Overwrote existing theme '{name}'")
        else:
            QMessageBox.critical(self, "Error", f"Failed to save theme '{name}'")
            self.notify_error(f"Failed to save theme '{name}'")

    def _populate_delete_combo(self):
        """Refresh delete theme combo with available themes."""
        if hasattr(self, 'delete_theme_combo'):
            current = self.delete_theme_combo.currentText()
            self.delete_theme_combo.blockSignals(True)
            self.delete_theme_combo.clear()
            self.delete_theme_combo.addItems(self.theme_manager.get_custom_themes())
            idx = self.delete_theme_combo.findText(current)
            if idx >= 0:
                self.delete_theme_combo.setCurrentIndex(idx)
            self.delete_theme_combo.blockSignals(False)

    def _delete_theme(self):
        """Delete the selected theme."""
        name = self.delete_theme_combo.currentText()
        if not name:
            return
        
        reply = QMessageBox.question(
            self, "Delete Theme", f"Are you sure you want to delete the theme '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.theme_manager.delete_theme(name):
                current = self.theme_manager.current_theme.get('name', '')
                if name == current:
                    if available := self.theme_manager.get_available_themes():
                        self.theme_manager.set_theme(available[0])
                else:
                    self._safe_theme_changed()
                self._populate_delete_combo()
                self.status_message.emit(f"Theme '{name}' deleted")
                self._notify('warning', f"Removed theme '{name}'")
            else:
                QMessageBox.warning(self, "Error", f"Failed to delete theme '{name}'")
                self._notify('error', f"Failed to delete theme '{name}'")

    def _update_save_button_label(self):
        """Update save button text based on whether theme exists."""
        name = self.new_theme_name_input.text().strip()
        if not name:
            self.save_theme_btn.setText("Save")
            return
        available = self.theme_manager.get_available_themes() or []
        self.save_theme_btn.setText("Overwrite" if name in available else "Save")
    
    # =========================================================================
    # Color Button Updates
    # =========================================================================
    
    def _update_color_buttons(self):
        """Update color picker buttons to current theme colors."""
        # Update old-style buttons
        for key, btn in getattr(self, 'theme_color_buttons', {}).items():
            color = self._get_effective_color(key)
            if self._button_color_cache.get(key) != color:
                if hasattr(btn, 'set_color'):
                    btn.set_color(color)
                else:
                    self._set_primary_color(btn, color)
                self._button_color_cache[key] = color
        
        # Update gradient color picker widget
        if hasattr(self, 'gradient_color_picker'):
            self.gradient_color_picker.set_colors(
                self._get_effective_color('gradient_color1'),
                self._get_effective_color('gradient_color2')
            )
        
        # Update base color pickers
        if hasattr(self, 'background_color_picker'):
            self.background_color_picker.set_color(self._get_effective_color('base_background'))
        
        if hasattr(self, 'base_color_picker_pair'):
            self.base_color_picker_pair.set_colors(
                self._get_effective_color('base_primary'),
                self._get_effective_color('base_accent')
            )
        
        # Auto-fill theme name input
        if hasattr(self, 'new_theme_name_input'):
            name = self.theme_manager.current_theme.get('name', '')
            if self.new_theme_name_input.text() != name:
                self.new_theme_name_input.setText(name)
        
        # Sync radius controls
        if hasattr(self, 'radius_slider'):
            val = int(self.theme_manager.current_theme.get('corner_radius', 4))
            if self.radius_slider.value() != val or self.radius_spin.value() != val:
                self.radius_slider.blockSignals(True)
                self.radius_spin.blockSignals(True)
                self.radius_slider.setValue(val)
                self.radius_spin.setValue(val)
                self.radius_slider.blockSignals(False)
                self.radius_spin.blockSignals(False)
        
        # Sync scrollbar radius controls
        if hasattr(self, 'sb_radius_slider'):
            sb_val = int(self.theme_manager.current_theme.get(
                'scrollbar_radius',
                self.radius_slider.value() if hasattr(self, 'radius_slider') else 4
            ))
            if self.sb_radius_slider.value() != sb_val or self.sb_radius_spin.value() != sb_val:
                self.sb_radius_slider.blockSignals(True)
                self.sb_radius_spin.blockSignals(True)
                self.sb_radius_slider.setValue(sb_val)
                self.sb_radius_spin.setValue(sb_val)
                self.sb_radius_slider.blockSignals(False)
                self.sb_radius_spin.blockSignals(False)
