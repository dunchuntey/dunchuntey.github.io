// The skeleton tool: runs the Python program in the browser (Pyodide) and
// shows its results. The Python files are in /assets/py/.
(function () {
  "use strict";

  var PYODIDE_HOME = "/home/pyodide/";
  var PY_FILES = ["skeletons_rehash.py", "inversions.py", "web_api.py"];
  var OPTIONAL_FILES = ["tonal_inversion_2_0.py"]; // used when it is on the site
  var FIELD_IDS = ["fret", "grouping", "length", "string", "interval"];

  var app = document.getElementById("skeletons-app");
  var api = null; // the Python bridge (web_api.py)
  var kinds = [];
  var current = null; // {state, mode} of the skeleton on show

  function $(id) {
    return document.getElementById(id);
  }

  function clear(element) {
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  function make(tag, text, className) {
    var element = document.createElement(tag);
    if (text !== undefined) {
      element.textContent = text;
    }
    if (className) {
      element.className = className;
    }
    return element;
  }

  function setStatus(message, isError) {
    $("sk-status").textContent = message;
    $("sk-status").className = isError ? "sk-error" : "";
    $("sk-status").hidden = !message;
  }

  function setMessage(message) {
    $("sk-message").textContent = message || "";
    $("sk-message").hidden = !message;
  }

  // ---- Python ---------------------------------------------------------------

  async function loadPython() {
    setStatus("Loading Python (about 10 MB the first time, then it is cached)...");
    var pyodide = await loadPyodide();
    var base = app.dataset.py;
    for (var name of PY_FILES) {
      var response = await fetch(base + name);
      if (!response.ok) {
        throw new Error("Could not load " + name);
      }
      pyodide.FS.writeFile(PYODIDE_HOME + name, await response.text());
    }
    for (var optional of OPTIONAL_FILES) {
      var extra = await fetch(base + optional);
      if (extra.ok) {
        pyodide.FS.writeFile(PYODIDE_HOME + optional, await extra.text());
      }
    }
    pyodide.runPython(
      "import sys\nsys.path.insert(0, '" + PYODIDE_HOME + "')\nimport web_api"
    );
    return pyodide.pyimport("web_api");
  }

  function call(name, payload) {
    return JSON.parse(api[name](JSON.stringify(payload)));
  }

  // ---- Controls -------------------------------------------------------------

  function fill(select, options) {
    options.forEach(function (option) {
      var element = make("option", option[1]);
      element.value = option[0];
      select.appendChild(element);
    });
  }

  function selectedKind() {
    var id = $("sk-kind").value;
    return kinds.filter(function (kind) {
      return kind.id === id;
    })[0];
  }

  function updateFields() {
    var kind = selectedKind();
    $("sk-description").textContent = kind.description;
    FIELD_IDS.forEach(function (id) {
      $("sk-row-" + id).hidden = kind.fields.indexOf(id) === -1;
    });
    $("sk-length-hint").textContent = kind.length_hint
      ? "(" + kind.length_hint + ")"
      : "";
  }

  function buildControls() {
    var frets = [["", "random"]];
    for (var fret = 0; fret <= 17; fret++) {
      frets.push([String(fret), String(fret)]);
    }
    fill($("sk-fret"), frets);
    fill($("sk-grouping"), [["", "random"], ["1", "1"], ["2", "2"], ["3", "3"]]);
    fill($("sk-string"), [
      ["", "random"], ["E", "E (low)"], ["A", "A"], ["D", "D"],
      ["g", "g"], ["b", "b"], ["e", "e (high)"],
    ]);
    fill($("sk-shflat"), [["#", "sharps"], ["b", "flats"]]);
    fill(
      $("sk-kind"),
      kinds.map(function (kind) {
        return [kind.id, kind.id.charAt(0).toUpperCase() + kind.id.slice(1)];
      })
    );
    $("sk-kind").addEventListener("change", updateFields);
    $("sk-generate").addEventListener("click", generate);
    updateFields();
    $("sk-controls").hidden = false;
  }

  function readParams() {
    return {
      kind: $("sk-kind").value,
      fret: $("sk-fret").value,
      grouping: $("sk-grouping").value,
      length: $("sk-length").value.trim(),
      string: $("sk-string").value,
      interval: $("sk-interval").value.trim(),
      shflat: $("sk-shflat").value,
    };
  }

  // ---- Showing a skeleton ---------------------------------------------------

  function generate() {
    setMessage("");
    var result = call("generate", readParams());
    if (result.error) {
      setMessage(result.error);
      return;
    }
    render(result);
  }

  function render(result) {
    current = { state: result.state, mode: result.mode };
    $("sk-output").hidden = false;
    $("sk-tab").textContent = result.text;
    renderModes(result.modes);
    $("sk-triads-simple").hidden = !result.triads;
    $("sk-triads-full").hidden = !result.triads;
    $("sk-compare").hidden = !result.compare;
    clear($("sk-triad-list"));
    $("sk-triad-text").textContent = "";
    $("sk-extra").textContent = "";
    $("sk-extra").hidden = true;
  }

  function renderModes(modes) {
    var box = $("sk-modes");
    clear(box);
    box.hidden = modes.length === 0;
    if (modes.length === 0) {
      return;
    }
    box.appendChild(make("span", "Modes: "));
    modes.forEach(function (mode) {
      var button = make("button", mode.roman, mode.n === current.mode ? "sk-on" : "");
      button.type = "button";
      button.title = mode.pattern;
      button.addEventListener("click", function () {
        var result = call("show", { state: current.state, mode: mode.n });
        if (result.error) {
          setMessage(result.error);
        } else {
          setMessage("");
          render(result);
        }
      });
      box.appendChild(button);
    });
  }

  
  function showTriads(adjacent) {
    var triads = call("triads", {
      state: current.state,
      mode: current.mode,
      adjacent: adjacent,
    });
    $("sk-extra").textContent = "";
    $("sk-extra").hidden = true;
    var list = $("sk-triad-list");
    clear(list);
    $("sk-triad-text").textContent = "";
    if (triads.length === 0) {
      list.appendChild(make("p", "No playable triad in this skeleton with that display."));
      return;
    }
    triads.forEach(function (triad) {
      var button = make("button", triad.name);
      button.type = "button";
      button.addEventListener("click", function () {
        $("sk-triad-text").textContent = triad.text;
      });
      list.appendChild(button);
    });
  }

  function showCompare() {
    var result = call("compare", { state: current.state, mode: current.mode });
    clear($("sk-triad-list"));
    $("sk-triad-text").textContent = "";
    $("sk-extra").textContent = result.text;
    $("sk-extra").hidden = false;
  }

  // ---- Start ----------------------------------------------------------------

  async function start() {
    try {
      api = await loadPython();
      kinds = JSON.parse(api.kinds_info());
      buildControls();
      $("sk-triads-simple").addEventListener("click", function () {
        showTriads(true);
      });
      $("sk-triads-full").addEventListener("click", function () {
        showTriads(false);
      });
      $("sk-compare").addEventListener("click", showCompare);
      setStatus("");
    } catch (error) {
      setStatus("The tool could not start: " + error.message, true);
    }
  }

  start();
})();
