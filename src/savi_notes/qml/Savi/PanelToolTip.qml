import QtQuick
import QtQuick.Controls
import Savi

// A themed tooltip: declare it inside the hovered item and bind `visible`.
// Set `hint` for a second, smaller line beneath, such as a shortcut.
ToolTip {
  id: root

  property string hint: ""

  delay: 400
  padding: 0

  background: Rectangle {
    color: Colors.tooltip.background
    border.width: Style.normalBorderWidth
    border.color: Colors.tooltip.border
    radius: Style.cornerRadius
  }

  contentItem: Column {
    spacing: Style.space(2)
    leftPadding: Style.normalBorderWidth + Style.spacing.controlPaddingX
    rightPadding: Style.normalBorderWidth + Style.spacing.controlPaddingX
    topPadding: Style.normalBorderWidth + Style.spacing.controlPaddingY
    bottomPadding: Style.normalBorderWidth + Style.spacing.controlPaddingY

    Text {
      textFormat: Text.PlainText
      text: root.text
      color: Colors.tooltip.text
      font.pixelSize: Style.font.bodySmall
    }

    Text {
      visible: root.hint !== ""
      textFormat: Text.PlainText
      text: root.hint
      color: Util.alpha(Colors.tooltip.text, 0.6)
      font.pixelSize: Style.font.caption
    }
  }
}
