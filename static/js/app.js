document.querySelectorAll(".toggle-raw").forEach((btn) => {
  btn.addEventListener("click", () => {
    const raw = btn.nextElementSibling;
    raw.hidden = !raw.hidden;
  });
});