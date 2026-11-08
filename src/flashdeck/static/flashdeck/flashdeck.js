// django-flashdeck: character buttons, the search on reference pages, and the
// reference opened from a card in a dialog.

// The folded form in which a search and the text it searches are compared, as
// flashdeck.marking.loosen makes it on the server: lower case, without accents or
// punctuation, with ß, æ and œ spelt out.
function fold(text) {
  return text
    .replace(/[’‘ʼ]/g, "'")
    .toLowerCase()
    .replace(/ß/g, "ss")
    .replace(/æ/g, "ae")
    .replace(/œ/g, "oe")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Character buttons type their character into the answer box last used, at the
// cursor, without taking the focus (or a phone's keyboard) away from it.
function setUpCharacters(form) {
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

// A search box hides the items (given by the selector in its data attribute) whose
// data-search text does not contain what is typed; Enter opens the first left.
function setUpSearch(root) {
  for (const input of root.querySelectorAll("[data-flashdeck-search]")) {
    const items = [...root.querySelectorAll(input.dataset.flashdeckSearch)];
    const status = input.parentElement.querySelector("[data-flashdeck-search-status]");
    input.addEventListener("input", () => {
      const query = fold(input.value);
      let shown = 0;
      for (const item of items) {
        const match = !query || item.dataset.search.includes(query);
        item.hidden = !match;
        shown += match;
      }
      if (status) status.textContent = query ? `${shown} found` : "";
    });
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      const link = items.find((item) => !item.hidden)?.querySelector("a");
      if (link) {
        event.preventDefault();
        link.click();
      }
    });
  }
}

// The reference, opened in a dialog by its button or ⌘K / Ctrl+K, so that what
// has been typed is kept. Its links open within the dialog, with a Back button.
// Opening it before marking is recorded, so that a right answer counts as nearly
// right.
function setUpReference() {
  const button = document.querySelector("[data-flashdeck-reference]");
  const dialog = document.querySelector("[data-flashdeck-dialog]");
  if (!button || !dialog) return;
  const body = dialog.querySelector("[data-flashdeck-dialog-body]");
  const back = dialog.querySelector("[data-flashdeck-back]");
  const history = [];
  let returnTo = null;

  async function load(url) {
    const fragment = new URL(url, window.location.href);
    fragment.searchParams.set("fragment", "1");
    const response = await fetch(fragment, { credentials: "same-origin" });
    // The page's own HTML, from the same site, rendered with escaping.
    body.innerHTML = response.ok ? await response.text() : "<p>The reference could not be loaded.</p>";
    back.hidden = history.length < 2;
    setUpSearch(body);
    body.scrollTop = 0;
    body.querySelector("[data-flashdeck-search]")?.focus();
  }

  function open() {
    if (dialog.open) return;
    returnTo = document.activeElement;
    const lookedUp = document.querySelector("[data-flashdeck-looked-up]");
    if (lookedUp) lookedUp.value = "1";
    dialog.showModal();
    if (!history.length) {
      history.push(button.dataset.flashdeckReference);
      load(history[0]);
    } else {
      body.querySelector("[data-flashdeck-search]")?.focus();
    }
  }

  button.addEventListener("click", open);
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      open();
    }
  });
  body.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-flashdeck-ref]");
    if (!link) return;
    event.preventDefault();
    history.push(link.href);
    load(link.href);
  });
  back.addEventListener("click", () => {
    history.pop();
    load(history[history.length - 1]);
  });
  dialog.querySelector("[data-flashdeck-close]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => returnTo?.focus());
}

document.addEventListener("DOMContentLoaded", () => {
  for (const form of document.querySelectorAll("[data-flashdeck-form]")) {
    setUpCharacters(form);
  }
  setUpSearch(document);
  setUpReference();
});
