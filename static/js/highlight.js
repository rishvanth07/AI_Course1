window.LuminaHighlight = (() => {
  const words = (text) => new Set(text.split(" "));
  const rules = {
    python: {
      keywords: words(
        "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield",
      ),
      builtins: words(
        "abs all any bool dict enumerate filter float format input int isinstance len list map max min open print range repr reversed round set sorted str sum tuple type zip",
      ),
      comment: /#[^\n]*/y,
      strings: /(?:"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|[rbfu]{0,2}"(?:\\.|[^"\\\n])*"?|[rbfu]{0,2}'(?:\\.|[^'\\\n])*'?)/iy,
      caseless: false,
    },
    javascript: {
      keywords: words(
        "async await break case catch class const continue default delete do else export extends false finally for function if import in instanceof let new null of return static super switch this throw true try typeof undefined var void while yield",
      ),
      builtins: words("Array Boolean console Date Error JSON Map Math Number Object parseFloat parseInt Promise Set String"),
      comment: /\/\/[^\n]*|\/\*[\s\S]*?(?:\*\/|$)/y,
      strings: /(?:"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?|`(?:\\.|[^`\\])*`?)/y,
      caseless: false,
    },
    sql: {
      keywords: words(
        "ALL AND AS ASC BETWEEN BY CASE CREATE DELETE DESC DISTINCT ELSE END EXISTS FROM FULL GROUP HAVING IN INNER INSERT INTO IS JOIN KEY LEFT LIKE LIMIT NOT NULL OFFSET ON OR ORDER OUTER PRIMARY RIGHT SELECT SET TABLE THEN UNION UPDATE VALUES WHEN WHERE WITH",
      ),
      builtins: words("AVG COALESCE COUNT IFNULL INTEGER LENGTH LOWER MAX MIN REAL ROUND SUBSTR SUM TEXT UPPER"),
      comment: /--[^\n]*/y,
      strings: /(?:'(?:''|[^'])*'?|"(?:""|[^"])*"?)/y,
      caseless: true,
    },
  };
  const number = /(?:0x[\da-f]+|\d+(?:\.\d+)?(?:e[+-]?\d+)?)/iy;
  const word = /[A-Za-z_$][\w$]*/y;

  const escape = (text) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  function match(pattern, text, at) {
    pattern.lastIndex = at;
    const found = pattern.exec(text);
    return found && found[0] ? found[0] : "";
  }

  function html(text, language) {
    const rule = rules[language];
    if (!rule) return escape(text);
    let out = "";
    let plain = "";
    let at = 0;
    const flush = () => {
      out += escape(plain);
      plain = "";
    };
    const wrap = (kind, value) => {
      flush();
      out += `<span class="tk-${kind}">${escape(value)}</span>`;
    };
    while (at < text.length) {
      const comment = match(rule.comment, text, at);
      if (comment) {
        wrap("comment", comment);
        at += comment.length;
        continue;
      }
      const string = match(rule.strings, text, at);
      if (string && /["'`]/.test(string)) {
        wrap("string", string);
        at += string.length;
        continue;
      }
      const previous = text[at - 1] || "";
      if (!/[\w$]/.test(previous)) {
        const digits = match(number, text, at);
        if (digits) {
          wrap("number", digits);
          at += digits.length;
          continue;
        }
        const name = match(word, text, at);
        if (name) {
          const key = rule.caseless ? name.toUpperCase() : name;
          if (rule.keywords.has(key)) wrap("keyword", name);
          else if (rule.builtins.has(key)) wrap("builtin", name);
          else if (text[at + name.length] === "(") wrap("call", name);
          else plain += name;
          at += name.length;
          continue;
        }
      }
      plain += text[at];
      at += 1;
    }
    flush();
    return out;
  }

  return { html };
})();
