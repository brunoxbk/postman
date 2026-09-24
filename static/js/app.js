document.querySelectorAll(".message-close").forEach((btn) => {
  btn.addEventListener("click", () => {
    btn.closest(".message").remove();
  });
});

document.querySelectorAll(".toggle-raw").forEach((btn) => {
  btn.addEventListener("click", () => {
    const raw = btn.nextElementSibling;
    raw.hidden = !raw.hidden;
    refreshBusy();
  });
});

document.addEventListener("submit", refreshBusy);