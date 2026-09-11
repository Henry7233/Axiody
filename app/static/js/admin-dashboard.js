(() => {
  "use strict";

  const tableBody = document.getElementById("clientTableBody");
  const statsGrid = document.getElementById("statsGrid");
  if (!tableBody && !statsGrid) return;

  const clients = [
    { name: "Acme Supplies", period: "Sep 2026", submitted: 4, bookkept: 3, underReview: 1 },
    { name: "Northstar Foods", period: "Sep 2026", submitted: 2, bookkept: 0, underReview: 2 },
    { name: "Greenline Studio", period: "Sep 2026", submitted: 6, bookkept: 6, underReview: 0 },
  ];

  const totals = [
    ["Clients", clients.length],
    ["Documents", clients.reduce((sum, client) => sum + client.submitted, 0)],
    ["Under review", clients.reduce((sum, client) => sum + client.underReview, 0)],
    ["Bookkept", clients.reduce((sum, client) => sum + client.bookkept, 0)],
  ];

  if (statsGrid) {
    statsGrid.replaceChildren(...totals.map(([label, value]) => {
      const card = document.createElement("article");
      card.className = "stat-card";
      card.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
      return card;
    }));
  }

  if (tableBody) tableBody.replaceChildren(...clients.map((client) => {
    const reviewUrl = tableBody.dataset.reviewUrl || "/admin/reviews";
    const row = document.createElement("tr");
    const link = new URL(reviewUrl, window.location.origin);
    link.searchParams.set("client", client.name);
    row.innerHTML = `
      <td>${client.name}</td>
      <td>${client.period}</td>
      <td>${client.submitted}</td>
      <td>${client.bookkept}</td>
      <td>${client.underReview}</td>
      <td><a class="btn btn--secondary" href="${link.pathname + link.search}">Review</a></td>
    `;
    return row;
  }));
})();
