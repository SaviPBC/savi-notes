import QtQuick
import Savi

// A flat button on the format toolbar: a glyph, or a short label, with a
// tooltip. It doesn't take focus, so the editor keeps its selection.
Rectangle {
  id: button
  property int glyph: 0
  property string label: ""
  property string tip: ""
  property bool dropdown: false
  signal activated()

  width: content.implicitWidth + Style.space(dropdown || label ? 16 : 12)
  height: Style.space(30)
  radius: Math.max(Style.cornerRadius, Style.space(6))
  color: mouse.pressed ? Util.alpha(Colors.foreground, 0.14) : mouse.containsMouse ? Util.alpha(Colors.foreground, 0.08) : "transparent"

  Row {
    id: content
    anchors.centerIn: parent
    spacing: Style.space(5)
    Text {
      visible: button.glyph !== 0
      anchors.verticalCenter: parent.verticalCenter
      text: button.glyph ? String.fromCodePoint(button.glyph) : ""
      color: Util.alpha(Colors.foreground, 0.85)
      font.family: Style.font.icon
      font.pixelSize: Style.font.title
    }
    Text {
      visible: button.label !== ""
      anchors.verticalCenter: parent.verticalCenter
      text: button.label
      color: Util.alpha(Colors.foreground, 0.85)
      font.pixelSize: Style.font.bodySmall
    }
    Text {
      visible: button.dropdown
      anchors.verticalCenter: parent.verticalCenter
      text: String.fromCodePoint(0xf0140)
      color: Util.alpha(Colors.foreground, 0.5)
      font.family: Style.font.icon
      font.pixelSize: Style.font.caption
    }
  }

  MouseArea {
    id: mouse
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: button.activated()
  }

  PanelToolTip {
    visible: mouse.containsMouse && button.tip !== ""
    text: button.tip
  }
}
