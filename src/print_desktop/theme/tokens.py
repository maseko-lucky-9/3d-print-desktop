"""Design tokens — mirror the ReelSmith dark palette referenced in plan §7.6.
Used by styles.qss via QSS variable substitution at app startup."""

# Backgrounds
BG_PAGE = "#0A0A0A"  # zinc-950 — body background
BG_CARD = "#18181B"  # zinc-900 — input + card fill
BG_CARD_RAISED = "#27272A"  # zinc-800 — hover / selected

# Borders + dividers
BORDER_SUBTLE = "rgba(255, 255, 255, 0.10)"  # white/10
BORDER_FOCUS = "rgba(255, 255, 255, 0.40)"

# Text
TEXT_PRIMARY = "#FFFFFF"
TEXT_MUTED = "#A1A1AA"  # zinc-400 — placeholder + secondary
TEXT_DIM = "#71717A"  # zinc-500 — tertiary captions

# Primary action
CTA_BG = "#FFFFFF"
CTA_FG = "#000000"
CTA_HOVER = "#F4F4F5"  # zinc-100

# Feature icon backdrop
ICON_CIRCLE_BG = "rgba(255, 255, 255, 0.08)"
ICON_CIRCLE_HOVER = "rgba(255, 255, 255, 0.14)"

# Status badges (PrintJob.state)
STATUS_DONE = "#10B981"  # emerald-500
STATUS_PRINTING = "#3B82F6"  # blue-500
STATUS_FAILED = "#EF4444"  # red-500
STATUS_CANCELLED = "#71717A"  # zinc-500
STATUS_SLICED = "#A1A1AA"  # zinc-400 — "Calculated" pre-send state
STATUS_WARNING = "#F59E0B"  # amber-500 — local/server quote drift (Phase 6)

# Radii
RADIUS_INPUT = 12
RADIUS_CARD = 8
RADIUS_BUTTON = 12

# Spacing scale (px)
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 48

# Typography
FONT_FAMILY = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif"
FONT_SIZE_BODY = 13
FONT_SIZE_CAPTION = 11
FONT_SIZE_HEADING = 18


def status_color(state: str) -> str:
    """Map a PrintJob.state to a status badge colour."""
    return {
        "done": STATUS_DONE,
        "printing": STATUS_PRINTING,
        "failed": STATUS_FAILED,
        "cancelled": STATUS_CANCELLED,
        "sliced": STATUS_SLICED,
        "queued": STATUS_PRINTING,
    }.get(state, TEXT_DIM)
