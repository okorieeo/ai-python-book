"""Check design tokens against WCAG 2.x contrast requirements."""
import json

def luminance(hex_color: str) -> float:
    """Relative luminance of a #RRGGBB color (WCAG definition)."""
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

def contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)

# (foreground token, background token, minimum ratio, what it is)
RULES = [
    ("text", "surface", 4.5, "body text"),
    ("text-muted", "surface", 4.5, "secondary text"),
    ("text", "surface-muted", 4.5, "text on cards"),
    ("on-primary", "primary", 4.5, "button label"),
    ("primary", "surface", 4.5, "links"),
    ("success", "surface", 4.5, "success message"),
    ("warning", "surface", 4.5, "warning message"),
    ("danger", "surface", 4.5, "error message"),
    ("border-strong", "surface", 3.0, "input border (UI component)"),
]

tokens = json.load(open("tokens.json", encoding="utf-8"))
failures = 0
for theme, palette in (("light", tokens["color"]), ("dark", tokens["color-dark"])):
    print(f"--- {theme} theme ---")
    for fg, bg, minimum, label in RULES:
        ratio = contrast(palette[fg], palette[bg])
        status = "PASS" if ratio >= minimum else "FAIL"
        failures += status == "FAIL"
        print(f"{status}  {ratio:5.2f}:1 (needs {minimum})  {label}: {fg} {palette[fg]} on {bg} {palette[bg]}")

print("--- a common mistake ---")
ratio = contrast("#9CA3AF", "#FFFFFF")
print(f"{'PASS' if ratio >= 4.5 else 'FAIL'}  {ratio:5.2f}:1 (needs 4.5)  light gray placeholder text on white")
print("The pale default border #D1D5DB on white is only", f"{contrast('#D1D5DB', '#FFFFFF'):.2f}:1, so inputs use border-strong instead.")
print(f"\n{failures} failure(s) in the token palettes")
