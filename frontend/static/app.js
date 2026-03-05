const API = "/api";
let currentPage = 0;
let pageSize = 25;
let sortOrder = "desc";

document.addEventListener("DOMContentLoaded", () => {
    loadStatus();
    loadDashboard();
    loadJobs();
    setInterval(loadStatus, 15000);
});

function switchTab(tab) {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
    document.querySelector(`[data-tab="${tab}"]`).classList.add("active");
    document.getElementById(`tab-${tab}`).classList.add("active");
    if (tab === "dashboard") loadDashboard();
    if (tab === "jobs") loadJobs();
    if (tab === "spools") loadSpools();
    if (tab === "settings") { loadSettings(); loadCfsSlots(); }
}

function showToast(msg, type = "info") {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.className = `toast ${type} show`;
    setTimeout(() => t.classList.remove("show"), 3000);
}

async function loadStatus() {
    try {
        const r = await fetch(`${API}/status`);
        const d = await r.json();
        document.getElementById("moonrakerDot").className =
            `status-dot ${d.moonraker_connected ? "connected" : "disconnected"}`;
        document.getElementById("spoolmanDot").className =
            `status-dot ${d.spoolman_connected ? "connected" : "disconnected"}`;
    } catch (e) {
        console.error("Status error:", e);
    }
}

async function triggerSync() {
    const icon = document.getElementById("syncIcon");
    icon.classList.add("spinning");
    try {
        const r = await fetch(`${API}/sync`, { method: "POST" });
        const d = await r.json();
        showToast(d.message || "Sync abgeschlossen", "success");
        loadDashboard();
        loadJobs();
    } catch (e) {
        showToast("Sync fehlgeschlagen", "error");
    }
    icon.classList.remove("spinning");
}

async function loadDashboard() {
    try {
        const r = await fetch(`${API}/statistics`);
        const s = await r.json();

        document.getElementById("totalCost").textContent = `${(s.total_cost || 0).toFixed(2)} EUR`;
        document.getElementById("totalJobs").textContent = s.total_jobs || 0;
        document.getElementById("completedJobs").textContent = s.completed_jobs || 0;
        document.getElementById("failedJobs").textContent = (s.cancelled_jobs || 0) + (s.error_jobs || 0);
        document.getElementById("totalFilament").textContent = `${(s.total_filament_g || 0).toFixed(0)} g`;
        document.getElementById("avgCost").textContent = `${(s.avg_cost_per_print || 0).toFixed(2)} EUR`;

        const filCost = s.total_filament_cost || 0;
        const eleCost = s.total_electricity_cost || 0;
        const maxCost = Math.max(filCost, eleCost, 1);

        document.getElementById("filamentBar").style.width = `${(filCost / maxCost) * 100}%`;
        document.getElementById("electricityBar").style.width = `${(eleCost / maxCost) * 100}%`;
        document.getElementById("totalFilamentCost").textContent = `${filCost.toFixed(2)} EUR`;
        document.getElementById("totalElectricityCost").textContent = `${eleCost.toFixed(2)} EUR`;

        const ftContainer = document.getElementById("filamentTypeStats");
        if (s.by_filament_type && s.by_filament_type.length > 0) {
            ftContainer.innerHTML = s.by_filament_type.map(ft => `
                <div class="filament-type-item">
                    <div>
                        <span class="filament-type-name">${ft.filament_type || "Unbekannt"}</span>
                        <span class="filament-type-details"> - ${ft.count} Drucke, ${(ft.total_g || 0).toFixed(0)}g</span>
                    </div>
                    <span style="font-weight:700">${(ft.total_cost || 0).toFixed(2)} EUR</span>
                </div>
            `).join("");
        } else {
            ftContainer.innerHTML = '<p class="text-muted">Keine Daten</p>';
        }

        const mContainer = document.getElementById("monthlyStats");
        if (s.by_month && s.by_month.length > 0) {
            const maxMonthCost = Math.max(...s.by_month.map(m => m.total_cost || 0), 1);
            mContainer.innerHTML = '<div class="monthly-chart">' + s.by_month.map(m => `
                <div class="monthly-bar-row">
                    <span class="monthly-label">${m.month || "?"}</span>
                    <div class="monthly-bar-container">
                        <div class="monthly-bar" style="width:${((m.total_cost || 0) / maxMonthCost) * 100}%"></div>
                    </div>
                    <span class="monthly-value">${(m.total_cost || 0).toFixed(2)} EUR</span>
                </div>
            `).join("") + '</div>';
        } else {
            mContainer.innerHTML = '<p class="text-muted">Keine Daten</p>';
        }
    } catch (e) {
        console.error("Dashboard error:", e);
    }
}

