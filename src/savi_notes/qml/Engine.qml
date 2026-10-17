import QtQuick

// The engine process, run by the host. call() sends one request and hands
// its reply to the callback; anything the engine reports on its own arrives
// through event().
QtObject {
  id: engine

  property int nextId: 1
  property var pending: ({})
  signal event(var message)
  signal exited(int code)

  function call(op, args, callback) {
    var request = Object.assign({ id: engine.nextId++, op: op }, args || {})
    engine.pending[request.id] = callback || null
    EngineBridge.send(JSON.stringify(request))
  }

  // Closing its input tells the engine the window is gone.
  function close() { EngineBridge.close() }

  property Connections bridge: Connections {
    target: EngineBridge
    function onLine(text) {
      var message
      try { message = JSON.parse(text) } catch (e) { console.warn("engine said:", text); return }
      if (message.id !== undefined) {
        var callback = engine.pending[message.id]
        delete engine.pending[message.id]
        if (callback) callback(message)
      } else if (message.event) engine.event(message)
    }
    function onExited(code) {
      // Requests in flight get an error; the host restarts the engine.
      var waiting = engine.pending
      engine.pending = {}
      for (var id in waiting) if (waiting[id]) waiting[id]({ error: "the notes engine stopped" })
      engine.exited(code)
    }
  }
}
