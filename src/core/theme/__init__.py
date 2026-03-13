"""
Core theme package: color utilities and stylesheet generation.

This package exists to keep `core.theme_manager` lean while preserving its
public API. Import helper functions from here inside the manager.
"""

from .colors import adjust_color, to_hex_rgb, get_contrasting_text_color, compute_palette, mix_colors
from .stylesheet import generate_stylesheet 

__all__ = [
    "adjust_color",
    "to_hex_rgb",
    "get_contrasting_text_color",
    "compute_palette",
    "generate_stylesheet",
    "mix_colors",
]
