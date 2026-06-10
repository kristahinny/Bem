const state = {
  token: localStorage.getItem("finance_token"),
  user: null,
  view: "dashboard",
  categories: [],
  expenses: [],
  incomes: [],
  users: [],
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
    month: $("#filterMonth").value,
    year: $("#filterYear").value,
    ...extra,
  });
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
  const titles = { dashboard: "Dashboard", expenses: "Contas a pagar", incomes: "Receitas", reports: "Relatorios", users: "Usuarios", settings: "Senha" };
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

async function loadDashboard() {
  const data = await api(`/api/dashboard?${query()}`);
  $("#cardPending").textContent = money(data.cards.total_pending);
  $("#cardPaid").textContent = money(data.cards.total_paid);
  $("#cardIncome").textContent = money(data.cards.total_income);
  $("#cardExpected").textContent = money(data.cards.expected_balance);
  $("#cardReal").textContent = money(data.cards.real_balance);
  $("#cardOverdue").textContent = data.cards.overdue_count;
  renderMiniList("#overdueList", data.overdue);
  renderMiniList("#upcomingList", data.upcoming);
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
  const status = $("#expenseStatus").value;
  const category = $("#expenseCategory").value;
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
      <td class="actions">
        ${item.status !== "Pago" ? `<button class="success" onclick="payExpense(${item.id})">Pagar</button>` : ""}
        <button class="edit" onclick="editExpense(${item.id})">Editar</button>
        <button class="danger" onclick="deleteExpense(${item.id})">Excluir</button>
      </td>
    </tr>
  `).join("") || `<tr><td colspan="6">Nenhuma conta cadastrada.</td></tr>`;
}

async function loadIncomes() {
  const status = $("#incomeStatus").value;
  const category = $("#incomeCategory").value;
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

async function saveExpense(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formData(form);
  const id = data.id;
  delete data.id;
  await api(id ? `/api/expenses/${id}` : "/api/expenses", { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
  clearForm(form);
  toast("Conta salva.");
  await loadExpenses();
}

async function saveIncome(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formData(form);
  const id = data.id;
  delete data.id;
  await api(id ? `/api/incomes/${id}` : "/api/incomes", { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
  clearForm(form);
  toast("Receita salva.");
  await loadIncomes();
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
};

window.deleteUser = async (id) => {
  if (!confirm("Excluir este usuario?")) return;
  await api(`/api/users/${id}`, { method: "DELETE" });
  toast("Usuario excluido.");
  await loadUsers();
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
  on("#clearExpenseForm", "click", () => clearForm($("#expenseForm")));
  on("#clearIncomeForm", "click", () => clearForm($("#incomeForm")));
  on("#expenseStatus", "change", loadExpenses);
  on("#expenseCategory", "change", loadExpenses);
  on("#incomeStatus", "change", loadIncomes);
  on("#incomeCategory", "change", loadIncomes);
  on("#reportType", "change", loadReport);
  on("#exportReport", "click", exportReport);
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
      setView("dashboard");
    } catch {
      logout(false);
    }
  }
}

boot();
