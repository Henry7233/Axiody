(() => {
  "use strict";

  const page = document.querySelector(".verification-page");
  if (!page) return;

  const fieldsContainer = document.getElementById("fieldsContainer");
  const toast = document.getElementById("toast");
  const previewMeta = document.getElementById("previewMeta");
  const documentType = document.getElementById("documentType");
  const documentConfidence = document.getElementById("documentConfidence");
  const previewImage = document.getElementById("previewImage");
  const previewPlaceholder = document.getElementById("previewPlaceholder");

  const client = page.dataset.client || "Selected client";
  const documentId = page.dataset.documentId || "document";
  const fields = [
    ["Client", client],
    ["Document ID", documentId],
    ["Invoice Number", "INV-2026-091"],
    ["Document Date", "2026-09-03"],
    ["Amount", "SGD 4,280.00"],
    ["Tax", "SGD 385.20"],
  ];

  previewMeta.textContent = `${client} · ${documentId}`;
  documentType.textContent = "Invoice";
  documentConfidence.textContent = "92% confidence";

  previewImage.addEventListener("error", () => {
    previewImage.hidden = true;
    previewPlaceholder.hidden = false;
  });

  fieldsContainer.replaceChildren(...fields.map(([label, value]) => {
    const wrapper = document.createElement("label");
    wrapper.className = "form-field";
    wrapper.innerHTML = `<span>${label}</span><input value="${value}">`;
    return wrapper;
  }));

  function show(message) {
    toast.textContent = message;
    toast.classList.add("toast--visible");
  }

  document.getElementById("saveBtn")?.addEventListener("click", () => show("Changes saved for review."));
  document.getElementById("rejectBtn")?.addEventListener("click", () => show("Document rejected."));
  document.getElementById("verifyForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    show("Document approved.");
  });
})();
