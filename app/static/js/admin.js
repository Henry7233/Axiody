// Admin settings use the shared controller from client.js, loaded first by the template.
(() => {
  'use strict';
  if (!window.AxiodySettings) return;
  window.AxiodySettings.init('admin', {
    registrations: ['A new client account is ready for onboarding checks.', '新的客户账户已准备好进行入职检查。', 'Akaun pelanggan baharu sedia untuk semakan pendaftaran.'],
    submissions: ['A client has submitted documents for processing and review.', '客户已提交文档，等待处理和审核。', 'Pelanggan telah menyerahkan dokumen untuk pemprosesan dan semakan.'],
    lowConfidence: ['A suggested document classification needs verification against the original file.', '建议的文档分类需要对照原始文件核实。', 'Pengelasan dokumen yang dicadangkan perlu disahkan dengan fail asal.'],
    humanReview: ['A document has been flagged for a human review decision.', '一份文档已被标记，需要人工审核决定。', 'Dokumen ditandakan untuk keputusan semakan manusia.'],
    overdue: ['A client still has an outstanding document after its deadline.', '截止日期已过，客户仍有未提交的文档。', 'Pelanggan masih mempunyai dokumen tertunggak selepas tarikh akhir.'],
    escalations: ['An unresolved reminder needs follow-up from the responsible administrator.', '未解决的提醒需要负责的管理员跟进。', 'Peringatan yang belum selesai memerlukan susulan pentadbir bertanggungjawab.'],
    weekly: ['A weekly digest summarizes registrations, submissions and outstanding reviews.', '每周摘要汇总注册、提交和待审核项目。', 'Ringkasan mingguan merangkumi pendaftaran, penyerahan dan semakan tertunggak.']
  }, (page, preferences) => {
    const summary = page.querySelector('[data-workspace-summary]');
    const view = page.querySelector('[name="dashboardView"]').selectedOptions[0].textContent;
    const sort = page.querySelector('[name="documentSort"]').selectedOptions[0].textContent;
    const perPage = { 'en-SG': 'items per page', 'zh-Hans': '条 / 页', ms: 'item setiap halaman' }[preferences.language];
    summary.textContent = `${view} · ${sort} · ${preferences.pageSize} ${perPage}`;
  });
})();
