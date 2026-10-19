"""TeX to SVG for the note renderer, in-process with ziamath (no browser, no Node)."""

import ziamath

# Plain SVG 1.1 paths. ziamath's default (SVG 2) draws each glyph as a <symbol> placed by
# <use>, which Qt's SVG renderer skips, leaving only the fraction bars.
ziamath.config.svg2 = False

# Sizes are pixels beside 15px text, which is what the renderer scales from.
SIZE = 15


def render(tex, display, color):
  """Returns (svg, width, height) for a TeX snippet in the given ink color."""
  math = ziamath.Latex(tex.strip(), size=SIZE, color=color, inline=not display)
  width, height = math.getsize()
  return math.svg(), float(width), float(height)
