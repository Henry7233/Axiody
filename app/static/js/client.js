document.querySelectorAll('.toggle').forEach(button => {
  button.addEventListener('click', () => {
    const input = document.getElementById(button.getAttribute('aria-controls'));
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    button.textContent = visible ? 'Hide' : 'Show';
    button.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
    button.setAttribute('aria-pressed', String(visible));
  });
});

const loginForm = document.querySelector('[data-js-login]');

if (loginForm) {
  loginForm.addEventListener('submit', async event => {
    event.preventDefault();

    const message = loginForm.querySelector('[role="status"]');
    const submitButton = loginForm.querySelector('[type="submit"]');
    const formData = new FormData(loginForm);

    submitButton.disabled = true;
    message.textContent = 'Checking your login...';

    try {
      const response = await fetch(loginForm.action, {
        method: 'POST',
        body: formData,
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        }
      });
      const result = await response.json();

      message.textContent = result.message;

      if (response.ok) {
        setTimeout(() => {
          window.location.href = result.redirect_url;
        }, 900);
      }
    } catch (error) {
      message.textContent = 'Something went wrong. Please try again.';
    } finally {
      submitButton.disabled = false;
    }
  });
}

// Notifications: search, filtering, sorting, and review details.
(() => {
  "use strict";

  // Shared with the login page; initialize only on notifications.html.
  const page = document.querySelector(".notifications-page");
  if (!page) return;

  const search = page.querySelector("#notification-search");
  const sort = page.querySelector("#notification-sort");
  const list = page.querySelector(".notification-list");
  const cards = Array.from(list.querySelectorAll(".notification-card"));
  const filters = Array.from(page.querySelectorAll("[data-filter]"));
  const empty = page.querySelector("#empty-state");
  const count = page.querySelector("#results-count");
  let activeFilter = "all";

  function updateResults() {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    const sorted = [...cards].sort((a, b) => {
      const recent = Date.parse(b.dataset.created) - Date.parse(a.dataset.created);
      if (sort.value === "oldest") return -recent;
      if (sort.value === "deadline") {
        const first = a.dataset.deadline || "9999-12-31";
        const second = b.dataset.deadline || "9999-12-31";
        return first.localeCompare(second) || recent;
      }
      return recent;
    });
    for (const card of sorted) {
      const matchesCategory = activeFilter === "all" || card.dataset.category === activeFilter;
      card.hidden = !(matchesCategory && card.textContent.toLocaleLowerCase().includes(query));
      if (!card.hidden) visible += 1;
      list.append(card);
    }
    empty.hidden = visible > 0;
    count.textContent = `${visible} notification${visible === 1 ? "" : "s"} shown`;
    for (const button of filters) {
      button.setAttribute("aria-pressed", String(button.dataset.filter === activeFilter));
    }
  }

  for (const button of filters) {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter;
      updateResults();
    });
  }
  search.addEventListener("input", updateResults);
  sort.addEventListener("change", updateResults);
  page.querySelector("#reset-filters").addEventListener("click", () => {
    activeFilter = "all";
    search.value = "";
    sort.value = "recent";
    updateResults();
    search.focus();
  });

  const detailDialog = page.querySelector("#detail-dialog");
  const detailContent = page.querySelector("#detail-content");
  for (const button of page.querySelectorAll("[data-details]")) {
    button.addEventListener("click", () => {
      const template = document.getElementById(button.dataset.details);
      detailContent.replaceChildren(template.content.cloneNode(true));
      detailDialog.showModal();
    });
  }
  for (const dialog of page.querySelectorAll("dialog")) {
    for (const button of dialog.querySelectorAll(".close-dialog, .dialog-done")) {
      button.addEventListener("click", () => dialog.close());
    }
    dialog.addEventListener("click", (event) => {
      const bounds = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) {
        dialog.close();
      }
    });
  }
  updateResults();
})();
