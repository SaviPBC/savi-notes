import QtQuick
import QtQuick.Controls
import Savi

// A themed tooltip: declare it inside the hovered item and bind `visible`.
ToolTip {
  id: root

  delay: 400
  padding: 0

  background: Rectangle {
    color: Colors.tooltip.background
    border.width: Style.normalBorderWidth
    border.color: Colors.tooltip.border
    radius: Style.cornerRadius
  }

  contentItem: Text {
    textFormat: Text.PlainText
    text: root.text
    color: Colors.tooltip.text
    font.pixelSize: Style.font.bodySmall
    leftPadding: Style.normalBorderWidth + Style.spacing.controlPaddingX
    rightPadding: Style.normalBorderWidth + Style.spacing.controlPaddingX
    topPadding: Style.normalBorderWidth + Style.spacing.controlPaddingY
    bottomPadding: Style.normalBorderWidth + Style.spacing.controlPaddingY
  }
}
