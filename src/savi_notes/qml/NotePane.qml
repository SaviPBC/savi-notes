import QtQuick

// One open note: what a split shows. It holds the note's text and edits
// and saves them; the NoteView showing it sets `view`.
QtObject {
  id: pane

  required property var app
  property var view: null

  property string path: ""
  readonly property var note: path ? (app.byPath[path] || null) : null
  property string body: ""
  property var ownTags: []
  // Embedded notes this one shows, from the engine's read.
  property var embeds: ({})
  property bool editing: false
  property bool dirty: false
  readonly property bool isArticle: path.indexOf("articles:") === 0

  // An article publishes when its editor is left, not as it is typed: each publish
  // re-indexes it for everyone's Claude.
  onEditingChanged: if (!editing && isArticle) save(function() {
    app.call("publish", { path: pane.path }, function(reply) {
      if (reply.error) { app.showStatus(reply.error, true); return }
      if (reply.published) {
        app.showStatus("Published to " + reply.department + "; Claude can search it in a few minutes", false)
        app.loadArticles()
      }
    })
  })

  property Timer saveTimer: Timer {
    interval: 700
    onTriggered: pane.save()
  }

  function open(target, done) {
    if (!target) return
    var go = function() {
      app.call("read", { path: target }, function(reply) {
        if (reply.error) { app.showStatus("Could not open " + target, true); return }
        var changed = target !== pane.path
        pane.path = target
        pane.body = reply.body
        pane.ownTags = reply.tags
        pane.embeds = reply.embeds || {}
        pane.dirty = false
        app.forgetNoteAssets()
        if (pane.view) {
          if (changed) pane.view.folds = {}
          pane.view.loadBody()
        }
        if (done) done()
      })
    }
    if (pane.dirty && target !== pane.path) save(go)
    else go()
  }

  function edited(text) {
    pane.body = text
    pane.dirty = true
    saveTimer.restart()
  }

  function save(done) {
    saveTimer.stop()
    if (!pane.path || !pane.dirty) { if (done) done(); return }
    var target = pane.path, text = pane.body
    app.call("save", { path: target, body: text }, function(reply) {
      if (reply.error) { app.showStatus("Could not save: " + reply.error, true); return }
      if (target === pane.path && text === pane.body) pane.dirty = false
      app.noteSaved(reply.note, pane)
      if (done) done()
    })
  }

  function setTags(tags) {
    if (!pane.path) return
    pane.ownTags = tags
    var target = pane.path
    save(function() {
      app.call("save", { path: target, tags: tags }, function(reply) {
        if (reply.error) { app.showStatus(reply.error, true); return }
        app.reload()
      })
    })
  }

  function rename(title) {
    title = title.trim()
    if (!pane.note || !title || title === pane.note.title) return
    save(function() {
      var from = pane.path
      app.call("rename", { path: from, title: title }, function(reply) {
        if (reply.error) { app.showStatus(reply.error, true); return }
        app.noteMoved(from, reply.path)
        if (pane.isArticle) app.loadArticles()
        app.reload()
        if (reply.updated > 0) app.showStatus("Updated links in " + reply.updated + " note" + (reply.updated > 1 ? "s" : ""), false)
      })
    })
  }

  function remove() {
    var target = pane.path
    var name = pane.note ? pane.note.title : ""
    saveTimer.stop()
    pane.dirty = false
    app.call("delete", { path: target }, function(reply) {
      if (reply.error) { app.showStatus(reply.error, true); return }
      app.showStatus(pane.isArticle ? "Deleted " + name + " from internal articles" : "Moved " + name + " to the trash", false)
      app.noteDeleted(target)
      if (target.indexOf("articles:") === 0) app.loadArticles()
      app.reload()
    })
  }

  function clear() {
    saveTimer.stop()
    pane.path = ""
    pane.body = ""
    pane.dirty = false
    pane.editing = false
  }
}
