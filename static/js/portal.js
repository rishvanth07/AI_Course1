const form = document.querySelector("#ask");
const input = document.querySelector("#query");
const plan = document.querySelector("#plan");
const hint = document.querySelector("#hint");
const submit = form.querySelector("button");

function setBusy(busy) {
  submit.disabled = busy;
  submit.textContent = busy ? "Drafting…" : "Draft a path";
  form.setAttribute("aria-busy", busy ? "true" : "false");
}

function renderPlan(data) {
  hint.textContent = "";
  plan.hidden = false;
  plan.replaceChildren();

  const header = document.createElement("header");
  const title = document.createElement("h2");
  title.textContent = data.title;
  const minutes = document.createElement("span");
  minutes.className = "minutes";
  minutes.textContent = `${data.minutes} min`;
  header.append(title, minutes);

  const list = document.createElement("ol");
  data.steps.forEach((step) => {
    const item = document.createElement("li");
    const label = document.createElement("strong");
    label.textContent = step.label;
    const text = document.createElement("p");
    text.textContent = step.text;
    item.append(label, text);
    list.append(item);
  });

  const next = document.createElement("p");
  next.className = "next";
  next.textContent = `Then: ${data.next}`;

  plan.append(header, list, next);
}

async function draft(query) {
  const cleaned = query.trim();
  if (!cleaned) {
    hint.textContent = "Tell Lumina what you want to learn.";
    input.focus();
    return;
  }

  setBusy(true);
  hint.textContent = "";
  try {
    const response = await fetch("/api/guide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: cleaned }),
    });
    const data = await response.json();
    if (!response.ok) {
      hint.textContent = data.error || "The path could not be drafted.";
      return;
    }
    renderPlan(data);
  } catch {
    hint.textContent = "The studio could not be reached. Try again in a moment.";
  } finally {
    setBusy(false);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  draft(input.value);
});

document.querySelectorAll("[data-query]").forEach((button) => {
  button.addEventListener("click", () => {
    const query = button.dataset.query;
    input.value = query;
    document.querySelectorAll(".chip").forEach((chip) => {
      chip.classList.toggle("is-on", chip === button);
    });
    draft(query);
    if (button.classList.contains("text-link")) {
      form.scrollIntoView({ block: "center" });
    }
  });
});
