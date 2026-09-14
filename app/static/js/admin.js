(() => {
  'use strict';

  const reminderPage = document.querySelector('[data-reminder-page]');

  if (reminderPage) {
    const periodSelect = reminderPage.querySelector('[data-reminder-period]');
    const clientSelect = reminderPage.querySelector('[data-reminder-client]');
    const rows = Array.from(reminderPage.querySelectorAll('[data-reminder-row]'));
    const emptyState = reminderPage.querySelector('[data-reminder-empty]');
    const countLabel = reminderPage.querySelector('[data-reminder-count]');
    const totalFollowups = reminderPage.querySelector('[data-reminder-total]');
    const totalEmails = reminderPage.querySelector('[data-reminder-emails]');

    const updateSummary = (visibleRows, sentTotal) => {
      if (totalFollowups) {
        totalFollowups.textContent = String(visibleRows);
      }
      if (totalEmails) {
        totalEmails.textContent = String(sentTotal);
      }
      if (countLabel) {
        countLabel.textContent = `Showing ${visibleRows} of ${rows.length} reminders`;
      }
    };

    const applyFilters = () => {
      const selectedPeriod = periodSelect ? periodSelect.value : 'all';
      const selectedClient = clientSelect ? clientSelect.value : 'all';
      let visibleRows = 0;
      let sentTotal = 0;

      rows.forEach((row) => {
        const matchesPeriod = selectedPeriod === 'all' || row.dataset.period === selectedPeriod;
        const matchesClient = selectedClient === 'all' || row.dataset.client === selectedClient;
        const shouldShow = matchesPeriod && matchesClient;

        row.hidden = !shouldShow;

        if (shouldShow) {
          visibleRows += 1;
          sentTotal += Number(row.dataset.emailCount || 0);
        }
      });

      if (emptyState) {
        emptyState.hidden = visibleRows !== 0;
      }

      updateSummary(visibleRows, sentTotal);
    };

    [periodSelect, clientSelect].forEach((control) => {
      if (control) {
        control.addEventListener('change', applyFilters);
      }
    });

    applyFilters();
    return;
  }

  if (!window.AxiodySettings) return;
  window.AxiodySettings.init('admin', {
    registrations: 'A new client account is ready for onboarding checks.',
    submissions: 'A client has submitted documents for processing and review.',
    lowConfidence: 'A suggested document classification needs verification against the original file.',
    humanReview: 'A document has been flagged for a human review decision.',
    overdue: 'A client still has an outstanding document after its deadline.',
    escalations: 'An unresolved reminder needs follow-up from the responsible administrator.',
    weekly: 'A weekly digest summarizes registrations, submissions and outstanding reviews.'
  }, (page, preferences) => {
    const summary = page.querySelector('[data-workspace-summary]');
    const view = page.querySelector('[name="dashboardView"]').selectedOptions[0].textContent;
    const sort = page.querySelector('[name="documentSort"]').selectedOptions[0].textContent;
    summary.textContent = `${view} - ${sort} - ${preferences.pageSize} items per page`;
  });
})();