function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return "-";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

function formatDate(timestamp) {
    if (!timestamp) return "-";
    const d = new Date(timestamp * 1000);
    return d.toLocaleDateString("de-DE", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit"
    });
}

function getStatusBadge(status) {
    const map = {
        completed: ["Fertig", "status-completed"],
        cancelled: ["Abbruch", "status-cancelled"],
        error: ["Fehler", "status-error"],
        klippy_shutdown: ["Shutdown", "status-error"],
        klippy_disconnect: ["Disconnect", "status-error"]
    };
    const [label, cls] = map[status] || [status, "status-cancelled"];
    return `<span class="status-badge ${cls}">${label}</span>`;
}

function toggleSortOrder() {
    sortOrder = sortOrder === "desc" ? "asc" : "desc";
    document.getElementById("sortOrderIcon").className =
        `fas fa-sort-${sortOrder === "desc" ? "down" : "up"}`;
    loadJobs();
}

async function loadJobs() {
    try {
        const status = document.getElementById("statusFilter").value;
        const sort = document.getElementById("sortBy").value;
        const offset = currentPage * pageSize;

        let url = `${API}/jobs?limit=${pageSize}&offset=${offset}&sort_by=${sort}&sort_order=${sortOrder}`;
        if (status !== "all") url += `&status=${status}`;

        const r = await fetch(url);
        const d = await r.json();

        const jobs = d.jobs || [];
        const total = d.total || 0;
        const tbody = document.getElementById("jobsTableBody");

        document.getElementById("jobCount").textContent = `${total} Auftraege`;

        if (jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">Keine Druckauftraege gefunden. Klicke auf Sync!</td></tr>';
            document.getElementById("pagination").innerHTML = "";
            return;
        }

        tbody.innerHTML = jobs.map(j => `
            <tr>
                <td>${getStatusBadge(j.status)}</td>
                <td title="${j.filename || ""}">${(j.filename || "?").substring(0, 35)}</td>
                <td>${formatDate(j.end_time || j.start_time)}</td>
                <td>${formatDuration(j.print_duration)}</td>
                <td>${(j.filament_used_g || 0).toFixed(1)}g</td>
                <td>
                    ${j.filament_color ? `<span class="spool-color" style="background:${j.filament_color}"></span>` : ""}
                    ${j.spool_name ? j.spool_name.substring(0, 20) : "-"}
                </td>
                <td>${(j.filament_cost || 0).toFixed(3)}</td>
                <td>${(j.electricity_cost || 0).toFixed(3)}</td>
                <td style="font-weight:700">${(j.total_cost || 0).toFixed(3)}</td>
                <td class="actions-cell">
                    <button class="btn-edit" onclick="openSpoolModal(${j.id}, '${(j.filename||'').replace(/'/g,"\\'").substring(0,40)}', ${j.spool_id || 'null'})" title="Spule ändern">
                        <i class="fas fa-circle-notch"></i>
                    </button>
                    <button class="btn-danger" onclick="deleteJob(${j.id})" title="Löschen">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `).join("");

        renderPagination(total);
    } catch (e) {
        console.error("Jobs error:", e);
        document.getElementById("jobsTableBody").innerHTML =
            '<tr><td colspan="10" class="text-center text-muted">Fehler beim Laden</td></tr>';
    }
}

