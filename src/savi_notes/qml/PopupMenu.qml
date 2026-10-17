import QtQuick
import Savi

// A dropdown of actions under a button. Items are { label, glyph, hint, run }
// or { label, glyph, items } for a submenu, which opens in place (Right or
// Enter goes in, Left goes back). Typing filters the list.
Item {
  id: menu

  property var items: []
  property var trail: []
  property string filter: ""
  property int selected: 0
  property int menuWidth: Style.space(250)
  // Where the card hangs from, or, opened above a button, where it rests.
  property real topEdge: 0
  property real bottomEdge: -1
  signal dismissed()

  readonly property var level: trail.length ? trail[trail.length - 1].items : items
  readonly property var shown: {
    var typed = filter.toLowerCase()
    if (!typed) return level
    // Filtering looks through submenus too, so "warn" finds the callout.
    var found = []
    var walk = function(list, prefix) {
      list.forEach(function(item) {
        if (item.items) walk(item.items, item.label + " · ")
        else if ((prefix + item.label).toLowerCase().indexOf(typed) >= 0) found.push(Object.assign({}, item, { label: prefix + item.label }))
      })
    }
    walk(level, "")
    return found
  }

  anchors.fill: parent
  visible: false
  z: 3000

  function openAt(x, y, list, above) {
    menu.items = list
    menu.trail = []
    menu.filter = ""
    menu.selected = 0
    card.x = Math.max(Style.space(8), Math.min(x, menu.width - card.width - Style.space(8)))
    menu.topEdge = above ? 0 : y
    menu.bottomEdge = above ? y : -1
    menu.visible = true
    keys.forceActiveFocus()
  }

  function close() {
    if (!visible) return
    visible = false
    dismissed()
  }

  function activate(index) {
    var item = shown[index]
    if (!item) return
    if (item.items) { trail = trail.concat([item]); filter = ""; selected = 0; return }
    close()
    item.run()
  }

  onSelectedChanged: {
    var top = (trail.length || filter ? Style.space(28) : 0) + selected * Style.space(30)
    if (top < flick.contentY) flick.contentY = top
    else if (top + Style.space(30) > flick.contentY + flick.height) flick.contentY = top + Style.space(30) - flick.height
  }

  function back() {
    if (filter) filter = ""
    else if (trail.length) trail = trail.slice(0, -1)
    else { close(); return }
    selected = 0
  }

  MouseArea {
    anchors.fill: parent
    onClicked: menu.close()
  }

  BorderSurface {
    id: card
    width: menu.menuWidth
    y: menu.bottomEdge >= 0 ? menu.bottomEdge - height : menu.topEdge
    height: Math.min(column.implicitHeight + Style.space(12), menu.bottomEdge >= 0 ? menu.bottomEdge - Style.space(12) : menu.height - menu.topEdge - Style.space(12))
    radius: Math.max(Style.cornerRadius, Style.space(10))
    color: Qt.rgba(Colors.background.r, Colors.background.g, Colors.background.b, 1)
    borderSpec: Border.localOrSurfaceSpec("popups", "border", Colors.popups.border, Colors.popups.border, 1)
    clip: true

    MouseArea { anchors.fill: parent }
    Rectangle { anchors.fill: parent; radius: card.radius; color: Util.alpha(Colors.foreground, 0.035) }

    Item {
      id: keys
      Keys.onPressed: function(event) {
        var k = event.key
        if (k === Qt.Key_Down || k === Qt.Key_Tab) menu.selected = Math.min(menu.shown.length - 1, menu.selected + 1)
        else if (k === Qt.Key_Up || k === Qt.Key_Backtab) menu.selected = Math.max(0, menu.selected - 1)
        else if (k === Qt.Key_Return || k === Qt.Key_Enter) menu.activate(menu.selected)
        else if (k === Qt.Key_Right && menu.shown[menu.selected] && menu.shown[menu.selected].items) menu.activate(menu.selected)
        else if (k === Qt.Key_Left && !menu.filter && menu.trail.length) menu.back()
        else if (k === Qt.Key_Escape) menu.close()
        else if (k === Qt.Key_Backspace) { if (menu.filter) { menu.filter = menu.filter.slice(0, -1); menu.selected = 0 } else menu.back() }
        else if (event.text && event.text >= " " && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) { menu.filter += event.text; menu.selected = 0 }
        else return
        event.accepted = true
      }
    }

    Flickable {
      id: flick
      anchors.fill: parent
      anchors.margins: Style.space(6)
      contentHeight: column.implicitHeight
      clip: true
      boundsBehavior: Flickable.StopAtBounds

      Column {
        id: column
        width: parent.width

        // Where we are: the submenu, or what's typed.
        Item {
          width: parent.width
          height: visible ? Style.space(28) : 0
          visible: menu.trail.length > 0 || menu.filter !== ""
          Text {
            x: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            text: menu.filter ? String.fromCodePoint(0xf0349) + "  " + menu.filter
                : menu.trail.length ? String.fromCodePoint(0xf0141) + "  " + menu.trail[menu.trail.length - 1].label : ""
            color: Util.alpha(Colors.foreground, 0.55)
            font.pixelSize: Style.font.caption
          }
          MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: menu.back() }
        }

        Repeater {
          model: menu.shown
          Rectangle {
            id: entry
            required property var modelData
            required property int index
            width: column.width
            height: Style.space(30)
            radius: Math.max(Style.cornerRadius, Style.space(6))
            color: index === menu.selected ? Util.alpha(Colors.accent, 0.2) : "transparent"

            Text {
              id: entryGlyph
              x: Style.space(8)
              width: Style.space(18)
              anchors.verticalCenter: parent.verticalCenter
              horizontalAlignment: Text.AlignHCenter
              text: entry.modelData.glyph ? String.fromCodePoint(entry.modelData.glyph) : ""
              color: entry.modelData.color || Util.alpha(Colors.foreground, 0.65)
              font.family: Style.font.icon
              font.pixelSize: Style.font.subtitle
            }
            Text {
              anchors.left: entryGlyph.right
              anchors.leftMargin: Style.space(10)
              anchors.right: entryHint.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              text: entry.modelData.label
              color: Colors.foreground
              font.pixelSize: Style.font.body
              elide: Text.ElideRight
            }
            Text {
              id: entryHint
              anchors.right: parent.right
              anchors.rightMargin: Style.space(10)
              anchors.verticalCenter: parent.verticalCenter
              text: entry.modelData.items ? String.fromCodePoint(0xf0142) : entry.modelData.hint || ""
              color: Util.alpha(Colors.foreground, 0.4)
              font.family: Style.font.icon
              font.pixelSize: Style.font.caption
            }
            MouseArea {
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onEntered: menu.selected = entry.index
              onClicked: menu.activate(entry.index)
            }
          }
        }

        Text {
          visible: menu.shown.length === 0
          x: Style.space(8)
          height: Style.space(30)
          verticalAlignment: Text.AlignVCenter
          text: "Nothing matches"
          color: Util.alpha(Colors.foreground, 0.45)
          font.pixelSize: Style.font.bodySmall
        }
      }
    }
  }
}
