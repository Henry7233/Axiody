(() => {
  "use strict";

  const table = document.getElementById("adminTableBody");
  if (!table) return;

  const deleteBaseUrl = table.dataset.deleteBaseUrl;
  const deleteAllUrl = table.dataset.deleteAllUrl;
  const search = document.getElementById("adminSearch");
  const roleFilter = document.getElementById("roleFilter");
  const dialog = document.getElementById("adminDialog");
  const form = document.getElementById("adminForm");
  const nameInput = document.getElementById("adminName");
  const emailInput = document.getElementById("adminEmail");
  const roleInput = document.getElementById("adminRole");
  const customRoleGroup = document.getElementById("customRoleGroup");
  const customRoleInput = document.getElementById("adminCustomRole");
  const passwordInput = document.getElementById("adminPassword");
  const passwordConfirmInput = document.getElementById("adminPasswordConfirm");
  const addButton = document.getElementById("addAdmin");
  const deleteAllButton = document.getElementById("deleteAllAdmins");
  const roleShortcutButtons = document.querySelectorAll("[data-role-shortcut]");
  const standardRoles = Array.from(roleInput.options)
    .map((option) => option.value)
    .filter((value) => value !== "Other");
  let editingRow = null;
  let nextId = 0;

  function updateCustomRoleField() {
    const usesCustomRole = roleInput.value === "Other";
    customRoleGroup.hidden = !usesCustomRole;
    customRoleInput.required = usesCustomRole;
    if (!usesCustomRole) {
      customRoleInput.value = "";
      customRoleInput.setCustomValidity("");
    }
  }

  function selectedRole() {
    return roleInput.value === "Other" ? customRoleInput.value.trim() : roleInput.value;
  }

  function validatePasswords(isNew) {
    const password = passwordInput.value;
    const confirmation = passwordConfirmInput.value;

    passwordInput.required = isNew;
    passwordConfirmInput.required = isNew || Boolean(password);
    passwordInput.setCustomValidity("");
    passwordConfirmInput.setCustomValidity("");

    if ((isNew || password || confirmation) && password.length < 8) {
      passwordInput.setCustomValidity("Enter at least 8 characters.");
    }
    if ((isNew || password || confirmation) && password !== confirmation) {
      passwordConfirmInput.setCustomValidity("Passwords must match.");
    }
  }

  function ensureRoleFilterOption(role, label = role) {
    const hasOption = Array.from(roleFilter.options).some((option) => option.value === role);
    if (hasOption) return;

    const option = document.createElement("option");
    option.value = role;
    option.textContent = label;
    roleFilter.append(option);
  }

  function fillAdminRow(row, admin) {
    Object.assign(row.dataset, {
      adminId: admin.id,
      name: admin.name,
      email: admin.email,
      role: admin.role,
      date: admin.date,
    });
    ["name", "email", "role", "date"].forEach((field) => {
      row.querySelector(`[data-field="${field}"]`).textContent = row.dataset[field];
    });
    row.querySelector(".admin-avatar").textContent = Array.from(admin.name)[0].toUpperCase();
    row.querySelector(".admin-edit").setAttribute("aria-label", `Edit ${admin.name}`);
    row.querySelector(".admin-delete").setAttribute("aria-label", `Delete ${admin.name}`);
  }

  function createAdminRow(admin) {
    const row = document.createElement("tr");
    // Only static markup goes into innerHTML; admin input is assigned as text below.
    row.innerHTML = `
      <td><div class="admin-person"><span class="avatar admin-avatar" aria-hidden="true"></span><strong data-field="name"></strong></div></td>
      <td data-field="email"></td><td data-field="role"></td><td data-field="date"></td>
      <td><div class="admin-actions"><button type="button" class="btn btn--secondary admin-edit">Edit</button><button type="button" class="btn btn--secondary admin-delete">Delete</button></div></td>`;
    fillAdminRow(row, admin);
    return row;
  }

  function refresh() {
    const rows = Array.from(table.rows);
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      const standardRole = standardRoles.includes(row.dataset.role);
      const roleMatches = roleFilter.value === "all"
        || row.dataset.role === roleFilter.value
        || (roleFilter.value === "other" && !standardRole);
      const matches = `${row.dataset.name} ${row.dataset.email}`.toLowerCase().includes(query)
        && roleMatches;
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    document.querySelectorAll("[data-stat]").forEach((stat) => {
      const counts = {
        total: rows.length,
        administrator: rows.filter((row) => row.dataset.role === "Administrator").length,
        admin_manager: rows.filter((row) => row.dataset.role === "Admin manager").length,
        reviewer: rows.filter((row) => row.dataset.role === "Reviewer").length,
        other: rows.filter((row) => !standardRoles.includes(row.dataset.role)).length,
      };
      stat.textContent = counts[stat.dataset.stat];
    });
    document.getElementById("adminsEmpty").hidden = visible > 0;
    document.getElementById("adminResults").textContent = `Showing ${visible} of ${rows.length} admins`;
  }

  function showAdminTable(role = "all") {
    search.value = "";
    if (role === "other") {
      ensureRoleFilterOption("other", "Other");
    }
    roleFilter.value = role;
    refresh();
    table.closest(".table-wrap").scrollIntoView({ behavior: "smooth", block: "start" });
    table.closest(".table-wrap").focus({ preventScroll: true });
  }

  function openEditor(row = null) {
    editingRow = row;
    form.reset();
    nameInput.setCustomValidity("");
    emailInput.setCustomValidity("");
    customRoleInput.setCustomValidity("");
    passwordInput.setCustomValidity("");
    passwordConfirmInput.setCustomValidity("");
    passwordInput.required = !row;
    passwordConfirmInput.required = !row;
    document.getElementById("adminDialogTitle").textContent = row ? "Edit admin" : "Add admin";
    if (row) {
      nameInput.value = row.dataset.name;
      emailInput.value = row.dataset.email;
      if (standardRoles.includes(row.dataset.role)) {
        roleInput.value = row.dataset.role;
      } else {
        roleInput.value = "Other";
        customRoleInput.value = row.dataset.role;
      }
    }
    updateCustomRoleField();
    dialog.showModal();
    nameInput.focus();
  }

  addButton.addEventListener("click", () => openEditor());
  table.addEventListener("click", (event) => {
    const editButton = event.target.closest(".admin-edit");
    if (editButton) {
      openEditor(editButton.closest("tr"));
      return;
    }

    const deleteButton = event.target.closest(".admin-delete");
    if (!deleteButton) return;

    const row = deleteButton.closest("tr");
    const adminName = row.dataset.name;
    if (!window.confirm(`Delete ${adminName}?`)) return;

    deleteButton.disabled = true;
    fetch(deleteBaseUrl.replace(/0$/, row.dataset.adminId), {
      method: "DELETE",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((response) => response.json().then((result) => ({ response, result })))
      .then(({ response, result }) => {
        if (!response.ok) {
          document.getElementById("adminsMessage").textContent = result.message || "Unable to delete this admin.";
          return;
        }

        row.remove();
        refresh();
        document.getElementById("adminsMessage").textContent = result.message;
      })
      .catch(() => {
        document.getElementById("adminsMessage").textContent = "Unable to delete this admin right now.";
      })
      .finally(() => {
        deleteButton.disabled = false;
      });
  });
  deleteAllButton.addEventListener("click", () => {
    if (!window.confirm("Delete all unprotected admin accounts? Protected admins will stay.")) return;

    deleteAllButton.disabled = true;
    fetch(deleteAllUrl, {
      method: "DELETE",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((response) => response.json().then((result) => ({ response, result })))
      .then(({ response, result }) => {
        if (!response.ok) {
          document.getElementById("adminsMessage").textContent = result.message || "Unable to delete admins.";
          return;
        }

        const deletedIds = new Set(result.deleted_ids.map(String));
        Array.from(table.rows).forEach((row) => {
          if (deletedIds.has(row.dataset.adminId)) row.remove();
        });
        refresh();
        document.getElementById("adminsMessage").textContent = result.message;
      })
      .catch(() => {
        document.getElementById("adminsMessage").textContent = "Unable to delete admins right now.";
      })
      .finally(() => {
        deleteAllButton.disabled = false;
      });
  });
  document.getElementById("cancelAdmin").addEventListener("click", () => dialog.close());
  nameInput.addEventListener("input", () => nameInput.setCustomValidity(""));
  emailInput.addEventListener("input", () => emailInput.setCustomValidity(""));
  roleInput.addEventListener("change", updateCustomRoleField);
  customRoleInput.addEventListener("input", () => customRoleInput.setCustomValidity(""));
  passwordInput.addEventListener("input", () => validatePasswords(!editingRow));
  passwordConfirmInput.addEventListener("input", () => validatePasswords(!editingRow));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = nameInput.value.trim();
    const email = emailInput.value.trim().toLowerCase();
    const role = selectedRole();
    const isNew = !editingRow;
    nameInput.setCustomValidity(name ? "" : "Enter a full name.");
    customRoleInput.setCustomValidity(role ? "" : "Enter a specific role.");
    const duplicate = Array.from(table.rows).some((row) => row !== editingRow
      && row.dataset.email.toLowerCase() === email);
    emailInput.setCustomValidity(duplicate ? "An admin with this email already exists." : "");
    validatePasswords(isNew);
    if (!form.reportValidity()) return;

    if (isNew) {
      const submitButton = form.querySelector('[type="submit"]');
      submitButton.disabled = true;
      try {
        const response = await fetch(form.dataset.createUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
          body: JSON.stringify({
            name,
            email,
            role: roleInput.value,
            custom_role: customRoleInput.value.trim(),
            password: passwordInput.value,
            password_confirmation: passwordConfirmInput.value,
          }),
        });
        const result = await response.json();
        if (!response.ok) {
          emailInput.setCustomValidity(result.message || "Unable to create this admin.");
          form.reportValidity();
          return;
        }

        const row = createAdminRow(result.admin);
        table.append(row);
        ensureRoleFilterOption(result.admin.role);
        dialog.close();
        refresh();
        document.getElementById("adminsMessage").textContent = result.message;
      } catch (error) {
        emailInput.setCustomValidity("Unable to create this admin right now.");
        form.reportValidity();
      } finally {
        submitButton.disabled = false;
      }
      return;
    }

    const row = editingRow;
    Object.assign(row.dataset, { name, email, role });
    fillAdminRow(row, {
      id: row.dataset.adminId || `preview-${++nextId}`,
      name,
      email,
      role,
      date: row.dataset.date,
    });
    ensureRoleFilterOption(role);
    dialog.close();
    refresh();
    if (editingRow.hidden) search.focus();
    document.getElementById("adminsMessage").textContent = `${name} updated in this view.`;
  });

  search.addEventListener("input", refresh);
  roleFilter.addEventListener("change", refresh);
  roleShortcutButtons.forEach((button) => {
    button.addEventListener("click", () => showAdminTable(button.dataset.roleShortcut));
  });
  document.getElementById("clearFilters").addEventListener("click", () => {
    search.value = "";
    roleFilter.value = "all";
    refresh();
    search.focus();
  });

  document.getElementById("adminControls").hidden = false;
  addButton.hidden = false;
  deleteAllButton.hidden = false;
  table.querySelectorAll(".admin-edit").forEach((button) => { button.hidden = false; });
  table.querySelectorAll(".admin-delete").forEach((button) => { button.hidden = false; });
  refresh();
})();
