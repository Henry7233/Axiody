(() => {
  "use strict";

  const page = document.querySelector(".verification-page");
  if (!page) return;

  const form = document.getElementById("verifyForm");
  const fields = document.getElementById("reviewFields");
  const toast = document.getElementById("toast");
  const previewImage = document.getElementById("previewImage");
  const previewPlaceholder = document.getElementById("previewPlaceholder");
  const decisionModal = document.getElementById("decisionModal");
  const decisionModalIcon = document.getElementById("decisionModalIcon");
  const decisionModalTitle = document.getElementById("decisionModalTitle");
  const decisionModalMessage = document.getElementById("decisionModalMessage");
  const decisionModalClose = document.getElementById("decisionModalClose");

  function hideFailedPreview() {
    previewImage.hidden = true;
    previewPlaceholder.hidden = false;
  }
  if (previewImage) {
    previewImage.addEventListener("error", hideFailedPreview);
    if (previewImage.complete && !previewImage.naturalWidth) hideFailedPreview();
  }

  function show(message) {
    toast.textContent = message;
    toast.classList.add("toast--visible");
  }

  function showDecisionModal(action, message) {
    if (!decisionModal) return;
    const approved = action === "approved";
    decisionModal.classList.remove("decision-modal--approved", "decision-modal--rejected");
    decisionModal.classList.add(approved ? "decision-modal--approved" : "decision-modal--rejected");
    decisionModalIcon.textContent = approved ? "\u2713" : "\u00d7";
    decisionModalTitle.textContent = approved ? "Document Approved" : "Document Rejected";
    decisionModalMessage.textContent = message;
    decisionModal.showModal();
  }

  async function saveReview(action) {
    if (fields.disabled || (action !== "rejected" && !form.reportValidity())) return;
    const payload = action === "rejected" ? {} : Object.fromEntries(new FormData(form));
    payload.action = action;
    fields.disabled = true;
    show("Saving...");
    try {
      const response = await fetch(page.dataset.reviewUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Review-Token": page.dataset.reviewToken },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || response.redirected) throw new Error(result.message || "Unable to save. Reload the page and try again.");
      show(result.message);
      if (action === "approved" || action === "rejected") showDecisionModal(action, result.message);
      if (payload.document_type) document.getElementById("documentType").textContent = payload.document_type;
      if (payload.title) document.getElementById("verify-title").textContent = payload.title;
      if (action === "saved") {
        fields.disabled = false;
      } else {
        document.getElementById("reviewStatus").textContent = "Classification status: Success";
      }
    } catch (error) {
      fields.disabled = false;
      show(error.message);
    }
  }

  document.getElementById("saveBtn").addEventListener("click", () => saveReview("saved"));
  document.getElementById("rejectBtn").addEventListener("click", () => saveReview("rejected"));
  decisionModalClose?.addEventListener("click", () => {
    window.location.assign(page.dataset.queueUrl);
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    saveReview("approved");
  });
})();
