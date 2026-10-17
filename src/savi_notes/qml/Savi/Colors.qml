pragma Singleton
import QtQuick

// Savi's palette (app.bysavi.com's _variables.scss): the brand green as the
// accent on white, and the same green on a navy-tinted dark theme. Dark or
// light follows the system unless the settings say.
QtObject {
  id: root

  readonly property bool dark: App.dark
  readonly property color background: dark ? "#13202a" : "#ffffff"
  readonly property color foreground: dark ? "#e1e9ec" : "#1d2b31"
  readonly property color accent: dark ? "#4ebc90" : "#38946f"
  readonly property color urgent: dark ? "#f0704a" : "#c63500"

  // Named colors the note renderer uses for headings, callouts and code.
  readonly property var palette: dark
    ? ({ red: "#e86a6a", orange: "#f0884e", yellow: "#ffc107", green: "#4ebc90", cyan: "#3fb8d8", blue: "#65a8e3", magenta: "#b183e6",
         muted: "#3a4c55", dark_foreground: "#8fa0a8", dark_background: "#1a2932", lighter_background: "#213440" })
    : ({ red: "#c63500", orange: "#d2601f", yellow: "#b58900", green: "#38946f", cyan: "#00a7ce", blue: "#378cd6", magenta: "#8a4fd0",
         muted: "#d8d8d8", dark_foreground: "#6c757d", dark_background: "#f1f3f9", lighter_background: "#e9f8ff" })

  readonly property QtObject popups: QtObject {
    readonly property color background: root.background
    readonly property color text: root.foreground
    readonly property color border: root.accent
  }

  readonly property QtObject tooltip: QtObject {
    readonly property color background: root.background
    readonly property color text: root.foreground
    readonly property color border: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.25)
  }

  // What mermaid diagrams are drawn with.
  readonly property var diagram: ({
    foreground: String(foreground), background: String(background),
    lighter_background: palette.lighter_background, dark_background: palette.dark_background,
    muted: palette.muted, dark_foreground: palette.dark_foreground
  })
}
