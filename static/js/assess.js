const root = document.querySelector("#assessment");
const intro = document.querySelector("#intro");
const exam = document.querySelector("#exam");

if (root && exam) {
  const limit = Number(root.dataset.limit) || 3;
  const count = Number(root.dataset.count) || 0;
  let remaining = Number(root.dataset.seconds) || 60;

  const startButton = document.querySelector("#start");
  const fsNote = document.querySelector("#fs-note");
  const questions = [...exam.querySelectorAll("[data-question]")];
  const dots = [...exam.querySelectorAll("[data-goto]")];
  const prev = document.querySelector("#prev");
  const next = document.querySelector("#next");
  const submit = document.querySelector("#submit-exam");
  const answered = document.querySelector("#answered");
  const progressBar = document.querySelector("#progress-bar");
  const timer = document.querySelector("#timer");
  const warnCount = document.querySelector("#warn-count strong");
  const violationsField = document.querySelector("#violations");
  const flagsField = document.querySelector("#flags");
  const endedField = document.querySelector("#ended");
  const warnModal = document.querySelector("#warn-modal");
  const warnTitle = document.querySelector("#warn-title");
  const warnText = document.querySelector("#warn-text");
  const resume = document.querySelector("#resume");
  const confirmModal = document.querySelector("#confirm-modal");
  const confirmText = document.querySelector("#confirm-text");
  const sending = document.querySelector("#sending");
  const sendingText = document.querySelector("#sending-text");

  const camCheck = document.querySelector("#cam-check");
  const camEnable = document.querySelector("#cam-enable");
  const camStatus = document.querySelector("#cam-status");
  const camPreview = document.querySelector("#cam-preview");
  const camLive = document.querySelector("#cam-live");
  const camCaption = document.querySelector("#cam-caption");
  const camPill = document.querySelector("#cam-pill");

  const prep = document.querySelector("#prep");
  const prepText = document.querySelector("#prep-text");
  const prepRetry = document.querySelector("#prep-retry");

  let current = 0;
  let running = false;
  let submitting = false;
  let away = false;
  let violations = 0;
  const flags = [];
  let clock = null;
  let deadline = 0;
  let usesFullscreen = false;
  let stream = null;
  let bankReady = !root.dataset.prepare;
  let watcher = null;
  let checking = false;
  let darkFor = 0;
  let noFaceFor = 0;
  let crowdFor = 0;

  const canFullscreen = Boolean(document.documentElement.requestFullscreen);
  const faceDetector = "FaceDetector" in window ? new window.FaceDetector({ fastMode: true, maxDetectedFaces: 3 }) : null;
  const probe = document.createElement("canvas");
  probe.width = 32;
  probe.height = 24;
  const probeContext = probe.getContext("2d", { willReadFrequently: true });

  const notices = {
    tab: ["You switched away", "Switching tabs or windows is recorded."],
    fullscreen: ["You left full screen", "Leaving full screen is recorded."],
    "camera-off": ["Your camera turned off", "The camera must stay on for the whole assessment."],
    "camera-covered": ["Your camera is covered", "The camera view is dark or blocked. Make sure your face is visible."],
    "no-face": ["We can't see you", "Stay in front of the camera for the whole assessment."],
    faces: ["More than one person in view", "Only you should be in front of the camera."],
  };

  const isFullscreen = () => Boolean(document.fullscreenElement);
  const cameraLive = () => {
    const track = stream && stream.getVideoTracks()[0];
    return Boolean(track && track.readyState === "live");
  };

  function updateStart() {
    startButton.disabled = !(bankReady && cameraLive());
  }

  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function prepareQuestions() {
    prep.classList.remove("is-failed");
    prepRetry.hidden = true;
    let failures = 0;
    let saved = 0;
    let total = 0;
    while (true) {
      let data = {};
      try {
        const response = await fetch(root.dataset.prepare, { method: "POST" });
        data = await response.json().catch(() => ({}));
        if (response.ok && data.ok) {
          if (data.ready) {
            window.location.reload();
            return;
          }
          failures = 0;
          saved = data.count;
          total = data.total;
          prepText.textContent = `Preparing ${total} questions for this lesson (${saved} ready)…`;
          continue;
        }
        throw new Error(data.error || "The question set could not be prepared.");
      } catch (error) {
        if (typeof data.count === "number") {
          saved = data.count;
          total = data.total;
        }
        failures += 1;
        if (failures < 3) {
          prepText.textContent = `Gemini is busy. Retrying in a few seconds${total ? ` (${saved} of ${total} ready)` : ""}…`;
          await pause(4000 * failures);
          continue;
        }
        const kept = saved ? ` ${saved} of ${total} questions are saved; trying again continues from there.` : "";
        prep.classList.add("is-failed");
        prepText.textContent = `${error.message.replace(/ Try again\.?$/, "")}${kept}`;
        prepRetry.hidden = false;
        return;
      }
    }
  }

  async function openCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw Object.assign(new Error("unsupported"), { name: "NotSupportedError" });
    }
    const media = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
      audio: false,
    });
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = media;
    camPreview.srcObject = stream;
    camLive.srcObject = stream;
    await camPreview.play().catch(() => {});
    camLive.play().catch(() => {});
    stream.getVideoTracks()[0].addEventListener("ended", () => {
      setCameraState("off");
      warn("camera-off");
    });
    setCameraState("on");
  }

  function cameraError(error) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") {
      return "Camera access was blocked. Allow the camera for this site in your browser settings, then try again.";
    }
    if (error.name === "NotFoundError" || error.name === "OverconstrainedError") {
      return "No camera was found. Connect a camera, then try again.";
    }
    if (error.name === "NotReadableError") {
      return "The camera is being used by another app. Close it, then try again.";
    }
    if (error.name === "NotSupportedError") {
      return "This browser can't share a camera. Open the assessment in a current version of Chrome, Edge, Safari, or Firefox.";
    }
    return "The camera could not be started. Try again.";
  }

  function setCameraState(state) {
    const on = state === "on";
    camCheck.classList.toggle("is-on", on);
    camPill.classList.toggle("is-off", !on);
    camCaption.textContent = on ? "Camera on" : "Camera off";
    camCaption.parentElement.classList.toggle("is-off", !on);
  }

  camEnable.addEventListener("click", async () => {
    camEnable.disabled = true;
    camStatus.textContent = "Waiting for camera permission…";
    try {
      await openCamera();
      camStatus.textContent = faceDetector
        ? "Camera is on. Keep your face centred and well lit during the assessment."
        : "Camera is on. Keep your face centred and well lit, and don't cover the camera.";
      camEnable.hidden = true;
    } catch (error) {
      camStatus.textContent = cameraError(error);
      camEnable.textContent = "Try again";
      camEnable.disabled = false;
    }
    updateStart();
  });

  if (prep) {
    camEnable.disabled = true;
    prepRetry.addEventListener("click", () => {
      bankReady = false;
      updateStart();
      prepareQuestions();
    });
    prepareQuestions().finally(() => {
      if (!stream) camEnable.disabled = false;
    });
  }

  async function enterFullscreen() {
    if (!canFullscreen || isFullscreen()) return isFullscreen();
    try {
      await document.documentElement.requestFullscreen({ navigationUI: "hide" });
      return true;
    } catch {
      return false;
    }
  }

  function isAnswered(field) {
    if (field.dataset.type === "fill") return field.querySelector("input").value.trim() !== "";
    if (field.dataset.type === "match") return [...field.querySelectorAll("select")].some((item) => item.value !== "");
    if (field.dataset.type === "code") {
      const box = field.querySelector("textarea");
      return box.value.trim() !== "" && box.value.trim() !== box.dataset.starter.trim();
    }
    return Boolean(field.querySelector("input:checked"));
  }

  function answeredCount() {
    return questions.filter(isAnswered).length;
  }

  function refresh() {
    questions.forEach((field, index) => {
      field.hidden = index !== current;
    });
    dots.forEach((dot, index) => {
      dot.classList.toggle("is-current", index === current);
      dot.classList.toggle("is-done", isAnswered(questions[index]));
      if (index === current) dot.setAttribute("aria-current", "step");
      else dot.removeAttribute("aria-current");
    });
    const done = answeredCount();
    answered.textContent = `${done} of ${count} answered`;
    progressBar.style.width = `${count ? ((current + 1) / count) * 100 : 0}%`;
    prev.disabled = current === 0;
    next.textContent = current === count - 1 ? "Review and submit" : "Next";
  }

  function go(index) {
    current = Math.max(0, Math.min(count - 1, index));
    refresh();
    const field = questions[current];
    const first = field.querySelector("input:checked") || field.querySelector("input, select, textarea");
    if (first) first.focus({ preventScroll: true });
  }

  function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  }

  function tick() {
    remaining = Math.ceil((deadline - Date.now()) / 1000);
    timer.textContent = formatTime(Math.max(0, remaining));
    timer.classList.toggle("is-low", remaining <= 60);
    if (remaining <= 0) finish("time", "Time is up. Submitting your answers…");
  }

  function stopCamera() {
    clearInterval(watcher);
    if (stream) stream.getTracks().forEach((track) => track.stop());
  }

  function finish(reason, message) {
    if (submitting) return;
    submitting = true;
    running = false;
    clearInterval(clock);
    stopCamera();
    endedField.value = reason;
    violationsField.value = String(violations);
    flagsField.value = flags.join(",");
    warnModal.hidden = true;
    confirmModal.hidden = true;
    sendingText.textContent = message;
    sending.hidden = false;
    submit.disabled = true;
    HTMLFormElement.prototype.submit.call(exam);
  }

  function warn(kind) {
    if (!running || submitting || away) return;
    away = true;
    violations += 1;
    flags.push(kind);
    violationsField.value = String(violations);
    flagsField.value = flags.join(",");
    warnCount.textContent = String(violations);
    warnCount.parentElement.classList.add("is-warned");
    if (violations >= limit) {
      finish("warnings", `You reached ${limit} warnings. Submitting your answers…`);
      return;
    }
    const [title, detail] = notices[kind] || notices.tab;
    warnTitle.textContent = title;
    const left = limit - violations;
    warnText.textContent =
      `${detail} This is warning ${violations} of ${limit}. ` +
      `${left} more and your answers will be submitted automatically.`;
    if (!cameraLive()) resume.textContent = "Turn camera back on";
    else resume.textContent = usesFullscreen ? "Return to full screen" : "Return to assessment";
    warnModal.hidden = false;
    resume.focus();
  }

  function brightness() {
    probeContext.drawImage(camLive, 0, 0, probe.width, probe.height);
    const pixels = probeContext.getImageData(0, 0, probe.width, probe.height).data;
    let total = 0;
    for (let index = 0; index < pixels.length; index += 4) {
      total += 0.299 * pixels[index] + 0.587 * pixels[index + 1] + 0.114 * pixels[index + 2];
    }
    return total / (pixels.length / 4);
  }

  async function watchCamera() {
    if (!running || submitting || away || checking) return;
    if (!cameraLive()) {
      setCameraState("off");
      warn("camera-off");
      return;
    }
    if (camLive.readyState < 2) {
      camLive.play().catch(() => {});
      return;
    }
    darkFor = brightness() < 18 ? darkFor + 1 : 0;
    if (darkFor >= 3) {
      darkFor = 0;
      warn("camera-covered");
      return;
    }
    if (!faceDetector) return;
    checking = true;
    try {
      const faces = await faceDetector.detect(camLive);
      noFaceFor = faces.length === 0 ? noFaceFor + 1 : 0;
      crowdFor = faces.length > 1 ? crowdFor + 1 : 0;
    } catch {
      noFaceFor = 0;
      crowdFor = 0;
    } finally {
      checking = false;
    }
    if (noFaceFor >= 4) {
      noFaceFor = 0;
      warn("no-face");
    } else if (crowdFor >= 2) {
      crowdFor = 0;
      warn("faces");
    }
  }

  startButton.addEventListener("click", async () => {
    if (!cameraLive()) {
      updateStart();
      return;
    }
    usesFullscreen = await enterFullscreen();
    if (!usesFullscreen) fsNote.hidden = false;
    intro.hidden = true;
    exam.hidden = false;
    document.querySelectorAll("[data-exam-only]").forEach((item) => {
      item.hidden = false;
    });
    document.body.classList.add("is-running");
    running = true;
    deadline = Date.now() + remaining * 1000;
    timer.textContent = formatTime(remaining);
    clock = setInterval(tick, 250);
    watcher = setInterval(watchCamera, 1000);
    camLive.play().catch(() => {});
    go(0);
  });

  exam.addEventListener("change", refresh);
  prev.addEventListener("click", () => go(current - 1));
  next.addEventListener("click", () => {
    if (current === count - 1) {
      openConfirm();
      return;
    }
    go(current + 1);
  });
  dots.forEach((dot, index) => dot.addEventListener("click", () => go(index)));

  function openConfirm() {
    const left = count - answeredCount();
    confirmText.textContent = left
      ? `${left} question${left === 1 ? " is" : "s are"} unanswered and will be marked incorrect. You can't change answers after submitting.`
      : "All questions are answered. You can't change answers after submitting.";
    confirmModal.hidden = false;
    document.querySelector("#confirm-submit").focus();
  }

  submit.addEventListener("click", openConfirm);
  document.querySelector("#cancel-submit").addEventListener("click", () => {
    confirmModal.hidden = true;
    submit.focus();
  });
  document.querySelector("#confirm-submit").addEventListener("click", () => {
    finish("submitted", "Submitting your answers…");
  });

  resume.addEventListener("click", async () => {
    if (!cameraLive()) {
      resume.disabled = true;
      try {
        await openCamera();
      } catch (error) {
        warnText.textContent = cameraError(error);
        resume.disabled = false;
        return;
      }
      resume.disabled = false;
    }
    if (usesFullscreen) await enterFullscreen();
    warnModal.hidden = true;
    darkFor = 0;
    noFaceFor = 0;
    crowdFor = 0;
    away = false;
    go(current);
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") warn("tab");
  });
  window.addEventListener("blur", () => warn("tab"));
  document.addEventListener("fullscreenchange", () => {
    if (!isFullscreen()) warn("fullscreen");
  });

  exam.addEventListener("input", refresh);
  exam.addEventListener("submit", (event) => {
    if (!submitting) event.preventDefault();
  });

  exam.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.matches("input")) {
      event.preventDefault();
      next.click();
      return;
    }
    if (event.target.matches(".as-code-input")) editorKey(event);
  });
  ["copy", "cut", "contextmenu"].forEach((name) => {
    exam.addEventListener(name, (event) => {
      if (!event.target.matches(".as-code-input")) event.preventDefault();
    });
  });

  function editorKey(event) {
    const box = event.target;
    const { selectionStart: start, selectionEnd: end, value } = box;
    const lineStart = value.lastIndexOf("\n", start - 1) + 1;
    if (event.key === "Tab" && event.shiftKey) {
      event.preventDefault();
      const spaces = value.slice(lineStart).match(/^ {1,4}/);
      if (spaces) {
        box.setRangeText("", lineStart, lineStart + spaces[0].length, "preserve");
        const shift = Math.min(spaces[0].length, start - lineStart);
        box.setSelectionRange(start - shift, Math.max(start - shift, end - spaces[0].length));
        paintEditor(box);
        refresh();
      }
    } else if (event.key === "Tab") {
      event.preventDefault();
      box.setRangeText("    ", start, end, "end");
      paintEditor(box);
      refresh();
    } else if (event.key === "Enter" && !event.shiftKey && !event.metaKey && !event.ctrlKey) {
      const indent = value.slice(lineStart, start).match(/^[ ]*/)[0];
      const opens = /[:{([]\s*$/.test(value.slice(lineStart, start)) ? "    " : "";
      event.preventDefault();
      box.setRangeText(`\n${indent}${opens}`, start, end, "end");
      paintEditor(box);
      refresh();
    } else if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      const run = box.closest(".as-code").querySelector("[data-run]");
      if (run) run.click();
    }
  }

  function paintEditor(box) {
    const editor = box.closest(".as-editor");
    if (!editor) return;
    const language = box.closest(".as-code").dataset.language;
    const code = editor.querySelector(".as-highlight code");
    const highlight = window.LuminaHighlight;
    code.innerHTML = highlight ? highlight.html(`${box.value}\n`, language) : "";
    editor.classList.toggle("is-painted", Boolean(highlight));
    const lines = box.value.split("\n").length;
    const gutter = editor.querySelector(".as-gutter");
    if (gutter.dataset.lines !== String(lines)) {
      gutter.dataset.lines = String(lines);
      gutter.textContent = Array.from({ length: lines }, (_, index) => index + 1).join("\n");
    }
    syncEditor(box);
  }

  function syncEditor(box) {
    const editor = box.closest(".as-editor");
    editor.querySelector(".as-highlight").scrollTop = box.scrollTop;
    editor.querySelector(".as-highlight").scrollLeft = box.scrollLeft;
    editor.querySelector(".as-gutter").scrollTop = box.scrollTop;
  }

  exam.querySelectorAll(".as-code-input").forEach((box) => {
    paintEditor(box);
    box.addEventListener("input", () => paintEditor(box));
    box.addEventListener("scroll", () => syncEditor(box));
  });

  exam.querySelectorAll("[data-reset]").forEach((button) => {
    let timer = null;
    button.addEventListener("click", () => {
      const box = button.closest(".as-code").querySelector(".as-code-input");
      if (!button.classList.contains("is-armed")) {
        button.classList.add("is-armed");
        button.textContent = "Reset to starter?";
        timer = setTimeout(() => {
          button.classList.remove("is-armed");
          button.textContent = "Reset";
        }, 3000);
        return;
      }
      clearTimeout(timer);
      button.classList.remove("is-armed");
      button.textContent = "Reset";
      box.value = box.dataset.starter || "";
      paintEditor(box);
      refresh();
      box.focus();
    });
  });

  function testsBlock(tests, hidden) {
    const block = document.createElement("div");
    block.className = "as-console-block";
    const passed = tests.filter((test) => test.pass).length;
    const heading = document.createElement("p");
    heading.textContent = `Examples · ${passed} of ${tests.length} passed`;
    const list = document.createElement("ul");
    list.className = "as-console-tests";
    tests.forEach((test) => {
      const item = document.createElement("li");
      item.className = test.pass ? "is-pass" : "is-fail";
      const mark = document.createElement("b");
      mark.textContent = test.pass ? "✓" : "✗";
      const call = document.createElement("code");
      call.textContent = test.call;
      const detail = document.createElement("span");
      detail.textContent = test.pass
        ? `→ ${test.got}`
        : `→ ${test.got || "no value"} · expected ${test.expected}`;
      item.append(mark, call, detail);
      list.append(item);
    });
    block.append(heading, list);
    if (hidden) {
      const note = document.createElement("p");
      note.className = "as-console-hidden";
      note.textContent = `${hidden} hidden test${hidden === 1 ? "" : "s"} will run when you submit.`;
      block.append(note);
    }
    return block;
  }

  function consoleBlock(title, text, tone = "") {
    const block = document.createElement("div");
    block.className = `as-console-block${tone ? ` is-${tone}` : ""}`;
    const heading = document.createElement("p");
    heading.textContent = title;
    const pre = document.createElement("pre");
    pre.textContent = text;
    block.append(heading, pre);
    return block;
  }

  function resultTable(columns, rows) {
    const table = document.createElement("table");
    const head = table.createTHead().insertRow();
    columns.forEach((column) => {
      const cell = document.createElement("th");
      cell.textContent = column;
      head.append(cell);
    });
    const body = table.createTBody();
    rows.forEach((row) => {
      const line = body.insertRow();
      row.forEach((value) => {
        line.insertCell().textContent = value === null ? "NULL" : String(value);
      });
    });
    return table;
  }

  exam.querySelectorAll("[data-run]").forEach((button) => {
    button.addEventListener("click", async () => {
      const number = button.dataset.run;
      const field = questions[Number(number)];
      const box = field.querySelector("textarea");
      const output = field.querySelector(`[data-console="${number}"]`);
      const language = field.querySelector(".as-code").dataset.language;
      button.disabled = true;
      button.textContent = "Running…";
      output.replaceChildren(consoleBlock("Running", "…"));
      try {
        const response = await fetch(root.dataset.run, {
          method: "POST",
          body: new URLSearchParams({ question: number, code: box.value }),
        });
        const result = await response.json();
        output.replaceChildren();
        if (language === "sql" && result.ok) {
          const block = consoleBlock(`Result · ${result.rows.length} row${result.rows.length === 1 ? "" : "s"}`, "");
          block.querySelector("pre").replaceWith(resultTable(result.columns, result.rows));
          output.append(block);
        } else if (result.ok || result.output) {
          output.append(consoleBlock("Output", result.output || "(no output)"));
        }
        if (Array.isArray(result.tests) && (result.ok || !result.error)) {
          output.append(testsBlock(result.tests, result.hidden || 0));
        }
        if (result.error) output.append(consoleBlock(result.ok ? "Messages" : "Error", result.error, "error"));
        if (!result.ok && !result.error) output.append(consoleBlock("Error", "The code could not run.", "error"));
      } catch {
        output.replaceChildren(consoleBlock("Error", "Lumina could not run the code. Try again.", "error"));
      } finally {
        button.disabled = false;
        button.textContent = "Run code";
      }
    });
  });

  window.addEventListener("beforeunload", (event) => {
    if (running && !submitting) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  window.addEventListener("pagehide", stopCamera);
}
