"""sketchclean — turn a photo of a sketch into a scanner-quality image or clean line art.

Checkpoint 1  scan.py   page, grain, light, levels        → scanner look
Checkpoint 2  clean.py  shading, contrast, thickness       → scanner or black & white
Checkpoint 3  even.py   gaps, even width, smooth/straight  → final lines (+ vector)
"""
from .config import CleanSettings, EvenSettings, OutputSettings, Settings
from .pipeline import Session, process

__all__ = ["Session", "process", "Settings", "CleanSettings", "EvenSettings", "OutputSettings"]
