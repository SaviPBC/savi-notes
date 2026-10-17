import QtQuick
import QtQuick.Controls
import Savi

// The panes, laid out from a tree: a leaf { pane } shows one note, a
// split { dir: "right" | "down", a, b } puts two subtrees side by side or
// one above the other, with a divider to drag between them.
Item {
  id: tree

  property var node: null
  property var app: null

  Loader {
    anchors.fill: parent
    sourceComponent: !tree.node ? null : tree.node.pane ? leaf : split
  }

  Component {
    id: leaf
    NoteView {
      app: tree.app
      pane: tree.node.pane
    }
  }

  Component {
    id: split
    SplitView {
      id: splitView
      orientation: tree.node.dir === "down" ? Qt.Vertical : Qt.Horizontal

      handle: Item {
        implicitWidth: Style.space(7)
        implicitHeight: Style.space(7)
        Rectangle {
          anchors.centerIn: parent
          width: splitView.orientation === Qt.Horizontal ? 1 : parent.width
          height: splitView.orientation === Qt.Horizontal ? parent.height : 1
          color: SplitHandle.hovered || SplitHandle.pressed ? Colors.accent : Util.alpha(Colors.foreground, 0.1)
        }
      }

      Loader {
        SplitView.preferredWidth: splitView.width / 2
        SplitView.preferredHeight: splitView.height / 2
        SplitView.minimumWidth: Style.space(240)
        SplitView.minimumHeight: Style.space(160)
        source: "PaneTree.qml"
        onLoaded: { item.app = tree.app; item.node = Qt.binding(function() { return tree.node.a }) }
      }
      Loader {
        SplitView.fillWidth: true
        SplitView.fillHeight: true
        SplitView.minimumWidth: Style.space(240)
        SplitView.minimumHeight: Style.space(160)
        source: "PaneTree.qml"
        onLoaded: { item.app = tree.app; item.node = Qt.binding(function() { return tree.node.b }) }
      }
    }
  }
}