function renderPagination(total) {
    const pages = Math.ceil(total / pageSize);
    const container = document.getElementById("pagination");
    if (pages <= 1) { container.innerHTML = ""; return; }

    let html = `<button ${currentPage === 0 ? "disabled" : ""} onclick="goToPage(${currentPage - 1})">
        <i class="fas fa-chevron-left"></i></button>`;

    for (let i = 0; i < pages; i++) {
        if (pages > 7 && i > 1 && i < pages - 2 && Math.abs(i - currentPage) > 1) {
            if (i === 2 || i === pages - 3) html += `<button disabled>...</button>`;
            continue;
        }
        html += `<button class="${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i + 1}</button>`;
    }

    html += `<button ${currentPage >= pages - 1 ? "disabled" : ""} onclick="goToPage(${currentPage + 1})">
        <i class="fas fa-chevron-right"></i></button>`;

    container.innerHTML = html;
}

function goToPage(page) {
    currentPage = page;
    loadJobs();
}

async function deleteJob(id) {
    if (!confirm("Druckauftrag wirklich loeschen?")) return;
    try {
        await fetch(`${API}/jobs/${id}`, { method: "DELETE" });
        showToast("Auftrag geloescht", "success");
        loadJobs();
        loadDashboard();
    } catch (e) {
        showToast("Fehler beim Loeschen", "error");
    }
}

async function loadSpools() {
    const grid = document.getElementById("spoolsGrid");
    try {
        const r = await fetch(`${API}/spools`);
        const spools = await r.json();

        if (!spools || spools.length === 0) {
            grid.innerHTML = '<p class="text-muted">Keine Spulen gefunden. Ist Spoolman verbunden?</p>';
            return;
        }

        grid.innerHTML = spools.map(s => {
            const filament = s.filament || {};
            const vendor = filament.vendor || {};
            const name = `${vendor.name || ""} ${filament.name || ""}`.trim() || `Spool #${s.id}`;
            const material = filament.material || "?";
            const color = filament.color_hex ? `#${filament.color_hex.replace("#","")}` : "#666";
            const remaining = s.remaining_weight || 0;
            const total = filament.weight || 1000;
            const pct = Math.min(100, Math.max(0, (remaining / total) * 100));
            const spoolPrice = (s.price != null && s.price > 0) ? s.price : null;
            const filamentPrice = (filament.price != null && filament.price > 0) ? filament.price : null;
            const price = spoolPrice !== null ? spoolPrice : (filamentPrice || 0);
            const priceLabel = spoolPrice !== null ? "Spulenpreis" : (filamentPrice ? "Filamentpreis" : "Preis");
            const weight = filament.weight || 0;

            return `
                <div class="spool-card" style="border-top-color:${color}">
                    <div class="spool-card-header">
                        <span class="spool-card-name">
                            <span class="spool-color" style="background:${color}"></span>
                            ${name}
                        </span>
                        <span class="spool-card-type">${material}</span>
                    </div>
                    <div class="spool-detail">
                        <span class="spool-detail-label">Verbleibend</span>
                        <span class="spool-detail-value">${remaining.toFixed(0)}g / ${total}g</span>
                    </div>
                    <div class="spool-detail">
                        <span class="spool-detail-label">${priceLabel}</span>
                        <span class="spool-detail-value">${price > 0 ? price.toFixed(2) + " EUR" : "-"}</span>
                    </div>
                    <div class="spool-detail">
                        <span class="spool-detail-label">EUR/kg</span>
                        <span class="spool-detail-value">${weight > 0 && price > 0 ? (price / weight * 1000).toFixed(2) : "-"}</span>
                    </div>
                    <div class="spool-progress">
                        <div class="spool-progress-bar" style="width:${pct}%;background:${color}"></div>
                    </div>
                </div>
            `;
        }).join("");
    } catch (e) {
        grid.innerHTML = '<p class="text-muted">Fehler beim Laden der Spulen</p>';
        console.error("Spools error:", e);
    }
}

