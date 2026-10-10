const desk = document.querySelector(".desk");
const drawer = document.querySelector("#lesson-drawer");
const backdrop = document.querySelector("#drawer-backdrop");
const log = document.querySelector("#chat-log");
const column = log ? log.querySelector(".chat-col") : null;
const chatForm = document.querySelector("#course-chat");
const box = document.querySelector("#prompt");
const courseId = desk.dataset.course;

let opener = null;
let drawerOpen = false;

function openDrawer(index) {
  let shown = null;
  drawer.querySelectorAll("[data-pane]").forEach((pane) => {
    const match = String(pane.dataset.pane) === String(index);
    pane.hidden = !match;
    if (match) shown = pane;
  });
  if (!shown) return;
  shown.querySelector(".drawer-body").scrollTop = 0;
  document.querySelectorAll("button[data-open]").forEach((row) => {
    row.classList.toggle("is-open", row.getAttribute("data-open") === String(index));
  });
  drawerOpen = true;
  backdrop.hidden = false;
  drawer.inert = false;
  drawer.setAttribute("aria-hidden", "false");
  requestAnimationFrame(() => {
    if (!drawerOpen) return;
    drawer.classList.add("is-open");
    backdrop.classList.add("is-open");
    shown.querySelector(".drawer-close").focus({ preventScroll: true });
  });
}

function closeDrawer() {
  if (!drawerOpen) return;
  drawerOpen = false;
  drawer.classList.remove("is-open");
  backdrop.classList.remove("is-open");
  drawer.inert = true;
  drawer.setAttribute("aria-hidden", "true");
  document.querySelectorAll("button[data-open]").forEach((row) => row.classList.remove("is-open"));
  setTimeout(() => {
    if (!drawerOpen) backdrop.hidden = true;
  }, 220);
  if (opener) opener.focus({ preventScroll: true });
}

if (desk.dataset.initial !== "") openDrawer(desk.dataset.initial);

drawer.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", closeDrawer);
});
backdrop.addEventListener("click", closeDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
});

document.querySelectorAll("button[data-open]").forEach((button) => {
  button.addEventListener("click", () => {
    const index = button.getAttribute("data-open");
    opener = button;
    openDrawer(index);
    const status = button.querySelector(".status");
    if (status && status.classList.contains("status-new")) {
      status.classList.remove("status-new");
      status.classList.add("status-study");
      status.textContent = "Studying";
    }
    fetch(`/courses/${courseId}/lessons/${index}/open`, { method: "POST" });
  });
});

function tutorNote(text) {
  const row = document.createElement("div");
  row.className = "msg msg-tutor";
  row.innerHTML = '<span class="avatar" aria-hidden="true">L</span><div class="bubble"><p></p></div>';
  row.querySelector("p").textContent = text;
  column.append(row);
  if (log) log.scrollTop = log.scrollHeight;
  return row;
}

document.querySelectorAll(".msg-copy").forEach((button) => {
  button.addEventListener("click", async () => {
    const bubble = button.closest(".bubble-wrap")?.querySelector(".bubble");
    if (!bubble) return;
    try {
      await navigator.clipboard.writeText(bubble.innerText.trim());
      button.textContent = "Copied";
      setTimeout(() => {
        button.textContent = "Copy";
      }, 1200);
    } catch {
      button.textContent = "Copy";
    }
  });
});

document.querySelectorAll(".suggest[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    if (!box || !chatForm) return;
    box.value = button.getAttribute("data-prompt") || "";
    chatForm.requestSubmit();
  });
});

if (log) log.scrollTop = log.scrollHeight;

if (box && chatForm) {
  const grow = () => {
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 160)}px`;
  };
  box.addEventListener("input", grow);
  box.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatForm.requestSubmit();
    }
  });
  chatForm.addEventListener("submit", () => {
    const button = chatForm.querySelector(".send");
    if (button) button.disabled = true;
    tutorNote("Thinking…");
  });
}
