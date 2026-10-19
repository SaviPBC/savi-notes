"""Render icon.svg into icon.icns for the macOS app bundle. Run it after changing the
icon; the .icns is committed, since building one needs nothing but Qt and this script."""

import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PySide6.QtGui import QGuiApplication, QIcon

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "savi_notes")
# (type, pixels): the PNG-payload entries macOS reads, standard and @2x.
ENTRIES = [("icp4", 16), ("icp5", 32), ("icp6", 64), ("ic07", 128), ("ic08", 256), ("ic09", 512), ("ic10", 1024),
           ("ic11", 32), ("ic12", 64), ("ic13", 256), ("ic14", 512)]


def png(icon, size):
  data = QByteArray()
  buffer = QBuffer(data)
  buffer.open(QIODevice.OpenModeFlag.WriteOnly)
  icon.pixmap(QSize(size, size)).toImage().save(buffer, "PNG")
  return bytes(data)


def main():
  QGuiApplication(sys.argv[:1])
  icon = QIcon(os.path.join(HERE, "icon.svg"))
  body = b"".join(kind.encode() + struct.pack(">I", 8 + len(p)) + p for kind, p in ((k, png(icon, s)) for k, s in ENTRIES))
  with open(os.path.join(HERE, "icon.icns"), "wb") as f:
    f.write(b"icns" + struct.pack(">I", 8 + len(body)) + body)


if __name__ == "__main__":
  main()
