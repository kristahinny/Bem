const state = {
  token: localStorage.getItem("finance_token"),
  user: null,
  view: "dashboard",
  categories: [],
  expenses: [],
  incomes: [],
  users: [],
  goals: [],
  importRows: [],
  managedCategories: [],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const on = (selector, event, handler) => {
  const element = $(selector);
  if (element) element.addEventListener(event, handler);
};
const money = (value) => Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const fmtDate = (value) => value ? value.split("-").reverse().join("/") : "";

const months = [
  "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
];

function authHeaders() {
  return state.token ? { Authorization: `Bearer ${state.token}` } : {};
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  if (response.status === 401) {
    logout(false);
    throw new Error("Login necessario");
  }
  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: "Erro inesperado" }));
    throw new Error(err.error || "Erro inesperado");
  }
  if (response.headers.get("content-type")?.includes("application/json")) return response.json();
  return response;
}

function toast(message) {
  const box = $("#toast");
  box.textContent = message;
  box.classList.remove("hidden");
  setTimeout(() => box.classList.add("hidden"), 2800);
}

function setupPeriod() {
  const now = new Date();
  $("#filterMonth").innerHTML = months.map((m, i) => `<option value="${i + 1}">${m}</option>`).join("");
  $("#filterMonth").value = now.getMonth() + 1;
  $("#filterYear").value = now.getFullYear();
  $("#filterMonth").addEventListener("change", refreshAll);
  $("#filterYear").addEventListener("change", refreshAll);
}

function query(extra = {}) {
  const params = new URLSearchParams({
    month: $("#filterMonth")?.value || "",
    year: $("#filterYear")?.value || "",
    ...extra,
  });
  if (state.user?.profile === "superadmin" && $("#filterUser")?.value) {
    params.set("user_id", $("#filterUser").value);
  }
  Object.entries(extra).forEach(([k, v]) => { if (!v) params.delete(k); });
  return params.toString();
}

function showApp() {
  $("#loginScreen").classList.add("hidden");
  $("#appShell").classList.remove("hidden");
  const isSuperAdmin = state.user?.profile === "superadmin";
  $$(".admin-only").forEach((el) => el.classList.toggle("hidden", !isSuperAdmin));
}

function showLogin() {
  $("#loginScreen").classList.remove("hidden");
  $("#appShell").classList.add("hidden");
}

function showRegisterForm() {
  $("#loginForm")?.classList.add("hidden");
  $("#registerForm")?.classList.remove("hidden");
  if ($("#loginMsg")) $("#loginMsg").textContent = "";
  if ($("#registerMsg")) $("#registerMsg").textContent = "";
}

function showLoginForm(message = "") {
  $("#registerForm")?.classList.add("hidden");
  $("#loginForm")?.classList.remove("hidden");
  if ($("#registerMsg")) $("#registerMsg").textContent = "";
  if ($("#loginMsg")) $("#loginMsg").textContent = message;
}

function setView(view) {
  if (view === "users" && state.user?.profile !== "superadmin") {
    toast("Acesso permitido somente para o SuperAdmin.");
    view = "dashboard";
  }
  state.view = view;
  const titles = { dashboard: "Dashboard", expenses: "Contas a pagar", incomes: "Receitas", goals: "Metas", reports: "Relatorios", users: "Usuarios", settings: "Senha" };
  $("#viewTitle").textContent = titles[view];
  $$(".view").forEach((el) => el.classList.add("hidden"));
  $(`#${view}View`).classList.remove("hidden");
  $$(".nav-btn").forEach((btn) => btn.classList.toggle("active", btn.dataset.view === view));
  refreshAll();
}

async function loadCategories() {
  const data = await api("/api/categories");
  state.categories = data.categories;
  const opts = data.categories.map((c) => `<option>${c}</option>`).join("");
  $$('select[name="category"]').forEach((select) => select.innerHTML = opts);
  $("#expenseCategory").innerHTML = `<option value="">Todas categorias</option>${opts}`;
  $("#incomeCategory").innerHTML = `<option value="">Todas categorias</option>${opts}`;
}

async function loadUserOptions() {
  if (state.user?.profile !== "superadmin") return;
  const data = await api("/api/users");
  state.users = data.users;
  const options = data.users.map((user) => `<option value="${user.id}">${escapeHtml(user.full_name || user.username)} (${escapeHtml(user.username)})</option>`).join("");
  const select = $("#filterUser");
  if (select) {
    select.innerHTML = `<option value="">Todos os usuarios</option>${options}`;
  }
}

