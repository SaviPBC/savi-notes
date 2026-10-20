import QtQuick
import QtQuick.Window
import QtQuick.Dialogs
import Savi

// Savi Notes: one window over a vault of markdown files organised by
// tags. engine.py does the file work, search and sync; this window
// keeps the open notes, in one pane or several splits, and the finder over
// them.
Window {
  id: window
  visible: true

  property string vault: App.vault
  property string initialNote: App.initialNote

  property var notes: []
  property var byPath: ({})
  // Internal articles this person edits on the AI Core: the finder's Articles tab, shown
  // only when there are departments. Each is listed in byPath too, so panes open them.
  property var articles: []
  property var departments: []
  property var byTitle: ({})
  property var tagCounts: []
  property var activeTags: []
  property string query: ""
  property var results: []
  property bool searching: false

  // The splits: a tree of { pane } leaves and { dir, a, b } splits (see
  // PaneTree), the panes in it, and the one the finder and keys act on.
  property var layout: null
  property var panes: []
  property var activePane: null
  readonly property var activeView: activePane ? activePane.view : null
  readonly property var current: activePane ? activePane.note : null
  readonly property string currentPath: activePane ? activePane.path : ""
  readonly property bool editing: activePane ? activePane.editing : false
  readonly property bool dirty: activePane ? activePane.dirty : false
  readonly property var ownTags: activePane ? activePane.ownTags : []

  // Embedded notes, remote images, math and diagrams the open notes asked for.
  property var assets: ({})
  property bool loaded: false

  property string indexState: ""
  property string syncState: ""
  property string syncMessage: ""
  property int syncTime: 0
  property bool syncEnabled: false

  property string status: ""
  property bool statusError: false
  property bool quitting: false

  title: (current ? current.title + (dirty ? " •" : "") + " · " : "") + (App.dev ? "Notes (dev)" : "Notes")
  color: Qt.rgba(Colors.background.r, Colors.background.g, Colors.background.b, 1)
  width: 1180
  height: 760
  minimumWidth: 720
  minimumHeight: 440

  // The finder's notes: search results, or every note under the chosen
  // tags, newest first.
  readonly property var visibleNotes: {
    if (query.trim()) return results
    if (activeTags.length === 0) return notes
    return notes.filter(function(n) {
      for (var i = 0; i < activeTags.length; i++) if (n.tags.indexOf(activeTags[i]) < 0) return false
      return true
    })
  }

  Engine {
    id: engine
    onEvent: function(message) { window.engineEvent(message) }
    onExited: function(code) {
      if (window.quitting) { Qt.quit(); return }
      // Stopped on purpose: signed out, or the sign-in was lost.
      if (App.needsSetup) return
      window.showStatus("The notes engine stopped and was restarted", true)
      reloadTimer.restart()
    }
  }

  function call(op, args, done) { engine.call(op, args, done) }

  onClosing: function(close) {
    if (window.quitting) return
    close.accepted = false
    window.quit()
  }

  // Save what is pending, then let the engine finish its last sync.
  function quit() {
    if (window.quitting) return
    window.quitting = true
    window.visible = false
    saveAll(function() { engine.close(); quitTimer.start() })
  }

  Timer { id: quitTimer; interval: 4000; onTriggered: Qt.quit() }
  Timer { id: reloadTimer; interval: 1500; onTriggered: window.reload() }

  Component.onCompleted: {
    var first = paneComponent.createObject(window)
    window.panes = [first]
    window.activePane = first
    window.layout = { pane: first }
    if (!App.needsSetup) start()
  }

  // Once there is a vault: list it and open the note asked for, or the finder.
  function start() {
    loadArticles()
    reload(function() {
      window.loaded = true
      if (window.initialNote) window.openNamed(window.initialNote)
      else finder.open()
    })
  }

  // A second launch hands its note to this window; the host also reports
  // a newer release.
  Connections {
    target: App
    function onOpenRequested(name) {
      window.raise()
      window.requestActivate()
      if (name) window.openNamed(name)
      else finder.open()
    }
    function onNeedsSetupChanged() {
      if (!App.needsSetup) { window.start(); return }
      // Signed out: nothing of the last person's notes stays on screen.
      finder.close()
      window.panes.forEach(function(p) { p.clear() })
      window.notes = []
      window.byPath = {}
      window.byTitle = {}
      window.tagCounts = []
      window.activeTags = []
      window.query = ""
      window.loaded = false
      window.syncState = ""
      window.syncTime = 0
      window.articles = []
      window.departments = []
    }
    function onUpdateChecked(message) { window.showStatus(message, false) }
    function onUpdateAvailable(version, required) {
      window.updateVersion = version
      updateDialog.selectedIndex = 1
      updateDialog.opened = true
      content.forceActiveFocus()
    }
  }

  property string updateVersion: ""

  // ---------------------------------------------------------------- engine

  function engineEvent(message) {
    if (message.event === "index") {
      window.indexState = message.done < message.total ? "Indexing " + message.done + " of " + message.total : ""
    } else if (message.event === "model") {
      window.indexState = "Downloading search model " + Math.round(100 * message.done / message.total) + "%"
    } else if (message.event === "search") {
      window.indexState = message.state === "error" ? "Word search only" : ""
      if (message.state === "error") console.warn("notes-engine:", message.message)
      if (window.query.trim()) runSearch()
    } else if (message.event === "sync") {
      window.syncState = message.state
      window.syncMessage = message.message || ""
      if (message.time) window.syncTime = message.time
      if (message.state === "conflict" || message.state === "error") showStatus(message.message, true)
    } else if (message.event === "account") {
      App.accountLost(message.state)
    } else if (message.event === "assets") {
      mergeAssets(message.assets)
    } else if (message.event === "changed") {
      forgetNoteAssets()
      reload(function() {
        window.panes.forEach(function(p) { if (p.path && !p.dirty && !p.editing) p.open(p.path) })
      })
    }
  }

  function articleEntry(a) {
    return { path: a.path, title: a.title, tags: [], ownTags: [], backlinks: [], links: [],
             snippet: a.department + (a.status === "ready" ? "" : " · " + a.status),
             mtime: a.mtime, article: true, department: a.department, status: a.status }
  }

  function loadArticles() {
    engine.call("articles", {}, function(reply) {
      if (!reply.articles) return
      var paths = Object.assign({}, window.byPath)
      window.articles.forEach(function(a) { delete paths[a.path] })
      reply.articles.forEach(function(a) { paths[a.path] = window.articleEntry(a) })
      window.byPath = paths
      window.articles = reply.articles
      window.departments = reply.departments
    })
  }

  // A new article is a draft until its editor is left, like any article edit.
  function newArticle(department, title) {
    var base = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 100) || "article"
    var key = base, n = 2
    while (window.byPath["articles:" + key]) key = base + "-" + n++
    var pane = window.activePane
    pane.save(function() {
      engine.call("newArticle", { key: key, department: department, title: title }, function(reply) {
        var paths = Object.assign({}, window.byPath)
        paths[reply.path] = window.articleEntry({ path: reply.path, title: title, department: department, status: "draft", mtime: Date.now() / 1000 })
        window.byPath = paths
        pane.editing = true
        pane.open(reply.path, function() { if (pane.view) pane.view.focusEditor() })
      })
    })
  }

  function reload(done) {
    engine.call("notes", { rescan: true }, function(reply) {
      if (!reply.notes) return
      var paths = {}, titles = {}, counts = {}
      reply.notes.forEach(function(n) {
        paths[n.path] = n
        titles[n.title.toLowerCase()] = n.path
        n.tags.forEach(function(t) { counts[t] = (counts[t] || 0) + 1 })
      })
      window.articles.forEach(function(a) { paths[a.path] = window.articleEntry(a) })
      window.notes = reply.notes
      window.byPath = paths
      window.byTitle = titles
      window.syncEnabled = reply.sync
      // Most used first.
      window.tagCounts = Object.keys(counts).sort(function(a, b) { return counts[b] - counts[a] || (a < b ? -1 : 1) })
        .map(function(t) { return { tag: t, count: counts[t] } })
      window.activeTags = window.activeTags.filter(function(t) { return counts[t] })
      if (window.query.trim()) runSearch()
      if (done) done()
    })
  }

  function updateListing(note) {
    if (!note) return
    var paths = Object.assign({}, window.byPath)
    var old = paths[note.path]
    note.backlinks = old ? old.backlinks : []
    paths[note.path] = note
    window.byPath = paths
    window.notes = [note].concat(window.notes.filter(function(n) { return n.path !== note.path }))
  }

  Timer {
    id: searchTimer
    interval: 140
    onTriggered: window.runSearch()
  }

  onQueryChanged: {
    if (query.trim()) { window.searching = true; searchTimer.restart() }
    else { window.results = []; window.searching = false }
    finder.resetSelection()
  }
  onActiveTagsChanged: { if (query.trim()) searchTimer.restart(); finder.resetSelection() }

  function runSearch() {
    var asked = window.query
    engine.call("search", { query: asked, tags: window.activeTags }, function(reply) {
      if (asked !== window.query) return
      window.results = reply.results || []
      window.searching = false
      finder.resetSelection()
      finder.searchSettled()
    })
  }

  // ---------------------------------------------------------------- panes

  Component {
    id: paneComponent
    NotePane { app: window }
  }

  // Replace the active pane's place in the layout with a split holding it
  // and a new pane, which becomes active.
  function split(dir) {
    var fresh = paneComponent.createObject(window)
    var target = window.activePane
    var swap = function(node) {
      if (node.pane) return node.pane === target ? { dir: dir, a: node, b: { pane: fresh } } : node
      return { dir: node.dir, a: swap(node.a), b: swap(node.b) }
    }
    window.panes = window.panes.concat([fresh])
    window.layout = swap(window.layout)
    window.activePane = fresh
    return fresh
  }

  // Open a note picked in the finder (or a new one by that name) in a split.
  function openSplit(dir) {
    finder.pick(dir === "right" ? "Open in split right" : "Open in split down", function(title) {
      var path = window.byTitle[title.toLowerCase()]
      var pane = split(dir)
      if (path) pane.open(path)
      else createNote(title, [])
    }, "New note")
  }

  // Close a split; its sibling takes the space.
  function closePane(target) {
    if (window.panes.length < 2) return
    target.save(function() {
      var prune = function(node) {
        if (node.pane) return node
        if (node.a.pane === target) return node.b
        if (node.b.pane === target) return node.a
        return { dir: node.dir, a: prune(node.a), b: prune(node.b) }
      }
      window.layout = prune(window.layout)
      window.panes = window.panes.filter(function(p) { return p !== target })
      if (window.activePane === target) window.activePane = window.panes[0]
      target.destroy()
      Qt.callLater(window.restoreFocus)
    })
  }

  function saveAll(done) {
    var dirty = window.panes.filter(function(p) { return p.dirty })
    var next = function() {
      if (!dirty.length) { if (done) done(); return }
      dirty.shift().save(next)
    }
    next()
  }

  // A pane saved: list it, and refresh other panes showing the same note.
  function noteSaved(note, from) {
    updateListing(note)
    if (!note) return
    window.panes.forEach(function(p) { if (p !== from && p.path === note.path && !p.dirty && !p.editing) p.open(p.path) })
  }

  function noteMoved(from, to) {
    window.panes.forEach(function(p) { if (p.path === from) p.path = to })
  }

  // Panes showing a deleted note close, or empty if it's the only one.
  function noteDeleted(path) {
    window.panes.filter(function(p) { return p.path === path }).forEach(function(p) {
      if (window.panes.length > 1) closePane(p)
      else { p.clear(); finder.open() }
    })
  }

  // ---------------------------------------------------------------- notes

  function openNote(path, done) {
    if (window.activePane) window.activePane.open(path, done)
  }

  function requestAssets(items) {
    engine.call("assets", { items: items, ink: String(Colors.foreground), theme: Colors.diagram }, function(reply) {
      if (reply.assets) mergeAssets(reply.assets)
    })
  }

  function mergeAssets(found) {
    var next = {}
    for (var k in window.assets) next[k] = window.assets[k]
    for (var key in found) next[key] = found[key]
    window.assets = next
    window.panes.forEach(function(p) { if (p.view && !p.editing) p.view.render() })
  }

  // Embedded notes change when their files do, so they're asked for afresh.
  function forgetNoteAssets() {
    var next = {}
    for (var k in window.assets) if (k.indexOf("note:") !== 0) next[k] = window.assets[k]
    window.assets = next
    window.panes.forEach(function(p) { if (p.view) p.view.forgetRequests() })
  }

  function openNamed(name, pane) {
    var path = window.byPath[name] ? name : window.byTitle[name.replace(/\.md$/, "").toLowerCase()]
    if (path) (pane || window.activePane).open(path)
    else createNote(name.replace(/\.md$/, ""), [])
  }

  function openNamedThen(name, pane, done) {
    var path = window.byTitle[name.replace(/\.md$/, "").toLowerCase()]
    if (path) pane.open(path, done)
    else openNamed(name, pane)
  }

  // Create a note and open it in the active pane.
  function createNote(title, tags, body, edit) {
    var pane = window.activePane
    pane.save(function() {
      engine.call("create", { title: title || "Untitled", tags: tags || [], body: body || "" }, function(reply) {
        if (reply.error) { showStatus(reply.error, true); return }
        reload(function() {
          pane.editing = edit !== false
          pane.open(reply.path, function() {
            if (!pane.view) return
            if (!title) pane.view.focusTitle()
            else if (pane.editing) pane.view.focusEditor()
          })
        })
      })
    })
  }

  function newNote() {
    var title = window.query.trim()
    var existing = title ? window.byTitle[title.toLowerCase()] : ""
    var tags = finder.opened ? window.activeTags : []
    finder.close()
    if (existing) { openNote(existing); return }
    createNote(title, tags)
  }

  function todaysNote() {
    var now = new Date()
    var pad = function(n) { return (n < 10 ? "0" : "") + n }
    var title = pad(now.getMonth() + 1) + "-" + pad(now.getDate()) + "-" + String(now.getFullYear()).slice(2)
    var existing = window.byTitle[title.toLowerCase()]
    var pane = window.activePane
    if (existing) { pane.editing = true; pane.open(existing, function() { if (pane.view) pane.view.focusEditor() }) }
    else createNote(title, ["daily"])
  }

  function setTags(tags) {
    if (window.activePane) window.activePane.setTags(tags)
  }

  function deleteNote() {
    if (window.activePane) window.activePane.remove()
  }

  function focusSearchFromView() {
    finder.open()
  }

  // Choose a note in the finder; done gets its title. createLabel names
  // the row offered for a title no note has.
  function pickNote(prompt, done, createLabel) {
    finder.pick(prompt, done, createLabel)
  }

  // Copy a file into the vault for embedding; done gets the name to use.
  function attach(source, done) {
    engine.call("attach", { source: source }, function(reply) {
      if (reply.error) { showStatus("Could not add " + source.split("/").pop() + ": " + reply.error, true); return }
      done(reply.name)
    })
  }

  function openFileActions() { finder.open("file") }
  function renameFromFinder() { if (activeView) activeView.focusTitle() }
  function addTagFromFinder() { if (activeView) activeView.startAddTag() }

  // The dialog reads keys from the window, so focus goes there.
  function confirmDelete() {
    if (!window.current) return
    deleteDialog.selectedIndex = 0
    deleteDialog.opened = true
    content.forceActiveFocus()
  }

  function confirmSignOut() {
    signOutDialog.selectedIndex = 0
    signOutDialog.opened = true
    content.forceActiveFocus()
  }

  function showTag(tag) {
    finder.open("notes", [tag])
  }

  // Back to the active note, or the empty window, when the finder closes.
  function restoreFocus() {
    if (window.activeView) window.activeView.restoreFocus()
    else content.forceActiveFocus()
  }

  // Shift twice, with nothing between, opens the finder: on This file
  // while a note is open. Every bare Shift is taken here, so one press
  // isn't counted again as it bubbles up.
  property real lastShift: 0
  function shiftTap(event) {
    if (event.key !== Qt.Key_Shift || (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))) {
      window.lastShift = 0
      return false
    }
    if (event.isAutoRepeat) return true
    var now = Date.now()
    if (now - window.lastShift < 400) { window.lastShift = 0; finder.toggle() }
    else window.lastShift = now
    return true
  }

  // Links act on the pane they were clicked in.
  function followLink(link, pane) {
    pane = pane || window.activePane
    var view = pane.view
    if (link.indexOf("note:") === 0) {
      var target = link.slice(5).split("#")
      var name = decodeURIComponent(target[0]), anchor = target[1] ? decodeURIComponent(target[1]) : ""
      if (byTitle[name.toLowerCase()] === pane.path) view.scrollToHeading(anchor)
      else if (anchor) openNamedThen(name, pane, function() { pane.view.scrollToHeading(anchor) })
      else openNamed(name, pane)
    }
    else if (link.indexOf("heading:") === 0) view.scrollToHeading(decodeURIComponent(link.slice(8)))
    else if (link.indexOf("fold:") === 0) view.toggleFold(parseInt(link.slice(5), 10))
    else if (link.indexOf("footnote:") === 0 || link.indexOf("footnote-ref:") === 0) view.scrollToFootnote(link)
    else if (link.indexOf("obsidian://open?") === 0) {
      var file = (link.match(/[?&]file=([^&]*)/) || [])[1]
      if (file) openNamed(decodeURIComponent(file).split("/").pop(), pane)
    }
    else if (link.indexOf("tag:") === 0) showTag(link.slice(4))
    else if (link.indexOf("task:") === 0) view.toggleTask(parseInt(link.slice(5), 10))
    else if (link.indexOf("file:") === 0) Qt.openUrlExternally(Util.fileUrl(decodeURIComponent(link.slice(5))))
    else Qt.openUrlExternally(link)
  }

  function toggleTag(tag) {
    var tags = window.activeTags.slice()
    var at = tags.indexOf(tag)
    if (at >= 0) tags.splice(at, 1)
    else tags.push(tag)
    window.activeTags = tags
  }

  // Signing out deletes this computer's copy, so only once the AI Core has every change.
  function signOut() {
    saveAll(function() {
      showStatus("Syncing before signing out…", false)
      engine.call("unsent", {}, function(reply) {
        if (reply.unsent === 0) App.signOut()
        else showStatus(reply.unsent + (reply.unsent === 1 ? " change hasn't" : " changes haven't") + " reached the AI Core yet. Try again once you're online.", true)
      })
    })
  }

  function syncNow() {
    if (!window.syncEnabled) return
    saveAll(function() { engine.call("sync", {}) })
  }

  // ---------------------------------------------------------------- pdf

  property var exporting: null

  function exportPdf() {
    if (!window.current) return
    window.exporting = window.activePane
    pdfDialog.currentFolder = Util.fileUrl(App.documents)
    pdfDialog.selectedFile = Util.fileUrl(App.documents + "/" + window.current.title + ".pdf")
    pdfDialog.open()
    App.fillFileName(window.current.title + ".pdf")
  }

  function exportMarkdown() {
    if (!window.current) return
    window.exporting = window.activePane
    mdDialog.currentFolder = Util.fileUrl(App.documents)
    mdDialog.selectedFile = Util.fileUrl(App.documents + "/" + window.current.title + ".md")
    mdDialog.open()
    App.fillFileName(window.current.title + ".md")
  }

  function importNotes() {
    importDialog.currentFolder = Util.fileUrl(App.home)
    importDialog.open()
  }

  function exportAll() {
    allDialog.currentFolder = Util.fileUrl(App.documents)
    allDialog.open()
  }

  FileDialog {
    id: mdDialog
    title: "Export as Markdown"
    fileMode: FileDialog.SaveFile
    nameFilters: ["Markdown (*.md)"]
    onAccepted: {
      var pane = window.exporting
      if (!pane || !pane.path) return
      var out = App.localPath(String(selectedFile))
      if (!/\.md$/i.test(out)) out += ".md"
      pane.save(function() {
        engine.call("export", { path: pane.path, out: out }, function(reply) {
          if (reply.error) { window.showStatus("Export failed: " + reply.error, true); return }
          window.showStatus("Exported " + out.split(/[\\/]/).pop(), false)
        })
      })
    }
  }

  FolderDialog {
    id: importDialog
    title: "Import notes from…"
    onAccepted: {
      var folder = App.localPath(String(selectedFolder))
      showStatus("Importing…", false)
      saveAll(function() {
        engine.call("import", { folder: folder }, function(reply) {
          if (reply.error) { window.showStatus("Import failed: " + reply.error, true); return }
          window.showStatus("Imported " + reply.notes + (reply.notes === 1 ? " note" : " notes")
            + (reply.renamed ? ", " + reply.renamed + " renamed because the title was taken" : ""), false)
          window.reload()
        })
      })
    }
  }

  FolderDialog {
    id: allDialog
    title: "Export all notes into…"
    onAccepted: {
      var folder = App.localPath(String(selectedFolder))
      saveAll(function() {
        engine.call("exportAll", { folder: folder }, function(reply) {
          if (reply.error) { window.showStatus("Export failed: " + reply.error, true); return }
          window.showStatus("Exported " + reply.notes + (reply.notes === 1 ? " note" : " notes") + " to " + reply.folder.replace(App.home, "~"), false)
          Qt.openUrlExternally(Util.fileUrl(reply.folder))
        })
      })
    }
  }

  FileDialog {
    id: pdfDialog
    title: "Export as PDF"
    fileMode: FileDialog.SaveFile
    nameFilters: ["PDF (*.pdf)"]
    onAccepted: {
      var pane = window.exporting
      if (!pane || !pane.note || !pane.view) return
      var out = App.localPath(String(selectedFile))
      if (!/\.pdf$/i.test(out)) out += ".pdf"
      var error = App.exportPdf(pane.note.title, pane.view.printHtml(), out)
      if (error) { window.showStatus("Export failed: " + error, true); return }
      window.showStatus("Exported " + out.split(/[\\/]/).pop(), false)
      Qt.openUrlExternally(Util.fileUrl(out))
    }
  }

  // ---------------------------------------------------------------- status

  function showStatus(text, error) {
    window.status = text
    window.statusError = error
    statusTimer.restart()
  }

  Timer {
    id: statusTimer
    interval: 3500
    onTriggered: window.status = ""
  }

  // App shortcuts. Text fields call this first so their own bindings
  // (Ctrl+K deletes to the end of the line in a TextEdit) don't win.
  function shortcut(event) {
    if (App.needsSetup) return false
    if (window.shiftTap(event)) return true
    var ctrl = event.modifiers & Qt.ControlModifier
    var shift = event.modifiers & Qt.ShiftModifier
    if (!ctrl) return false
    if (event.key === Qt.Key_K || event.key === Qt.Key_L || event.key === Qt.Key_P) finder.open()
    else if (event.key === Qt.Key_N) window.newNote()
    else if (event.key === Qt.Key_D) window.todaysNote()
    else if (shift && event.key === Qt.Key_E) window.exportPdf()
    else if (event.key === Qt.Key_E) { if (activeView) activeView.toggleEditing() }
    else if (event.key === Qt.Key_S) window.saveAll()
    else if (event.key === Qt.Key_W || event.key === Qt.Key_Q) window.quit()
    else return false
    return true
  }

  // ---------------------------------------------------------------- UI

  Item {
    id: content
    anchors.fill: parent
    focus: true

    Keys.onPressed: function(event) {
      if (deleteDialog.opened) { event.accepted = deleteDialog.handleKey(event); return }
      if (signOutDialog.opened) { event.accepted = signOutDialog.handleKey(event); return }
      if (updateDialog.opened) { event.accepted = updateDialog.handleKey(event); return }
      event.accepted = window.shortcut(event)
    }

    PaneTree {
      anchors.fill: parent
      node: window.layout
      app: window
    }

    Finder {
      id: finder
      app: window
      anchors.fill: parent
      z: 1000
    }

    Text {
      anchors.horizontalCenter: parent.horizontalCenter
      anchors.bottom: parent.bottom
      // In the reading strip, or above the format bar while editing.
      anchors.bottomMargin: !window.current ? Style.space(14) : window.editing ? Style.space(62) : Style.space(12)
      text: window.status
      color: window.statusError ? Colors.urgent : Colors.accent
      font.pixelSize: Style.font.caption
      opacity: window.status ? 1 : 0
      Behavior on opacity { NumberAnimation { duration: 180 } }
    }

    ConfirmDialog {
      id: deleteDialog
      anchors.fill: parent
      z: 2000
      message: window.current && window.current.article
        ? "Delete " + window.current.title + " from " + window.current.department + "'s internal articles? Claude stops finding it."
        : "Move " + (window.current ? window.current.title : "this note") + " to the trash?"
      cancelText: "Keep"
      confirmText: "Delete"
      onCanceled: { opened = false; window.restoreFocus() }
      onConfirmed: { opened = false; window.deleteNote() }
    }

    ConfirmDialog {
      id: signOutDialog
      anchors.fill: parent
      z: 2000
      message: "Sign out? This computer's copy of your notes is removed, and signing in again needs your recovery key. If you haven't saved it, copy it from Settings first."
      cancelText: "Stay signed in"
      confirmText: "Sign out"
      onCanceled: { opened = false; window.restoreFocus() }
      onConfirmed: { opened = false; window.signOut() }
    }

    Onboarding {
      anchors.fill: parent
      z: 3000
    }

    ConfirmDialog {
      id: updateDialog
      anchors.fill: parent
      z: 2000
      message: "Savi Notes " + window.updateVersion + " is available. Update and reopen?"
      cancelText: "Later"
      confirmText: "Update"
      destructive: false
      onCanceled: { opened = false; window.restoreFocus() }
      onConfirmed: { opened = false; App.runUpdate(window.updateVersion) }
    }
  }
}
