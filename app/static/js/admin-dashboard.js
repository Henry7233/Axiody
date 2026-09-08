(() => {
  "use strict";

  const tableBody = document.getElementById("clientTableBody");
  const statsGrid = document.getElementById("statsGrid");
  if (!tableBody || !statsGrid) return;

  const reviewUrl = tableBody.dataset.reviewUrl || "/admin/reviews";
  const clients = [
    { name: "Acme Supplies", period: "Sep 2026", documents: 4, missing: 1, status: "Needs review" },
    { name: "Northstar Foods", period: "Sep 2026", documents: 2, missing: 2, status: "Pending files" },
    { name: "Greenline Studio", period: "Sep 2026", documents: 6, missing: 0, status: "Ready" },
  ];

  const totals = [
    ["Clients", clients.length],
    ["Documents", clients.reduce((sum, client) => sum + client.documents, 0)],
    ["Missing", clients.reduce((sum, client) => sum + client.missing, 0)],
    ["Ready", clients.filter((client) => client.status === "Ready").length],
  ];

  statsGrid.replaceChildren(...totals.map(([label, value]) => {
    const card = document.createElement("article");
    card.className = "stat-card";
    card.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    return card;
  }));

  tableBody.replaceChildren(...clients.map((client) => {
    const row = document.createElement("tr");
    const link = new URL(reviewUrl, window.location.origin);
    link.searchParams.set("client", client.name);
    row.innerHTML = `
      <td>${client.name}</td>
      <td>${client.period}</td>
      <td>${client.documents}</td>
      <td>${client.missing}</td>
      <td>${client.status}</td>
      <td><a class="btn btn--secondary" href="${link.pathname + link.search}">Review</a></td>
    `;
    return row;
  }));
})();
