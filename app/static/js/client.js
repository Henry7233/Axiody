// Show all three record categories in the dashboard's HTML subview.
(() => {
  const dashboard = document.querySelector('.client-dashboard');
  if (!dashboard) return;
  const viewAll = dashboard.querySelector('[data-view-all-records]');
  const dialog = dashboard.querySelector('#client-records-dialog');
  if (!viewAll || !dialog) return;

  viewAll.addEventListener('click', () => {
    if (dialog.open) return;
    dialog.showModal();
    dialog.scrollTop = 0;
    document.body.classList.add('client-records-open');
  });
  dialog.querySelector('[data-close-records]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    const bounds = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) {
      dialog.close();
    }
  });
  // Native dialog behavior also handles Escape and keeps focus inside the overlay.
  dialog.addEventListener('close', () => {
    document.body.classList.remove('client-records-open');
    viewAll.focus({ preventScroll: true });
  });
})();

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

// Shared settings controller. Admin's role-specific entry point lives in admin.js.
// Browser storage holds preferences/profile display fields only, never credentials.
window.AxiodySettings = (() => {
  "use strict";
  const messages = {
    saved: ['Preferences saved on this browser.', '偏好已保存在此浏览器中。', 'Pilihan disimpan dalam pelayar ini.'],
    temporary: ['Changes apply for this visit only. Sign in to save preferences for your account.', '更改仅在本次访问中生效。请登录以保存账户偏好。', 'Perubahan untuk lawatan ini sahaja. Log masuk untuk menyimpan pilihan akaun.'],
    storageError: ['Browser storage is unavailable. Your changes are temporary; allow site storage and try again.', '浏览器存储不可用。更改为临时更改；请允许网站存储后重试。', 'Storan pelayar tidak tersedia. Perubahan bersifat sementara; benarkan storan laman dan cuba lagi.'],
    localSaved: ['Profile saved on this browser. Your sign-in email and password have not changed.', '资料已保存在此浏览器中。登录邮箱和密码未更改。', 'Profil disimpan dalam pelayar ini. E-mel log masuk dan kata laluan tidak berubah.'],
    accountSaved: ['Account changes saved.', '账户更改已保存。', 'Perubahan akaun disimpan.'],
    discarded: ['Account editor closed. Unsaved edits were discarded.', '账户编辑器已关闭。未保存的编辑已放弃。', 'Editor akaun ditutup. Suntingan yang belum disimpan telah dibuang.'],
    saving: ['Saving changes…', '正在保存更改…', 'Menyimpan perubahan…'],
    saveError: ['Unable to confirm the account update. Your edits are still here. Please try again.', '无法确认账户更新。您的编辑仍保留在此处，请重试。', 'Tidak dapat mengesahkan kemas kini akaun. Suntingan anda masih di sini. Sila cuba lagi.'],
    nameRequired: ['Enter your full name.', '请输入您的姓名。', 'Masukkan nama penuh anda.'],
    passwordWeak: ['Use at least 8 characters including a letter, a number and a symbol.', '请使用至少8个字符，包含字母、数字和符号。', 'Gunakan sekurang-kurangnya 8 aksara termasuk huruf, nombor dan simbol.'],
    passwordMismatch: ['The new passwords must match.', '两次输入的新密码必须一致。', 'Kata laluan baharu mesti sepadan.'],
    showPassword: ['Show password', '显示密码', 'Tunjukkan kata laluan'],
    hidePassword: ['Hide password', '隐藏密码', 'Sembunyikan kata laluan'],
    closeHelp: ['Close help', '关闭帮助', 'Tutup bantuan'],
    noAlerts: ['No alert categories are selected. You can turn them back on in Notifications.', '未选择提醒类别。您可以在通知中重新开启。', 'Tiada kategori makluman dipilih. Anda boleh mengaktifkannya semula dalam Pemberitahuan.'],
    noName: ['Name not provided', '未提供姓名', 'Nama belum diberikan'],
    noEmail: ['Email not provided', '未提供邮箱', 'E-mel belum diberikan'],
    settings: ['Settings', '设置', 'Tetapan']
  };

  function init(role, alertExamples, onPreferencesChanged = () => {}) {
    const page = document.querySelector(`[data-settings-role="${role}"]`);
    if (!page || page.dataset.initialized) return;
    page.dataset.initialized = 'true';
    const form = page.querySelector('[data-account-form]');
    const name = form.elements.full_name;
    const email = form.elements.email;
    const password = form.elements.password;
    const confirmation = form.elements.password_confirmation;
    const accountStatus = page.querySelector('[data-account-status]');
    const preferenceStatus = page.querySelector('[data-preference-status]');
    const preferenceControls = [...page.querySelectorAll('[data-preference]')];
    const notificationControls = [...page.querySelectorAll('[data-notification]')];
    const dialog = page.querySelector('.settings-dialog');
    const helpContent = page.querySelector('[data-help-content]');
    const editButton = page.querySelector('[data-edit-account]');
    const record = page.querySelector('[data-account-record]');
    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
    const storageKey = page.dataset.userId ? `axiody.settings.v1.${role}.${page.dataset.userId}` : null;
    const state = { preferences: {}, notifications: {}, profile: null };
    let savedProfile = { full_name: name.value, email: email.value };
    let saving = false;
    let activeHelp = '';
    let helpTrigger = null;
    let storageFailed = false;

    // A backend can supply account_update_url and a CSRF token through template context.
    // Contract: authenticated POST form data; JSON {account: {full_name, email}} on success.
    let accountUrl = null;
    try {
      if (page.dataset.accountUrl) {
        const candidate = new URL(page.dataset.accountUrl, location.href);
        if (candidate.origin === location.origin && ['http:', 'https:'].includes(candidate.protocol)) accountUrl = candidate;
      }
    } catch (_) { /* An invalid endpoint never receives account data. */ }

    function languageIndex() {
      return { 'en-SG': 0, 'zh-Hans': 1, ms: 2 }[state.preferences.language] ?? 0;
    }
    function message(key) { return messages[key][languageIndex()]; }
    function status(element, key, error = false) {
      element.dataset.statusKey = key;
      element.dataset.error = String(error);
      element.textContent = key ? message(key) : '';
    }
    function allowed(control, value) {
      return preferenceControls.some(item => item.name === control.name &&
        (item.tagName === 'SELECT' ? [...item.options].some(option => option.value === value) : item.value === value));
    }
    function readPreferences() {
      for (const control of preferenceControls) {
        if (control.type !== 'radio' || control.checked) state.preferences[control.name] = control.value;
      }
      for (const control of notificationControls) state.notifications[control.name] = control.checked;
    }
    readPreferences();
    if (storageKey) {
      try {
        const stored = JSON.parse(localStorage.getItem(storageKey) || 'null');
        if (stored && typeof stored === 'object') {
          for (const control of preferenceControls) {
            const value = stored.preferences?.[control.name];
            if (typeof value === 'string' && allowed(control, value)) state.preferences[control.name] = value;
          }
          for (const control of notificationControls) {
            if (typeof stored.notifications?.[control.name] === 'boolean') state.notifications[control.name] = stored.notifications[control.name];
          }
          if (!accountUrl && typeof stored.profile?.full_name === 'string' && typeof stored.profile?.email === 'string') {
            savedProfile = { full_name: stored.profile.full_name.slice(0, 100), email: stored.profile.email.slice(0, 254) };
            state.profile = { ...savedProfile };
          }
        }
      } catch (_) { storageFailed = true; }
    }

    function persist() {
      if (!storageKey) return false;
      try {
        localStorage.setItem(storageKey, JSON.stringify(state));
        storageFailed = false;
        return true;
      } catch (_) {
        storageFailed = true;
        return false;
      }
    }
    function updateRecord() {
      record.querySelector('[data-record-name]').textContent = savedProfile.full_name || message('noName');
      record.querySelector('[data-record-email]').textContent = savedProfile.email || message('noEmail');
    }
    function passwordLabels() {
      for (const button of form.querySelectorAll('.settings-password-toggle')) {
        button.setAttribute('aria-label', message(button.getAttribute('aria-pressed') === 'true' ? 'hidePassword' : 'showPassword'));
      }
    }
    function translate(root = page) {
      const lang = { 'en-SG': 'en', 'zh-Hans': 'zh', ms: 'ms' }[state.preferences.language] || 'en';
      for (const element of root.querySelectorAll('[data-en]')) element.textContent = element.dataset[lang] || element.dataset.en;
    }
    function applyTheme() {
      page.dataset.theme = state.preferences.theme === 'system' ? (systemTheme.matches ? 'dark' : 'light') : state.preferences.theme;
    }
    function renderPreview() {
      const list = helpContent.querySelector('[data-alert-preview]');
      if (!list) return;
      list.replaceChildren();
      for (const control of notificationControls) {
        if (!state.notifications[control.name]) continue;
        const item = document.createElement('li');
        const heading = document.createElement('strong');
        const example = document.createElement('p');
        heading.textContent = control.closest('label').querySelector('[data-en]').textContent;
        example.textContent = alertExamples[control.name][languageIndex()];
        item.append(heading, example);
        list.append(item);
      }
      if (!list.childElementCount) {
        const item = document.createElement('li');
        item.textContent = message('noAlerts');
        list.append(item);
      }
    }
    function applyPreferences() {
      for (const control of preferenceControls) {
        if (control.type === 'radio') control.checked = state.preferences[control.name] === control.value;
        else control.value = state.preferences[control.name];
      }
      for (const control of notificationControls) control.checked = state.notifications[control.name];
      page.dataset.fontSize = state.preferences.fontSize;
      page.lang = state.preferences.language;
      applyTheme();
      translate();
      passwordLabels();
      updateRecord();
      document.title = `${message('settings')} | AXIODY`;
      page.querySelector('.settings-dialog-x').setAttribute('aria-label', message('closeHelp'));
      for (const element of [accountStatus, preferenceStatus]) {
        if (element.dataset.statusKey) element.textContent = message(element.dataset.statusKey);
      }
      if (activeHelp && helpTrigger) {
        page.querySelector('#settings-dialog-title').textContent = helpTrigger.querySelector('strong')?.textContent || helpTrigger.querySelector('[data-en]').textContent;
        renderPreview();
      }
      onPreferencesChanged(page, { ...state.preferences });
      // Future dashboard/notification consumers can subscribe without sharing account credentials.
      page.dispatchEvent(new CustomEvent('axiody:settings-change', {
        bubbles: true, detail: { role, preferences: { ...state.preferences }, notifications: { ...state.notifications } }
      }));
    }
    function changedPreference() {
      readPreferences();
      const saved = persist();
      applyPreferences();
      status(preferenceStatus, saved ? 'saved' : storageKey ? 'storageError' : 'temporary', !saved && !!storageKey);
    }
    for (const control of [...preferenceControls, ...notificationControls]) control.addEventListener('change', changedPreference);
    systemTheme.addEventListener('change', applyTheme);

    function setBusy(busy) {
      saving = busy;
      form.setAttribute('aria-busy', String(busy));
      for (const control of form.querySelectorAll('input, button')) control.disabled = busy;
      if (!accountUrl) {
        password.disabled = confirmation.disabled = true;
        for (const button of form.querySelectorAll('.settings-password-toggle')) button.disabled = true;
      }
    }
    function clearPasswords() {
      password.value = confirmation.value = '';
      password.type = confirmation.type = 'password';
      password.setCustomValidity('');
      confirmation.setCustomValidity('');
      for (const button of form.querySelectorAll('.settings-password-toggle')) button.setAttribute('aria-pressed', 'false');
      passwordLabels();
    }
    function resetAccount() {
      name.value = savedProfile.full_name;
      email.value = savedProfile.email;
      name.setCustomValidity('');
      clearPasswords();
      updateRecord();
    }
    function dirty() {
      return name.value !== savedProfile.full_name || email.value !== savedProfile.email || password.value !== '' || confirmation.value !== '';
    }
    for (const button of form.querySelectorAll('.settings-password-toggle')) {
      button.addEventListener('click', () => {
        const input = document.getElementById(button.getAttribute('aria-controls'));
        input.type = input.type === 'password' ? 'text' : 'password';
        button.setAttribute('aria-pressed', String(input.type === 'text'));
        passwordLabels();
      });
    }
    form.addEventListener('input', () => {
      name.setCustomValidity('');
      password.setCustomValidity('');
      confirmation.setCustomValidity('');
      status(accountStatus, '');
    });
    page.querySelector('[data-close-account]').addEventListener('click', () => {
      if (saving) return;
      resetAccount();
      form.hidden = true;
      record.hidden = false;
      editButton.hidden = false;
      editButton.setAttribute('aria-expanded', 'false');
      status(accountStatus, 'discarded');
      editButton.focus();
    });
    editButton.addEventListener('click', () => {
      form.hidden = false;
      record.hidden = true;
      editButton.hidden = true;
      editButton.setAttribute('aria-expanded', 'true');
      status(accountStatus, '');
      name.focus();
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (saving) return;
      name.value = name.value.trim();
      email.value = email.value.trim();
      name.setCustomValidity(name.value ? '' : message('nameRequired'));
      if (accountUrl) {
        const strong = password.value.length >= 8 && /[\p{L}]/u.test(password.value) && /[0-9]/.test(password.value) && /[^\p{L}\p{N}\s]/u.test(password.value);
        password.setCustomValidity(password.value && !strong ? message('passwordWeak') : '');
        confirmation.setCustomValidity(password.value !== confirmation.value ? message('passwordMismatch') : '');
      }
      if (!form.reportValidity()) return;
      const nextProfile = { full_name: name.value, email: email.value };
      if (!accountUrl) {
        const previousProfile = state.profile;
        state.profile = nextProfile;
        if (storageKey && !persist()) {
          state.profile = previousProfile;
          status(accountStatus, 'storageError', true);
          return;
        }
        savedProfile = nextProfile;
        resetAccount();
        status(accountStatus, storageKey ? 'localSaved' : 'temporary');
        return;
      }
      // Collect the form before disabling controls; never put passwords in storage or URLs.
      const payload = new FormData(form);
      if (!password.value) {
        payload.delete('password');
        payload.delete('password_confirmation');
      }
      setBusy(true);
      status(accountStatus, 'saving');
      const abort = new AbortController();
      const timeout = setTimeout(() => abort.abort(), 15000);
      try {
        const response = await fetch(accountUrl, {
          method: 'POST', body: payload, credentials: 'same-origin',
          headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          signal: abort.signal, redirect: 'error'
        });
        if (!response.ok) throw new Error('Account update failed');
        const result = await response.json();
        if (typeof result.account?.full_name !== 'string' || typeof result.account?.email !== 'string') throw new Error('Account update was not confirmed');
        savedProfile = { full_name: result.account.full_name, email: result.account.email };
        resetAccount();
        status(accountStatus, 'accountSaved');
      } catch (_) {
        status(accountStatus, 'saveError', true);
      } finally {
        clearTimeout(timeout);
        setBusy(false);
      }
    });
    window.addEventListener('beforeunload', event => {
      if (!dirty()) return;
      event.preventDefault();
      event.returnValue = '';
    });

    for (const trigger of page.querySelectorAll('[data-help]')) {
      trigger.addEventListener('click', () => {
        activeHelp = trigger.dataset.help;
        helpTrigger = trigger;
        const template = page.querySelector(`#${activeHelp}`);
        if (!template) return;
        helpContent.replaceChildren(template.content.cloneNode(true));
        translate(helpContent);
        page.querySelector('#settings-dialog-title').textContent = trigger.querySelector('strong')?.textContent || trigger.querySelector('[data-en]').textContent;
        renderPreview();
        dialog.showModal();
      });
    }
    for (const button of dialog.querySelectorAll('[data-dismiss]')) button.addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => {
      const bounds = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
    });
    dialog.addEventListener('close', () => {
      activeHelp = '';
      helpTrigger?.focus();
    });
    setBusy(false);
    resetAccount();
    applyPreferences();
    if (storageFailed) status(preferenceStatus, 'storageError', true);
  }
  return { init };
})();

window.AxiodySettings.init('client', {
  reminders: ['A requested document is approaching its submission deadline.', '所需文档即将到达提交截止日期。', 'Dokumen yang diminta menghampiri tarikh akhir penyerahan.'],
  status: ['A reviewed document has a status update. Open the feedback to see the next step.', '已审核文档的状态有更新。打开反馈查看下一步。', 'Dokumen yang disemak mempunyai kemas kini status. Buka maklum balas untuk langkah seterusnya.'],
  announcements: ['An important service announcement is available for clients.', '有一则面向客户的重要服务公告。', 'Pengumuman perkhidmatan penting tersedia untuk pelanggan.'],
  promotions: ['An optional product update or offer is available by email.', '可通过邮件接收可选的产品更新或优惠。', 'Kemas kini produk atau tawaran pilihan tersedia melalui e-mel.']
});
