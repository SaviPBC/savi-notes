import QtQuick
import Savi

// The first run, and whenever the sign-in or the note key is missing: sign in
// to the Savi AI Core, then either save a new recovery key or enter the one
// another computer showed. The host (App.setupStep) decides which step shows.
FocusScope {
  id: onboarding

  property bool semantic: App.semantic
  property bool saved: false
  readonly property string step: App.setupStep

  visible: App.needsSetup
  onVisibleChanged: if (visible) forceActiveFocus()
  onStepChanged: { saved = false; recoveryInput.text = ""; if (step === "recover") recoveryInput.forceActiveFocus() }
  Component.onCompleted: if (visible) forceActiveFocus()
  Keys.onReturnPressed: primary()
  Keys.onEnterPressed: primary()

  function primary() {
    if (step === "signin") App.signIn(onboarding.semantic)
    else if (step === "newKey" && onboarding.saved) App.keySaved()
    else if (step === "recover" && recoveryInput.text.trim()) App.recover(recoveryInput.text)
  }

  component Button: Rectangle {
    id: button
    property string label
    property bool primary: true
    signal clicked()
    width: buttonLabel.implicitWidth + Style.space(36)
    height: Style.space(38)
    radius: Math.max(Style.cornerRadius, Style.space(8))
    opacity: enabled ? 1 : 0.4
    color: primary ? (buttonMouse.containsMouse ? Qt.lighter(Colors.accent, 1.1) : Colors.accent)
         : Util.alpha(Colors.foreground, buttonMouse.containsMouse ? 0.14 : 0.08)
    Text {
      id: buttonLabel
      anchors.centerIn: parent
      text: button.label
      color: button.primary ? Colors.background : Colors.foreground
      font.pixelSize: Style.font.body
      font.weight: button.primary ? Font.DemiBold : Font.Normal
    }
    MouseArea {
      id: buttonMouse
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: button.clicked()
    }
  }

  component Prose: Text {
    width: parent.width
    wrapMode: Text.Wrap
    color: Util.alpha(Colors.foreground, 0.7)
    font.pixelSize: Style.font.body
    lineHeight: 1.25
  }

  component Check: Item {
    id: check
    property bool checked
    property string label
    signal toggled()
    width: parent.width
    height: checkText.implicitHeight
    Rectangle {
      id: box
      width: Style.space(18)
      height: width
      radius: Style.space(4)
      color: check.checked ? Colors.accent : "transparent"
      border.width: 1
      border.color: check.checked ? Colors.accent : Util.alpha(Colors.foreground, 0.4)
      Text {
        anchors.centerIn: parent
        visible: check.checked
        text: String.fromCodePoint(0xf012c)
        color: Colors.background
        font.family: Style.font.icon
        font.pixelSize: Style.font.bodySmall
      }
    }
    Text {
      id: checkText
      anchors.left: box.right
      anchors.leftMargin: Style.space(10)
      anchors.right: parent.right
      wrapMode: Text.Wrap
      text: check.label
      color: Util.alpha(Colors.foreground, 0.75)
      font.pixelSize: Style.font.bodySmall
      lineHeight: 1.2
    }
    MouseArea {
      anchors.fill: parent
      cursorShape: Qt.PointingHandCursor
      onClicked: check.toggled()
    }
  }

  Rectangle { anchors.fill: parent; color: Colors.background }

  Column {
    anchors.centerIn: parent
    width: Math.min(parent.width - Style.space(48), Style.space(520))
    spacing: Style.space(18)

    Text {
      text: String.fromCodePoint(onboarding.step === "newKey" || onboarding.step === "recover" ? 0xf0306 : 0xf0ebf)
      color: Colors.accent
      font.family: Style.font.icon
      font.pixelSize: Style.font.display * 2
    }

    Text {
      width: parent.width
      wrapMode: Text.Wrap
      text: onboarding.step === "newKey" ? "Save your recovery key"
          : onboarding.step === "recover" ? "Enter your recovery key"
          : onboarding.step === "waiting" ? "Finish signing in in your browser"
          : "Welcome to Savi Notes"
      color: Colors.foreground
      font.pixelSize: Style.font.display
      font.weight: Font.Bold
    }

    // ---------------------------------------------------------------- sign in

    Prose {
      visible: onboarding.step === "signin"
      text: "Your notes are encrypted on this computer before they're saved to the Savi AI Core, so they're on every computer you sign in to and no one at Savi can read them. Notes are organised by tags, not folders."
    }

    Prose {
      visible: onboarding.step === "waiting"
      text: "Sign in with your Savi Google account and authorize Savi Notes, then come back here."
    }

    Row {
      visible: onboarding.step === "signin"
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

    Check {
      visible: onboarding.step === "signin"
      checked: onboarding.semantic
      label: "Find notes by meaning as well as by words. This downloads a small language model (about 170 MB) the first time, and it runs on this computer."
      onToggled: onboarding.semantic = !onboarding.semantic
    }

    // ---------------------------------------------------------------- new key

    Prose {
      visible: onboarding.step === "newKey"
      text: "It unlocks your notes on any other computer you sign in to. Savi doesn't keep a copy, so if you lose this key and this computer, nobody can recover your notes. Save it in your password manager."
    }

    Rectangle {
      visible: onboarding.step === "newKey"
      width: parent.width
      height: keyText.implicitHeight + Style.space(24)
      radius: Math.max(Style.cornerRadius, Style.space(8))
      color: Util.alpha(Colors.foreground, 0.05)
      border.width: 1
      border.color: Util.alpha(Colors.foreground, 0.1)
      TextEdit {
        id: keyText
        anchors.left: parent.left
        anchors.leftMargin: Style.space(14)
        anchors.right: copyButton.left
        anchors.rightMargin: Style.space(10)
        anchors.verticalCenter: parent.verticalCenter
        text: App.recoveryKey
        readOnly: true
        selectByMouse: true
        wrapMode: TextEdit.Wrap
        color: Colors.foreground
        selectionColor: Util.alpha(Colors.accent, 0.4)
        font.family: Style.font.mono
        font.pixelSize: Style.font.body
      }
      Button {
        id: copyButton
        anchors.right: parent.right
        anchors.rightMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        height: Style.space(28)
        primary: false
        label: copied ? "Copied" : "Copy"
        property bool copied: false
        onClicked: { App.copy(App.recoveryKey); copied = true }
      }
    }

    Check {
      visible: onboarding.step === "newKey"
      checked: onboarding.saved
      label: "I've saved my recovery key somewhere safe"
      onToggled: onboarding.saved = !onboarding.saved
    }

    // ---------------------------------------------------------------- recover

    Prose {
      visible: onboarding.step === "recover"
      text: "Your notes are already set up on another computer, which showed you a recovery key. Enter it to unlock them here."
    }

    Rectangle {
      visible: onboarding.step === "recover"
      width: parent.width
      height: Style.space(40)
      radius: Math.max(Style.cornerRadius, Style.space(8))
      color: Util.alpha(Colors.foreground, 0.05)
      border.width: 1
      border.color: recoveryInput.activeFocus ? Colors.accent : Util.alpha(Colors.foreground, 0.1)
      TextInput {
        id: recoveryInput
        anchors.fill: parent
        anchors.leftMargin: Style.space(12)
        anchors.rightMargin: Style.space(12)
        verticalAlignment: TextInput.AlignVCenter
        color: Colors.foreground
        selectionColor: Util.alpha(Colors.accent, 0.4)
        selectedTextColor: Colors.foreground
        font.family: Style.font.mono
        font.pixelSize: Style.font.body
        clip: true
        Keys.onReturnPressed: onboarding.primary()
        Keys.onEnterPressed: onboarding.primary()
        Text {
          anchors.verticalCenter: parent.verticalCenter
          visible: !parent.text
          text: "XXXX-XXXX-XXXX-…"
          color: Util.alpha(Colors.foreground, 0.35)
          font: parent.font
        }
      }
    }

    // ---------------------------------------------------------------- shared

    Text {
      visible: App.setupError !== ""
      width: parent.width
      wrapMode: Text.Wrap
      text: App.setupError
      color: Colors.urgent
      font.pixelSize: Style.font.bodySmall
    }

    Row {
      spacing: Style.space(10)

      Button {
        visible: onboarding.step !== "waiting"
        enabled: onboarding.step !== "newKey" || onboarding.saved
        label: onboarding.step === "newKey" ? "Start taking notes" : onboarding.step === "recover" ? "Unlock notes" : "Sign in with Savi"
        onClicked: onboarding.primary()
      }

      Button {
        visible: onboarding.step === "waiting"
        primary: false
        label: "Cancel"
        onClicked: App.cancelSignIn()
      }
    }

    Text {
      visible: onboarding.step === "recover"
      text: "Lost your recovery key? Start over"
      color: Util.alpha(Colors.foreground, startOverMouse.containsMouse ? 0.8 : 0.5)
      font.pixelSize: Style.font.bodySmall
      font.underline: startOverMouse.containsMouse
      MouseArea {
        id: startOverMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: startOverDialog.opened = true
      }
    }
  }

  ConfirmDialog {
    id: startOverDialog
    anchors.fill: parent
    message: "Start over with a new recovery key? The notes saved to the AI Core can't be opened without the old key, so they'll be deleted."
    cancelText: "Keep looking"
    confirmText: "Delete and start over"
    onCanceled: opened = false
    onConfirmed: { opened = false; App.startOver() }
  }
}
