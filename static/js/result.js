if (window.LuminaHighlight) {
  document.querySelectorAll("pre.as-pre[data-language]").forEach((block) => {
    block.innerHTML = window.LuminaHighlight.html(block.textContent, block.dataset.language);
  });
}

const coach = document.querySelector("#coach");

if (coach) {
  const button = document.querySelector("#coach-button");
  const text = document.querySelector("#coach-text");
  const fallback = "Lumina could not write feedback right now. Try again in a moment.";

  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "Reviewing…";
    coach.classList.add("is-busy");
    coach.classList.remove("is-failed");
    text.textContent = "Lumina is reading your answers. This can take up to a minute.";
    try {
      const response = await fetch(coach.dataset.feedback, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.ok) {
        window.location.reload();
        return;
      }
      throw new Error(data.error || fallback);
    } catch (error) {
      coach.classList.remove("is-busy");
      coach.classList.add("is-failed");
      text.textContent = error instanceof TypeError ? fallback : error.message;
      button.disabled = false;
      button.textContent = "Try again";
    }
  });
}