async function loadSettings() {
    try {
        const r = await fetch(`${API}/settings`);
        const s = await r.json();

        if (s.electricity_cost_per_kwh)
            document.getElementById("settingElectricity").value = s.electricity_cost_per_kwh.value;
        if (s.printer_power_watts)
            document.getElementById("settingPower").value = s.printer_power_watts.value;
        if (s.default_filament_cost_per_kg)
            document.getElementById("settingFilament").value = s.default_filament_cost_per_kg.value;

        const r2 = await fetch(`${API}/status`);
        const st = await r2.json();
        document.getElementById("connectionDetails").innerHTML = `
            <div class="conn-item">
                <span class="conn-label">Moonraker</span>
                <span>${st.moonraker_connected ?
                    '<span style="color:var(--success)"><i class="fas fa-check-circle"></i> Verbunden</span>' :
                    '<span style="color:var(--danger)"><i class="fas fa-times-circle"></i> Getrennt</span>'
                }</span>
            </div>
            <div class="conn-item">
                <span class="conn-label">Spoolman</span>
                <span>${st.spoolman_connected ?
                    '<span style="color:var(--success)"><i class="fas fa-check-circle"></i> Verbunden</span>' :
                    '<span style="color:var(--danger)"><i class="fas fa-times-circle"></i> Getrennt</span>'
                }</span>
            </div>
            <div class="conn-item">
                <span class="conn-label">Letzte Sync</span>
                <span>${st.last_sync || "Noch nie"}</span>
            </div>
            <div class="conn-item">
                <span class="conn-label">Drucke in DB</span>
                <span style="font-weight:700">${st.total_jobs_in_db || 0}</span>
            </div>
        `;
    } catch (e) {
        console.error("Settings error:", e);
    }
}

