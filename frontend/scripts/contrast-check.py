"""Contrast ratio checker for semantic design tokens."""


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def luminance(rgb):
    def adj(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = [adj(c) for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(h1, h2):
    l1 = luminance(hex_to_rgb(h1))
    l2 = luminance(hex_to_rgb(h2))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


tokens = {
    "surface-base": "#0a0a1a",
    "surface-raised": "#12122a",
    "surface-overlay": "#0f0f24",
    "surface-sunken": "#0d0d20",
    "content-primary": "#e8e8f0",
    "content-secondary": "#c8c8e0",
    "content-tertiary": "#9ca3af",
    "content-muted": "#6b7280",
    "interactive-default": "#7c3aed",
    "status-success": "#34d399",
    "status-warning": "#fbbf24",
    "status-error": "#f87171",
    "status-info": "#a78bfa",
}

checks = [
    ("content-primary", "surface-base", "4.5:1 text"),
    ("content-primary", "surface-raised", "4.5:1 text"),
    ("content-secondary", "surface-base", "4.5:1 text"),
    ("content-secondary", "surface-raised", "4.5:1 text"),
    ("content-tertiary", "surface-base", "4.5:1 text"),
    ("content-tertiary", "surface-raised", "4.5:1 text"),
    ("content-muted", "surface-base", "3:1 UI"),
    ("content-muted", "surface-raised", "3:1 UI"),
    ("interactive-default", "surface-base", "3:1 UI"),
    ("interactive-default", "surface-raised", "3:1 UI"),
    ("status-success", "surface-base", "3:1 UI"),
    ("status-success", "surface-raised", "3:1 UI"),
    ("status-warning", "surface-base", "3:1 UI"),
    ("status-warning", "surface-raised", "3:1 UI"),
    ("status-error", "surface-base", "3:1 UI"),
    ("status-error", "surface-raised", "3:1 UI"),
    ("status-info", "surface-base", "3:1 UI"),
    ("status-info", "surface-raised", "3:1 UI"),
]

print("| Foreground | Background | Ratio | Requirement | Pass |")
print("|---|---|---|---|---|")
all_pass = True
for fg, bg, req in checks:
    r = contrast(tokens[fg], tokens[bg])
    threshold = 4.5 if "4.5" in req else 3.0
    p = "PASS" if r >= threshold else "FAIL"
    if p == "FAIL":
        all_pass = False
    print(f"| {fg} | {bg} | {r:.2f}:1 | {req} | {p} |")

print()
if all_pass:
    print("ALL CHECKS PASSED")
else:
    print("SOME CHECKS FAILED — review and adjust tokens")
