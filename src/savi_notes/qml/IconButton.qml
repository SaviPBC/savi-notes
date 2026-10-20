import QtQuick
import Savi

// A small round icon button with a tooltip, as in Settings. Tab reaches
// it; Return and Space press it.
Item {
  id: iconButton
  property string glyph: ""
  property string tip: ""
  property string tipHint: ""
  property bool highlighted: false
  property bool busy: false
  signal activated()

  width: Style.space(28)
  height: width
  opacity: enabled ? 1 : 0.35

  activeFocusOnTab: true
  Keys.onReturnPressed: iconButton.activated()
  Keys.onEnterPressed: iconButton.activated()
  Keys.onSpacePressed: iconButton.activated()

  Rectangle {
    anchors.fill: parent
    radius: width / 2
    color: iconButton.highlighted ? Util.alpha(Colors.accent, 0.22)
         : Util.alpha(Colors.foreground, iconMouse.containsMouse || iconButton.activeFocus ? 0.16 : 0.08)
    border.width: iconButton.activeFocus ? 1 : 0
    border.color: Colors.accent
  }

  Spinner {
    anchors.centerIn: parent
    implicitWidth: Style.font.title
    visible: iconButton.busy
  }

  Text {
    anchors.centerIn: parent
    visible: !iconButton.busy
    text: iconButton.glyph
    color: iconButton.highlighted ? Colors.accent : Colors.foreground
    font.pixelSize: Style.font.title
  }

  MouseArea {
    id: iconMouse
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: iconButton.activated()
  }

  PanelToolTip {
    visible: iconMouse.containsMouse && iconButton.tip !== ""
    text: iconButton.tip
    hint: iconButton.tipHint
  }
}
