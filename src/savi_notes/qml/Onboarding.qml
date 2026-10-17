import QtQuick
import QtQuick.Dialogs
import Savi

// The first run: where the notes live, and whether to search them by
// meaning. Everything else has a default.
FocusScope {
  id: onboarding

  property string folder: App.suggestedVault
  property bool semantic: true

  visible: App.needsSetup
  onVisibleChanged: if (visible) forceActiveFocus()
  Component.onCompleted: if (visible) forceActiveFocus()
  // Enter starts with what's shown.
  Keys.onReturnPressed: App.finishSetup(onboarding.folder, onboarding.semantic)
  Keys.onEnterPressed: App.finishSetup(onboarding.folder, onboarding.semantic)

  Rectangle { anchors.fill: parent; color: Colors.background }

  Column {
    anchors.centerIn: parent
    width: Math.min(parent.width - Style.space(48), Style.space(520))
    spacing: Style.space(18)

    Text {
      text: String.fromCodePoint(0xf0ebf)
      color: Colors.accent
      font.family: Style.font.icon
      font.pixelSize: Style.font.display * 2
    }

    Text {
      text: "Welcome to Savi Notes"
      color: Colors.foreground
      font.pixelSize: Style.font.display
      font.weight: Font.Bold
    }

    Text {
      width: parent.width
      wrapMode: Text.Wrap
      text: "Your notes are plain markdown files in one folder on this computer, so they're yours to back up, sync or open elsewhere. Notes are organised by tags, not folders."
      color: Util.alpha(Colors.foreground, 0.7)
      font.pixelSize: Style.font.body
      lineHeight: 1.25
    }

    // The folder.
    Column {
      width: parent.width
      spacing: Style.space(6)

      Text {
        text: "Keep notes in"
        color: Util.alpha(Colors.foreground, 0.55)
        font.pixelSize: Style.font.caption
      }

      Rectangle {
        width: parent.width
        height: Style.space(40)
        radius: Math.max(Style.cornerRadius, Style.space(8))
        color: Util.alpha(Colors.foreground, 0.05)
        border.width: 1
        border.color: Util.alpha(Colors.foreground, 0.1)

        TextInput {
          id: folderInput
          anchors.left: parent.left
          anchors.leftMargin: Style.space(12)
          anchors.right: chooseButton.left
          anchors.rightMargin: Style.space(8)
          anchors.verticalCenter: parent.verticalCenter
          text: onboarding.folder
          color: Colors.foreground
          selectionColor: Util.alpha(Colors.accent, 0.4)
          selectedTextColor: Colors.foreground
          font.pixelSize: Style.font.body
          clip: true
          focus: true
          onTextChanged: onboarding.folder = text
          Keys.onReturnPressed: App.finishSetup(onboarding.folder, onboarding.semantic)
          Keys.onEnterPressed: App.finishSetup(onboarding.folder, onboarding.semantic)
        }

        Rectangle {
          id: chooseButton
          anchors.right: parent.right
          anchors.rightMargin: Style.space(6)
          anchors.verticalCenter: parent.verticalCenter
          width: chooseLabel.implicitWidth + Style.space(20)
          height: Style.space(28)
          radius: Math.max(Style.cornerRadius, Style.space(6))
          color: Util.alpha(Colors.foreground, chooseMouse.containsMouse ? 0.14 : 0.08)
          Text {
            id: chooseLabel
            anchors.centerIn: parent
            text: "Choose…"
            color: Colors.foreground
            font.pixelSize: Style.font.bodySmall
          }
          MouseArea {
            id: chooseMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: { folderDialog.currentFolder = Util.fileUrl(onboarding.folder); folderDialog.open() }
          }
        }
      }
    }

    // Theme.
    Row {
      spacing: Style.space(6)
      Text {
        anchors.verticalCenter: parent.verticalCenter
        text: "Theme"
        color: Util.alpha(Colors.foreground, 0.55)
        font.pixelSize: Style.font.caption
        rightPadding: Style.space(8)
      }
      Repeater {
        model: [["system", "System"], ["dark", "Dark"], ["light", "Light"]]
        Rectangle {
          required property var modelData
          readonly property bool current: App.theme === modelData[0]
          width: themeLabel.implicitWidth + Style.space(22)
          height: Style.space(28)
          radius: height / 2
          color: current ? Colors.accent : Util.alpha(Colors.foreground, themeMouse.containsMouse ? 0.12 : 0.06)
          Text {
            id: themeLabel
            anchors.centerIn: parent
            text: parent.modelData[1]
            color: parent.current ? Colors.background : Colors.foreground
            font.pixelSize: Style.font.bodySmall
            font.weight: parent.current ? Font.DemiBold : Font.Normal
          }
          MouseArea {
            id: themeMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: App.setTheme(parent.modelData[0])
          }
        }
      }
    }

    // Meaning search.
    Item {
      width: parent.width
      height: semanticText.implicitHeight

      Rectangle {
        id: box
        width: Style.space(18)
        height: width
        radius: Style.space(4)
        color: onboarding.semantic ? Colors.accent : "transparent"
        border.width: 1
        border.color: onboarding.semantic ? Colors.accent : Util.alpha(Colors.foreground, 0.4)
        Text {
          anchors.centerIn: parent
          visible: onboarding.semantic
          text: String.fromCodePoint(0xf012c)
          color: Colors.background
          font.family: Style.font.icon
          font.pixelSize: Style.font.bodySmall
        }
      }
      Text {
        id: semanticText
        anchors.left: box.right
        anchors.leftMargin: Style.space(10)
        anchors.right: parent.right
        wrapMode: Text.Wrap
        text: "Find notes by meaning as well as by words. This downloads a small language model (about 170 MB) the first time, and everything runs on this computer."
        color: Util.alpha(Colors.foreground, 0.75)
        font.pixelSize: Style.font.bodySmall
        lineHeight: 1.2
      }
      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: onboarding.semantic = !onboarding.semantic
      }
    }

    Rectangle {
      width: startLabel.implicitWidth + Style.space(36)
      height: Style.space(38)
      radius: Math.max(Style.cornerRadius, Style.space(8))
      color: startMouse.containsMouse ? Qt.lighter(Colors.accent, 1.1) : Colors.accent
      Text {
        id: startLabel
        anchors.centerIn: parent
        text: "Start taking notes"
        color: Colors.background
        font.pixelSize: Style.font.body
        font.weight: Font.DemiBold
      }
      MouseArea {
        id: startMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: App.finishSetup(onboarding.folder, onboarding.semantic)
      }
    }
  }

  FolderDialog {
    id: folderDialog
    title: "Where should your notes live?"
    onAccepted: folderInput.text = App.localPath(String(selectedFolder))
  }
}
