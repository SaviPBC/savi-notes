.pragma library

// Markdown to the HTML subset Qt's rich text understands, laid out like
// Obsidian's reading view in the Wolfen theme's colors. Obsidian syntax
// included: [[links]], ![[embeds]], #tags, tasks, ==highlights==, %%comments%%,
// footnotes, > [!callouts], $math$ and mermaid diagrams. FORMAT.md documents
// every syntax rendered here (the wolfnotes skill reads it); keep it in step.
//
// Links come back through onLinkActivated as note:<name>[#anchor], heading:,
// tag:, task:<line>, fold:<line>, file:, or web URLs. Things the page needs
// but doesn't have (embedded notes, remote images, math, diagrams) are
// reported through theme.need({ kind, key, ... }) and looked up again in
// theme.embeds[key] on the next render.

function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")
}

function hex(c) {
  return "#" + [c.r, c.g, c.b].map(function(v) {
    var n = Math.round(v * 255)
    return (n < 16 ? "0" : "") + n.toString(16)
  }).join("")
}

function parseHex(h) {
  return { r: parseInt(h.slice(1, 3), 16) / 255, g: parseInt(h.slice(3, 5), 16) / 255, b: parseInt(h.slice(5, 7), 16) / 255 }
}

// Flatten a translucent color onto the background; Qt's table cells ignore alpha.
function mix(fg, bg, a) {
  return hex({ r: fg.r * a + bg.r * (1 - a), g: fg.g * a + bg.g * (1 - a), b: fg.b * a + bg.b * (1 - a) })
}

// Callout types and their aliases, with Obsidian's colors and icons.
var CALLOUTS = {
  note: ["blue", 0xf03eb], abstract: ["cyan", 0xf0147], info: ["blue", 0xf02fd], todo: ["blue", 0xf05e1],
  tip: ["cyan", 0xf0238], success: ["green", 0xf012c], question: ["orange", 0xf02d7], warning: ["orange", 0xf0026],
  failure: ["red", 0xf0156], danger: ["red", 0xf140b], bug: ["red", 0xf00e4], example: ["magenta", 0xf0279],
  quote: ["muted", 0xf027e]
}
var CALLOUT_ALIASES = {
  summary: "abstract", tldr: "abstract", hint: "tip", important: "tip", check: "success", done: "success",
  help: "question", faq: "question", caution: "warning", attention: "warning", fail: "failure",
  missing: "failure", error: "danger", cite: "quote"
}

// ---------------------------------------------------------------- styles

// t: everything rendering needs, derived once per render from the theme:
// { accent, fg, bg, palette: { red, ... } (colors), size, sans, mono, width,
//   embeds, exists(title), folds, print, need(item) }
function styles(theme) {
  // Palette entries may be hex strings or color objects.
  var p = {}
  for (var key in theme.palette || {}) p[key] = typeof theme.palette[key] === "string" ? parseHex(theme.palette[key]) : theme.palette[key]
  function named(name, fallback) { return p[name] ? hex(p[name]) : fallback }
  var fg = hex(theme.fg), accent = hex(theme.accent)
  var s = theme.size / 15
  var t = {
    fg: fg,
    bg: hex(theme.bg),
    accent: accent,
    muted: mix(theme.fg, theme.bg, 0.7),
    faint: named("dark_foreground", mix(theme.fg, theme.bg, 0.45)),
    border: named("muted", mix(theme.fg, theme.bg, 0.25)),
    codeBg: theme.print ? "#f3f3f5" : named("dark_background", mix(theme.fg, theme.bg, 0.05)),
    red: named("red", accent), green: named("green", fg), yellow: named("yellow", fg),
    blue: named("blue", accent), magenta: named("magenta", accent), cyan: named("cyan", accent),
    orange: named("orange", named("yellow", accent)),
    brightCyan: named("bright_cyan", named("cyan", accent)), brightMagenta: named("bright_magenta", named("magenta", accent)),
    surface: hex(theme.bg),
    mono: theme.mono,
    sans: theme.sans || "sans-serif",
    icon: theme.icon || "Symbols Nerd Font Mono",
    size: theme.size,
    px: function(v) { return Math.round(v * s * 10) / 10 + "px" },
    gap: Math.round(15 * s),
    width: theme.width,
    embeds: theme.embeds || {},
    exists: theme.exists || function() { return true },
    folds: theme.folds || {},
    print: !!theme.print,
    need: theme.need || function() {},
    theme: theme
  }
  if (t.print) {
    t.red = t.green = t.yellow = t.blue = t.magenta = t.orange = t.fg
    t.cyan = t.brightCyan = t.brightMagenta = t.fg
    t.faint = t.muted
  }
  t.codeColor = t.cyan
  t.highlightBg = theme.print ? "#fff3a3" : mix(p.yellow || theme.accent, theme.bg, 0.3)
  t.tagBg = theme.print ? "#ececf0" : mix(p.cyan || theme.accent, theme.bg, 0.14)
  t.link = t.blue
  t.unresolved = theme.print ? t.fg : mix(p.magenta || theme.accent, theme.bg, 0.7)
  return t
}

// ---------------------------------------------------------------- blocks

// Lines are { s: text, n: line number in the body } so tasks can be ticked
// from anywhere in the tree.

function expandTabs(s) {
  return s.replace(/^[ \t]+/, function(ws) {
    var out = ""
    for (var i = 0; i < ws.length; i++) out += ws[i] === "\t" ? "    ".slice(out.length % 4) : " "
    return out
  })
}

function indentOf(s) { return s.match(/^ */)[0].length }

// %%Comments%% vanish, inline or across lines, outside code.
function stripComments(lines) {
  var fence = null, inComment = false
  return lines.map(function(s) {
    if (fence) {
      if (new RegExp("^\\s*" + fence[0] + "{" + fence.length + ",}\\s*$").test(s)) fence = null
      return s
    }
    var f = !inComment && s.match(/^\s*(`{3,}|~{3,})/)
    if (f) { fence = f[1]; return s }
    var out = "", k = 0
    while (k < s.length) {
      if (inComment) {
        var end = s.indexOf("%%", k)
        if (end < 0) break
        inComment = false
        k = end + 2
        continue
      }
      var tick = s.indexOf("`", k), open = s.indexOf("%%", k)
      if (open < 0) { out += s.slice(k); break }
      if (tick >= 0 && tick < open) {
        var close = s.indexOf("`", tick + 1)
        if (close < 0) { out += s.slice(k); break }
        out += s.slice(k, close + 1)
        k = close + 1
        continue
      }
      out += s.slice(k, open)
      inComment = true
      k = open + 2
    }
    return out
  })
}

var LIST = /^( *)([-*+]|(\d{1,9})[.)])( +|$)(.*)$/
var HR = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/
var HEADING = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$/
var FENCE = /^( *)(`{3,}|~{3,})[ \t]*([^\s`]*)/
var DELIMITER = /^ *\|? *:?-+:? *(\| *:?-+:? *)*\|? *$/

