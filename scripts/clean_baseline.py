"""Compatibility guard for the removed destructive broker cleanup utility."""

raise SystemExit(
    "This command is disabled. Use scripts/reset-paper-baseline.py --dry-run; "
    "the safe reset never cancels orders or closes broker positions."
)
