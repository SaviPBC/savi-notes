"""The Savi Notes window: Qt Quick hosting the QML, the engine process beside
it, one instance per user, signing in and the note key, PDF export and the
update check."""

import hashlib
import json
import os
import base64
import shlex
import tomllib
import shutil
import subprocess
import sys
import threading

from PySide6.QtCore import QMarginsF, QObject, QProcess, QSizeF, Qt, QTimer, QUrl, Property, Signal, Slot
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from . import __version__, account, config, crypto, desktop, update

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

  def stop(self):
    self.closing = True
    self.queue = []
    if self.proc.state() != QProcess.NotRunning:
      self.proc.closeWriteChannel()
      if not self.proc.waitForFinished(15000):
        self.proc.kill()
        self.proc.waitForFinished(2000)
    self.closing = False

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
  stepChanged = Signal()
  stepReady = Signal(str, str)
  themeChanged = Signal()
  lookChanged = Signal()
  semanticChanged = Signal()
  updateChecked = Signal(str)

  def __init__(self, cfg, initial_note, families, bridge):
    super().__init__()
    self.cfg = cfg
    self.initial = initial_note
    self.families = families
    self.bridge = bridge
    self.account = account.load()
    self.pending_key = None
    self.cancel = threading.Event()
    self.step = self.first_step()
    self.error = ""
    self.stepReady.connect(self.stepped)
    self.look_stamp, self.look_data = None, {}
    self.reload_look()
    # A theme switch replaces the file, so look for that rather than watching it.
    self.look_timer = QTimer(self)
    self.look_timer.timeout.connect(self.reload_look)
    self.look_timer.start(2000)
    if self.step == "recover":
      QTimer.singleShot(0, self.resume)
    QGuiApplication.styleHints().colorSchemeChanged.connect(lambda scheme: self.darkChanged.emit())

  # ---------------------------------------------------------------- setup

  @Property(bool, notify=needsSetupChanged)
  def needsSetup(self):
    return self.step != ""

  @Property(str, notify=stepChanged)
  def setupStep(self):
    """signin, waiting (the browser is open), newKey, recover, preparing (the first sync and
    index, before the window is used), or "" once set up."""
    return self.step

  @Property(str, notify=stepChanged)
  def setupError(self):
    return self.error

  @Property(str, notify=stepChanged)
  def recoveryKey(self):
    """Shown once while the new key is being set up, and on request after."""
    key = self.pending_key or account.note_key(self.account)
    return crypto.recovery_text(key) if key else ""

  @Property(str, notify=stepChanged)
  def email(self):
    return self.account.get("email", "")

  def go(self, step, error=""):
    was = self.needsSetup
    self.step, self.error = step, error
    self.stepChanged.emit()
    if was != self.needsSetup:
      self.needsSetupChanged.emit()

  def first_step(self):
    if not self.account.get("access"):
      return "signin"
    return "" if account.note_key(self.account) else "recover"

  def in_background(self, work):
    """Network calls off the UI thread; `work` returns the next step and an error."""
    def run():
      try:
        step, error = work()
      except account.Offline:
        step, error = self.step if self.step != "waiting" else "signin", "Couldn't reach the Savi AI Core. Check your connection and try again."
      except account.SignedOut:
        self.account = {}
        account.clear()
        step, error = "signin", "Your sign-in has expired. Sign in again."
      except Exception as e:
        step, error = self.step if self.step != "waiting" else "signin", str(e)
      self.stepReady.emit(step, error)
    threading.Thread(target=run, daemon=True).start()

  @Slot(bool)
  def signIn(self, semantic):
    self.cfg["semantic"] = bool(semantic)
    config.save(self.cfg)
    self.cancel = threading.Event()
    self.go("waiting")

    def work():
      try:
        signed = account.sign_in(self.cfg["gateway"], self.cancel)
      except account.Cancelled:
        return "signin", ""
      client = account.Client(signed)
      vault = client.call("GET", "/vault")
      kept = account.note_key(self.account) if self.account.get("email") == vault["email"] else None
      self.account = {**signed, "email": vault["email"]}
      if vault["key_check"] is None:
        self.pending_key = crypto.new_key()
        account.save(self.account)
        return "newKey", ""
      if kept and crypto.opens(kept, vault["key_check"]):
        self.account["key"] = base64.b64encode(kept).decode()
        account.save(self.account)
        return "", ""
      account.save(self.account)
      return "recover", ""
    self.in_background(work)

  def resume(self):
    """Signed in last time but closed before the key was set: find out which step that was."""
    self.go("waiting")

    def work():
      if account.Client(self.account).call("GET", "/vault")["key_check"] is None:
        self.pending_key = crypto.new_key()
        return "newKey", ""
      return "recover", ""
    self.in_background(work)

  @Slot()
  def cancelSignIn(self):
    self.cancel.set()

  @Slot()
  def keySaved(self):
    """The person has the recovery key somewhere safe: store the key and say so to the AI Core."""
    key = self.pending_key

    def work():
      try:
        account.Client(self.account).call("PUT", "/vault", {"key_check": crypto.key_check(key)})
      except account.Refused as e:
        if e.status == 409:
          self.pending_key = None
          return "recover", "Another device finished setting up first. Enter the recovery key it showed."
        raise
      self.keep(key)
      return "", ""
    self.in_background(work)

  @Slot(str)
  def recover(self, text):
    def work():
      try:
        key = crypto.parse_recovery(text)
      except crypto.WrongKey:
        return "recover", "That isn't a recovery key. It's 52 letters and numbers in groups of four."
      check = account.Client(self.account).call("GET", "/vault")["key_check"]
      if check is None:
        self.pending_key = crypto.new_key()
        return "newKey", "Your notes were reset on another device, so this account starts fresh."
      if not crypto.opens(key, check):
        return "recover", "That recovery key doesn't open these notes. Check it and try again."
      self.keep(key)
      return "", ""
    self.in_background(work)

  @Slot()
  def startOver(self):
    """For a lost recovery key: the notes on the AI Core can't be opened any more, so clear them."""
    def work():
      account.Client(self.account).call("DELETE", "/vault")
      self.forget_local()
      self.pending_key = crypto.new_key()
      return "newKey", ""
    self.in_background(work)

  def keep(self, key):
    self.pending_key = None
    self.account["key"] = base64.b64encode(key).decode()
    account.save(self.account)

  def stepped(self, step, error):
    """Back on the UI thread with the outcome of a background step. Signed in and unlocked
    means the notes come down and get indexed first, behind a progress screen."""
    if step == "":
      self.go("preparing")
      self.start_engine()
    else:
      self.go(step, error)

  @Slot()
  def prepared(self):
    if self.step == "preparing":
      self.go("")

  def start_engine(self):
    import_legacy(self.cfg)
    os.makedirs(config.vault_dir(), exist_ok=True)
    self.bridge.start(config.vault_dir())
    if not config.DEV:
      from . import shortcuts
      shortcuts.install()

  def forget_local(self):
    """This computer's copy, which signing out or starting over must not leave behind."""
    from . import sync
    shutil.rmtree(config.vault_dir(), ignore_errors=True)
    for leftover in (sync.state_path(),):
      if os.path.exists(leftover):
        os.remove(leftover)

  @Slot()
  def signOut(self):
    """Called once the engine has said nothing is left to send."""
    self.bridge.stop()
    self.forget_local()
    self.account = {}
    account.clear()
    self.go("signin")

  @Slot(str)
  def accountLost(self, state):
    """The engine found the sign-in revoked, or the notes sealed under a different key."""
    self.bridge.stop()
    if state == "wrongKey":
      self.account.pop("key", None)
      account.save(self.account)
      self.forget_local()
      self.go("recover", "Your notes were set up again on another device. Enter the new recovery key.")
    else:
      self.account = {k: v for k, v in self.account.items() if k in ("email", "key", "gateway")}
      account.save(self.account)
      self.go("signin", "Sign in again to keep syncing your notes.")

  @Slot(str)
  def fillFileName(self, name):
    """Qt's own save dialog, used where there is no native one (Linux without a portal), shows
    an empty name however selectedFile is set; native dialogs fill it in themselves. So put it
    in the dialog's name box once the dialog is up, if there is such a box."""
    def fill(tries):
      for window in QGuiApplication.allWindows():
        stack = [window.contentItem()] if hasattr(window, "contentItem") else []
        while stack:
          item = stack.pop()
          if item.objectName() == "fileNameTextField":
            item.setProperty("text", name)
            return
          stack.extend(item.childItems())
      if tries:
        QTimer.singleShot(50, lambda: fill(tries - 1))
    fill(10)

  @Slot(str)
  def copy(self, text):
    QGuiApplication.clipboard().setText(text)

  @Property(str, constant=True)
  def home(self):
    return os.path.expanduser("~").replace("\\", "/")

  @Property(str, constant=True)
  def documents(self):
    from platformdirs import user_documents_dir
    return user_documents_dir().replace("\\", "/")

  def reload_look(self):
    try:
      stat = os.stat(config.theme_path())
      stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError:
      stamp = None
    if stamp == self.look_stamp:
      return
    self.look_stamp = stamp
    try:
      with open(config.theme_path(), "rb") as f:
        self.look_data = tomllib.load(f)
    except OSError:
      self.look_data = {}
    except tomllib.TOMLDecodeError as e:
      sys.stderr.write("savi-notes: theme.toml: %s\n" % e)
      self.look_data = {}
    font = QFont(QGuiApplication.font())
    font.setFamilies([self.uiFamily, self.families["icon"]])
    font.setPixelSize(int(self.look_data.get("font", {}).get("size", 13)))
    QGuiApplication.setFont(font)
    self.lookChanged.emit()
    self.darkChanged.emit()

  @Property("QVariantMap", notify=lookChanged)
  def look(self):
    """The theme file's contents; {} means the Savi look."""
    return self.look_data

  @Property(bool, constant=True)
  def dev(self):
    return config.DEV

  @Property(bool, constant=True)
  def isMac(self):
    return sys.platform == "darwin"

  @Property(str, notify=lookChanged)
  def uiFamily(self):
    return self.look_data.get("font", {}).get("family") or self.families["ui"]

  @Property(str, notify=lookChanged)
  def monoFamily(self):
    return self.look_data.get("font", {}).get("mono") or self.families["mono"]

  @Property(str, constant=True)
  def iconFamily(self):
    return self.families["icon"]

  @Property(str, constant=True)
  def version(self):
    return __version__

  @Property(str, notify=vaultChanged)
  def vault(self):
    return config.vault_dir().replace("\\", "/")

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
    if self.look_data.get("colors"):
      return self.look_data.get("mode", "dark") != "light"
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
      doc.setDefaultFont(QFont(self.uiFamily, 11))
      doc.setBaseUrl(QUrl.fromLocalFile(config.vault_dir() + "/"))
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
    # The installed command, not sys.argv[0]: the window runs as python -m savi_notes.
    from . import shortcuts
    launcher = shortcuts.launcher(gui=True)
    if not command:
      QGuiApplication.instance().quit()
      return
    if sys.platform == "win32":
      # One string through the shell: as a list, Python escapes the quotes for cmd with
      # backslashes, which cmd doesn't understand ("Windows cannot find '\\'").
      line = "timeout /t 3 /nobreak >nul & %s & start \"\" \"%s\"" % (subprocess.list2cmdline(command), launcher)
      subprocess.Popen(line, shell=True, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
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


def import_legacy(cfg):
  """0.1 kept notes in a folder the person chose. The first time this version runs, a copy
  of that folder becomes the local copy, and from there goes up to the AI Core. The old
  folder is left as it was."""
  old = cfg.pop("vault", "")
  cfg.pop("sync", None)
  config.save(cfg)
  new = config.vault_dir()
  if not old or not os.path.isdir(old) or (os.path.isdir(new) and os.listdir(new)):
    return
  shutil.copytree(old, new, ignore=shutil.ignore_patterns(".*"), dirs_exist_ok=True)


def run(note=""):
  cfg = config.load()

  desktop.name_app()
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
  # Before sign-in too, so whoever installed it through Claude Code can try the skill at once.
  if not config.DEV:
    from . import skill
    skill.install()
  if not app_obj.needsSetup:
    import_legacy(cfg)
    bridge.start(config.vault_dir())

  def connection():
    sock = server.nextPendingConnection()
    if not sock:
      return

    def read():
      for line in bytes(sock.readAll()).decode("utf-8", "replace").splitlines():
        try:
          desktop.bring_forward()
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
  desktop.bring_forward()
  from . import shortcuts
  if not app_obj.needsSetup and not config.DEV:
    shortcuts.install()

  if not os.environ.get("SAVI_NOTES_NO_UPDATE_CHECK") and not config.DEV:
    threading.Thread(target=check_updates, args=(app_obj,), daemon=True).start()
  code = app.exec()
  bridge.wait(8000)
  return code