async function loadManagedCategories() {
  if (state.user?.profile !== "superadmin") return;
  const data = await api("/api/categories/manage");
  state.managedCategories = data.categories;
  const target = $("#categoryList");
  if (!target) return;
  target.innerHTML = data.categories.map((category) => `
    <div class="mini-item">
      <strong>${escapeHtml(category.name)}</strong>
      <button class="danger" onclick="deleteCategory(${category.id})">Excluir</button>
    </div>
  `).join("");
}

async function loadDashboard() {
  const data = await api(`/api/dashboard?${query()}`);
  $("#cardPending").textContent = money(data.cards.total_pending);
  $("#cardPaid").textContent = money(data.cards.total_paid);
  $("#cardIncome").textContent = money(data.cards.total_income);
  $("#cardExpenses").textContent = money(data.cards.total_expenses);
  $("#cardMonthBalance").textContent = money(data.cards.month_balance);
  $("#cardExpected").textContent = money(data.cards.expected_balance);
  $("#cardReal").textContent = money(data.cards.real_balance);
  $("#cardGoals").textContent = money(data.cards.goals_total);
  $("#cardFutureInstallments").textContent = money(data.cards.future_installments);
  $("#cardOverdue").textContent = data.cards.overdue_count;
  $("#cardUpcoming").textContent = data.cards.upcoming_count;
  renderMiniList("#overdueList", data.overdue);
  renderMiniList("#upcomingList", data.upcoming);
  await loadCharts();
}

async function loadCharts() {
  const data = await api(`/api/charts?${query()}`);
  renderBars("#chartIncomes", data.incomes, "income");
  renderBars("#chartExpenses", data.expenses, "expense");
  renderBars("#chartBalances", data.balances, "balance");
  renderBars("#chartGoals", data.goals, "goal");
}

function renderBars(selector, values, cls) {
  const target = $(selector);
  if (!target) return;
  const max = Math.max(...values.map((v) => Math.abs(Number(v))), 1);
  target.innerHTML = values.map((value) => {
    const height = Math.max((Math.abs(Number(value)) / max) * 120, 3);
    return `<span class="bar ${cls}" style="height:${height}px" title="${money(value)}"></span>`;
  }).join("");
}

function renderMiniList(selector, items) {
  const target = $(selector);
  if (!items.length) {
    target.innerHTML = `<p class="message">Nenhum registro encontrado.</p>`;
    return;
  }
  target.innerHTML = items.map((item) => `
    <div class="mini-item">
      <div><strong>${escapeHtml(item.description)}</strong><br><span>${escapeHtml(item.category)} - ${fmtDate(item.due_date)}</span></div>
      <strong>${money(item.amount)}</strong>
    </div>
  `).join("");
}

async function loadExpenses() {
  const status = $("#expenseStatus")?.value || "";
  const category = $("#expenseCategory")?.value || "";
  const data = await api(`/api/expenses?${query({ status, category })}`);
  state.expenses = data.expenses;
  $("#expenseCount").textContent = data.expenses.length;
  $("#expensesTable").innerHTML = data.expenses.map((item) => `
    <tr>
      <td>${escapeHtml(item.description)}</td>
      <td>${escapeHtml(item.category)}</td>
      <td>${money(item.amount)}</td>
      <td>${fmtDate(item.due_date)}</td>
      <td><span class="pill ${item.status}">${item.status}</span></td>
      <td>${item.installment_total ? `${item.installment_number}/${item.installment_total}` : "-"}</td>
      <td class="actions">
        ${item.status !== "Pago" ? `<button class="success" onclick="payExpense(${item.id})">Pagar</button>` : ""}
        ${item.installment_group ? `<button class="danger" onclick="cancelFutureInstallments(${item.id})">Cancelar futuras</button>` : ""}
        <button class="edit" onclick="editExpense(${item.id})">Editar</button>
        <button class="danger" onclick="deleteExpense(${item.id})">Excluir</button>
      </td>
    </tr>
  `).join("") || `<tr><td colspan="7">Nenhuma conta cadastrada.</td></tr>`;
}

