"""Every user setting in one place: its default, its range, and what it means.

Each setting changes ONE thing. They are applied after the lines are found, so moving
one slider never changes what another slider does.
"""
from dataclasses import dataclass, field

# working resolution: small photos are enlarged, huge scans reduced, to this long side
WORK_LONG_SIDE = 2400
MAX_LONG_SIDE = 4000


@dataclass
class CleanSettings:
    """Checkpoint 2: remove shades and clear the lines."""
    output: str = "bw"              # "scan" = grayscale scanner look | "bw" = black & white
    method: str = "ai"              # B&W lines from "ai" (ONNX model) or "classic" (falls back if no model)
    keep_detail: bool = True        # AI: add back hatching, dots and small marks the AI treats as tone
    remove_shading: bool = True     # drop soft pencil shading / smudges, keep the lines
    contrast: float = 0.0           # -1 softer .. 0 auto .. +1 stronger (darker lines, whiter paper)
    sharpness: float = 0.6          # 0 off .. 2 strong (scanner output only)
    thickness: float = 0.0          # -2 thinner .. +3 bolder, in pixels of the original photo


@dataclass
class EvenSettings:
    """Checkpoint 3: fix uneven lines (black & white output only)."""
    even_width: str = "uniform"     # "off" | "light" (trim bulges, fill thin spots) | "full" (each line
                                    # at its own steady width) | "uniform" (ALL lines at one pen width)
    uniform_width: float = 0.0      # uniform: pen width in original-photo pixels (0 = auto: a normal stroke)
    beautify: float = 1.0           # uniform: 0 off .. 1 normal .. 2 strong — redraw each line on a smoothed
                                    # centre path (removes hand shake), and continue lines that stop just
                                    # short of another line so they touch
    smooth: float = 1.0             # 0 follow the pencil .. 2 very smooth and straight
    join_gaps: bool = True          # bridge small breaks between two line ends


@dataclass
class OutputSettings:
    color: str = "#000000"          # line colour
    dpi: int = 300
    width_cm: float = 0.0           # 0 = keep working size
    formats: tuple = ("png", "tiff", "bmp", "svg", "pdf", "eps", "dxf")


@dataclass
class Settings:
    clean: CleanSettings = field(default_factory=CleanSettings)
    even: EvenSettings = field(default_factory=EvenSettings)
    output: OutputSettings = field(default_factory=OutputSettings)


# ranges used by the GUI and CLI (min, max, step)
RANGES = {
    "contrast": (-1.0, 1.0, 0.05),
    "sharpness": (0.0, 2.0, 0.1),
    "thickness": (-2.0, 3.0, 0.25),
    "smooth": (0.0, 2.0, 0.1),
}