function listMarker(s) {
  var m = s.match(LIST)
  if (!m || HR.test(s)) return null
  var width = m[2].length + (m[4].length > 4 || !m[5] ? 1 : m[4].length)
  return { indent: m[1].length, ordered: !!m[3], start: m[3] ? parseInt(m[3], 10) : 1, content: m[1].length + width, text: m[5] }
}

function isTableStart(L, i) {
  return L[i].s.indexOf("|") >= 0 && i + 1 < L.length && L[i + 1].s.indexOf("-") >= 0 && DELIMITER.test(L[i + 1].s)
    && (L[i + 1].s.indexOf("|") >= 0 || L[i].s.indexOf("|") >= 0)
}

// Whether a line starts a block that ends the paragraph above it.
function interrupts(s) {
  return HEADING.test(s) || FENCE.test(s) || /^ {0,3}>/.test(s) || HR.test(s) || /^\s*\$\$/.test(s)
    || /^ {0,3}<pre\b/i.test(s) || /^ {0,3}\[\^[^\]]+\]:/.test(s) || !!listMarker(s)
}

function splitCells(line) {
  var cells = [], cur = "", code = false
  var s = line.trim().replace(/^\|/, "")
  for (var i = 0; i < s.length; i++) {
    var c = s[i]
    if (c === "\\" && s[i + 1] === "|") { cur += "|"; i++; continue }
    if (c === "`") code = !code
    if (c === "|" && !code) { cells.push(cur.trim()); cur = ""; continue }
    cur += c
  }
  if (cur.trim() || !/\|\s*$/.test(line)) cells.push(cur.trim())
  return cells
}

function unescapeHtml(s) {
  return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, "\"").replace(/&#39;/g, "'").replace(/&amp;/g, "&")
}

function parseBlocks(L, ctx) {
  var out = []
  var i = 0, m
  while (i < L.length) {
    var s = L[i].s
    if (!s.trim()) { i++; continue }

    // Fenced code, diagrams and math.
    if ((m = s.match(FENCE))) {
      var fence = m[2], strip = new RegExp("^ {0," + m[1].length + "}"), lang = m[3].toLowerCase()
      var closing = new RegExp("^ *" + (fence[0] === "`" ? "`" : "~") + "{" + fence.length + ",}[ \\t]*$")
      var code = []
      i++
      while (i < L.length && !closing.test(L[i].s)) code.push(L[i++].s.replace(strip, ""))
      i++
      if (lang === "mermaid") out.push({ type: "mermaid", text: code.join("\n"), lang: lang })
      else if (lang === "math") out.push({ type: "math", tex: code.join("\n").trim() })
      else out.push({ type: "code", lang: lang, text: code.join("\n") })
      continue
    }

    // Display math.
    if (/^\s*\$\$/.test(s)) {
      var tex = s.trim().slice(2)
      var done = tex.lastIndexOf("$$")
      if (done >= 0) { tex = tex.slice(0, done); i++ }
      else {
        i++
        while (i < L.length && L[i].s.indexOf("$$") < 0) tex += "\n" + L[i++].s
        if (i < L.length) tex += "\n" + L[i++].s.slice(0, L[i - 1].s.indexOf("$$"))
      }
      out.push({ type: "math", tex: tex.trim() })
      continue
    }

    // Literal <pre> blocks, shown as code.
    if (/^ {0,3}<pre\b/i.test(s)) {
      var raw = []
      while (i < L.length) {
        raw.push(L[i].s)
        if (/<\/pre>/i.test(L[i++].s)) break
      }
      var text = raw.join("\n").replace(/^\s*<pre[^>]*>(\s*<code[^>]*>)?/i, "").replace(/(<\/code>\s*)?<\/pre>.*$/i, "")
      out.push({ type: "code", lang: "", text: unescapeHtml(text) })
      continue
    }

    // Indented code.
    if (/^ {4}/.test(s)) {
      var lines = []
      while (i < L.length && (/^ {4}/.test(L[i].s) || !L[i].s.trim())) lines.push(L[i++].s.replace(/^ {4}/, ""))
      while (lines.length && !lines[lines.length - 1].trim()) lines.pop()
      out.push({ type: "code", lang: "", text: lines.join("\n") })
      continue
    }

    if ((m = s.match(HEADING))) {
      out.push({ type: "heading", level: m[1].length, text: m[2] || "" })
      i++
      continue
    }

    if (HR.test(s)) { out.push({ type: "hr" }); i++; continue }

    if (isTableStart(L, i)) {
      var head = splitCells(s)
      var align = splitCells(L[i + 1].s).map(function(c) { return /^:-+:$/.test(c) ? "center" : /-:$/.test(c) ? "right" : "left" })
      var rows = []
      i += 2
      while (i < L.length && L[i].s.trim() && L[i].s.indexOf("|") >= 0) rows.push(splitCells(L[i++].s))
      out.push({ type: "table", head: head, align: align, rows: rows })
      continue
    }

    // Block quotes and callouts, with lazy continuation lines.
    if (/^ {0,3}>/.test(s)) {
      var q = []
      while (i < L.length) {
        var line = L[i].s
        if (/^ {0,3}>/.test(line)) q.push({ s: expandTabs(line.replace(/^ {0,3}> ?/, "")), n: L[i].n })
        else if (line.trim() && q[q.length - 1].s.trim() && !interrupts(line)) q.push({ s: line, n: L[i].n })
        else break
        i++
      }
      var cm = q[0].s.match(/^\[!([^\]]+)\]([+-]?)[ \t]*(.*)$/)
      if (cm) out.push({ type: "callout", kind: cm[1].trim().toLowerCase(), fold: cm[2], title: cm[3], n: q[0].n, children: parseBlocks(q.slice(1), ctx) })
      else out.push({ type: "quote", children: parseBlocks(q, ctx) })
      continue
    }

    // Footnote definitions; indented lines below belong to them.
    if ((m = s.match(/^ {0,3}\[\^([^\]]+)\]:[ \t]?(.*)$/))) {
      var body = [{ s: m[2], n: L[i].n }]
      i++
      while (i < L.length) {
        var next = L[i].s
        if (/^ {4}/.test(next)) body.push({ s: next.slice(4), n: L[i].n })
        else if (!next.trim()) {
          var j = i
          while (j < L.length && !L[j].s.trim()) j++
          if (j < L.length && /^ {4}/.test(L[j].s)) body.push({ s: "", n: L[i].n })
          else break
        } else if (body[body.length - 1].s.trim() && !interrupts(next)) body.push({ s: next, n: L[i].n })
        else break
        i++
      }
      ctx.footnotes[m[1]] = parseBlocks(body, ctx)
      continue
    }

    var marker = listMarker(s)
    if (marker) {
      var list = { type: "list", ordered: marker.ordered, start: marker.start, items: [] }
      while (i < L.length) {
        var mk = listMarker(L[i].s)
        if (!mk || mk.ordered !== list.ordered || mk.indent >= marker.content) break
        var item = { n: L[i].n, task: null }
        var task = mk.text.match(/^\[(.)\](?:\s+|$)(.*)$/)
        if (task) { item.task = task[1]; mk.text = task[2] }
        var content = [{ s: mk.text, n: L[i].n }]
        i++
        while (i < L.length) {
          var c = L[i].s
          if (!c.trim()) {
            var k = i
            while (k < L.length && !L[k].s.trim()) k++
            if (k < L.length && indentOf(L[k].s) >= mk.content) { content.push({ s: "", n: L[i].n }); i++; continue }
            break
          }
          if (indentOf(c) >= mk.content) content.push({ s: c.slice(mk.content), n: L[i].n })
          else if (content[content.length - 1].s.trim() && !interrupts(c) && !listMarker(c)) content.push({ s: c.trim(), n: L[i].n })
          else break
          i++
        }
        item.children = parseBlocks(content, ctx)
        list.items.push(item)
        // A blank line between items keeps the list going.
        var after = i
        while (after < L.length && !L[after].s.trim()) after++
        var sibling = after < L.length && listMarker(L[after].s)
        item.loose = after > i
        if (after > i && !(sibling && sibling.ordered === list.ordered && sibling.indent < marker.content)) break
        i = after
      }
      out.push(list)
      continue
    }

    // Paragraph, or a setext heading.
    var para = []
    while (i < L.length && L[i].s.trim()) {
      if (para.length && /^ {0,3}(=+|-+)[ \t]*$/.test(L[i].s)) {
        out.push({ type: "heading", level: L[i].s.trim()[0] === "=" ? 1 : 2, text: para.map(function(l) { return l.s.trim() }).join(" ") })
        para = null
        i++
        break
      }
      if (para.length && (interrupts(L[i].s) || isTableStart(L, i))) break
      para.push(L[i++])
    }
    if (para && para.length) out.push({ type: "para", lines: para.map(function(l) { return l.s.replace(/^\s+/, "") }) })
  }
  return out
}

