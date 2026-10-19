pragma Singleton
import QtQuick

// Sizes and fonts. space() is the pixel measure every layout goes through;
// the fonts come from the host (App), so each platform's own UI font is used
// and the bundled icon font fills in the glyphs. A theme file's [font] size and
// [shape] (App.look) replace the defaults here.
QtObject {
  id: root

  function space(px) {
    var n = Number(px)
    return !isFinite(n) || n <= 0 ? 0 : Math.max(1, Math.round(n))
  }

  readonly property var shape: App.look.shape || ({})
  readonly property int fontBaseSize: (App.look.font || {}).size || 13
  readonly property real fontScale: fontBaseSize / 12
  function fontPx(mult) { return Math.max(1, Math.round(fontBaseSize * mult)) }

  readonly property int cornerRadius: shape["corner-radius"] !== undefined ? shape["corner-radius"] : 10
  readonly property int normalBorderWidth: shape["border-width"] !== undefined ? shape["border-width"] : 1
  // The modifier named in shortcut hints: Qt maps Control to Command on macOS.
  readonly property string ctrl: App.isMac ? "⌘" : "Ctrl"

  readonly property QtObject font: QtObject {
    readonly property string family: App.uiFamily
    readonly property string mono: App.monoFamily
    readonly property string icon: App.iconFamily
    readonly property int caption: root.fontPx(0.833)
    readonly property int bodySmall: root.fontPx(0.917)
    readonly property int body: root.fontPx(1.0)
    readonly property int subtitle: root.fontPx(1.083)
    readonly property int title: root.fontPx(1.167)
    readonly property int display: root.fontPx(2.0)
  }

  readonly property QtObject spacing: QtObject {
    readonly property int controlPaddingX: 8
    readonly property int controlPaddingY: 4
  }
}
