// Admin settings use the shared controller from settings.js, loaded first by the template.
(() => {
  'use strict';
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
