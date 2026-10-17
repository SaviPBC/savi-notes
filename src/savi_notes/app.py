"""The Savi Notes window: Qt Quick hosting the QML, the engine process beside
it, one instance per user, PDF export and the update check."""

import hashlib
import json
import os
import shlex
import subprocess
import sys
import threading

from PySide6.QtCore import QMarginsF, QObject, QProcess, QSizeF, Qt, QTimer, QUrl, Property, Signal, Slot
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from . import __version__, config, update

HERE = os.path.dirname(os.path.abspath(__file__))
QML_DIR = os.path.join(HERE, "qml")
ICON_FONT = os.path.join(HERE, "fonts", "SymbolsNerdFontMono-Regular.ttf")
ICON = os.path.join(HERE, "icon.svg")


class EngineBridge(QObject):
  """The engine as a child process, one JSON message per line each way."""

  line = Signal(str)
  exited = Signal(int)

  def __init__(self):
    super().__init__()
    self.ready = False
    self.queue = []
    self.buffer = b""
    self.proc = QProcess(self)
    self.proc.readyReadStandardOutput.connect(self.read)
    self.proc.readyReadStandardError.connect(self.read_errors)
    self.proc.started.connect(self.started)
    self.proc.finished.connect(self.finished)
    self.vault = ""
    self.closing = False

  def finished(self, code, status):
    self.ready = False
    self.exited.emit(code)
    # Not asked to stop: bring it back, and the window reloads.
    if not self.closing and self.vault:
      QTimer.singleShot(1000, lambda: self.start(self.vault))

  def start(self, vault):
    """Requests sent before this are kept until the engine is up."""
    self.vault = vault
    python = sys.executable
    if sys.platform == "win32":
      # pythonw keeps a console window from opening beside the app.
      windowless = os.path.join(os.path.dirname(python), "pythonw.exe")
      if os.path.exists(windowless):
        python = windowless
    self.proc.start(python, ["-m", "savi_notes.engine", "serve", vault])

  def started(self):
    self.ready = True
    for text in self.queue:
      self.write(text)
    self.queue = []

  @Slot(str)
  def send(self, text):
    if self.ready:
      self.write(text)
    else:
      self.queue.append(text)

  def write(self, text):
    self.proc.write((text + "\n").encode("utf-8"))

  def read(self):
    self.buffer += bytes(self.proc.readAllStandardOutput())
    while b"\n" in self.buffer:
      line, self.buffer = self.buffer.split(b"\n", 1)
      if line.strip():
        self.line.emit(line.decode("utf-8", "replace"))

  def read_errors(self):
    sys.stderr.write(bytes(self.proc.readAllStandardError()).decode("utf-8", "replace"))

  @Slot()
  def close(self):
    """Closing the engine's input tells it the window is gone."""
    self.closing = True
    self.proc.closeWriteChannel()

  def restart(self, vault):
    self.closing = True
    if self.proc.state() != QProcess.NotRunning:
      self.proc.closeWriteChannel()
      if not self.proc.waitForFinished(5000):
        self.proc.kill()
        self.proc.waitForFinished(2000)
    self.closing = False
    self.queue = []
    self.start(vault)

  def wait(self, ms):
    if self.proc.state() != QProcess.NotRunning:
      self.proc.waitForFinished(ms)


