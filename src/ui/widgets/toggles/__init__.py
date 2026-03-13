# Toggles module initialization
from .classic_toggle import ClassicToggle
from .dot_toggle import DotToggle
from .multi_step_toggle import MultiStepToggle
from .styleable_toggle import StyleableToggle, StyleableLabel, STYLE_REGISTRY

__all__ = [
    'ClassicToggle',
    'DotToggle',
    'MultiStepToggle',
    'StyleableToggle',
    'StyleableLabel',
    'STYLE_REGISTRY',
]