async function loadIncomes() {
  const status = $("#incomeStatus")?.value || "";
  const category = $("#incomeCategory")?.value || "";
  const data = await api(`/api/incomes?${query({ status, category })}`);
  state.incomes = data.incomes;
  $("#incomeCount").textContent = data.incomes.length;
  $("#incomesTable").innerHTML = data.incomes.map((item) => `
    <tr>
      <td>${escapeHtml(item.description)}</td>
      <td>${escapeHtml(item.category)}</td>
      <td>${money(item.amount)}</td>
      <td>${fmtDate(item.receipt_date)}</td>
      <td><span class="pill ${item.status}">${item.status}</span></td>
      <td class="actions">
        <button class="edit" onclick="editIncome(${item.id})">Editar</button>
        <button class="danger" onclick="deleteIncome(${item.id})">Excluir</button>
      </td>
    </tr>
  `).join("") || `<tr><td colspan="6">Nenhuma receita cadastrada.</td></tr>`;
}

async function loadReport() {
  const data = await api(`/api/report?${query({ type: $("#reportType").value })}`);
  $("#reportIncome").textContent = money(data.summary.total_income);
  $("#reportExpense").textContent = money(data.summary.total_expense);
  $("#reportBalance").textContent = money(data.summary.final_balance);
  $("#paidReport").innerHTML = reportRows(data.paid_expenses, "due_date");
  $("#pendingReport").innerHTML = reportRows(data.pending_expenses, "due_date");
  await loadCashflow();
}

async function loadCashflow() {
  const data = await api(`/api/cashflow?${query()}`);
  $("#cashflowTable").innerHTML = data.cashflow.map((row) => `
    <tr><td>${row.month}</td><td>${money(row.incomes)}</td><td>${money(row.expenses)}</td><td>${money(row.goals)}</td><td>${money(row.balance)}</td></tr>
  `).join("");
}

async function loadGoals() {
  const data = await api(`/api/goals?${query()}`);
  state.goals = data.goals;
  $("#goalCount").textContent = data.goals.length;
  $("#goalsList").innerHTML = data.goals.map((goal) => `
    <article class="goal-item">
      <div class="section-head">
        <div><strong>${escapeHtml(goal.name)}</strong><br><span class="message">${escapeHtml(goal.description || "")}</span></div>
        <span class="pill ${goal.status}">${goal.status}</span>
      </div>
      <div class="progress"><span style="width:${goal.percent_complete}%"></span></div>
      <div>${money(goal.current_amount)} de ${money(goal.target_amount)} | Falta ${money(goal.remaining_amount)} | ${goal.percent_complete}% | Previsao: ${escapeHtml(goal.forecast)}</div>
      <div class="actions">
        <button class="edit" onclick="editGoal(${goal.id})">Editar</button>
        <button class="success" onclick="changeGoalAmount(${goal.id}, 'add')">Adicionar valor</button>
        <button class="edit" onclick="changeGoalAmount(${goal.id}, 'withdraw')">Retirar valor</button>
        <button class="danger" onclick="deleteGoal(${goal.id})">Excluir</button>
      </div>
    </article>
  `).join("") || `<p class="message">Nenhuma meta cadastrada.</p>`;
}

async function loadUsers() {
  const data = await api("/api/users");
  state.users = data.users;
  $("#userCount").textContent = data.users.length;
  $("#usersTable").innerHTML = data.users.map((item) => `
    <tr>
      <td>${escapeHtml(item.full_name)}</td>
      <td>${escapeHtml(item.username)}</td>
      <td><span class="pill ${item.profile}">${item.profile}</span></td>
      <td><span class="pill ${item.active ? "Recebido" : "Vencido"}">${item.active ? "Ativo" : "Inativo"}</span></td>
      <td>${item.created_at ? fmtDate(item.created_at.slice(0, 10)) : ""}</td>
      <td class="actions">
        <button class="edit" onclick="editUser(${item.id})">Editar</button>
        <button class="edit" onclick="changeUserPassword(${item.id})">Senha</button>
        ${item.profile !== "superadmin" ? `<button class="success" onclick="toggleUser(${item.id})">${item.active ? "Desativar" : "Ativar"}</button>` : ""}
        ${item.profile !== "superadmin" ? `<button class="danger" onclick="deleteUser(${item.id})">Excluir</button>` : ""}
      </td>
    </tr>
  `).join("") || `<tr><td colspan="6">Nenhum usuario cadastrado.</td></tr>`;
  await loadManagedCategories();
}

function reportRows(items, dateField) {
  return items.map((item) => `
    <tr><td>${escapeHtml(item.description)}</td><td>${fmtDate(item[dateField])}</td><td>${money(item.amount)}</td><td><span class="pill ${item.status}">${item.status}</span></td></tr>
  `).join("") || `<tr><td>Nenhum registro.</td></tr>`;
}

