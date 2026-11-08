// django-flashdeck: the character buttons type their character into the answer box
// last used, at the cursor, without taking the focus (or a phone's keyboard) away
// from it.
document.addEventListener("DOMContentLoaded", () => {
  for (const form of document.querySelectorAll("[data-flashdeck-form]")) {
    const inputs = form.querySelectorAll("input[type=text]");
    let target = inputs[0];
    for (const input of inputs) {
      input.addEventListener("focus", () => {
        target = input;
      });
    }
    for (const button of form.querySelectorAll("[data-flashdeck-insert]")) {
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => {
        if (!target) return;
        const start = target.selectionStart ?? target.value.length;
        const end = target.selectionEnd ?? target.value.length;
        target.setRangeText(button.dataset.flashdeckInsert, start, end, "end");
        target.focus();
      });
    }
  }
});
