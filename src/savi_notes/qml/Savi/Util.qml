pragma Singleton
import QtQuick

QtObject {
  function alpha(c, opacity) {
    var a = Math.max(0, Math.min(1, Number(opacity) || 0))
    if (!c) return Qt.rgba(0, 0, 0, a)
    if (typeof c === "string") c = Qt.color(c)
    return Qt.rgba(c.r, c.g, c.b, a)
  }

  // A file:// URL for a local path on any platform (C:\x → file:///C:/x).
  function fileUrl(path) {
    if (!path) return ""
    path = String(path).replace(/\\/g, "/")
    if (path[0] !== "/") path = "/" + path
    return "file://" + path.split("/").map(encodeURIComponent).join("/").replace(/^\/([A-Za-z])%3A/, "/$1:")
  }
}
