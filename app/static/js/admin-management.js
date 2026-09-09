(() => {
  "use strict";

  const table = document.getElementById("adminTableBody");
  if (!table) return;

  const search = document.getElementById("adminSearch");
  const roleFilter = document.getElementById("roleFilter");
  const statusFilter = document.getElementById("statusFilter");
  const dialog = document.getElementById("adminDialog");
  const form = document.getElementById("adminForm");
  const nameInput = document.getElementById("adminName");
  const emailInput = document.getElementById("adminEmail");
  const roleInput = document.getElementById("adminRole");
  const statusInput = document.getElementById("adminStatus");
  const addButton = document.getElementById("addAdmin");
  let editingRow = null;
  let nextId = 0;

  function refresh() {
    const rows = Array.from(table.rows);
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      const matches = `${row.dataset.name} ${row.dataset.email}`.toLowerCase().includes(query)
        && (roleFilter.value === "all" || row.dataset.role === roleFilter.value)
        && (statusFilter.value === "all" || row.dataset.status === statusFilter.value);
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    document.querySelectorAll("[data-stat]").forEach((stat) => {
      stat.textContent = stat.dataset.stat === "total" ? rows.length
        : rows.filter((row) => row.dataset.status === stat.dataset.stat).length;
    });
    document.getElementById("adminsEmpty").hidden = visible > 0;
    document.getElementById("adminResults").textContent = `Showing ${visible} of ${rows.length} admins`;
  }

  function openEditor(row = null) {
    editingRow = row;
    form.reset();
    nameInput.setCustomValidity("");
    emailInput.setCustomValidity("");
    document.getElementById("adminDialogTitle").textContent = row ? "Edit admin" : "Add admin";
    if (row) {
      nameInput.value = row.dataset.name;
      emailInput.value = row.dataset.email;
      roleInput.value = row.dataset.role;
      statusInput.value = row.dataset.status;
    }
    dialog.showModal();
    nameInput.focus();
  }

  addButton.addEventListener("click", () => openEditor());
  table.addEventListener("click", (event) => {
    const button = event.target.closest(".admin-edit");
    if (button) openEditor(button.closest("tr"));
  });
  document.getElementById("cancelAdmin").addEventListener("click", () => dialog.close());
  nameInput.addEventListener("input", () => nameInput.setCustomValidity(""));
  emailInput.addEventListener("input", () => emailInput.setCustomValidity(""));

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = nameInput.value.trim();
    const email = emailInput.value.trim().toLowerCase();
    nameInput.setCustomValidity(name ? "" : "Enter a full name.");
    const duplicate = Array.from(table.rows).some((row) => row !== editingRow
      && row.dataset.email.toLowerCase() === email);
    emailInput.setCustomValidity(duplicate ? "An admin with this email already exists." : "");
    if (!form.reportValidity()) return;

    const isNew = !editingRow;
    const row = editingRow || document.createElement("tr");
    if (isNew) {
      row.dataset.adminId = `preview-${++nextId}`;
      // Only static markup goes into innerHTML; admin input is assigned as text below.
      row.innerHTML = `
        <td><div class="admin-person"><span class="avatar admin-avatar" aria-hidden="true"></span><strong data-field="name"></strong></div></td>
        <td data-field="email"></td><td data-field="role"></td><td>Never</td>
        <td><span data-field="status"></span></td>
        <td><button type="button" class="btn btn--secondary admin-edit">Edit</button></td>`;
      table.append(row);
    }
    Object.assign(row.dataset, { name, email, role: roleInput.value, status: statusInput.value });
    ["name", "email", "role"].forEach((field) => {
      row.querySelector(`[data-field="${field}"]`).textContent = row.dataset[field];
    });
    row.querySelector(".admin-avatar").textContent = Array.from(name)[0].toUpperCase();
    row.querySelector(".admin-edit").setAttribute("aria-label", `Edit ${name}`);
    const badge = row.querySelector('[data-field="status"]');
    badge.className = `admin-status admin-status--${row.dataset.status}`;
    badge.textContent = row.dataset.status[0].toUpperCase() + row.dataset.status.slice(1);

    dialog.close();
    refresh();
    if (editingRow && editingRow.hidden) search.focus();
    document.getElementById("adminsMessage").textContent = `${name} ${isNew ? "added to" : "updated in"} the preview.${row.hidden ? " This admin is hidden by the current filters." : ""}`;
  });

  search.addEventListener("input", refresh);
  roleFilter.addEventListener("change", refresh);
  statusFilter.addEventListener("change", refresh);
  document.getElementById("clearFilters").addEventListener("click", () => {
    search.value = "";
    roleFilter.value = "all";
    statusFilter.value = "all";
    refresh();
    search.focus();
  });

  document.getElementById("adminControls").hidden = false;
  addButton.hidden = false;
  table.querySelectorAll(".admin-edit").forEach((button) => { button.hidden = false; });
  refresh();
})();
