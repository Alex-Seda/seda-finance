(() => {
  const root = document.documentElement;
  const toggle = document.querySelector(".theme-toggle");
  if (!toggle) return;

  const labels = { auto: "Auto", light: "Light", dark: "Dark" };
  const themes = ["auto", "light", "dark"];

  const updateToggle = (theme) => {
    const label = toggle.querySelector(".theme-label");
    if (label) label.textContent = labels[theme] || labels.auto;
    toggle.setAttribute(
      "aria-label",
      `Color theme: ${labels[theme] || labels.auto}. Click to change.`
    );
    toggle.dataset.theme = theme;
  };

  const currentTheme = () => localStorage.getItem("theme") || "auto";
  updateToggle(currentTheme());

  toggle.addEventListener("click", () => {
    const current = currentTheme();
    const next = themes[(themes.indexOf(current) + 1) % themes.length];
    localStorage.setItem("theme", next);
    root.dataset.theme = next;
    updateToggle(next);
  });
})();
