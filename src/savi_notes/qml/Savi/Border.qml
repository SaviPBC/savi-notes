pragma Singleton
import QtQuick
import "BorderGeometry.js" as Geometry

// Border specs: { widths, color, gradient }, read the same way as in the Wolfen
// shell this app came from. A theme's [section] border may be one colour or a
// gradient written "#a #b 45deg"; BorderSurface draws a gradient with BorderOverlay.
QtObject {
  readonly property var noGradient: ({ colors: [], angle: 0, enabled: false })

  function none() { return { widths: Geometry.parseWidthSpec(0, 0), color: "transparent", gradient: noGradient } }
  function flat(color, width) {
    return { widths: Geometry.parseWidthSpec(width === undefined ? 1 : width, 1), color: color, gradient: noGradient }
  }

  function gradient(raw) {
    var colors = [], angle = 0
    String(raw || "").trim().split(/\s+/).forEach(function(part) {
      if (/^-?\d+(\.\d+)?deg$/.test(part)) angle = Number(part.replace(/deg$/, ""))
      else if (part) colors.push(Geometry.canonicalColor(part))
    })
    return { colors: colors, angle: angle, enabled: colors.length > 1 }
  }

  function localOrSurfaceSpec(section, key, color, fallback, width) {
    var raw = (App.look[section] || {})[key]
    var spec = flat(color || fallback, width)
    if (raw) spec.gradient = gradient(raw)
    return spec
  }

  function needsOverlay(spec) { return Geometry.needsOverlay(spec) }
  function canUseNative(spec) { return Geometry.canUseNative(spec) }
  function top(spec) { return spec && spec.widths ? spec.widths.top : 0 }
  function right(spec) { return spec && spec.widths ? spec.widths.right : 0 }
  function bottom(spec) { return spec && spec.widths ? spec.widths.bottom : 0 }
  function left(spec) { return spec && spec.widths ? spec.widths.left : 0 }
  function uniformWidth(spec) { return top(spec) }
  function color(spec) { return spec ? spec.color : "transparent" }
}
