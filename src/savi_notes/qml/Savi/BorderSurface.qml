import QtQuick
import Savi

// A rectangle whose border comes from a Border spec.
Rectangle {
  id: root

  property var borderSpec: Border.none()
  property real padding: 0
  property real topPadding: padding
  property real rightPadding: padding
  property real bottomPadding: padding
  property real leftPadding: padding

  readonly property real contentTopInset: Border.top(borderSpec) + topPadding
  readonly property real contentRightInset: Border.right(borderSpec) + rightPadding
  readonly property real contentBottomInset: Border.bottom(borderSpec) + bottomPadding
  readonly property real contentLeftInset: Border.left(borderSpec) + leftPadding

  border.width: Border.top(borderSpec)
  border.color: Border.color(borderSpec)
}
