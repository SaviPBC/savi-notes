import QtQuick
import QtQuick.Dialogs
import Savi
import "Markdown.js" as Markdown

// One pane's note: its title and tags, then the body, rendered to read or
// as markdown source to edit. The Pane holds the text and saves it.
FocusScope {
  id: view

  required property var app
  required property var pane
  property var shownPane: null
  readonly property bool active: app.activePane === pane

  // Whichever pane has focus is the one the finder and shortcuts act on.
  onActiveFocusChanged: if (activeFocus) app.activePane = pane
  onPaneChanged: attach()
  Component.onCompleted: attach()
  Component.onDestruction: if (shownPane && shownPane.view === view) shownPane.view = null

  function attach() {
    if (shownPane && shownPane.view === view) shownPane.view = null
    shownPane = pane
    if (!pane) return
    pane.view = view
    loadBody()
  }

  function saveAndRead() {
    pane.save()
    if (pane.editing) toggleEditing()
  }

  // Open the new-tag field under the title.
  function startAddTag() {
    if (!note) return
    addTag.adding = true
    tagInput.forceActiveFocus()
  }

  readonly property var note: pane.note
  // Obsidian's reading view: 15px sans text in a 700px column.
  readonly property int columnWidth: Math.min(Math.round(700 * Style.fontScale), width - Style.space(96))
  readonly property int bodySize: Style.fontPx(1.25)
  readonly property string sans: "sans-serif"
  property string rendered: ""
  property var folds: ({})
  property var wanted: []
  property var requested: ({})
  // The heading level of the line the cursor is on, for the toolbar.
  readonly property int headingLevel: {
    if (!pane.editing) return 0
    var t = editor.text, p = editor.cursorPosition
    var m = t.slice(t.lastIndexOf("\n", p - 1) + 1).match(/^(#{1,6})[ \t]/)
    return m ? m[1].length : 0
  }

  function theme(forPrint) {
    var embeds = {}
    for (var a in app.assets) embeds[a] = app.assets[a]
    for (var e in pane.embeds) embeds[e] = pane.embeds[e]
    return {
      accent: forPrint ? Qt.color("#3b5bdb") : Colors.accent,
      fg: forPrint ? Qt.color("#1d1f21") : Colors.foreground,
      bg: forPrint ? Qt.color("#ffffff") : Colors.background,
      palette: Colors.palette,
      print: forPrint,
      mono: Style.font.mono,
      icon: Style.font.icon,
      sans: view.sans,
      size: view.bodySize,
      width: forPrint ? 640 : view.columnWidth,
      embeds: embeds,
      folds: view.folds,
      exists: function(title) { return !!app.byTitle[title.toLowerCase()] },
      need: function(item) { view.wanted.push(item) }
    }
  }

  function loadBody() {
    editor.text = pane.body
    render()
    if (active) restoreFocus()
  }

  function render() {
    view.wanted = []
    view.rendered = Markdown.render(pane.body, view.theme(false))
    var ask = view.wanted.filter(function(item) { return !view.requested[item.key] })
    if (!ask.length) return
    ask.forEach(function(item) { view.requested[item.key] = true })
    app.requestAssets(ask)
  }

  function forgetRequests() {
    var next = {}
    for (var k in view.requested) if (k.indexOf("note:") !== 0) next[k] = true
    view.requested = next
  }

  function toggleFold(line) {
    var next = {}
    for (var k in view.folds) next[k] = view.folds[k]
    var callout = (pane.body.split("\n")[line] || "").match(/\[![^\]]+\]([+-]?)/)
    var open = next[line] !== undefined ? next[line] : !(callout && callout[1] === "-")
    next[line] = !open
    view.folds = next
    render()
  }

  // Scroll the reader to the first line that starts with text.
  function scrollToText(text, last) {
    if (!text) return
    var plain = reader.getText(0, reader.length).toLowerCase()
    var want = "\n" + text.toLowerCase()
    var at = last ? plain.lastIndexOf(want) : plain.indexOf(want)
    if (at < 0) at = last ? plain.lastIndexOf(text.toLowerCase()) : plain.indexOf(text.toLowerCase())
    else at += 1
    if (at < 0) return
    var rect = reader.positionToRectangle(at)
    page.contentY = Math.max(0, Math.min(page.contentHeight - page.height, column.y + body.y + rect.y - Style.space(24)))
  }

  function scrollToHeading(anchor) {
    if (anchor && anchor[0] !== "^") Qt.callLater(scrollToText, anchor, false)
  }

  function scrollToFootnote(link) {
    var n = link.split(":")[1]
    if (link.indexOf("footnote-ref:") === 0) scrollToText("[" + n + "]", false)
    else scrollToText(n + ".", true)
  }

  function printHtml() {
    return Markdown.render(pane.body, view.theme(true))
  }

  onColumnWidthChanged: if (note && !pane.editing) render()

  function toggleEditing() {
    if (!note) return
    pane.editing = !pane.editing
    if (pane.editing) focusEditor()
    else { pane.save(); render(); reader.forceActiveFocus() }
  }

  function focusEditor() {
    pane.editing = true
    editor.forceActiveFocus()
  }

  function restoreFocus() {
    if (!note) view.forceActiveFocus()
    else if (pane.editing) editor.forceActiveFocus()
    else reader.forceActiveFocus()
  }

  // ------------------------------------------------------------ formatting

  // Replace start..end with text, select within it, and save.
  function replace(start, end, text, selStart, selEnd) {
    if (end > start) editor.remove(start, end)
    if (text) editor.insert(start, text)
    editor.select(selStart, selEnd === undefined ? selStart : selEnd)
    editor.forceActiveFocus()
    pane.edited(editor.text)
  }

  // Wrap the selection in markers, or unwrap it if it already is. With
  // nothing selected the placeholder is put in and selected.
  function wrap(before, after, placeholder) {
    var t = editor.text, s = editor.selectionStart, e = editor.selectionEnd
    if (t.slice(s - before.length, s) === before && t.slice(e, e + after.length) === after) {
      replace(s - before.length, e + after.length, t.slice(s, e), s - before.length, e - before.length)
      return
    }
    var sel = t.slice(s, e)
    if (sel.length >= before.length + after.length && sel.indexOf(before) === 0 && sel.slice(sel.length - after.length) === after) {
      var inner = sel.slice(before.length, sel.length - after.length)
      replace(s, e, inner, s, s + inner.length)
      return
    }
    var text = sel || placeholder || ""
    replace(s, e, before + text + after, s + before.length, s + before.length + text.length)
  }

  // Put text at the cursor (replacing the selection), selecting selLen
  // characters at caret within it.
  function insertInline(before, after, fallback, caret, selLen) {
    var s = editor.selectionStart, e = editor.selectionEnd
    var text = before + (editor.text.slice(s, e) || fallback || "") + after
    replace(s, e, text, s + caret, s + caret + (selLen || 0))
  }

  function webLink() {
    var s = editor.selectionStart, e = editor.selectionEnd, sel = editor.text.slice(s, e)
    if (/^https?:\/\/\S+$/.test(sel)) replace(s, e, "[](" + sel + ")", s + 1)
    else if (sel) replace(s, e, "[" + sel + "](https://)", s + sel.length + 3, s + sel.length + 11)
    else replace(s, e, "[text](https://)", s + 1, s + 5)
  }

  // The whole lines the selection touches.
  function selectedLines() {
    var t = editor.text, s = editor.selectionStart, e = editor.selectionEnd
    if (e > s && t[e - 1] === "\n") e--
    var start = t.lastIndexOf("\n", s - 1) + 1
    var end = t.indexOf("\n", e)
    if (end < 0) end = t.length
    return { start: start, end: end, lines: t.slice(start, end).split("\n") }
  }

  function rewriteLines(change) {
    var r = selectedLines()
    var hadSelection = editor.selectionEnd > editor.selectionStart
    var fromEnd = r.end - editor.cursorPosition
    var text = change(r.lines).join("\n")
    if (hadSelection) replace(r.start, r.end, text, r.start, r.start + text.length)
    else replace(r.start, r.end, text, Math.max(r.start, r.start + text.length - fromEnd))
  }

  function setHeading(level) {
    rewriteLines(function(lines) {
      // Inside a quote or callout the heading goes after the >.
      return lines.map(function(l) {
        var m = l.match(/^((?:\s*> ?)*)(.*)$/)
        return m[1] + (level ? "#".repeat(level) + " " : "") + m[2].replace(/^#{1,6}[ \t]+/, "")
      })
    })
  }

  // Bullets, numbers, tasks and quotes: applied to every line, or taken off
  // if every line already has it.
  function setList(kind) {
    var marker = /^(\s*)(?:[-*+] \[.\] |[-*+] |\d+[.)] |> ?)/
    var has = { bullet: /^\s*[-*+] (?!\[.\] )/, number: /^\s*\d+[.)] /, task: /^\s*[-*+] \[.\] /, quote: /^\s*>/ }[kind]
    rewriteLines(function(lines) {
      var filled = lines.filter(function(l) { return l.trim() })
      var off = filled.length > 0 && filled.every(function(l) { return has.test(l) })
      var n = 0
      return lines.map(function(l) {
        if (!l.trim() && lines.length > 1) return l
        var m = l.match(marker)
        var indent = (m ? m[1] : l.match(/^\s*/)[0])
        var rest = m ? l.slice(m[0].length) : l.slice(indent.length)
        if (off) return indent + rest
        n++
        var prefix = { bullet: "- ", number: n + ". ", task: "- [ ] ", quote: "> " }[kind]
        return indent + prefix + rest
      })
    })
  }

  // A block on lines of its own, with a blank line before it. caret and
  // selLen pick what to select inside it.
  function insertBlock(text, caret, selLen) {
    var t = editor.text, p = editor.selectionEnd
    var lineStart = t.lastIndexOf("\n", p - 1) + 1
    var lineEnd = t.indexOf("\n", p)
    if (lineEnd < 0) lineEnd = t.length
    var blank = t.slice(lineStart, lineEnd).trim() === ""
    var at = blank ? lineStart : lineEnd
    var before = blank ? (lineStart > 1 && t[lineStart - 2] !== "\n" ? "\n" : "") : "\n\n"
    // A blank line after it too, when text follows straight on.
    var after = lineEnd + 1 < t.length && t[lineEnd + 1] !== "\n" ? "\n" : ""
    replace(at, blank ? lineEnd : at, before + text + after, at + before.length + caret, at + before.length + caret + (selLen || 0))
  }

  function insertCode(lang) {
    var sel = editor.text.slice(editor.selectionStart, editor.selectionEnd)
    if (sel) editor.remove(editor.selectionStart, editor.selectionEnd)
    var open = "```" + lang + "\n"
    insertBlock(open + sel + "\n```", lang ? open.length + sel.length : 3, 0)
  }

  function insertTable() {
    insertBlock("| Column | Column |\n| ------ | ------ |\n|        |        |", 2, 6)
  }

  function insertCallout(kind, foldable) {
    var sel = editor.text.slice(editor.selectionStart, editor.selectionEnd)
    if (sel) editor.remove(editor.selectionStart, editor.selectionEnd)
    var title = foldable ? "Question" : "Title"
    var head = "> [!" + kind + "]" + (foldable ? "-" : "") + " "
    var body = (sel || (foldable ? "Answer" : "")).split("\n").map(function(l) { return "> " + l }).join("\n")
    insertBlock(head + title + "\n" + body, head.length, title.length)
  }

  // [^n] at the cursor, its definition at the end, and the cursor there.
  function insertFootnote() {
    var used = (editor.text.match(/\[\^(\d+)\]/g) || []).map(function(m) { return parseInt(m.slice(2), 10) })
    var n = used.length ? Math.max.apply(null, used) + 1 : 1
    var s = editor.selectionStart, e = editor.selectionEnd
    if (e > s) editor.remove(s, e)
    editor.insert(s, "[^" + n + "]")
    var t = editor.text
    var tail = (t[t.length - 1] !== "\n" ? "\n\n" : "\n") + "[^" + n + "]: "
    replace(t.length, t.length, tail, t.length + tail.length)
  }

  // A ^id on the cursor's line, so other notes can link to it.
  function addBlockId() {
    var r = selectedLines()
    var line = r.lines[r.lines.length - 1]
    var id = (line.match(/\^([\w-]+)\s*$/) || [])[1]
    if (!id) {
      id = Math.random().toString(16).slice(2, 8)
      replace(r.end, r.end, (line.trim() ? " " : "") + "^" + id, r.end + id.length + (line.trim() ? 2 : 1))
    }
    app.showStatus("Link to it with [[" + note.title + "#^" + id + "]]", false)
  }

  // Pick a note in the finder; the selection, if any, becomes the link text.
  function linkNote(embed) {
    var s = editor.selectionStart, e = editor.selectionEnd
    var alias = editor.text.slice(s, e).replace(/\n/g, " ")
    app.pickNote(embed ? "Embed note" : "Link to note", function(title) {
      var link = (embed ? "![[" : "[[") + title + (alias && !embed ? "|" + alias : "") + "]]"
      replace(s, e, link, s + link.length)
    })
  }

  function attachFile() {
    attachStart = editor.selectionStart
    attachEnd = editor.selectionEnd
    attachDialog.open()
  }

  property int attachStart: 0
  property int attachEnd: 0

  FileDialog {
    id: attachDialog
    title: "Insert image or file"
    fileMode: FileDialog.OpenFile
    onAccepted: {
      var source = App.localPath(String(selectedFile))
      app.attach(source, function(name) {
        var link = "![[" + name + "]]"
        view.replace(view.attachStart, view.attachEnd, link, view.attachStart + link.length)
      })
    }
    onRejected: editor.forceActiveFocus()
  }

  function openInsertMenu() { formatBar.openInsert() }

  // A click on the rendered note edits it, with the cursor near where the
  // click landed: the words before it are looked for in the source.
  function editAt(x, y) {
    var plain = reader.getText(0, reader.length)
    var p = reader.positionAt(x, y)
    var lineStart = Math.max(plain.lastIndexOf("\u2029", p - 1), plain.lastIndexOf("\n", p - 1)) + 1
    var source = pane.body, at = -1
    // How many times the line's text appears before the click, to tell
    // repeated lines apart.
    var line = plain.slice(lineStart, p)
    for (var len = 24; len >= 3 && at < 0; len = Math.floor(len / 2)) {
      var needle = line.slice(-len)
      if (needle.trim().length < 3) continue
      var nth = plain.slice(0, p).split(needle).length - 1
      var found = -1
      for (var i = 0; i < nth; i++) { found = source.indexOf(needle, found + 1); if (found < 0) break }
      if (found >= 0) at = found + needle.length
    }
    if (at < 0) {
      var ahead = plain.slice(p, p + 12).replace(/[\u2029\n].*$/, "")
      at = ahead.trim().length >= 3 ? source.indexOf(ahead) : -1
    }
    focusEditor()
    if (at >= 0) editor.cursorPosition = at
  }

  function focusTitle() {
    titleInput.forceActiveFocus()
    titleInput.selectAll()
  }

  function toggleTask(lineIndex) {
    var next = Markdown.toggleTask(pane.body, lineIndex)
    if (next === pane.body) return
    editor.text = next
    pane.edited(next)
    render()
  }

  // A click on an empty pane makes it the active one.
  MouseArea {
    anchors.fill: parent
    onClicked: view.forceActiveFocus()
  }

  // With splits, a dot in the corner marks the pane the finder and
  // shortcuts act on.
  Rectangle {
    visible: view.active && app.panes.length > 1
    x: parent.width - width - Style.space(12)
    y: Style.space(12)
    width: Style.space(7)
    height: width
    radius: width / 2
    z: 10
    color: Colors.accent
  }

  // Nothing open.
  Column {
    anchors.centerIn: parent
    spacing: Style.space(12)
    visible: !view.note
    Text {
      anchors.horizontalCenter: parent.horizontalCenter
      text: String.fromCodePoint(0xf0ebf)
      color: Util.alpha(Colors.accent, 0.8)
      font.family: Style.font.icon
      font.pixelSize: Style.font.display * 2
    }
    Text {
      anchors.horizontalCenter: parent.horizontalCenter
      text: "Press Shift twice to find or create a note"
      color: Util.alpha(Colors.foreground, 0.55)
      font.pixelSize: Style.font.body
    }
    Grid {
      anchors.horizontalCenter: parent.horizontalCenter
      columns: 2
      columnSpacing: Style.space(14)
      rowSpacing: Style.space(6)
      Repeater {
        model: [["Shift Shift", "Find"], [Style.ctrl + "+N", "New note"], [Style.ctrl + "+D", "Today's note"], [Style.ctrl + "+E", "Edit / read"], [Style.ctrl + "+Shift+E", "Export as PDF"]]
        Text {
          required property var modelData
          required property int index
          text: modelData[0] + "  " + modelData[1]
          color: Util.alpha(Colors.foreground, 0.4)
          font.pixelSize: Style.font.caption
        }
      }
    }
  }

  Flickable {
    id: page
    anchors.fill: parent
    visible: !!view.note
    contentWidth: width
    contentHeight: column.y + column.height + Style.space(80) + (pane.editing ? formatBar.height : readBar.height)
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    function ensureVisible(rect) {
      var top = column.y + body.y + rect.y
      var covered = Style.space(40) + (pane.editing ? formatBar.height : 0)
      if (top < contentY + Style.space(20)) contentY = Math.max(0, top - Style.space(20))
      else if (top + rect.height > contentY + height - covered) contentY = top + rect.height - height + covered
    }

    Column {
      id: column
      x: Math.round((page.width - view.columnWidth) / 2)
      y: Style.space(36)
      width: view.columnWidth
      spacing: Style.space(10)

      // Title, renamed in place.
      Item {
        width: parent.width
        height: Math.max(titleInput.implicitHeight, actions.height)

        TextEdit {
          id: titleInput
          width: parent.width - actions.width - Style.space(12)
          text: view.note ? view.note.title : ""
          wrapMode: TextEdit.Wrap
          color: Colors.foreground
          selectionColor: Util.alpha(Colors.accent, 0.45)
          selectedTextColor: Colors.foreground
          font.family: view.sans
          font.pixelSize: Math.round(view.bodySize * 1.618)
          font.weight: Font.Bold
          selectByMouse: true
          onActiveFocusChanged: if (!activeFocus) pane.rename(text.replace(/\n/g, " "))
          Keys.onPressed: function(event) {
            if (app.shortcut(event)) event.accepted = true
            else if (event.key === Qt.Key_Escape) { text = view.note ? view.note.title : ""; reader.forceActiveFocus(); event.accepted = true }
            else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { pane.rename(text); view.focusEditor(); event.accepted = true }
          }
        }

        Row {
          id: actions
          anchors.right: parent.right
          y: Math.round((titleInput.font.pixelSize * 1.4 - height) / 2)
          spacing: Style.space(6)
          IconButton {
            glyph: String.fromCodePoint(0xf01d9)
            tip: "Menu"
            tipHint: "Press Shift twice"
            onActivated: app.openFileActions()
          }
        }
      }

      // Tags: frontmatter tags can be removed; #tags written in the body
      // show dimmer and change with the text.
      Flow {
        id: tagRow
        width: parent.width
        spacing: Style.space(6)

        Repeater {
          model: view.note ? view.note.tags : []

          Rectangle {
            id: tagChip
            required property string modelData
            readonly property bool own: pane.ownTags.indexOf(modelData) >= 0
            width: tagLabel.implicitWidth + Style.space(18) + (removeTag.visible ? removeTag.width + Style.space(4) : 0)
            height: Style.space(24)
            radius: height / 2
            color: own ? Util.alpha(Colors.accent, 0.16) : Util.alpha(Colors.foreground, 0.05)

            Text {
              id: tagLabel
              x: Style.space(9)
              anchors.verticalCenter: parent.verticalCenter
              text: "#" + tagChip.modelData
              color: tagChip.own ? Colors.accent : Util.alpha(Colors.foreground, 0.55)
              font.pixelSize: Style.font.bodySmall
            }
            MouseArea {
              id: tagMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: app.showTag(tagChip.modelData)
            }
            Text {
              id: removeTag
              anchors.left: tagLabel.right
              anchors.leftMargin: Style.space(4)
              anchors.verticalCenter: parent.verticalCenter
              visible: tagChip.own && tagMouse.containsMouse || removeMouse.containsMouse
              text: String.fromCodePoint(0xf0156)
              color: removeMouse.containsMouse ? Colors.urgent : Util.alpha(Colors.accent, 0.8)
              font.family: Style.font.icon
              font.pixelSize: Style.font.caption
              MouseArea {
                id: removeMouse
                anchors.fill: parent
                anchors.margins: -Style.space(3)
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: pane.setTags(pane.ownTags.filter(function(t) { return t !== tagChip.modelData }))
              }
            }
          }
        }

        // Add a tag.
        Rectangle {
          id: addTag
          property bool adding: false
          width: adding ? Style.space(150) : addLabel.implicitWidth + Style.space(18)
          height: Style.space(24)
          radius: height / 2
          color: Util.alpha(Colors.foreground, adding || addMouse.containsMouse ? 0.08 : 0.04)
          border.width: tagInput.activeFocus ? 1 : 0
          border.color: Colors.accent

          Text {
            id: addLabel
            visible: !addTag.adding
            anchors.centerIn: parent
            text: String.fromCodePoint(0xf0722) + " tag"
            color: Util.alpha(Colors.foreground, 0.5)
            font.pixelSize: Style.font.bodySmall
          }
          MouseArea {
            id: addMouse
            anchors.fill: parent
            visible: !addTag.adding
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: { addTag.adding = true; tagInput.forceActiveFocus() }
          }
          TextInput {
            id: tagInput
            visible: addTag.adding
            anchors.fill: parent
            anchors.leftMargin: Style.space(10)
            anchors.rightMargin: Style.space(10)
            verticalAlignment: TextInput.AlignVCenter
            color: Colors.foreground
            selectionColor: Util.alpha(Colors.accent, 0.45)
            font.pixelSize: Style.font.bodySmall
            clip: true
            validator: RegularExpressionValidator { regularExpression: /#?[A-Za-z][\w\/-]*/ }

            readonly property var suggestions: {
              var typed = text.replace(/^#/, "").toLowerCase()
              if (!typed) return []
              return app.tagCounts.map(function(t) { return t.tag }).filter(function(t) {
                return t.indexOf(typed) === 0 && pane.ownTags.indexOf(t) < 0 && t !== typed
              }).slice(0, 5)
            }

            function commit(value) {
              var tag = value.replace(/^#/, "").toLowerCase()
              if (tag && pane.ownTags.indexOf(tag) < 0) pane.setTags(pane.ownTags.concat([tag]))
              text = ""
            }

            Keys.onPressed: function(event) {
              if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) commit(text)
              else if (event.key === Qt.Key_Tab && suggestions.length) text = suggestions[0]
              else if (event.key === Qt.Key_Escape) { text = ""; addTag.adding = false; reader.forceActiveFocus() }
              else return
              event.accepted = true
            }
            onActiveFocusChanged: if (!activeFocus) { if (text) commit(text); addTag.adding = false }
          }
        }

        Repeater {
          model: tagInput.activeFocus ? tagInput.suggestions : []
          Rectangle {
            required property string modelData
            width: suggestionLabel.implicitWidth + Style.space(18)
            height: Style.space(24)
            radius: height / 2
            color: Util.alpha(Colors.foreground, suggestionMouse.containsMouse ? 0.1 : 0.04)
            Text {
              id: suggestionLabel
              anchors.centerIn: parent
              text: "#" + parent.modelData
              color: Util.alpha(Colors.foreground, 0.6)
              font.pixelSize: Style.font.bodySmall
            }
            MouseArea {
              id: suggestionMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onPressed: tagInput.commit(parent.modelData)
            }
          }
        }
      }

      Text {
        text: {
          if (!view.note) return ""
          var words = (pane.body.match(/\S+/g) || []).length
          var edited = Qt.formatDateTime(new Date(view.note.mtime * 1000), "MMM d, yyyy  h:mm ap")
          return "Edited " + edited + "  ·  " + words + (words === 1 ? " word" : " words")
        }
        color: Util.alpha(Colors.foreground, 0.4)
        font.pixelSize: Style.font.caption
      }

      Item { width: 1; height: Style.space(6) }

      // Body: the rendered note, or its source with a tinted copy beneath
      // the (transparent) text being edited.
      Item {
        id: body
        width: parent.width
        height: pane.editing ? Math.max(editor.contentHeight, Style.space(240)) : Math.max(reader.contentHeight, Style.space(120))

        TextEdit {
          id: reader
          visible: !pane.editing
          width: parent.width
          readOnly: true
          selectByMouse: true
          textFormat: TextEdit.RichText
          wrapMode: TextEdit.Wrap
          text: view.rendered
          color: Colors.foreground
          selectionColor: Util.alpha(Colors.accent, 0.35)
          selectedTextColor: Colors.foreground
          font.family: view.sans
          font.pixelSize: view.bodySize
          onLinkActivated: function(link) { app.followLink(link, view.pane) }

          Keys.onPressed: function(event) {
            if (app.shortcut(event)) { event.accepted = true; return }
            if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier)) return
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) view.focusEditor()
            else if (event.key === Qt.Key_Down || event.key === Qt.Key_J) page.contentY = Math.min(page.contentHeight - page.height, page.contentY + Style.space(60))
            else if (event.key === Qt.Key_Up || event.key === Qt.Key_K) page.contentY = Math.max(0, page.contentY - Style.space(60))
            else if (event.key === Qt.Key_Slash) app.focusSearchFromView()
            else return
            event.accepted = true
          }

          MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.NoButton
            cursorShape: reader.hoveredLink ? Qt.PointingHandCursor : Qt.IBeamCursor
          }

          // A click (not a drag to select) that isn't on a link edits.
          TapHandler {
            onTapped: function(point) {
              if (!reader.linkAt(point.position.x, point.position.y) && !reader.selectedText) view.editAt(point.position.x, point.position.y)
            }
          }
        }

        Text {
          id: tinted
          visible: pane.editing
          width: parent.width
          textFormat: Text.RichText
          wrapMode: Text.Wrap
          text: pane.editing ? Markdown.tint(editor.text, view.theme(false)) : ""
          font: editor.font
        }

        TextEdit {
          id: editor
          visible: pane.editing
          width: parent.width
          wrapMode: TextEdit.Wrap
          textFormat: TextEdit.PlainText
          selectByMouse: true
          persistentSelection: true
          color: "transparent"
          selectedTextColor: "transparent"
          selectionColor: Util.alpha(Colors.accent, 0.3)
          font.family: Style.font.mono
          font.pixelSize: view.bodySize
          tabStopDistance: Style.space(28)

          cursorDelegate: Rectangle {
            width: 2
            color: Colors.accent
            visible: editor.activeFocus
            SequentialAnimation on opacity {
              running: editor.activeFocus
              loops: Animation.Infinite
              NumberAnimation { to: 1; duration: 0 }
              PauseAnimation { duration: 530 }
              NumberAnimation { to: 0; duration: 0 }
              PauseAnimation { duration: 530 }
            }
          }

          onTextChanged: if (activeFocus && text !== pane.body) pane.edited(text)
          onCursorRectangleChanged: if (activeFocus) page.ensureVisible(cursorRectangle)

          Keys.onPressed: function(event) {
            if (app.shortcut(event)) { event.accepted = true; return }
            if (event.key === Qt.Key_Escape) { view.toggleEditing(); event.accepted = true; return }
            var ctrl = event.modifiers & Qt.ControlModifier, shift = event.modifiers & Qt.ShiftModifier
            if (ctrl && shift && event.key === Qt.Key_I) { view.openInsertMenu(); event.accepted = true; return }
            if (ctrl && !shift && event.key === Qt.Key_B) { view.wrap("**", "**", "bold"); event.accepted = true; return }
            if (ctrl && !shift && event.key === Qt.Key_I) { view.wrap("*", "*", "italic"); event.accepted = true; return }
            // Return continues a list, Tab indents one.
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
              var start = text.lastIndexOf("\n", cursorPosition - 1) + 1
              var line = text.slice(start, cursorPosition)
              var m = line.match(/^(\s*)([-*+]|\d+[.)])(\s+)(\[[ xX]\]\s+)?(.*)$/)
              if (!m) return
              if (!m[5].trim()) { remove(start, cursorPosition); event.accepted = true; return }
              var marker = /\d/.test(m[2]) ? (parseInt(m[2], 10) + 1) + m[2].slice(-1) : m[2]
              insert(cursorPosition, "\n" + m[1] + marker + m[3] + (m[4] ? "[ ] " : ""))
              event.accepted = true
            } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
              var lineStart = text.lastIndexOf("\n", cursorPosition - 1) + 1
              if (event.key === Qt.Key_Backtab || (event.modifiers & Qt.ShiftModifier)) {
                var lead = text.slice(lineStart, lineStart + 2).match(/^ {1,2}|^\t/)
                if (lead) remove(lineStart, lineStart + lead[0].length)
              } else if (/^\s*([-*+]|\d+[.)])\s/.test(text.slice(lineStart))) insert(lineStart, "  ")
              else insert(cursorPosition, "  ")
              event.accepted = true
            }
          }
        }
      }

      // Notes that link here.
      Column {
        width: parent.width
        spacing: Style.space(6)
        topPadding: Style.space(24)
        visible: !!view.note && view.note.backlinks && view.note.backlinks.length > 0

        Rectangle { width: parent.width; height: 1; color: Util.alpha(Colors.foreground, 0.08) }
        Text {
          topPadding: Style.space(8)
          text: String.fromCodePoint(0xf0339) + "  Linked from"
          color: Util.alpha(Colors.foreground, 0.5)
          font.pixelSize: Style.font.caption
        }
        Flow {
          width: parent.width
          spacing: Style.space(6)
          Repeater {
            model: view.note && view.note.backlinks ? view.note.backlinks : []
            Rectangle {
              id: backlink
              required property string modelData
              readonly property var linked: app.byPath[modelData]
              width: backlinkLabel.implicitWidth + Style.space(20)
              height: Style.space(26)
              radius: Math.max(Style.cornerRadius, Style.space(8))
              color: Util.alpha(Colors.foreground, backlinkMouse.containsMouse ? 0.1 : 0.05)
              border.width: 1
              border.color: Util.alpha(Colors.foreground, 0.08)
              Text {
                id: backlinkLabel
                anchors.centerIn: parent
                text: backlink.linked ? backlink.linked.title : backlink.modelData
                color: Colors.foreground
                font.pixelSize: Style.font.bodySmall
              }
              MouseArea {
                id: backlinkMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: pane.open(backlink.modelData)
              }
            }
          }
        }
      }
    }
  }

  // Clicking empty space below a short note edits at its end.
  MouseArea {
    visible: !!view.note
    x: column.x + page.x
    y: column.y + body.y + body.height - page.contentY
    width: column.width
    height: Math.max(0, view.height - y)
    cursorShape: Qt.IBeamCursor
    onClicked: { view.focusEditor(); editor.cursorPosition = editor.length }
  }

  // Reading: a strip saying how to start editing, where the format bar
  // sits while editing. Status messages take its text's place.
  Rectangle {
    id: readBar
    visible: !!view.note && !pane.editing
    y: parent.height - height
    width: parent.width
    height: Style.space(40)
    color: Qt.rgba(Colors.background.r, Colors.background.g, Colors.background.b, 1)

    Rectangle { width: parent.width; height: 1; color: Util.alpha(Colors.foreground, 0.08) }

    Text {
      anchors.centerIn: parent
      visible: !app.status
      text: Style.ctrl + " + E to edit"
      color: Util.alpha(Colors.foreground, 0.35)
      font.pixelSize: Style.font.caption
    }
  }

  FormatBar {
    id: formatBar
    view: view
    app: view.app
    menu: popupMenu
    visible: !!view.note && pane.editing
    width: parent.width
    height: Style.space(48)
    y: parent.height - height
    contentX: column.x
    contentWidth: view.columnWidth
  }

  PopupMenu {
    id: popupMenu
    onDismissed: editor.forceActiveFocus()
  }
}
