(() => {
  'use strict';

  const reminderPage = document.querySelector('[data-reminder-page]');

  if (reminderPage) {
    const periodSelect = reminderPage.querySelector('[data-reminder-period]');
    const clientSelect = reminderPage.querySelector('[data-reminder-client]');
    [periodSelect, clientSelect].forEach((control) => {
      if (control) {
        control.addEventListener('change', () => control.form.requestSubmit());
      }
    });

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
  });
})();