async function refreshAll() {
  if (!state.token) return;
  try {
    if (state.view === "dashboard") await loadDashboard();
    if (state.view === "expenses") await loadExpenses();
    if (state.view === "incomes") await loadIncomes();
    if (state.view === "goals") await loadGoals();
    if (state.view === "reports") await loadReport();
    if (state.view === "users") await loadUsers();
  } catch (error) {
    toast(error.message);
  }
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function fillForm(form, item) {
  if (!form) return;
  Object.entries(item).forEach(([key, value]) => {
    if (form.elements[key]) form.elements[key].value = value ?? "";
  });
}

function clearForm(form) {
  if (!form || typeof form.reset !== "function") return;
  form.reset();
  if (form.elements.id) form.elements.id.value = "";
}

function setPeriodFromDate(value) {
  if (!value) return;
  const [year, month] = value.split("-");
  if (year && month && $("#filterYear") && $("#filterMonth")) {
    $("#filterYear").value = year;
    $("#filterMonth").value = String(Number(month));
  }
}

function clearUserFilterForOwnSave() {
  if (state.user?.profile === "superadmin" && $("#filterUser")) {
    $("#filterUser").value = "";
  }
}

function revealSavedExpense(data) {
  setPeriodFromDate(data.due_date);
  clearUserFilterForOwnSave();
  if ($("#expenseStatus") && $("#expenseStatus").value && $("#expenseStatus").value !== data.status) {
    $("#expenseStatus").value = "";
  }
  if ($("#expenseCategory") && $("#expenseCategory").value && $("#expenseCategory").value !== data.category) {
    $("#expenseCategory").value = "";
  }
}

function revealSavedIncome(data) {
  setPeriodFromDate(data.receipt_date);
  clearUserFilterForOwnSave();
  if ($("#incomeStatus") && $("#incomeStatus").value && $("#incomeStatus").value !== data.status) {
    $("#incomeStatus").value = "";
  }
  if ($("#incomeCategory") && $("#incomeCategory").value && $("#incomeCategory").value !== data.category) {
    $("#incomeCategory").value = "";
  }
}

async function saveExpense(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formData(form);
  const id = data.id;
  delete data.id;
  await api(id ? `/api/expenses/${id}` : "/api/expenses", { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
  revealSavedExpense(data);
  clearForm(form);
  toast("Conta salva.");
  await loadExpenses();
  if (state.view === "expenses") await loadDashboard().catch(() => {});
}

async function saveIncome(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formData(form);
  const id = data.id;
  delete data.id;
  await api(id ? `/api/incomes/${id}` : "/api/incomes", { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
  revealSavedIncome(data);
  clearForm(form);
  toast("Receita salva.");
  await loadIncomes();
  if (state.view === "incomes") await loadDashboard().catch(() => {});
}

async function saveUser(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formData(form);
  const id = data.id;
  delete data.id;
  if (id && !data.password) delete data.password;
  await api(id ? `/api/users/${id}` : "/api/users", { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
  clearForm(form);
  toast("Usuario salvo.");
  await loadUsers();
  await loadUserOptions();
}

async function saveGoal(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formData(form);
  const id = data.id;
  delete data.id;
  await api(id ? `/api/goals/${id}` : "/api/goals", { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
  clearForm(form);
  toast("Meta salva.");
  await loadGoals();
}

async function saveCategory(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formData(form);
  await api("/api/categories", { method: "POST", body: JSON.stringify(data) });
  clearForm(form);
  toast("Categoria adicionada.");
  await loadCategories();
  await loadManagedCategories();
}

function toggleInstallmentFields() {
  const show = $("#isInstallment")?.value === "Sim";
  $$(".installment-fields").forEach((field) => field.classList.toggle("hidden", !show));
  const dueDate = $("#expenseForm")?.elements?.due_date?.value;
  const firstDue = $("#expenseForm")?.elements?.first_due_date;
  if (show && firstDue && !firstDue.value) firstDue.value = dueDate || "";
}

async function parseImportFile(file) {
  const text = await file.text();
  const lines = text.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) return [];
  const separator = lines[0].includes(";") ? ";" : ",";
  const headers = lines[0].split(separator).map((header) => header.trim());
  return lines.slice(1).map((line) => {
    const values = line.split(separator);
    return Object.fromEntries(headers.map((header, index) => [header, (values[index] || "").trim()]));
  });
}

async function previewImport(event) {
  const file = event.currentTarget.files?.[0];
  if (!file) return;
  state.importRows = await parseImportFile(file);
  const data = await api("/api/import/preview", { method: "POST", body: JSON.stringify({ rows: state.importRows }) });
  $("#importSummary").textContent = `${data.valid.length} linhas validas, ${data.errors.length} erros.`;
  $("#importPreview").innerHTML = [
    ...data.valid.slice(0, 10).map((row) => `<tr><td>OK</td><td>${escapeHtml(row.tipo)}</td><td>${escapeHtml(row.descricao_ou_nome)}</td><td>${money(row.valor)}</td></tr>`),
    ...data.errors.map((err) => `<tr><td>Erro linha ${err.line}</td><td colspan="3">${escapeHtml(err.error)}</td></tr>`),
  ].join("");
}

async function commitImport() {
  if (!state.importRows.length) {
    toast("Selecione uma planilha primeiro.");
    return;
  }
  const payload = { rows: state.importRows };
  if (state.user?.profile === "superadmin" && $("#filterUser")?.value) payload.user_id = $("#filterUser").value;
  const data = await api("/api/import/commit", { method: "POST", body: JSON.stringify(payload) });
  toast(`${data.imported} registros importados.`);
  state.importRows = [];
  if ($("#importFile")) $("#importFile").value = "";
  $("#importSummary").textContent = "";
  $("#importPreview").innerHTML = "";
  await refreshAll();
}

async function registerAccount(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form) return;
  const data = formData(form);
  $("#registerMsg").textContent = "";
  if (!data.full_name.trim()) {
    $("#registerMsg").textContent = "Nome obrigatorio.";
    return;
  }
  if (!data.username.trim()) {
    $("#registerMsg").textContent = "Usuario obrigatorio.";
    return;
  }
  if (data.password.length < 6) {
    $("#registerMsg").textContent = "A senha deve ter pelo menos 6 caracteres.";
    return;
  }
  if (data.password !== data.confirm_password) {
    $("#registerMsg").textContent = "Confirmacao de senha diferente da senha.";
    return;
  }
  try {
    await api("/api/register", { method: "POST", body: JSON.stringify(data) });
    if (form && typeof form.reset === "function") {
      form.reset();
    }
    showLoginForm("Conta criada com sucesso. Faça login.");
  } catch (error) {
    $("#registerMsg").textContent = error.message;
  }
}

window.editExpense = (id) => {
  const item = state.expenses.find((row) => row.id === id);
  if (item) fillForm($("#expenseForm"), item);
};

window.editIncome = (id) => {
  const item = state.incomes.find((row) => row.id === id);
  if (item) fillForm($("#incomeForm"), item);
};

window.editUser = (id) => {
  const item = state.users.find((row) => row.id === id);
  if (item) fillForm($("#userForm"), { ...item, active: item.active ? "true" : "false", password: "" });
};

window.editGoal = (id) => {
  const item = state.goals.find((row) => row.id === id);
  if (item) fillForm($("#goalForm"), item);
};

window.deleteExpense = async (id) => {
  if (!confirm("Excluir esta conta?")) return;
  await api(`/api/expenses/${id}`, { method: "DELETE" });
  toast("Conta excluida.");
  await loadExpenses();
};

window.deleteIncome = async (id) => {
  if (!confirm("Excluir esta receita?")) return;
  await api(`/api/incomes/${id}`, { method: "DELETE" });
  toast("Receita excluida.");
  await loadIncomes();
};

window.payExpense = async (id) => {
  const paymentDate = prompt("Data de pagamento (AAAA-MM-DD):", new Date().toISOString().slice(0, 10));
  if (!paymentDate) return;
  await api(`/api/expenses/${id}/pay`, { method: "POST", body: JSON.stringify({ payment_date: paymentDate }) });
  toast("Conta marcada como paga.");
  await loadExpenses();
};

window.cancelFutureInstallments = async (id) => {
  if (!confirm("Cancelar parcelas futuras nao pagas?")) return;
  const data = await api(`/api/expenses/${id}/cancel-future`, { method: "POST", body: "{}" });
  toast(`${data.cancelled} parcelas futuras canceladas.`);
  await loadExpenses();
};

window.changeGoalAmount = async (id, action) => {
  const label = action === "add" ? "Adicionar valor" : "Retirar valor";
  const amount = prompt(`${label}:`);
  if (!amount) return;
  await api(`/api/goals/${id}/${action}`, { method: "POST", body: JSON.stringify({ amount }) });
  toast("Meta atualizada.");
  await loadGoals();
};

window.deleteGoal = async (id) => {
  if (!confirm("Excluir esta meta?")) return;
  await api(`/api/goals/${id}`, { method: "DELETE" });
  toast("Meta excluida.");
  await loadGoals();
};

window.deleteCategory = async (id) => {
  if (!confirm("Excluir esta categoria?")) return;
  await api(`/api/categories/${id}`, { method: "DELETE" });
  toast("Categoria excluida.");
  await loadCategories();
  await loadManagedCategories();
};

window.changeUserPassword = async (id) => {
  const password = prompt("Nova senha do usuario:");
  if (!password) return;
  await api(`/api/users/${id}/password`, { method: "POST", body: JSON.stringify({ password }) });
  toast("Senha alterada.");
};

window.toggleUser = async (id) => {
  await api(`/api/users/${id}/toggle`, { method: "POST", body: "{}" });
  toast("Status do usuario atualizado.");
  await loadUsers();
  await loadUserOptions();
};

window.deleteUser = async (id) => {
  if (!confirm("Excluir este usuario?")) return;
  await api(`/api/users/${id}`, { method: "DELETE" });
  toast("Usuario excluido.");
  await loadUsers();
  await loadUserOptions();
};

function logout(callApi = true) {
  if (callApi && state.token) api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
  state.token = null;
  state.user = null;
  localStorage.removeItem("finance_token");
  showLogin();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

async function exportReport() {
  const response = await fetch(`/api/report/export?${query({ type: $("#reportType").value })}`, { headers: authHeaders() });
  if (!response.ok) throw new Error("Falha ao exportar relatorio");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "relatorio-financeiro.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  toast("Relatorio exportado.");
}

function bindEvents() {
  on("#loginForm", "submit", async (event) => {
    event.preventDefault();
    $("#loginMsg").textContent = "";
    try {
      const data = await api("/api/login", { method: "POST", body: JSON.stringify(formData(event.currentTarget)) });
      state.token = data.token;
      state.user = data.user;
      localStorage.setItem("finance_token", state.token);
      showApp();
      await loadCategories();
      await loadUserOptions();
      setView("dashboard");
    } catch (error) {
      $("#loginMsg").textContent = error.message;
    }
  });
  on("#showRegisterBtn", "click", showRegisterForm);
  on("#showLoginBtn", "click", () => showLoginForm());
  on("#registerForm", "submit", registerAccount);
  $$(".nav-btn").forEach((btn) => btn.addEventListener("click", () => setView(btn.dataset.view)));
  on("#logoutBtn", "click", () => logout(true));
  on("#expenseForm", "submit", saveExpense);
  on("#incomeForm", "submit", saveIncome);
  on("#goalForm", "submit", saveGoal);
  on("#categoryForm", "submit", saveCategory);
  on("#clearExpenseForm", "click", () => clearForm($("#expenseForm")));
  on("#clearIncomeForm", "click", () => clearForm($("#incomeForm")));
  on("#clearGoalForm", "click", () => clearForm($("#goalForm")));
  on("#isInstallment", "change", toggleInstallmentFields);
  on("#expenseStatus", "change", loadExpenses);
  on("#expenseCategory", "change", loadExpenses);
  on("#incomeStatus", "change", loadIncomes);
  on("#incomeCategory", "change", loadIncomes);
  on("#filterUser", "change", refreshAll);
  on("#reportType", "change", loadReport);
  on("#exportReport", "click", exportReport);
  on("#downloadTemplate", "click", () => {
    window.location.href = "/api/import/template";
  });
  on("#importFile", "change", previewImport);
  on("#commitImport", "click", commitImport);
  on("#userForm", "submit", saveUser);
  on("#clearUserForm", "click", () => clearForm($("#userForm")));
  on("#passwordForm", "submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form) return;
    $("#passwordMsg").textContent = "";
    try {
      await api("/api/change-password", { method: "POST", body: JSON.stringify(formData(form)) });
      if (form && typeof form.reset === "function") {
        form.reset();
      }
      $("#passwordMsg").textContent = "Senha alterada com sucesso.";
    } catch (error) {
      $("#passwordMsg").textContent = error.message;
    }
  });
}

async function boot() {
  setupPeriod();
  bindEvents();
  if (state.token) {
    try {
      const data = await api("/api/me");
      state.user = data.user;
      showApp();
      await loadCategories();
      await loadUserOptions();
      setView("dashboard");
    } catch {
      logout(false);
    }
  }
}

boot();