class App(QObject):
  """What the QML needs from the host."""

  openRequested = Signal(str)
  updateAvailable = Signal(str, bool)
  darkChanged = Signal()
  vaultChanged = Signal()
  needsSetupChanged = Signal()
  themeChanged = Signal()
  semanticChanged = Signal()
  syncChanged = Signal()
  updateChecked = Signal(str)

  def __init__(self, cfg, initial_note, families, bridge):
    super().__init__()
    self.cfg = cfg
    self.initial = initial_note
    self.families = families
    self.bridge = bridge
    QGuiApplication.styleHints().colorSchemeChanged.connect(lambda scheme: self.darkChanged.emit())

  @Property(bool, notify=needsSetupChanged)
  def needsSetup(self):
    return not self.cfg["vault"]

  @Property(str, constant=True)
  def suggestedVault(self):
    return config.default_vault().replace("\\", "/")

  @Slot(str, bool)
  def finishSetup(self, folder, semantic):
    """The onboarding's answers: save them, start the engine, add the launcher and skill."""
    folder = os.path.normpath(folder or config.default_vault())
    os.makedirs(folder, exist_ok=True)
    self.cfg["vault"] = folder
    self.cfg["semantic"] = bool(semantic)
    config.save(self.cfg)
    self.bridge.start(folder)
    from . import shortcuts, skill
    skill.install()
    shortcuts.install()
    self.vaultChanged.emit()
    self.needsSetupChanged.emit()

  @Property(str, constant=True)
  def home(self):
    return os.path.expanduser("~").replace("\\", "/")

  @Property(str, constant=True)
  def documents(self):
    from platformdirs import user_documents_dir
    return user_documents_dir().replace("\\", "/")

  @Property(bool, constant=True)
  def isMac(self):
    return sys.platform == "darwin"

  @Property(str, constant=True)
  def uiFamily(self):
    return self.families["ui"]

  @Property(str, constant=True)
  def monoFamily(self):
    return self.families["mono"]

  @Property(str, constant=True)
  def iconFamily(self):
    return self.families["icon"]

  @Property(str, constant=True)
  def version(self):
    return __version__

  @Property(str, notify=vaultChanged)
  def vault(self):
    return self.cfg["vault"].replace("\\", "/")

  @Property(str, constant=True)
  def initialNote(self):
    return self.initial

  @Property(str, notify=themeChanged)
  def theme(self):
    return self.cfg.get("theme", "system")

  @Slot(str)
  def setTheme(self, theme):
    self.cfg["theme"] = theme if theme in ("dark", "light") else "system"
    config.save(self.cfg)
    self.themeChanged.emit()
    self.darkChanged.emit()

  @Property(bool, notify=semanticChanged)
  def semantic(self):
    return bool(self.cfg.get("semantic", True))

  @Slot(bool)
  def setSemantic(self, on):
    self.cfg["semantic"] = bool(on)
    config.save(self.cfg)
    self.semanticChanged.emit()
    self.bridge.send(json.dumps({"id": 0, "op": "settings"}))

  @Property(bool, notify=syncChanged)
  def sync(self):
    return bool(self.cfg.get("sync", True))

  @Slot(bool)
  def setSync(self, on):
    self.cfg["sync"] = bool(on)
    config.save(self.cfg)
    self.syncChanged.emit()
    self.bridge.send(json.dumps({"id": 0, "op": "settings"}))

  @Slot(str)
  def setVault(self, folder):
    """Move to another notes folder: the engine restarts on it."""
    folder = os.path.normpath(folder)
    if not folder or folder == self.cfg["vault"]:
      return
    os.makedirs(folder, exist_ok=True)
    self.cfg["vault"] = folder
    config.save(self.cfg)
    self.bridge.restart(folder)
    self.vaultChanged.emit()

  @Slot()
  def checkUpdates(self):
    def check():
      found = update.latest()
      if not found:
        self.updateChecked.emit("Could not reach GitHub to check")
      elif update.is_newer(found[0], __version__):
        self.updateAvailable.emit(found[0], found[1])
      else:
        self.updateChecked.emit("Savi Notes %s is the newest release" % __version__)
    threading.Thread(target=check, daemon=True).start()

  @Property(bool, notify=darkChanged)
  def dark(self):
    theme = self.cfg.get("theme", "system")
    if theme in ("dark", "light"):
      return theme == "dark"
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark

  @Slot(str, result=str)
  def localPath(self, url):
    return QUrl(url).toLocalFile().replace("\\", "/")

  @Slot(str, str, str, result=str)
  def exportPdf(self, title, html, out):
    """Print the note's rendered HTML to a PDF; returns an error or ""."""
    try:
      escaped = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
      doc = QTextDocument()
      doc.setDefaultFont(QFont(self.families["ui"], 11))
      doc.setBaseUrl(QUrl.fromLocalFile(self.cfg["vault"] + "/"))
      doc.setHtml("<h1>%s</h1>%s" % (escaped, html))
      writer = QPdfWriter(out)
      writer.setTitle(title)
      writer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
      writer.setPageMargins(QMarginsF(18, 18, 18, 20), QPageLayout.Unit.Millimeter)
      writer.setResolution(96)
      page = writer.pageLayout().paintRectPixels(writer.resolution())
      doc.setPageSize(QSizeF(page.width(), page.height()))
      doc.print_(writer)
      return ""
    except Exception as e:
      return str(e)

  @Slot(str)
  def runUpdate(self, version):
    """Install the release once this window has closed, then reopen."""
    command = update.install_command(version)
    launcher = sys.argv[0] if os.path.isabs(sys.argv[0]) else (
      __import__("shutil").which("savi-notes") or "savi-notes")
    if not command:
      QGuiApplication.instance().quit()
      return
    if sys.platform == "win32":
      line = "timeout /t 3 /nobreak >nul & %s & start \"\" \"%s\"" % (subprocess.list2cmdline(command), launcher)
      subprocess.Popen(["cmd", "/c", line], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
      line = "sleep 3; %s; exec %s" % (shlex.join(command), shlex.quote(launcher))
      subprocess.Popen(["sh", "-c", line], start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    QGuiApplication.instance().quit()


def instance_name():
  # One window per settings file, so a second launch opens in the first.
  return "savi-notes-" + hashlib.sha1(config.path().encode("utf-8")).hexdigest()[:10]


def hand_to_running(note):
  """True when another window took the request."""
  sock = QLocalSocket()
  sock.connectToServer(instance_name())
  if not sock.waitForConnected(400):
    return False
  sock.write((json.dumps({"open": note}) + "\n").encode("utf-8"))
  sock.waitForBytesWritten(1000)
  sock.disconnectFromServer()
  return True


def check_updates(app_obj):
  found = update.latest()
  if found and update.is_newer(found[0], __version__):
    app_obj.updateAvailable.emit(found[0], found[1])


def run(note=""):
  cfg = config.load()
  if cfg["vault"] and not os.path.isdir(cfg["vault"]):
    os.makedirs(cfg["vault"], exist_ok=True)

  QQuickStyle.setStyle("Basic")
  QGuiApplication.setApplicationName("Savi Notes")
  QGuiApplication.setOrganizationName("Savi")
  QGuiApplication.setApplicationVersion(__version__)
  QGuiApplication.setDesktopFileName("savi-notes")
  app = QGuiApplication(sys.argv[:1])
  app.setWindowIcon(QIcon(ICON))

  if hand_to_running(note):
    return 0
  QLocalServer.removeServer(instance_name())
  server = QLocalServer()
  server.listen(instance_name())

  icon_id = QFontDatabase.addApplicationFont(ICON_FONT)
  icon_family = QFontDatabase.applicationFontFamilies(icon_id)[0] if icon_id >= 0 else "Symbols Nerd Font Mono"
  ui_family = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
  mono_family = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
  # The UI font with the icon font behind it, so glyphs show wherever text does.
  font = QFont()
  font.setFamilies([ui_family, icon_family])
  font.setPixelSize(13)
  app.setFont(font)

  bridge = EngineBridge()
  app_obj = App(cfg, note, {"ui": ui_family, "mono": mono_family, "icon": icon_family}, bridge)
  if cfg["vault"]:
    bridge.start(cfg["vault"])
    from . import skill
    skill.install()

  def connection():
    sock = server.nextPendingConnection()
    if not sock:
      return

    def read():
      for line in bytes(sock.readAll()).decode("utf-8", "replace").splitlines():
        try:
          app_obj.openRequested.emit(str(json.loads(line).get("open") or ""))
        except ValueError:
          pass
    sock.readyRead.connect(read)
  server.newConnection.connect(connection)

  engine = QQmlApplicationEngine()
  engine.addImportPath(QML_DIR)
  engine.rootContext().setContextProperty("App", app_obj)
  engine.rootContext().setContextProperty("EngineBridge", bridge)
  engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "NotesWindow.qml")))
  if not engine.rootObjects():
    sys.stderr.write("savi-notes: the window could not be created\n")
    return 1

  if not os.environ.get("SAVI_NOTES_NO_UPDATE_CHECK"):
    threading.Thread(target=check_updates, args=(app_obj,), daemon=True).start()
  code = app.exec()
  bridge.wait(8000)
  return code
