import QtQuick
import Savi

// A two-button question over the window. The host feeds it keys through
// handleKey(); Left/Right move between the buttons.
Item {
  id: root

  property bool opened: false
  property string message: ""
  property string cancelText: "Cancel"
  property string confirmText: "Confirm"
  // Red confirm button for actions that can't be undone.
  property bool destructive: true
  property int selectedIndex: 1

  signal canceled()
  signal confirmed()

  function handleKey(event) {
    if (!root.opened) return false
    if (event.key === Qt.Key_Escape) { root.canceled(); return true }
    if (event.key === Qt.Key_Left || event.key === Qt.Key_Right || event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
      root.selectedIndex = root.selectedIndex === 0 ? 1 : 0
      return true
    }
    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
      if (root.selectedIndex === 0) root.canceled()
      else root.confirmed()
      return true
    }
    return false
  }

  visible: opened

  Rectangle {
    anchors.fill: parent
    color: Util.alpha(Colors.background, 0.7)

    MouseArea { anchors.fill: parent; onClicked: root.canceled() }

    BorderSurface {
      id: card
      width: Math.min(parent.width - Style.space(32), Style.space(370))
      height: card.contentTopInset + card.contentBottomInset + messageText.implicitHeight + Style.space(20) + Style.space(34)
      anchors.centerIn: parent
      color: Colors.background
      borderSpec: Border.flat(Colors.accent, Style.normalBorderWidth)
      padding: Style.space(18)
      radius: Style.cornerRadius

      MouseArea { anchors.fill: parent; onClicked: {} }

      Item {
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset

        Text {
          id: messageText
          textFormat: Text.PlainText
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.top: parent.top
          text: root.message
          color: Colors.foreground
          font.pixelSize: Style.font.title
          wrapMode: Text.WordWrap
        }

        Row {
          anchors.right: parent.right
          anchors.bottom: parent.bottom
          spacing: Style.space(10)

          Repeater {
            model: [root.cancelText, root.confirmText]

            Rectangle {
              required property int index
              required property string modelData
              readonly property bool selected: root.selectedIndex === index
              readonly property bool red: root.destructive && index === 1
              readonly property color tone: red ? Colors.urgent : Colors.accent

              width: Style.space(88)
              height: Style.space(34)
              radius: Math.max(Style.cornerRadius, Style.space(8))
              color: selected ? Util.alpha(tone, 0.2) : "transparent"
              border.width: Style.normalBorderWidth
              border.color: selected ? tone : Util.alpha(Colors.foreground, 0.38)

              Text {
                textFormat: Text.PlainText
                anchors.centerIn: parent
                text: parent.modelData
                color: parent.selected ? parent.tone : Colors.foreground
                font.pixelSize: Style.font.caption
              }

              MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onEntered: root.selectedIndex = parent.index
                onClicked: { if (parent.index === 0) root.canceled(); else root.confirmed() }
              }
            }
          }
        }
      }
    }
  }
}
