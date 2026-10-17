pragma Singleton
import QtQuick

// Border specs: { width, color }. Kept as functions so surfaces read the
// same way as in the Wolfen shell this app came from.
QtObject {
  function none() { return { width: 0, color: "transparent" } }
  function flat(color, width) { return { width: width === undefined ? 1 : width, color: color } }
  function localOrSurfaceSpec(section, key, color, fallback, width) { return flat(color || fallback, width) }
  function top(spec) { return spec ? spec.width : 0 }
  function right(spec) { return spec ? spec.width : 0 }
  function bottom(spec) { return spec ? spec.width : 0 }
  function left(spec) { return spec ? spec.width : 0 }
  function color(spec) { return spec ? spec.color : "transparent" }
}