async function saveSettings() {
    try {
        const settings = {
            electricity_cost_per_kwh: parseFloat(document.getElementById("settingElectricity").value) || 0.30,
            printer_power_watts: parseFloat(document.getElementById("settingPower").value) || 200,
            default_filament_cost_per_kg: parseFloat(document.getElementById("settingFilament").value) || 25
        };

        const r = await fetch(`${API}/settings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(settings)
        });

        if (r.ok) {
            showToast("Einstellungen gespeichert", "success");
        } else {
            showToast("Fehler beim Speichern", "error");
        }
    } catch (e) {
        showToast("Fehler beim Speichern", "error");
    }
}

// ── CFS Slots ──────────────────────────────────────────────────
let _cfsData = { slots: [], spools: [] };

async function loadCfsSlots() {
    try {
        const r = await fetch(`${API}/cfs-slots`);
        _cfsData = await r.json();
        renderCfsSlots();
    } catch(e) {
        document.getElementById("cfsSlotsList").innerHTML = '<p class="text-muted">Fehler beim Laden</p>';
    }
}

function renderCfsSlots() {
    const container = document.getElementById("cfsSlotsList");
    const spoolOptions = `<option value="">-- keine --</option>` +
        _cfsData.spools.map(s => {
            const mat = s.material ? ` [${s.material}]` : "";
            return `<option value="${s.id}">${s.name}${mat}</option>`;
        }).join("");

    container.innerHTML = _cfsData.slots.map(slot => {
        const info = slot.spool_info;
        const color = info?.color || "#666";
        const colorDot = info ? `<span class="spool-color" style="background:${color}"></span>` : "";
        return `
            <div class="cfs-slot-row">
                <span class="cfs-slot-label">
                    <i class="fas fa-box-open" style="color:var(--accent)"></i>
                    ${slot.slot_label}
                </span>
                <div class="cfs-slot-select-wrap">
                    ${colorDot}
                    <select class="modal-select cfs-slot-select" data-slot-key="${slot.slot_key}" onchange="updateCfsSlotColor(this)">
                        ${spoolOptions.replace(`value="${slot.spool_id}"`, `value="${slot.spool_id}" selected`)}
                    </select>
                </div>
            </div>`;
    }).join("");
}

function updateCfsSlotColor(select) {
    const sid = parseInt(select.value);
    const spool = _cfsData.spools.find(s => s.id === sid);
    const dot = select.previousElementSibling;
    if (dot && dot.classList.contains("spool-color")) {
        dot.style.background = spool?.color || "#666";
        dot.style.display = spool ? "inline-block" : "none";
    }
}

async function saveCfsSlots() {
    const selects = document.querySelectorAll(".cfs-slot-select");
    const slots = Array.from(selects).map(s => ({
        slot_key: s.dataset.slotKey,
        spool_id: s.value ? parseInt(s.value) : null
    }));
    try {
        const r = await fetch(`${API}/cfs-slots`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slots })
        });
        if (r.ok) {
            showToast("CFS-Slots gespeichert", "success");
            await loadCfsSlots();
        } else {
            showToast("Fehler beim Speichern", "error");
        }
    } catch(e) {
        showToast("Fehler beim Speichern", "error");
    }
}
// ────────────────────────────────────────────────────────────

// ── Spool Modal ────────────────────────────────────────────
let _modalJobId = null;
let _allSpools = [];

async function openSpoolModal(jobId, filename, currentSpoolId) {
    _modalJobId = jobId;
    document.getElementById("modalJobName").textContent = filename || `Job #${jobId}`;

    const slotSel = document.getElementById("modalSlotSelect");
    const spoolSel = document.getElementById("modalSpoolSelect");
    slotSel.innerHTML = '<option value="">Lade...</option>';
    spoolSel.innerHTML = '<option value="">Lade...</option>';
    document.getElementById("spoolModal").showModal();

    try {
        // CFS-Daten und Spulen parallel laden
        const [cfsR, spoolsR] = await Promise.all([
            fetch(`${API}/cfs-slots`),
            fetch(`${API}/spools`)
        ]);
        _cfsData = await cfsR.json();
        _allSpools = await spoolsR.json();

        // Slot-Dropdown befüllen
        slotSel.innerHTML = '<option value="">-- kein Slot --</option>' +
            _cfsData.slots.map(slot => {
                const info = slot.spool_info;
                const spoolName = info ? ` (${info.name})` : " (leer)";
                // Slot vorauswählen wenn spool_id übereinstimmt
                const sel = slot.spool_id == currentSpoolId ? " selected" : "";
                return `<option value="${slot.slot_key}"${sel}>${slot.slot_label}${spoolName}</option>`;
            }).join("");

        // Spulen-Dropdown befüllen
        spoolSel.innerHTML = '<option value="">-- aus Slot übernehmen --</option>' +
            _allSpools.map(s => {
                const f = s.filament || {};
                const v = (f.vendor || {}).name || "";
                const name = `${v} ${f.name||""}`.trim() || `Spool #${s.id}`;
                const mat = f.material ? ` [${f.material}]` : "";
                const rem = s.remaining_weight != null ? ` – ${s.remaining_weight.toFixed(0)}g` : "";
                const sel = s.id == currentSpoolId ? " selected" : "";
                return `<option value="${s.id}"${sel}>${name}${mat}${rem}</option>`;
            }).join("");
    } catch(e) {
        slotSel.innerHTML = '<option value="">Fehler</option>';
    }
}

function onModalSlotChange() {
    // Wenn ein Slot gewählt wird, Spulen-Dropdown auf "aus Slot übernehmen" zurücksetzen
    const slotSel = document.getElementById("modalSlotSelect");
    const spoolSel = document.getElementById("modalSpoolSelect");
    if (slotSel.value) spoolSel.value = "";
}

function closeSpoolModal(event) {
    document.getElementById("spoolModal").close();
    _modalJobId = null;
}

async function saveSpoolAssignment() {
    if (!_modalJobId) return;
    const slotKey = document.getElementById("modalSlotSelect").value;
    const spoolId = document.getElementById("modalSpoolSelect").value;

    // Spule ermitteln: direkte Auswahl hat Vorrang, sonst aus Slot
    let resolvedSpoolId = spoolId ? parseInt(spoolId) : null;
    if (!resolvedSpoolId && slotKey) {
        const slot = _cfsData.slots.find(s => s.slot_key === slotKey);
        resolvedSpoolId = slot?.spool_id || null;
    }

    try {
        const r = await fetch(`${API}/jobs/${_modalJobId}/spool`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ spool_id: resolvedSpoolId })
        });
        if (r.ok) {
            showToast("Spule aktualisiert", "success");
            document.getElementById("spoolModal").close();
            _modalJobId = null;
            loadJobs();
            loadDashboard();
        } else {
            showToast("Fehler beim Speichern", "error");
        }
    } catch(e) {
        showToast("Fehler beim Speichern", "error");
    }
}
// ────────────────────────────────────────────────────────────

async function recalculateCosts() {
    try {
        const r = await fetch(`${API}/recalculate`, { method: "POST" });
        const d = await r.json();
        showToast(d.message || "Kosten neu berechnet", "success");
        loadDashboard();
        loadJobs();
    } catch (e) {
        showToast("Fehler bei Neuberechnung", "error");
    }
}
