import QtQuick
import Savi
import "Markdown.js" as Markdown

// The bar under the editor: text formatting on the left, and an Insert menu
// with everything else a note can hold (see the notes tagged #obsidian).
Rectangle {
  id: bar

  required property var view
  required property var app
  required property var menu
  property int contentX: 0
  property int contentWidth: width

  color: Qt.rgba(Colors.background.r, Colors.background.g, Colors.background.b, 1)

  function openHeadings() {
    var items = [{ label: "Text", glyph: 0xf027d, run: function() { view.setHeading(0) } }]
    for (var i = 1; i <= 6; i++) (function(level) {
      items.push({ label: "Heading " + level, glyph: 0xf026b + level - 1, hint: "#".repeat(level), run: function() { view.setHeading(level) } })
    })(i)
    var at = headingButton.mapToItem(menu, 0, -Style.space(4))
    menu.menuWidth = Style.space(200)
    menu.openAt(at.x, at.y, items, true)
  }

  function openInsert() {
    var callouts = Object.keys(Markdown.CALLOUTS).map(function(kind) {
      return { label: kind[0].toUpperCase() + kind.slice(1), glyph: Markdown.CALLOUTS[kind][1], run: function() { view.insertCallout(kind, false) } }
    })
    callouts.push({ label: "Foldable", glyph: 0xf084d, hint: "[!faq]-", run: function() { view.insertCallout("faq", true) } })
    var languages = [["Plain", ""], ["Bash", "bash"], ["CSS", "css"], ["Go", "go"], ["HTML", "html"], ["JavaScript", "js"], ["JSON", "json"],
                     ["Markdown", "md"], ["PHP", "php"], ["Python", "python"], ["Rust", "rust"], ["SQL", "sql"], ["TypeScript", "ts"], ["YAML", "yaml"]]
      .map(function(l) { return { label: l[0], hint: l[1], run: function() { view.insertCode(l[1]) } } })
    var items = [
      { label: "Embed note", glyph: 0xf0b78, hint: "![[ ]]", run: function() { view.linkNote(true) } },
      { label: "Image or file…", glyph: 0xf03e2, hint: "![[ ]]", run: function() { view.attachFile() } },
      { label: "Image from the web", glyph: 0xf0976, hint: "![](url)", run: function() { view.insertInline("![", "](https://)", "", 2) } },
      { label: "Table", glyph: 0xf04eb, run: function() { view.insertTable() } },
      { label: "Code block", glyph: 0xf0169, items: languages },
      { label: "Callout", glyph: 0xf0ce4, items: callouts },
      { label: "Diagram", glyph: 0xf0e93, items: [
        { label: "Flowchart", run: function() { view.insertBlock("```mermaid\ngraph TD\n  A[Start] --> B[Finish]\n```", 22, 5) } },
        { label: "Sequence", run: function() { view.insertBlock("```mermaid\nsequenceDiagram\n  Alice->>Bob: Hello\n```", 29, 5) } }
      ] },
      { label: "Math block", glyph: 0xf0871, hint: "$$", run: function() { view.insertBlock("$$\n\n$$", 3, 0) } },
      { label: "Inline math", glyph: 0xf04a0, hint: "$", run: function() { view.wrap("$", "$", "") } },
      { label: "Footnote", glyph: 0xf0283, hint: "[^1]", run: function() { view.insertFootnote() } },
      { label: "Inline footnote", glyph: 0xf0283, hint: "^[ ]", run: function() { view.wrap("^[", "]", "") } },
      { label: "Comment block", glyph: 0xf0182, hint: "%%", run: function() { view.insertBlock("%%\n\n%%", 3, 0) } },
      { label: "Divider", glyph: 0xf0374, hint: "---", run: function() { view.insertBlock("---", 3, 0) } },
      { label: "Block ID", glyph: 0xf0efe, hint: "^id", run: function() { view.addBlockId() } }
    ]
    var at = insertButton.mapToItem(menu, insertButton.width - Style.space(260), -Style.space(4))
    menu.menuWidth = Style.space(260)
    menu.openAt(at.x, at.y, items, true)
  }

  Rectangle { width: parent.width; height: 1; color: Util.alpha(Colors.foreground, 0.08) }

  // In a narrow split the formatting buttons scroll sideways; Insert and
  // Save stay put.
  Flickable {
    x: bar.contentX - Style.space(8)
    width: insertButton.x - x - Style.space(8)
    height: parent.height
    contentWidth: buttons.width
    contentHeight: height
    clip: true
    flickableDirection: Flickable.HorizontalFlick
    boundsBehavior: Flickable.StopAtBounds

    Row {
      id: buttons
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(2)


      ToolbarButton {
        id: headingButton
        width: Style.space(64)
        label: view.headingLevel ? "H" + view.headingLevel : "Text"
        dropdown: true
        tip: "Heading"
        onActivated: bar.openHeadings()
      }

      Rectangle { width: 1; height: Style.space(18); anchors.verticalCenter: parent.verticalCenter; color: Util.alpha(Colors.foreground, 0.1) }

      ToolbarButton { glyph: 0xf0264; tip: "Bold  " + Style.ctrl + "+B"; onActivated: view.wrap("**", "**", "bold") }
      ToolbarButton { glyph: 0xf0277; tip: "Italic  " + Style.ctrl + "+I"; onActivated: view.wrap("*", "*", "italic") }
      ToolbarButton { glyph: 0xf0281; tip: "Strikethrough"; onActivated: view.wrap("~~", "~~", "") }
      ToolbarButton { glyph: 0xf0652; tip: "Highlight"; onActivated: view.wrap("==", "==", "") }
      ToolbarButton { glyph: 0xf0174; tip: "Inline code"; onActivated: view.wrap("`", "`", "") }
      ToolbarButton { glyph: 0xf0182; tip: "Comment (hidden when reading)"; onActivated: view.wrap("%%", "%%", "") }

      Rectangle { width: 1; height: Style.space(18); anchors.verticalCenter: parent.verticalCenter; color: Util.alpha(Colors.foreground, 0.1) }

      ToolbarButton { glyph: 0xf1178; tip: "Link to note"; onActivated: view.linkNote(false) }
      ToolbarButton { glyph: 0xf0339; tip: "Web link"; onActivated: view.webLink() }

      Rectangle { width: 1; height: Style.space(18); anchors.verticalCenter: parent.verticalCenter; color: Util.alpha(Colors.foreground, 0.1) }

      ToolbarButton { glyph: 0xf0279; tip: "Bulleted list"; onActivated: view.setList("bullet") }
      ToolbarButton { glyph: 0xf027b; tip: "Numbered list"; onActivated: view.setList("number") }
      ToolbarButton { glyph: 0xf0756; tip: "Task list"; onActivated: view.setList("task") }
      ToolbarButton { glyph: 0xf0757; tip: "Quote"; onActivated: view.setList("quote") }
    }
  }

  ToolbarButton {
    id: insertButton
    x: saveButton.x - width - Style.space(4)
    anchors.verticalCenter: parent.verticalCenter
    glyph: 0xf0704
    label: "Insert"
    dropdown: true
    tip: "Insert  " + Style.ctrl + "+Shift+I"
    onActivated: bar.openInsert()
  }

  // Edits save as you type; this saves now and goes back to reading.
  ToolbarButton {
    id: saveButton
    x: bar.contentX + bar.contentWidth - width + Style.space(8)
    anchors.verticalCenter: parent.verticalCenter
    glyph: view.pane.dirty ? 0xf0193 : 0xf0818
    tip: (view.pane.dirty ? "Save and read" : "Saved; back to reading") + "  Esc"
    onActivated: view.saveAndRead()
  }
}
