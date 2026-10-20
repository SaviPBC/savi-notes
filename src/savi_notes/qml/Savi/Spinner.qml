import QtQuick
import Savi

// A ring with a turning arc. Drawn rather than a rotated glyph: a glyph's box isn't
// centred on its ink, and differently per platform font, so it wobbles as it turns.
Item {
  id: root

  property color color: Colors.accent
  property bool running: visible

  implicitWidth: Style.font.body
  implicitHeight: implicitWidth

  Canvas {
    id: canvas
    anchors.fill: parent
    property color color: root.color
    onColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onPaint: {
      var ctx = getContext("2d")
      var line = Math.max(1.5, width / 8)
      var r = (width - line) / 2
      ctx.reset()
      ctx.lineWidth = line
      ctx.lineCap = "round"
      ctx.strokeStyle = Util.alpha(color, 0.2)
      ctx.beginPath()
      ctx.arc(width / 2, height / 2, r, 0, 2 * Math.PI)
      ctx.stroke()
      ctx.strokeStyle = color
      ctx.beginPath()
      ctx.arc(width / 2, height / 2, r, -Math.PI / 2, Math.PI / 4)
      ctx.stroke()
    }

    RotationAnimator on rotation {
      running: root.running
      from: 0; to: 360; duration: 900
      loops: Animation.Infinite
    }
  }
}