function parse(src) {
  var raw = src.replace(/\r/g, "").split("\n")
  var stripped = stripComments(raw)
  var L = stripped.map(function(s, n) { return { s: expandTabs(s), n: n } })
  var ctx = { footnotes: {}, order: [], numbers: {} }
  ctx.blocks = parseBlocks(L, ctx)
  return ctx
}

// ---------------------------------------------------------------- inline

function linkHtml(href, label, color, t, external) {
  var html = "<a href=\"" + esc(href) + "\" style=\"color:" + color + "; text-decoration:underline;\">" + label + "</a>"
  if (external && !t.print)
    html += "<span style=\"font-family:'" + t.mono + "'; font-size:" + t.px(11) + "; color:" + t.faint + ";\"> \u{F03CC}</span>"
  return html
}

function noteHref(target, anchor) {
  return "note:" + encodeURIComponent(target) + (anchor ? "#" + encodeURIComponent(anchor) : "")
}

function inline(text, t, ctx) {
  var stash = []
  function keep(html) { stash.push(html); return "\u0001" + (stash.length - 1) + "\u0002" }
  function restore(s) { return s.replace(/\u0001(\d+)\u0002/g, function(m, i) { return stash[+i] }) }

  text = text.replace(/(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)/g, function(m, ticks, code) {
    if (/^ .* $/.test(code)) code = code.slice(1, -1)
    return keep(codeSpan(code, t))
  })
  text = text.replace(/\\([!-\/:-@\[-`{-~])/g, function(m, c) { return keep(esc(c)) })
  text = text.replace(/\$(?=[^\s$])([^$\n]*?[^\s\\$])\$(?!\d)/g, function(m, tex) { return keep(math(tex, false, t)) })
  text = text.replace(/\$([^\s$])\$/g, function(m, tex) { return keep(math(tex, false, t)) })

  // Footnotes: [^label] and inline ^[text].
  text = text.replace(/\^\[([^\]]+)\]/g, function(m, note) {
    if (!ctx) return m
    var label = "inline:" + ctx.order.length
    ctx.footnotes[label] = [{ type: "para", lines: [note] }]
    return keep(footnoteRef(label, t, ctx))
  })
  text = text.replace(/\[\^([^\]]+)\]/g, function(m, label) {
    return ctx && ctx.footnotes[label] ? keep(footnoteRef(label, t, ctx)) : m
  })

  text = text.replace(/!\[\[([^\]|#]*)(#[^\]|]*)?(?:\|([^\]]*))?\]\]/g, function(m, name, anchor, size) {
    return keep(embed(name.trim(), anchor ? anchor.slice(1) : "", size || "", "", t, ctx))
  })
  text = text.replace(/\[\[([^\]|#]*)(#[^\]|]*)?(?:\|([^\]]*))?\]\]/g, function(m, target, anchor, alias) {
    target = target.trim()
    anchor = anchor ? anchor.slice(1).trim() : ""
    if (!target && !anchor) return m
    var label = alias || (target ? target + (anchor ? " > " + anchor.replace(/^\^/, "") : "") : anchor.replace(/^\^/, ""))
    if (!target) return keep(linkHtml("heading:" + encodeURIComponent(anchor), esc(label), t.link, t))
    return keep(linkHtml(noteHref(target, anchor), esc(label), t.exists(target) ? t.link : t.unresolved, t))
  })
  text = text.replace(/!\[([^\]]*)\]\((?:<([^>]+)>|([^)\s]*))(?:\s+"[^"]*")?\)/g, function(m, alt, angled, plain) {
    var parts = alt.split("|")
    var size = parts.length > 1 && /^\d+(x\d+)?$/.test(parts[parts.length - 1].trim()) ? parts.pop().trim() : ""
    var src = angled || plain
    return keep(embed(/^[a-z][\w+.-]*:/i.test(src) ? src : decodeURIComponent(src), "", size, parts.join("|"), t, ctx))
  })
  text = text.replace(/\[([^\]]*)\]\((?:<([^>]+)>|([^)\s]*))(?:\s+"[^"]*")?\)/g, function(m, label, angled, plain) {
    var url = angled || plain
    var labelHtml = emphasis(esc(label))
    if (url && !/^[a-z][\w+.-]*:/i.test(url) && url[0] !== "#") {
      var path = decodeURIComponent(url).replace(/\.md(?=#|$)/, "")
      var hash = path.indexOf("#")
      var target = hash >= 0 ? path.slice(0, hash) : path
      return keep(linkHtml(noteHref(target, hash >= 0 ? path.slice(hash + 1) : ""), labelHtml, t.exists(target) ? t.link : t.unresolved, t))
    }
    if (url[0] === "#") return keep(linkHtml("heading:" + encodeURIComponent(decodeURIComponent(url.slice(1))), labelHtml, t.link, t))
    return keep(linkHtml(url, labelHtml, t.link, t, true))
  })
  text = text.replace(/<((?:https?|mailto|obsidian):[^\s>]+)>|((?:https?:\/\/|www\.)[^\s<>]+[^\s<>).,;:!?'"*_~])/g, function(m, angled, bare) {
    var url = angled || bare
    return keep(linkHtml(/^www\./.test(url) ? "https://" + url : url, esc(url), t.link, t, true))
  })
  text = text.replace(/(^|[^\w&\/#\]\)])#([\w\/-]*[A-Za-z_\/-][\w\/-]*)/g, function(m, lead, tag) {
    return lead + keep("<a href=\"tag:" + esc(tag.toLowerCase()) + "\" style=\"color:" + t.cyan + "; background-color:" + t.tagBg
                       + "; font-size:" + t.px(13.125) + "; text-decoration:none;\"> #" + esc(tag) + " </a>")
  })

  text = esc(text).replace(/&lt;br\s*\/?&gt;/gi, "<br>")
  return restore(emphasis(text))
}

function emphasis(text) {
  text = text.replace(/\*\*\*(?=\S)([\s\S]*?\S)\*\*\*/g, "<b><i>$1</i></b>")
  text = text.replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, "<b>$1</b>")
  text = text.replace(/(^|[^\w])__(?=\S)([\s\S]*?\S)__(?!\w)/g, "$1<b>$2</b>")
  text = text.replace(/(^|[^\w*])\*(?=[^\s*])([\s\S]*?[^\s*]|[^\s*])\*(?!\*)/g, "$1<i>$2</i>")
  text = text.replace(/(^|[^\w_])_(?=[^\s_])([\s\S]*?[^\s_]|[^\s_])_(?!\w)/g, "$1<i>$2</i>")
  text = text.replace(/~~(?=\S)([\s\S]*?\S)~~/g, "<s>$1</s>")
  text = text.replace(/==(?=\S)([\s\S]*?\S)==/g, "<span style=\"background-color:\u0003;\">$1</span>")
  return text
}

// Padded with small no-break spaces: thin spaces are whitespace, and the one after
// the space before the span collapsed, leaving the gap on one side only.
function codeSpan(code, t) {
  var pad = "<span style=\"font-size:" + t.px(5) + ";\">&nbsp;</span>"
  return "<span style=\"font-family:'" + t.mono + "'; font-size:" + t.px(13.125) + "; color:" + t.codeColor
    + "; background-color:" + t.codeBg + ";\">" + pad + esc(code).replace(/ /g, "&nbsp;") + pad + "</span>"
}

function footnoteRef(label, t, ctx) {
  if (!ctx.numbers[label]) { ctx.order.push(label); ctx.numbers[label] = ctx.order.length }
  var n = ctx.numbers[label]
  return "<sup><a href=\"footnote:" + n + "\" style=\"color:" + t.link + "; text-decoration:none;\">[" + n + "]</a></sup>"
}

// ---------------------------------------------------------------- embeds

function asset(key, item, t) {
  var info = t.embeds[key]
  if (info === undefined) { item.key = key; t.need(item) }
  return info
}

// A file URL on any platform (C:\x → file:///C:/x).
function fileUrl(path) {
  path = String(path).replace(/\\/g, "/")
  if (path[0] !== "/") path = "/" + path
  return "file://" + encodeURI(path).replace(/#/g, "%23").replace(/\?/g, "%3F")
}

function image(info, size, t) {
  var file = t.print && info.printFile ? info.printFile : info.file
  var width = info.width, height = info.height
  var dims = String(size || "").match(/^(\d+)(?:x(\d+))?$/)
  if (dims) {
    width = Math.min(width, parseInt(dims[1], 10))
    height = dims[2] ? parseInt(dims[2], 10) : Math.round(info.height * width / info.width)
  }
  if (width > t.width) { height = Math.round(height * t.width / width); width = t.width }
  return "<img src=\"" + fileUrl(file) + "\" width=\"" + Math.round(width) + "\" height=\"" + Math.round(height) + "\">"
}

function embed(name, anchor, size, alt, t, ctx) {
  if (/^https?:/.test(name)) {
    var remote = asset(name, { kind: "image", url: name }, t)
    if (remote && remote.width > 0) return "<a href=\"" + esc(name) + "\">" + image(remote, size, t) + "</a>"
    return linkHtml(name, esc(alt || name), t.link, t, true)
  }
  var info = t.embeds[name] || t.embeds[name.split("/").pop()]
  if (info && info.width > 0)
    return "<a href=\"file:" + encodeURIComponent(info.file) + "\">" + image(info, size, t) + "</a>"
  if (info && info.file)
    return linkHtml("file:" + encodeURIComponent(info.file), esc(alt || name), t.link, t)
  if (!/\.md$/i.test(name) && /\.\w{2,4}$/.test(name)) return esc(alt || name)
  // An embedded note: placed as a block after its paragraph.
  return "\u0004" + JSON.stringify({ name: name.replace(/\.md$/i, ""), anchor: anchor }) + "\u0005"
}

// The part of a note an ![[Note#Heading]] or ![[Note#^block]] embed shows.
function section(body, anchor) {
  if (!anchor) return body
  var lines = body.split("\n")
  if (anchor[0] === "^") {
    var id = new RegExp("\\s\\^" + anchor.slice(1).replace(/[^\w-]/g, "") + "\\s*$")
    for (var i = 0; i < lines.length; i++) {
      if (!id.test(lines[i])) continue
      var start = i
      while (start > 0 && lines[start - 1].trim() && !listMarker(lines[i])) start--
      return lines.slice(start, i + 1).join("\n")
    }
    return ""
  }
  var want = anchor.trim().toLowerCase(), from = -1, level = 0
  for (var k = 0; k < lines.length; k++) {
    var m = lines[k].match(HEADING)
    if (!m) continue
    if (from >= 0 && m[1].length <= level) return lines.slice(from, k).join("\n")
    if (from < 0 && (m[2] || "").trim().toLowerCase() === want) { from = k; level = m[1].length }
  }
  return from >= 0 ? lines.slice(from).join("\n") : ""
}

function noteEmbed(spec, t, depth) {
  var info = asset("note:" + spec.name, { kind: "note", name: spec.name }, t)
  if (info === undefined) return ""
  if (!info || info.missing || depth >= 4) {
    return box(" bgcolor=\"" + t.codeBg + "\"", "<td align=\"center\" style=\"padding:" + t.px(8) + ";\"><a href=\"" + noteHref(spec.name)
      + "\" style=\"color:" + t.muted + "; text-decoration:none; font-size:" + t.px(13.125) + ";\">\u201c" + esc(spec.name) + "\u201d is not created yet. Click to create.</a></td>")
  }
  var inner = renderDoc(section(info.body, spec.anchor), t, depth + 1)
  return barred(t.accent, "<p style=\"margin:0; " + lh(t, 22.5) + " font-weight:600;\"><a href=\"" + noteHref(spec.name, spec.anchor)
    + "\" style=\"color:" + t.fg + "; text-decoration:none;\">" + esc(info.title || spec.name) + "</a></p>" + space(4 * t.size / 15) + inner, t)
}

function math(tex, display, t) {
  var info = asset((display ? "$$" : "$") + tex, { kind: "math", tex: tex, display: display }, t)
  if (info && info.width > 0) {
    var img = image(info, "", t)
    return display ? img : img.replace("<img ", "<img style=\"vertical-align:middle\" ")
  }
  return "<span style=\"font-family:'" + t.mono + "'; font-size:" + t.px(13.125) + "; color:" + t.codeColor + ";\">" + esc(tex) + "</span>"
}

// ---------------------------------------------------------------- code

var KEYWORDS = {
  c: "abstract as async await break case catch class const continue debugger default def defer delete do else enum export extends false final finally fn for foreach from func function go if impl implements import in instanceof interface let match mod mut namespace new null nil of package private protected pub public readonly return self static struct super switch this throw throws trait true try type typeof undefined use var void when where while with yield echo elseif endif endforeach require require_once include",
  py: "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield self",
  sh: "if then else elif fi for while until do done case esac in function return local export source exit set unset readonly declare shift trap sudo cd echo",
  sql: "select from where and or not insert into values update set delete create table drop alter add column join left right inner outer full cross on as group by order having limit offset distinct union all null is in like ilike between case when then else end primary key foreign references index default exists asc desc with returning view if begin commit rollback grant",
  css: "important"
}
var LANGS = {
  js: "c", javascript: "c", ts: "c", typescript: "c", jsx: "c", tsx: "c", json: "c", java: "c", c: "c", cpp: "c", "c++": "c", cs: "c", csharp: "c",
  go: "c", rust: "c", rs: "c", php: "c", swift: "c", kotlin: "c", kt: "c", dart: "c", scala: "c", groovy: "c", qml: "c", lua: "c",
  python: "py", py: "py", ruby: "py", rb: "py",
  sh: "sh", bash: "sh", zsh: "sh", shell: "sh", console: "sh", fish: "sh", dockerfile: "sh", docker: "sh", ini: "sh", toml: "sh", conf: "sh", env: "sh",
  sql: "sql", mysql: "sql", postgres: "sql", postgresql: "sql", sqlite: "sql",
  css: "css", scss: "css", less: "css",
  yaml: "yaml", yml: "yaml",
  md: "md", markdown: "md",
  html: "html", xml: "html", svg: "html", vue: "html", blade: "html"
}

function span(color, s, bold) {
  return "<span style=\"color:" + color + ";" + (bold ? " font-weight:600;" : "") + "\">" + s + "</span>"
}

function highlight(code, lang, t) {
  var kind = LANGS[lang]
  if (!kind || t.print) return esc(code)
  var c = { keyword: t.brightMagenta, fn: t.yellow, string: t.green, number: t.magenta, property: t.brightCyan,
            operator: t.red, punct: t.muted, comment: t.faint, important: t.orange }
  if (kind === "md") return highlightMarkdown(code, c)
  if (kind === "yaml") {
    return code.split("\n").map(function(line) {
      var m = line.match(/^(\s*-?\s*)([\w.\-"' ]+?)(:)(\s|$)(.*)$/)
      if (/^\s*#/.test(line)) return span(c.comment, esc(line))
      if (!m) return esc(line)
      return esc(m[1]) + span(c.property, esc(m[2])) + span(c.punct, ":") + m[4] + highlightCode(m[5], "sh", c)
    }).join("\n")
  }
  if (kind === "html") {
    return esc(code).replace(/(&lt;!--[\s\S]*?--&gt;)|(&lt;\/?)([\w:-]+)([^&]*?)(\/?&gt;)/g, function(m, comment, open, tag, attrs, close) {
      if (comment) return span(c.comment, comment)
      attrs = attrs.replace(/([\w:-]+)(=)(&quot;[^&]*?&quot;|'[^']*')?/g, function(a, name, eq, value) {
        return span(c.property, name) + span(c.punct, eq) + (value ? span(c.string, value) : "")
      })
      return span(c.punct, open) + span(c.operator, tag) + attrs + span(c.punct, close)
    })
  }
  return highlightCode(code, kind, c)
}

function highlightCode(code, kind, c) {
  var comment = { c: "//[^\\n]*|/\\*[\\s\\S]*?\\*/", py: "#[^\\n]*", sh: "#[^\\n]*", sql: "--[^\\n]*|/\\*[\\s\\S]*?\\*/", css: "/\\*[\\s\\S]*?\\*/" }[kind]
  var strings = kind === "py" ? "\"\"\"[\\s\\S]*?\"\"\"|'''[\\s\\S]*?'''|" : ""
  var re = new RegExp("(" + comment + ")|(" + strings + "\"(?:\\\\.|[^\"\\\\\\n])*\"|'(?:\\\\.|[^'\\\\\\n])*'|`(?:\\\\.|[^`\\\\])*`)"
    + "|(\\b(?:0x[\\da-fA-F]+|\\d[\\d_]*(?:\\.\\d+)?(?:[eE][+-]?\\d+)?)\\b)|([A-Za-z_$][\\w$-]*)(\\s*\\()?|([{}()\\[\\];,.])|([=+\\-*/%<>!&|^~?:@]+)", "g")
  var words = {}
  KEYWORDS[kind].split(" ").forEach(function(w) { words[w] = true })
  var out = "", last = 0, m
  while ((m = re.exec(code))) {
    out += esc(code.slice(last, m.index))
    last = re.lastIndex
    if (m[1]) out += span(c.comment, esc(m[1]))
    else if (m[2]) {
      var isKey = /^\s*:/.test(code.slice(re.lastIndex)) && kind === "c"
      out += span(isKey ? c.property : c.string, esc(m[2]))
    } else if (m[3]) out += span(c.number, m[3])
    else if (m[4]) {
      var word = m[4]
      if (kind === "sh" && word.indexOf("-") > 0 && !m[5]) word = word.split("-")[0], re.lastIndex = m.index + word.length
      var lower = kind === "sql" ? word.toLowerCase() : word
      if (words[lower]) out += span(c.keyword, esc(word)) + (m[5] && word === m[4] ? span(c.punct, esc(m[5])) : "")
      else if (m[5] && word === m[4]) out += span(c.fn, esc(word)) + span(c.punct, esc(m[5]))
      else if (/^\s*:(?!:)/.test(code.slice(m.index + word.length)) && (kind === "c" || kind === "css")) out += span(c.property, esc(word))
      else out += esc(word)
    } else if (m[6]) out += span(c.punct, esc(m[6]))
    else if (m[7]) out += span(c.operator, esc(m[7]))
  }
  return out + esc(code.slice(last))
}

function highlightMarkdown(code, c) {
  var fenced = false
  var lines = code.split("\n")
  return lines.map(function(line, i) {
    if (/^\s*(```|~~~)/.test(line)) { fenced = !fenced; return span(c.punct, esc(line)) }
    if (fenced || /^( {4}|\t)/.test(line)) return span(c.keyword, esc(line))
    var m
    if ((m = line.match(/^(#{1,6}\s)(.*)$/))) return span(c.punct, esc(m[1])) + span(c.important, esc(m[2]), true)
    if (line.indexOf("|") >= 0 && DELIMITER.test(lines[i + 1] || "") && /-/.test(lines[i + 1])) {
      return line.split("|").map(function(cell) { return span(c.important, esc(cell), true) }).join(span(c.punct, "|"))
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line) || /^[\s|:-]+$/.test(line) && line.indexOf("-") >= 0) return span(c.punct, esc(line))
    var lead = ""
    if ((m = line.match(/^(\s*(?:>\s*)*(?:[-*+]|\d+[.)])?\s*(?:\[.\]\s)?)(.*)$/)) && m[1]) {
      lead = span(c.punct, esc(m[1]))
      line = m[2]
    }
    var stash = []
    function keep(html) { stash.push(html); return "\u0001" + (stash.length - 1) + "\u0002" }
    line = line.replace(/`[^`]*`/g, function(s) { return keep(span(c.keyword, esc(s))) })
    line = line.replace(/(!?)(\[\[[^\]]*\]\]|\[[^\]]*\]\([^)]*\))/g, function(s, bang, link) { return keep((bang ? span(c.operator, "!") : "") + esc(link)) })
    line = line.replace(/(\*\*|__)(?=\S)(.+?)(\1)/g, function(s, a, inner) { return keep(span(c.punct, a) + "<b>" + esc(inner) + "</b>" + span(c.punct, a)) })
    line = line.replace(/\|/g, function() { return keep(span(c.punct, "|")) })
    return lead + esc(line).replace(/\u0001(\d+)\u0002/g, function(s, k) { return stash[+k] })
  }).join("\n")
}

// ---------------------------------------------------------------- render

// Blocks carry no margins; the gaps between them are spacer lines. Qt's
// margins misbehave around tables (a paragraph's never reaches a table
// below it, and a table's background covers its own), and a cell is only
// painted behind its contents, so a spacer is what keeps a bar beside a
// quote unbroken.
function space(px) {
  return px > 0 ? "<p style=\"margin:0; font-size:1px; line-height:" + Math.round(px) + "px;\">&nbsp;</p>" : ""
}

function box(attrs, cells) {
  return "<table width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"margin:0;\"" + (attrs || "") + "><tr>" + cells + "</tr></table>"
}

// A block with a thin bar down its left side. A cell's background only
// shades the paragraphs in it, but a table's fills the table, so the bar is
// the outer table's background showing beside a table that covers the rest.
function barred(color, inner, t) {
  return box(" bgcolor=\"" + color + "\"", "<td width=\"2\"></td><td>" + box(" bgcolor=\"" + t.surface + "\"", "<td style=\"padding-left:" + t.px(22) + ";\">" + inner + "</td>") + "</td>")
}

// Qt won't center a paragraph that holds only an image.
function centered(html) {
  return "<p align=\"center\" style=\"margin:0;\">&nbsp;" + html + "&nbsp;</p>"
}

function lh(t, px) { return "line-height:" + t.px(px) + ";" }

function pOpen(t) { return "<p style=\"margin:0; " + lh(t, 22.5) + "\">" }

// The space Obsidian leaves above and below each kind of block.
function spacing(b, t, prev) {
  var unit = t.size / 15
  if (b.type === "heading") return { top: !prev || prev.type === "heading" ? t.gap : Math.round(37.5 * unit), bottom: t.gap }
  if (b.type === "hr") return { top: Math.round(30 * unit), bottom: Math.round(30 * unit) }
  return { top: t.gap, bottom: t.gap }
}

function blocks(list, t, ctx, trailing, inItem) {
  var out = "", below = 0
  list.forEach(function(b, k) {
    var gap = spacing(b, t, list[k - 1])
    // A list nested in a list item sits right under the item's text.
    if (inItem && b.type === "list" && list[k - 1].type === "para") gap.top = below = 0
    if (k > 0) out += space(Math.max(below, gap.top))
    below = gap.bottom
    out += block(b, t, ctx)
  })
  return out + (trailing && list.length ? space(below) : "")
}

function block(b, t, ctx) {
  if (b.type === "para") return para(b.lines, t, ctx)
  if (b.type === "heading") return heading(b, t, ctx)
  if (b.type === "code") return codeBlock(b.text, b.lang, t)
  if (b.type === "mermaid") return diagram(b, t)
  if (b.type === "math") return centered(math(b.tex, true, t))
  if (b.type === "hr") return "<hr style=\"margin:0; color:" + t.border + "; background-color:" + t.border + ";\">"
  if (b.type === "table") return table(b, t, ctx)
  if (b.type === "quote") return barred(t.accent, blocks(b.children, t, ctx, false), t)
  if (b.type === "callout") return callout(b, t, ctx)
  if (b.type === "list") return listHtml(b, t, ctx)
  return ""
}

function para(lines, t, ctx) {
  var html = lines.map(function(l) { return inline(l.replace(/\s+\^[A-Za-z0-9-]+\s*$/, "").replace(/ {2,}$/, ""), t, ctx) }).join("<br>")
  // Embedded notes break out of the paragraph.
  var parts = html.split(/\u0004([^\u0005]*)\u0005/)
  var chunks = []
  for (var i = 0; i < parts.length; i++) {
    if (i % 2) { chunks.push(noteEmbed(JSON.parse(parts[i]), t, ctx.depth)); continue }
    var text = parts[i].replace(/^(<br>)+|(<br>)+$/g, "")
    if (text.replace(/<br>/g, "").trim()) chunks.push(pOpen(t) + text + "</p>")
  }
  return chunks.filter(function(c) { return c }).join(space(t.gap))
}

function heading(b, t, ctx) {
  var sizes = [1.618, 1.462, 1.318, 1.188, 1.076, 1], weights = [700, 700, 700, 700, 700, 600], heights = [1.2, 1.2, 1.3, 1.4, 1.5, 1.5]
  var colors = [t.red, t.green, t.yellow, t.blue, t.magenta, t.magenta]
  var i = b.level - 1
  return "<p style=\"margin:0; " + lh(t, 15 * sizes[i] * heights[i]) + " font-size:" + t.px(15 * sizes[i])
    + "; font-weight:" + weights[i] + "; color:" + colors[i] + ";\">" + inline(b.text, t, ctx) + "</p>"
}

function codeBlock(text, lang, t) {
  return box(" bgcolor=\"" + t.codeBg + "\"", "<td style=\"padding:" + t.px(12) + " " + t.px(16) + ";\"><p style=\"margin:0; white-space:pre-wrap; "
    + lh(t, 19.6875) + " font-family:'" + t.mono + "'; font-size:" + t.px(13.125) + "; color:" + t.codeColor + ";\">" + highlight(text, lang, t) + "</p></td>")
}

function diagram(b, t) {
  var info = asset("mermaid:" + b.text, { kind: "mermaid", src: b.text }, t)
  if (info && info.width > 0) return centered(image(info, "", t))
  return codeBlock(b.text, "", t)
}

function table(b, t, ctx) {
  var html = "<table cellspacing=\"0\" cellpadding=\"0\" border=\"1\" bordercolor=\"" + t.border + "\" style=\"border-collapse:collapse; margin:0;\">"
  function cell(text, k, head) {
    return "<td align=\"" + (b.align[k] || "left") + "\" style=\"padding:" + t.px(4) + " " + t.px(8) + ";\"><p style=\"margin:0; " + lh(t, 19.5)
      + (head ? " font-weight:600;" : "") + "\">" + inline(text || "", t, ctx) + "</p></td>"
  }
  html += "<tr>" + b.head.map(function(c, k) { return cell(c, k, true) }).join("") + "</tr>"
  b.rows.forEach(function(row) {
    var cells = []
    for (var k = 0; k < b.head.length; k++) cells.push(cell(row[k], k, false))
    html += "<tr>" + cells.join("") + "</tr>"
  })
  return html + "</table>"
}

function callout(b, t, ctx) {
  var kind = CALLOUT_ALIASES[b.kind] || b.kind
  var style = CALLOUTS[kind] || CALLOUTS.note
  var color = style[0] === "muted" ? t.muted : t[style[0]]
  var fill = t.print ? "#f3f3f5" : mix(parseHex(color), parseHex(t.bg), 0.1)
  var open = t.folds[b.n] !== undefined ? t.folds[b.n] : b.fold !== "-"
  var title = b.title ? inline(b.title, t, ctx) : esc(b.kind.charAt(0).toUpperCase() + b.kind.slice(1))
  var icon = "<span style=\"font-family:'" + t.icon + "';\">" + String.fromCodePoint(style[1]) + "</span>&nbsp;&nbsp;"
  var fold = b.fold ? "&nbsp;&nbsp;<a href=\"fold:" + b.n + "\" style=\"color:" + color + "; text-decoration:none; font-family:'" + t.icon + "';\">"
    + String.fromCodePoint(open ? 0xf0140 : 0xf0142) + "</a>" : ""
  var head = "<p style=\"margin:0; " + lh(t, 19.5) + " font-weight:600; color:" + color + ";\">"
    + (b.fold ? "<a href=\"fold:" + b.n + "\" style=\"color:" + color + "; text-decoration:none;\">" + icon + "</a>" : icon) + title + fold + "</p>"
  var inner = Object.create(t)
  inner.surface = fill
  var body = open && b.children.length ? space(t.gap) + blocks(b.children, inner, ctx, true) : ""
  return box(" bgcolor=\"" + fill + "\"", "<td style=\"padding:" + t.px(12) + " " + t.px(12) + " " + t.px(12) + " " + t.px(24) + ";\">" + head + body + "</td>")
}

function listHtml(b, t, ctx) {
  var markerWidth = Math.round(25 * t.size / 15)
  var pad = Math.round(1.125 * t.size / 15)
  var rows = []
  b.items.forEach(function(item, k) {
    var marker
    var done = item.task !== null && item.task !== " "
    if (item.task !== null) {
      marker = "<a href=\"task:" + item.n + "\" style=\"color:" + (done ? t.accent : t.faint) + "; text-decoration:none; font-family:'" + t.icon + "';\">"
        + String.fromCodePoint(done ? 0xf0135 : 0xf0131) + "</a>"
    } else if (b.ordered) marker = "<span style=\"color:" + t.faint + ";\">" + (b.start + k) + ".</span>"
    else marker = "<span style=\"color:" + t.faint + "; font-size:" + t.px(11) + ";\">●</span>"
    // A blank line before the next item leaves a gap, as in Obsidian.
    var inner = blocks(item.children, t, ctx, item.loose && k < b.items.length - 1, true) || pOpen(t) + "&nbsp;</p>"
    if (done) inner = "<span style=\"color:" + t.muted + ";\"><s>" + inner + "</s></span>"
    rows.push("<td width=\"" + markerWidth + "\" align=\"right\" valign=\"top\" style=\"padding-top:" + pad + "px; padding-bottom:" + pad + "px; padding-right:" + Math.round(7 * t.size / 15) + "px;\">"
      + pOpen(t) + marker + "</p></td><td width=\"100%\" valign=\"top\" style=\"padding-top:" + pad + "px; padding-bottom:" + pad + "px;\">" + inner + "</td>")
  })
  return box("", rows.join("</tr><tr>"))
}

function footnotes(t, ctx) {
  if (!ctx.order.length) return ""
  var unit = t.size / 15
  var rows = "", i = 0
  // Footnotes may cite more footnotes, so the list can grow while it renders.
  while (i < ctx.order.length) {
    var label = ctx.order[i++]
    var inner = blocks(ctx.footnotes[label], t, ctx, false)
    var back = " <a href=\"footnote-ref:" + i + "\" style=\"color:" + t.faint + "; text-decoration:none;\">↩︎</a>"
    inner = inner.replace(/<\/p>(?![\s\S]*<\/p>)/, back + "</p>")
    rows += "<tr><td width=\"" + Math.round(22 * unit) + "\" align=\"right\" valign=\"top\" style=\"padding-right:" + Math.round(4 * unit) + "px;\">"
      + "<p style=\"margin:0; " + lh(t, 19.6875) + " color:" + t.faint + ";\">" + i + ".</p></td><td valign=\"top\">" + inner + "</td></tr>"
  }
  return space(30 * unit) + "<hr style=\"margin:0; color:" + t.border + "; background-color:" + t.border + ";\">" + space(30 * unit)
    + "<table cellspacing=\"0\" cellpadding=\"0\" style=\"margin:0; font-size:" + t.px(13.125) + ";\">" + rows + "</table>"
}

function renderDoc(src, t, depth) {
  var ctx = parse(src)
  ctx.depth = depth
  var html = blocks(ctx.blocks, t, ctx, false)
  html += footnotes(t, ctx)
  return html.replace(/\u0003/g, t.highlightBg)
}

function render(src, theme) {
  var t = styles(theme)
  return "<div style=\"color:" + t.fg + "; font-family:'" + t.sans + "'; font-size:" + t.size + "px;\">" + renderDoc(src, t, 0) + "</div>"
}

// Toggle the task box on a body line.
function toggleTask(body, lineIndex) {
  var lines = body.split("\n")
  var line = lines[lineIndex]
  if (line === undefined) return body
  lines[lineIndex] = line.replace(/^(\s*(?:>\s*)*(?:[-*+]|\d+[.)])\s+\[)(.)(\])/, function(m, a, mark, b) {
    return a + (mark === " " ? "x" : " ") + b
  })
  return lines.join("\n")
}

// Markdown source tinted for the editor: same characters, only colors, so
// the text lays out exactly as the TextEdit above it does.
function tint(src, theme) {
  var accent = hex(theme.accent), dim = mix(theme.fg, theme.bg, 0.45), fg = hex(theme.fg)
  function color(c, s) { return "<span style=\"color:" + c + ";\">" + s + "</span>" }
  var fenced = false
  return "<div style=\"white-space:pre-wrap; color:" + fg + ";\">" + src.split("\n").map(function(line) {
    if (/^\s*(```|~~~)/.test(line)) { fenced = !fenced; return color(dim, esc(line)) }
    if (fenced) return color(dim, esc(line))
    var m = line.match(/^(#{1,6}\s)(.*)$/)
    if (m) return color(accent, esc(m[1])) + color(fg, esc(m[2]))
    var lead = ""
    if ((m = line.match(/^(\s*(?:[-*+]|\d+[.)])\s+(?:\[.\]\s+)?|\s*>\s?)(.*)$/))) {
      lead = color(accent, esc(m[1]))
      line = m[2]
    }
    var stash = []
    function keep(html) { stash.push(html); return "\u0001" + (stash.length - 1) + "\u0002" }
    line = line.replace(/`[^`]*`/g, function(s) { return keep(color(dim, esc(s))) })
    line = line.replace(/%%.*?(%%|$)/g, function(s) { return keep(color(dim, esc(s))) })
    line = line.replace(/!?\[\[[^\]]*\]\]|!?\[[^\]]*\]\([^)]*\)|https?:\/\/\S+/g, function(s) { return keep(color(accent, esc(s))) })
    line = line.replace(/(^|[^\w&\/#])(#[A-Za-z][\w\/-]*)/g, function(s, a, tag) { return a + keep(color(accent, esc(tag))) })
    line = line.replace(/\*\*|__|~~|==/g, function(s) { return keep(color(dim, s)) })
    line = esc(line).replace(/\u0001(\d+)\u0002/g, function(s, k) { return stash[+k] })
    return lead + line
  }).join("<br>") + "</div>"
}
