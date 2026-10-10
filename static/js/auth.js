(() => {
  document.querySelectorAll("[data-reveal]").forEach((button) => {
    const input = document.getElementById(button.dataset.reveal);
    button.addEventListener("click", () => {
      const visible = input.type === "text";
      input.type = visible ? "password" : "text";
      button.textContent = visible ? "Show" : "Hide";
    });
  });

  const form = document.querySelector("form");
  const submit = form.querySelector("button[type=submit]");
  const idle = submit.textContent;
  form.addEventListener("submit", () => {
    submit.disabled = true;
    submit.textContent = form.hasAttribute("data-signup") ? "Creating account…" : "Signing in…";
  });
  window.addEventListener("pageshow", () => {
    submit.disabled = false;
    submit.textContent = idle;
  });

  if (!form.hasAttribute("data-signup")) return;

  const password = form.querySelector("#password");
  const confirm = form.querySelector("#confirm");
  const strength = form.querySelector("#strength");
  const text = strength.querySelector(".strength-text");
  const labels = ["At least 8 characters.", "Weak", "Fair", "Good", "Strong"];

  const level = (value) => {
    if (value.length < 8) return 0;
    let score = 1;
    if (value.length >= 12) score += 1;
    if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1;
    if (/\d/.test(value) && /[^A-Za-z0-9]/.test(value)) score += 1;
    if (new Set(value).size < 4) score = 1;
    return Math.min(score, 4);
  };

  const check = () => {
    const value = password.value;
    const score = value ? level(value) : 0;
    strength.dataset.level = String(score);
    text.textContent = value && score === 0 ? `${8 - value.length} more character${8 - value.length === 1 ? "" : "s"}` : labels[score];
    confirm.setCustomValidity(confirm.value && confirm.value !== value ? "The two passwords don't match." : "");
  };

  password.addEventListener("input", check);
  confirm.addEventListener("input", check);
})();
