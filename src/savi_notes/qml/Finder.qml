import QtQuick
import Savi

// Find anything, as in PyCharm's Search Everywhere: Shift twice opens it over
// the note. One box searches notes or tags, Left and Right switch between
// them, and with nothing typed it lists the latest notes.
Item {
  id: finder

  required property var app
  property bool opened: false
  property string tab: "notes"
  property int selected: 0
  // While picking a note for a link: what to call back with its title.
  property var picker: null
  property string pickPrompt: ""
  property string pickCreate: ""
  // "This file" leads while a note is open.
  readonly property var tabs: (app.current ? [{ id: "file", label: "This file" }] : [])
    .concat([{ id: "notes", label: "Notes" }, { id: "tags", label: "Tags" }, { id: "settings", label: "Settings" }])
  readonly property var fileActions: [
    { label: "Add tag", glyph: 0xf0722, run: function() { app.addTagFromFinder() } },
    { label: "Rename", glyph: 0xf0455, run: function() { app.renameFromFinder() } },
    { label: "Open note split right", glyph: 0xf0bcc, run: function() { app.openSplit("right") } },
    { label: "Open note split down", glyph: 0xf0bcb, run: function() { app.openSplit("down") } }
  ].concat(app.panes.length > 1 ? [{ label: "Close split", glyph: 0xf0158, run: function() { app.closePane(app.activePane) } }] : []).concat([
    { label: "Export as PDF", glyph: 0xf0226, hint: Style.ctrl + "+Shift+E", run: function() { app.exportPdf() } },
    { label: "Delete note", glyph: 0xf09e7, danger: true, run: function() { app.confirmDelete() } }
  ])
  // Settings rows stay open after Enter, so the new value shows.
  readonly property var settingsRows: [
    { label: "Theme", glyph: 0xf0594, hint: { system: "System", dark: "Dark", light: "Light" }[App.theme], stay: true,
      run: function() { App.setTheme({ system: "dark", dark: "light", light: "system" }[App.theme]) } },
    { label: "Find notes by meaning", glyph: 0xf0349, hint: App.semantic ? "On" : "Off", stay: true, run: function() { App.setSemantic(!App.semantic) } },
    { label: "Copy recovery key", glyph: 0xf0306, hint: "For your other computers", run: function() { App.copy(App.recoveryKey); app.showStatus("Recovery key copied", false) } },
    { label: "Sign out", glyph: 0xf0343, hint: App.email, danger: true, run: function() { app.signOut() } },
    { label: "Check for updates", glyph: 0xf06b0, hint: "Savi Notes " + App.version, run: function() { App.checkUpdates() } }
  ]
  readonly property bool actionTab: tab === "file" || tab === "settings"
  readonly property var visibleActions: {
    var typed = app.query.trim().toLowerCase()
    return (tab === "settings" ? settingsRows : fileActions).filter(function(a) { return a.label.toLowerCase().indexOf(typed) >= 0 })
  }

  // A "New note" row follows the matches whenever the query isn't an exact title.
  readonly property bool offersCreate: tab === "notes" && app.query.trim() !== "" && !app.byTitle[app.query.trim().toLowerCase()]
  // On Tags, a name no note carries yet offers to add it to the open note,
  // or to start a note with it.
  readonly property string newTag: {
    var typed = app.query.trim().replace(/^#/, "").toLowerCase()
    if (tab !== "tags" || !/^[a-z][\w\/-]*$/.test(typed)) return ""
    return app.tagCounts.some(function(t) { return t.tag === typed }) ? "" : typed
  }
  readonly property var visibleTags: {
    var typed = app.query.trim().replace(/^#/, "").toLowerCase()
    if (!typed) return app.tagCounts
    var starts = [], contains = []
    app.tagCounts.forEach(function(t) {
      var at = t.tag.indexOf(typed)
      if (at === 0) starts.push(t)
      else if (at > 0) contains.push(t)
    })
    return starts.concat(contains)
  }
  readonly property int rowCount: actionTab ? visibleActions.length : tab === "tags" ? visibleTags.length + (newTag ? 1 : 0) : app.visibleNotes.length + (offersCreate ? 1 : 0)
  // The "New note" row leads the list; notes follow it.
  readonly property int noteOffset: offersCreate ? 1 : 0
  readonly property var selectedNote: tab === "notes" ? app.visibleNotes[selected - noteOffset] || null : null

  visible: opacity > 0
  opacity: opened ? 1 : 0
  Behavior on opacity { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }

  function open(tab, tags) {
    searchInput.text = ""
    app.activeTags = tags || []
    finder.tab = tab || "notes"
    finder.opened = true
    resetSelection()
    searchInput.forceActiveFocus()
  }

  function pick(prompt, done, createLabel) {
    open("notes")
    finder.picker = done
    finder.pickPrompt = prompt
    finder.pickCreate = createLabel || "Link to new note"
  }

  function close() {
    if (!opened) return
    opened = false
    picker = null
    searchInput.text = ""
    app.activeTags = []
    app.restoreFocus()
  }

  function toggle() { if (opened) close(); else open(app.current ? "file" : "notes") }

  function switchTab(step) {
    if (picker) return
    var at = tabs.findIndex(function(t) { return t.id === finder.tab })
    finder.tab = tabs[(at + step + tabs.length) % tabs.length].id
    resetSelection()
  }

  // The best match starts selected, so Enter opens it; Up reaches "New note".
  function resetSelection() {
    finder.selected = tab === "notes" && offersCreate && app.visibleNotes.length ? 1 : 0
    list.positionViewAtBeginning()
  }

  // Enter before the results for the latest keystroke arrive waits for them.
  property bool pendingActivate: false
  function searchSettled() {
    if (!pendingActivate) return
    pendingActivate = false
    activate(selected)
  }

  function activate(index) {
    if (actionTab) {
      var action = visibleActions[index]
      if (!action) return
      if (!action.stay) close()
      action.run()
      return
    }
    if (tab === "tags") {
      if (index >= visibleTags.length) { if (newTag) addTag(newTag); return }
      app.toggleTag(visibleTags[index].tag)
      searchInput.text = ""
      finder.tab = "notes"
      resetSelection()
      return
    }
    if (app.searching) { pendingActivate = true; return }
    if (picker) {
      var done = picker
      var picked = app.visibleNotes[index - noteOffset]
      var title = offersCreate && index === 0 ? app.query.trim() : picked ? picked.title : ""
      if (!title) return
      close()
      done(title)
      return
    }
    if (offersCreate && index === 0) { app.newNote(); return }
    var note = app.visibleNotes[index - noteOffset]
    if (!note) return
    close()
    app.openNote(note.path)
  }

  function addTag(tag) {
    close()
    if (!app.current) { app.createNote("", [tag]); return }
    if (app.ownTags.indexOf(tag) < 0) app.setTags(app.ownTags.concat([tag]))
    app.showStatus("Tagged " + app.current.title + " #" + tag, false)
  }

  function relativeTime(seconds) {
    var diff = Date.now() / 1000 - seconds
    if (diff < 60) return "now"
    if (diff < 3600) return Math.floor(diff / 60) + "m"
    if (diff < 86400) return Math.floor(diff / 3600) + "h"
    if (diff < 86400 * 7) return Math.floor(diff / 86400) + "d"
    return Qt.formatDate(new Date(seconds * 1000), diff < 86400 * 300 ? "MMM d" : "MMM yyyy")
  }

  // Clicking outside closes it.
  MouseArea {
    anchors.fill: parent
    onClicked: finder.close()
    Rectangle { anchors.fill: parent; color: Qt.rgba(0, 0, 0, 0.28) }
  }

  BorderSurface {
    id: card
    width: Math.min(Style.space(760), parent.width - Style.space(48))
    height: Math.min(Style.space(560), parent.height - y - Style.space(24))
    anchors.horizontalCenter: parent.horizontalCenter
    y: Math.round(Math.max(Style.space(24), parent.height * 0.08))
    scale: finder.opened ? 1 : 0.98
    Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
    radius: Math.max(Style.cornerRadius, Style.space(12))
    color: Qt.rgba(Colors.background.r, Colors.background.g, Colors.background.b, 1)
    borderSpec: Border.localOrSurfaceSpec("popups", "border", Colors.popups.border, Colors.popups.border, 1)

    // Keep clicks inside from closing it.
    MouseArea { anchors.fill: parent }

    Rectangle { anchors.fill: parent; radius: card.radius; color: Util.alpha(Colors.foreground, 0.035) }

    // Tabs, and the note actions beside them.
    Row {
      id: tabRow
      x: Style.space(14)
      y: Style.space(12)
      spacing: Style.space(4)

      Repeater {
        model: finder.picker ? [{ id: "notes", label: finder.pickPrompt }] : finder.tabs
        Rectangle {
          id: tabPill
          required property var modelData
          readonly property bool current: finder.tab === modelData.id
          width: tabLabel.implicitWidth + Style.space(26)
          height: Style.space(30)
          radius: Math.max(Style.cornerRadius, Style.space(8))
          color: current ? Util.alpha(Colors.accent, 0.16) : tabMouse.containsMouse ? Util.alpha(Colors.foreground, 0.06) : "transparent"
          border.width: current ? 1 : 0
          border.color: Util.alpha(Colors.accent, 0.7)
          Text {
            id: tabLabel
            anchors.centerIn: parent
            text: tabPill.modelData.label
            color: tabPill.current ? Colors.foreground : Util.alpha(Colors.foreground, 0.65)
            font.pixelSize: Style.font.body
            font.weight: tabPill.current ? Font.DemiBold : Font.Normal
          }
          MouseArea {
            id: tabMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: { finder.tab = tabPill.modelData.id; finder.resetSelection(); searchInput.forceActiveFocus() }
          }
        }
      }
    }

    Row {
      visible: !finder.picker
      anchors.right: parent.right
      anchors.rightMargin: Style.space(14)
      anchors.verticalCenter: tabRow.verticalCenter
      spacing: Style.space(6)

      IconButton {
        glyph: String.fromCodePoint(0xf00f6)
        tip: "Today's note  " + Style.ctrl + "+D"
        onActivated: { finder.close(); app.todaysNote() }
      }
      IconButton {
        id: syncButton
        visible: app.syncEnabled
        glyph: app.syncState === "conflict" || app.syncState === "error" ? String.fromCodePoint(0xf04e7)
             : app.syncState === "offline" ? String.fromCodePoint(0xf0164)
             : String.fromCodePoint(0xf04e6)
        highlighted: app.syncState === "running"
        tip: app.syncState === "running" ? "Syncing…"
           : app.syncState === "offline" ? "Offline; will sync later"
           : app.syncState === "conflict" || app.syncState === "error" ? app.syncMessage
           : app.syncTime ? "Synced " + finder.relativeTime(app.syncTime) + (finder.relativeTime(app.syncTime) === "now" ? "" : " ago") + "; click to sync now"
           : "Sync now"
        onActivated: app.syncNow()

        RotationAnimator on rotation {
          running: app.syncState === "running"
          from: 0; to: -360; duration: 1100
          loops: Animation.Infinite
          onStopped: syncButton.rotation = 0
        }
      }
      IconButton {
        glyph: String.fromCodePoint(0xf039d)
        tip: "New note  " + Style.ctrl + "+N"
        onActivated: app.newNote()
      }
    }

    // The box: chosen tags, then the query.
    Rectangle {
      id: searchBox
      x: Style.space(14)
      y: tabRow.y + tabRow.height + Style.space(10)
      width: parent.width - Style.space(28)
      height: Style.space(40)
      radius: Math.max(Style.cornerRadius, Style.space(8))
      color: Util.alpha(Colors.foreground, 0.05)
      border.width: 1
      border.color: searchInput.activeFocus ? Colors.accent : Util.alpha(Colors.foreground, 0.1)

      Text {
        id: searchIcon
        x: Style.space(13)
        anchors.verticalCenter: parent.verticalCenter
        text: String.fromCodePoint(0xf0349)
        color: Util.alpha(Colors.foreground, 0.5)
        font.family: Style.font.icon
        font.pixelSize: Style.font.title
      }

      Row {
        id: chips
        anchors.left: searchIcon.right
        anchors.leftMargin: app.activeTags.length ? Style.space(9) : 0
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(5)

        Repeater {
          model: app.activeTags
          Rectangle {
            required property string modelData
            width: chipLabel.implicitWidth + Style.space(18)
            height: Style.space(24)
            radius: height / 2
            color: chipMouse.containsMouse ? Util.alpha(Colors.accent, 0.8) : Colors.accent
            Text {
              id: chipLabel
              anchors.centerIn: parent
              text: "#" + parent.modelData + "  " + String.fromCodePoint(0xf0156)
              color: Colors.background
              font.pixelSize: Style.font.bodySmall
              font.bold: true
            }
            MouseArea {
              id: chipMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: { app.toggleTag(parent.modelData); searchInput.forceActiveFocus() }
            }
          }
        }
      }

      TextInput {
        id: searchInput
        anchors.left: chips.right
        anchors.leftMargin: Style.space(9)
        anchors.right: hint.left
        anchors.rightMargin: spinner.visible ? spinner.implicitWidth + Style.space(18) : Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        color: Colors.foreground
        selectionColor: Util.alpha(Colors.accent, 0.45)
        selectedTextColor: Colors.foreground
        font.pixelSize: Style.font.subtitle
        clip: true
        onTextChanged: app.query = text

        Keys.onPressed: function(event) {
          var ctrl = event.modifiers & Qt.ControlModifier
          var plain = !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier))
          var listKey = event.key === Qt.Key_J || event.key === Qt.Key_K || event.key === Qt.Key_Return || event.key === Qt.Key_Enter
          if (!(ctrl && listKey) && app.shortcut(event)) { event.accepted = true; return }
          if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && ctrl) { if (!finder.picker) app.newNote() }
          else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) finder.activate(finder.selected)
          else if (plain && event.key === Qt.Key_Right || event.key === Qt.Key_Tab) finder.switchTab(1)
          else if (plain && event.key === Qt.Key_Left || event.key === Qt.Key_Backtab) finder.switchTab(-1)
          else if (event.key === Qt.Key_Down || (ctrl && event.key === Qt.Key_J)) finder.selected = Math.min(finder.rowCount - 1, finder.selected + 1)
          else if (event.key === Qt.Key_Up || (ctrl && event.key === Qt.Key_K)) finder.selected = Math.max(0, finder.selected - 1)
          else if (event.key === Qt.Key_PageDown) finder.selected = Math.min(finder.rowCount - 1, finder.selected + 10)
          else if (event.key === Qt.Key_PageUp) finder.selected = Math.max(0, finder.selected - 10)
          else if (event.key === Qt.Key_Backspace && !text && app.activeTags.length) app.activeTags = app.activeTags.slice(0, -1)
          else if (event.key === Qt.Key_Escape && text) text = ""
          else if (event.key === Qt.Key_Escape) finder.close()
          else return
          event.accepted = true
        }

        Text {
          anchors.fill: parent
          verticalAlignment: Text.AlignVCenter
          visible: !searchInput.text
          text: finder.picker ? "Find a note" : finder.tab === "settings" ? "Search settings" : finder.tab === "file" ? "Search actions" : finder.tab === "tags" ? "Search tags" : app.activeTags.length ? "Search these notes" : "Search or create"
          color: Util.alpha(Colors.foreground, 0.4)
          font: searchInput.font
        }
      }

      // Shown only once a search runs long enough to notice, so quick ones
      // don't flicker it.
      Text {
        id: spinner
        anchors.right: hint.left
        anchors.rightMargin: Style.space(10)
        anchors.verticalCenter: parent.verticalCenter
        visible: false
        text: String.fromCodePoint(0xf0772)
        color: Colors.accent
        font.family: Style.font.icon
        font.pixelSize: Style.font.title

        RotationAnimator on rotation {
          running: spinner.visible
          from: 0; to: 360; duration: 800
          loops: Animation.Infinite
        }

        Timer {
          interval: 250
          running: app.searching
          onTriggered: spinner.visible = true
        }
        Connections {
          target: app
          function onSearchingChanged() { if (!app.searching) spinner.visible = false }
        }
      }

      Text {
        id: hint
        anchors.right: parent.right
        anchors.rightMargin: Style.space(13)
        anchors.verticalCenter: parent.verticalCenter
        visible: !finder.picker
        text: "← → switch tabs"
        color: Util.alpha(Colors.foreground, 0.3)
        font.pixelSize: Style.font.caption
      }
    }

    ListView {
      id: list
      x: Style.space(10)
      y: searchBox.y + searchBox.height + Style.space(8)
      width: parent.width - Style.space(20)
      height: footer.y - y - Style.space(4)
      clip: true
      spacing: Style.space(2)
      boundsBehavior: Flickable.StopAtBounds
      model: finder.rowCount
      currentIndex: finder.selected
      highlightFollowsCurrentItem: false
      onCurrentIndexChanged: positionViewAtIndex(currentIndex, ListView.Contain)

      delegate: Rectangle {
        id: row
        required property int index
        readonly property bool isTag: finder.tab === "tags"
        readonly property var action: finder.actionTab ? finder.visibleActions[index] || null : null
        readonly property var tagItem: isTag && index < finder.visibleTags.length ? finder.visibleTags[index] : null
        readonly property bool isCreate: action ? false : isTag ? index >= finder.visibleTags.length : finder.offersCreate && index === 0
        readonly property var note: action || isTag || isCreate ? null : app.visibleNotes[index - finder.noteOffset] || null
        readonly property bool chosen: !!tagItem && app.activeTags.indexOf(tagItem.tag) >= 0
        readonly property bool meaning: !!note && note.match === "meaning"
        width: list.width
        height: Style.space(34)
        radius: Math.max(Style.cornerRadius, Style.space(6))
        color: index === finder.selected ? Util.alpha(Colors.accent, 0.2)
             : rowMouse.containsMouse ? Util.alpha(Colors.foreground, 0.05) : "transparent"

        Text {
          id: rowIcon
          x: Style.space(10)
          width: Style.space(18)
          anchors.verticalCenter: parent.verticalCenter
          horizontalAlignment: Text.AlignHCenter
          text: row.action ? String.fromCodePoint(row.action.glyph)
              : row.isCreate ? String.fromCodePoint(row.isTag ? 0xf0722 : 0xf039d)
              : row.isTag ? String.fromCodePoint(row.chosen ? 0xf012c : 0xf04f9)
              : String.fromCodePoint(0xf0219)
          color: row.action && row.action.danger ? Colors.urgent : row.isCreate || row.chosen ? Colors.accent : Util.alpha(Colors.foreground, 0.55)
          font.family: Style.font.icon
          font.pixelSize: Style.font.subtitle
        }

        Text {
          id: rowTitle
          anchors.left: rowIcon.right
          anchors.leftMargin: Style.space(10)
          anchors.verticalCenter: parent.verticalCenter
          width: Math.min(implicitWidth, row.isCreate ? parent.width - Style.space(60) : parent.width * 0.5)
          text: row.action ? row.action.label
              : row.isCreate && row.isTag ? (app.current ? "Add #" + finder.newTag + " to " + app.current.title : "New note tagged #" + finder.newTag)
              : row.isTag ? (row.tagItem ? row.tagItem.tag : "")
              : row.isCreate ? (finder.picker ? finder.pickCreate + " “" : "New note “") + app.query.trim() + "”"
              : row.note ? row.note.title : ""
          color: row.action && row.action.danger ? Colors.urgent : Colors.foreground
          font.pixelSize: Style.font.subtitle
          elide: Text.ElideRight
        }

        // The tags and opening words, dimmed, as PyCharm shows a file's folder.
        Text {
          anchors.left: rowTitle.right
          anchors.leftMargin: Style.space(10)
          anchors.right: rowMeta.left
          anchors.rightMargin: Style.space(10)
          anchors.verticalCenter: parent.verticalCenter
          visible: !!row.note
          textFormat: Text.StyledText
          text: {
            if (!row.note) return ""
            var tags = row.note.tags.map(function(t) { return "#" + t }).join(" ")
            var snippet = (row.note.snippet || "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
            return (tags ? "<font color='" + Util.alpha(Colors.accent, 0.75) + "'>" + tags + "</font>  " : "") + snippet
          }
          color: Util.alpha(Colors.foreground, 0.4)
          font.pixelSize: Style.font.bodySmall
          elide: Text.ElideRight
        }

        Text {
          id: rowMeta
          anchors.right: parent.right
          anchors.rightMargin: Style.space(12)
          anchors.verticalCenter: parent.verticalCenter
          text: row.action ? row.action.hint || ""
              : row.isTag ? (row.tagItem ? row.tagItem.count : "")
              : row.note ? (row.meaning ? String.fromCodePoint(0xf0674) + " " : "") + finder.relativeTime(row.note.mtime)
              : ""
          color: row.meaning ? Colors.accent : Util.alpha(Colors.foreground, 0.4)
          font.family: Style.font.icon
          font.pixelSize: Style.font.caption
        }

        MouseArea {
          id: rowMouse
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: { finder.selected = row.index; finder.activate(row.index); if (finder.opened) searchInput.forceActiveFocus() }
        }
      }

      Text {
        anchors.centerIn: parent
        width: parent.width - Style.space(30)
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        visible: finder.rowCount === 0 && app.loaded
        text: finder.tab === "tags" ? (app.tagCounts.length ? "No tags match" : "No tags yet")
            : app.activeTags.length ? "No notes carry all of these tags"
            : "No notes yet.\nType a title above and press Enter."
        color: Util.alpha(Colors.foreground, 0.45)
        font.pixelSize: Style.font.bodySmall
      }
    }

    // Where the selected note lives, and counts or index state.
    Item {
      id: footer
      y: parent.height - height
      width: parent.width
      height: Style.space(34)

      Rectangle { width: parent.width; height: 1; color: Util.alpha(Colors.foreground, 0.08) }

      Text {
        anchors.left: parent.left
        anchors.leftMargin: Style.space(16)
        anchors.right: counts.left
        anchors.rightMargin: Style.space(12)
        anchors.verticalCenter: parent.verticalCenter
        readonly property var shownNote: finder.tab === "file" ? app.current : finder.tab === "settings" ? null : finder.selectedNote
        text: shownNote ? (app.vault + "/" + shownNote.path).replace(App.home, "~") : ""
        color: Util.alpha(Colors.foreground, 0.45)
        font.pixelSize: Style.font.caption
        elide: Text.ElideMiddle
      }

      Text {
        id: counts
        anchors.right: parent.right
        anchors.rightMargin: Style.space(16)
        anchors.verticalCenter: parent.verticalCenter
        text: {
          if (app.indexState) return app.indexState
          if (finder.actionTab) return ""
          if (finder.tab === "tags") { var t = finder.visibleTags.length; return t + (t === 1 ? " tag" : " tags") }
          var n = app.visibleNotes.length
          if (app.query.trim()) return n + (n === 1 ? " match" : " matches")
          return n + (n === 1 ? " note" : " notes")
        }
        color: Util.alpha(Colors.foreground, 0.45)
        font.pixelSize: Style.font.caption
      }
    }
  }

}
