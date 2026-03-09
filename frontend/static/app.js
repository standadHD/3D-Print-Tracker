const API = "/api";
let currentPage = 0;
let pageSize = 25;
let sortOrder = "desc";
let currentSortBy = "end_time";

document.addEventListener("DOMContentLoaded", () => {
    loadStatus();
    loadDashboard();
    loadFilamentTypeFilter();
    loadJobs();
    setInterval(loadStatus, 15000);
});

function switchTab(tab) {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
    document.querySelector(`[data-tab="${tab}"]`).classList.add("active");
    document.getElementById(`tab-${tab}`).classList.add("active");
    if (tab === "dashboard") loadDashboard();
    if (tab === "jobs") { loadJobs(); loadFilamentTypeFilter(); }
    if (tab === "spoolmgmt") loadSpoolMgmt();
    if (tab === "spools") loadSpools();
    if (tab === "settings") { loadSettings(); loadCfsSlots(); }
}

function showToast(msg, type = "info") {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.className = `toast ${type} show`;
    setTimeout(() => t.classList.remove("show"), 3000);
}

// ── Status ────────────────────────────────────────────────────────────────────
async function loadStatus() {
    try {
        const r = await fetch(`${API}/status`);
        const d = await r.json();
        document.getElementById("moonrakerDot").className =
            `status-dot ${d.moonraker_connected ? "connected" : "disconnected"}`;
        document.getElementById("spoolmanDot").className =
            `status-dot ${d.spoolman_connected ? "connected" : "disconnected"}`;
    } catch (e) { console.error("Status error:", e); }
}

async function triggerSync() {
    const icon = document.getElementById("syncIcon");
    icon.classList.add("spinning");
    try {
        const r = await fetch(`${API}/sync`, { method: "POST" });
        const d = await r.json();
        showToast(d.message || "Sync abgeschlossen", "success");
        loadDashboard(); loadJobs();
    } catch (e) { showToast("Sync fehlgeschlagen", "error"); }
    icon.classList.remove("spinning");
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
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
                </div>`).join("");
        } else {
            ftContainer.innerHTML = '<p class="text-muted">Keine Daten</p>';
        }
        const mContainer = document.getElementById("monthlyStats");
        if (s.by_month && s.by_month.length > 0) {
            const maxM = Math.max(...s.by_month.map(m => m.total_cost || 0), 1);
            mContainer.innerHTML = '<div class="monthly-chart">' + s.by_month.map(m => `
                <div class="monthly-bar-row">
                    <span class="monthly-label">${m.month || "?"}</span>
                    <div class="monthly-bar-container">
                        <div class="monthly-bar" style="width:${((m.total_cost || 0) / maxM) * 100}%"></div>
                    </div>
                    <span class="monthly-value">${(m.total_cost || 0).toFixed(2)} EUR</span>
                </div>`).join("") + '</div>';
        } else {
            mContainer.innerHTML = '<p class="text-muted">Keine Daten</p>';
        }
    } catch (e) { console.error("Dashboard error:", e); }
}

// ── Jobs ──────────────────────────────────────────────────────────────────────
function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return "-";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function formatDate(timestamp) {
    if (!timestamp) return "-";
    return new Date(timestamp * 1000).toLocaleDateString("de-DE", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit"
    });
}

function getStatusBadge(status) {
    const map = {
        completed: ["Fertig", "status-completed"], cancelled: ["Abbruch", "status-cancelled"],
        error: ["Fehler", "status-error"], klippy_shutdown: ["Shutdown", "status-error"],
        klippy_disconnect: ["Disconnect", "status-error"]
    };
    const [label, cls] = map[status] || [status, "status-cancelled"];
    return `<span class="status-badge ${cls}">${label}</span>`;
}

function setSortBy(field) {
    if (currentSortBy === field) sortOrder = sortOrder === "desc" ? "asc" : "desc";
    else { currentSortBy = field; sortOrder = "desc"; }
    updateSortIcons(); goToPage(0); loadJobs();
}

function updateSortIcons() {
    ["filename", "end_time", "print_duration", "filament_used_g", "total_cost"].forEach(f => {
        const el = document.getElementById(`sort-${f}`);
        if (el) el.textContent = f === currentSortBy ? (sortOrder === "desc" ? "↓" : "↑") : "";
    });
}

async function loadFilamentTypeFilter() {
    try {
        const types = await (await fetch(`${API}/filament-types`)).json();
        const sel = document.getElementById("filamentTypeFilter");
        const current = sel.value;
        sel.innerHTML = '<option value="all">Alle Typen</option>' +
            types.map(t => `<option value="${t}"${t === current ? " selected" : ""}>${t}</option>`).join("");
    } catch (e) { console.error("Filament types error:", e); }
}

async function loadJobs() {
    try {
        const status = document.getElementById("statusFilter").value;
        const filamentType = document.getElementById("filamentTypeFilter").value;
        const offset = currentPage * pageSize;
        let url = `${API}/jobs?limit=${pageSize}&offset=${offset}&sort_by=${currentSortBy}&sort_order=${sortOrder}`;
        if (status !== "all") url += `&status=${status}`;
        if (filamentType !== "all") url += `&filament_type=${encodeURIComponent(filamentType)}`;
        const r = await fetch(url);
        const d = await r.json();
        const jobs = d.jobs || [];
        const total = d.total || 0;
        const tbody = document.getElementById("jobsTableBody");
        document.getElementById("jobCount").textContent = `${total} Auftraege`;
        if (jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="11" class="text-center text-muted">Keine Druckauftraege gefunden. Klicke auf Sync!</td></tr>';
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
                <td>${j.filament_type ? `<span class="filament-type-badge">${j.filament_type}</span>` : "-"}</td>
                <td>
                    ${j.filament_color ? `<span class="spool-color" style="background:${j.filament_color}"></span>` : ""}
                    ${j.spool_name ? j.spool_name.substring(0, 20) : "-"}
                </td>
                <td>${(j.filament_cost || 0).toFixed(3)}</td>
                <td>${(j.electricity_cost || 0).toFixed(3)}</td>
                <td style="font-weight:700">${(j.total_cost || 0).toFixed(3)}</td>
                <td class="actions-cell">
                    <button class="btn-edit" onclick="openSpoolModal(${j.id}, '${(j.filename||'').replace(/'/g,"\\'").substring(0,40)}', ${j.spool_id || 'null'}, ${j.filament_used_g || 0})" title="Spule / Filament ändern">
                        <i class="fas fa-circle-notch"></i>
                    </button>
                    <button class="btn-danger" onclick="deleteJob(${j.id})" title="Löschen">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>`).join("");
        renderPagination(total);
    } catch (e) {
        console.error("Jobs error:", e);
        document.getElementById("jobsTableBody").innerHTML =
            '<tr><td colspan="11" class="text-center text-muted">Fehler beim Laden</td></tr>';
    }
}

function renderPagination(total) {
    const pages = Math.ceil(total / pageSize);
    const container = document.getElementById("pagination");
    if (pages <= 1) { container.innerHTML = ""; return; }
    let html = `<button ${currentPage === 0 ? "disabled" : ""} onclick="goToPage(${currentPage - 1})"><i class="fas fa-chevron-left"></i></button>`;
    for (let i = 0; i < pages; i++) {
        if (pages > 7 && i > 1 && i < pages - 2 && Math.abs(i - currentPage) > 1) {
            if (i === 2 || i === pages - 3) html += `<button disabled>...</button>`;
            continue;
        }
        html += `<button class="${i === currentPage ? "active" : ""}" onclick="goToPage(${i})">${i + 1}</button>`;
    }
    html += `<button ${currentPage >= pages - 1 ? "disabled" : ""} onclick="goToPage(${currentPage + 1})"><i class="fas fa-chevron-right"></i></button>`;
    container.innerHTML = html;
}

function goToPage(page) { currentPage = page; loadJobs(); }

async function deleteJob(id) {
    if (!confirm("Druckauftrag wirklich löschen?")) return;
    try {
        await fetch(`${API}/jobs/${id}`, { method: "DELETE" });
        showToast("Auftrag gelöscht", "success"); loadJobs(); loadDashboard();
    } catch (e) { showToast("Fehler beim Löschen", "error"); }
}

// ── Spool Modal (Druckjob zuordnen) ───────────────────────────────────────────
let _modalJobId = null;
let _cfsData = { slots: [], spools: [] };
let _allLocalSpools = [];
let _currentSpoolSource = "local";

function setSpoolSource(src) {
    _currentSpoolSource = src;
    document.getElementById("srcBtnLocal").classList.toggle("active", src === "local");
    document.getElementById("srcBtnSpoolman").classList.toggle("active", src === "spoolman");
    document.getElementById("localSpoolGroup").style.display = src === "local" ? "" : "none";
    document.getElementById("spoolmanGroup").style.display = src === "spoolman" ? "" : "none";
}

async function openSpoolModal(jobId, filename, currentSpoolId, currentFilamentG) {
    _modalJobId = jobId;
    document.getElementById("modalJobName").textContent = filename || `Job #${jobId}`;
    const filInput = document.getElementById("modalFilamentG");
    filInput.value = currentFilamentG > 0 ? currentFilamentG.toFixed(1) : "";
    document.getElementById("modalFilamentHint").textContent =
        currentFilamentG > 0 ? `Aktuell: ${currentFilamentG.toFixed(1)}g` : "Kein Wert erfasst";
    setSpoolSource("local");

    const [cfsR, spoolsR, localR] = await Promise.all([
        fetch(`${API}/cfs-slots`),
        fetch(`${API}/spools`),
        fetch(`${API}/local/spools`)
    ]);
    _cfsData = await cfsR.json();
    _allLocalSpools = await localR.json();

    // Lokale Spulen Dropdown
    const localSel = document.getElementById("modalLocalSpoolSelect");
    localSel.innerHTML = '<option value="">-- keine Spule --</option>' +
        _allLocalSpools.map(s => {
            const vendor = s.vendor_name ? `${s.vendor_name} ` : "";
            const label = s.label || `${vendor}${s.filament_name || ""}`.trim() || `Spule #${s.id}`;
            const rem = s.remaining_weight != null ? ` (${s.remaining_weight}g)` : "";
            const loc = s.location ? ` @ ${s.location}` : "";
            const sel = s.id == currentSpoolId ? " selected" : "";
            return `<option value="${s.id}"${sel}>${label}${rem}${loc}</option>`;
        }).join("");

    // Spoolman Slots Dropdown
    const slotSel = document.getElementById("modalSlotSelect");
    const spoolSel = document.getElementById("modalSpoolSelect");
    slotSel.innerHTML = '<option value="">-- kein Ort --</option>' +
        _cfsData.slots.filter(s => s.slot_key !== "__unassigned__").map(slot => {
            const hasCurrent = slot.spools.some(s => s.id == currentSpoolId);
            return `<option value="${slot.slot_key}"${hasCurrent ? " selected" : ""}>${slot.slot_label} (${slot.spools.length} Spulen)</option>`;
        }).join("");
    spoolSel.innerHTML = '<option value="">-- direkt auswählen --</option>' +
        _cfsData.spools.map(s => {
            const loc = s.location ? ` @ ${s.location}` : "";
            return `<option value="${s.id}"${s.id == currentSpoolId ? " selected" : ""}>${s.name}${loc}</option>`;
        }).join("");

    document.getElementById("spoolModal").showModal();
}

function onModalSlotChange() {
    const slotSel = document.getElementById("modalSlotSelect");
    if (slotSel.value) document.getElementById("modalSpoolSelect").value = "";
}

function closeSpoolModal() {
    document.getElementById("spoolModal").close();
    _modalJobId = null;
}

async function saveSpoolAssignment() {
    if (!_modalJobId) return;
    const filamentG = document.getElementById("modalFilamentG").value;
    let resolvedSpoolId = null;
    let spoolSource = _currentSpoolSource;

    if (_currentSpoolSource === "local") {
        resolvedSpoolId = document.getElementById("modalLocalSpoolSelect").value || null;
    } else {
        const spoolId = document.getElementById("modalSpoolSelect").value;
        const slotKey = document.getElementById("modalSlotSelect").value;
        resolvedSpoolId = spoolId || null;
        if (!resolvedSpoolId && slotKey) {
            const slot = _cfsData.slots.find(s => s.slot_key === slotKey);
            resolvedSpoolId = slot?.spools?.[0]?.id || null;
        }
        spoolSource = "spoolman";
    }

    try {
        let ok = true;
        if (filamentG !== "") {
            const r = await fetch(`${API}/jobs/${_modalJobId}/filament`, {
                method: "PATCH", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filament_used_g: parseFloat(filamentG) })
            });
            if (!r.ok) ok = false;
        }
        if (ok && resolvedSpoolId) {
            const r = await fetch(`${API}/jobs/${_modalJobId}/spool`, {
                method: "PATCH", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ spool_id: resolvedSpoolId ? parseInt(resolvedSpoolId) : null, spool_source: spoolSource })
            });
            if (!r.ok) ok = false;
        }
        if (ok) {
            showToast("Gespeichert", "success");
            document.getElementById("spoolModal").close();
            _modalJobId = null;
            loadJobs(); loadDashboard();
        } else {
            showToast("Fehler beim Speichern", "error");
        }
    } catch (e) { showToast("Fehler beim Speichern", "error"); }
}

// ── Spoolman Spulen (Übersicht) ───────────────────────────────────────────────
async function loadSpools() {
    const grid = document.getElementById("spoolsGrid");
    try {
        const spools = await (await fetch(`${API}/spools`)).json();
        if (!spools || spools.length === 0) {
            grid.innerHTML = '<p class="text-muted">Keine Spulen gefunden. Ist Spoolman verbunden?</p>';
            return;
        }
        grid.innerHTML = spools.map(s => {
            const filament = s.filament || {};
            const vendor = filament.vendor || {};
            const name = `${vendor.name || ""} ${filament.name || ""}`.trim() || `Spool #${s.id}`;
            const material = filament.material || "?";
            const color = filament.color_hex ? `#${filament.color_hex.replace("#", "")}` : "#666";
            const remaining = s.remaining_weight || 0;
            const total = filament.weight || 1000;
            const pct = Math.min(100, Math.max(0, (remaining / total) * 100));
            const spoolPrice = s.price > 0 ? s.price : null;
            const filamentPrice = filament.price > 0 ? filament.price : null;
            const price = spoolPrice ?? (filamentPrice || 0);
            const priceLabel = spoolPrice != null ? "Spulenpreis" : (filamentPrice ? "Filamentpreis" : "Preis");
            return `
                <div class="spool-card" style="border-top-color:${color}">
                    <div class="spool-card-header">
                        <span class="spool-card-name"><span class="spool-color" style="background:${color}"></span>${name}</span>
                        <span class="spool-card-type">${material}</span>
                    </div>
                    <div class="spool-detail"><span class="spool-detail-label">Verbleibend</span>
                        <span class="spool-detail-value">${remaining.toFixed(0)}g / ${total}g</span></div>
                    <div class="spool-detail"><span class="spool-detail-label">${priceLabel}</span>
                        <span class="spool-detail-value">${price > 0 ? price.toFixed(2) + " EUR" : "-"}</span></div>
                    <div class="spool-progress">
                        <div class="spool-progress-bar" style="width:${pct}%;background:${color}"></div>
                    </div>
                </div>`;
        }).join("");
    } catch (e) {
        grid.innerHTML = '<p class="text-muted">Fehler beim Laden der Spulen</p>';
    }
}

// ── Eigene Spulenverwaltung ───────────────────────────────────────────────────
let _vendors = [];
let _filaments = [];
let _localSpools = [];

async function loadSpoolMgmt() {
    await Promise.all([loadVendors(), loadFilaments(), loadLocalSpools()]);
}

// Vendors
async function loadVendors() {
    _vendors = await (await fetch(`${API}/local/vendors`)).json();
    renderVendors();
}

function renderVendors() {
    const container = document.getElementById("vendorsList");
    if (!_vendors.length) {
        container.innerHTML = '<p class="text-muted">Noch keine Hersteller angelegt.</p>';
        return;
    }
    container.innerHTML = _vendors.map(v => `
        <div class="mgmt-item">
            <div class="mgmt-item-info">
                <div class="mgmt-item-name">${v.name}</div>
                ${v.website ? `<div class="mgmt-item-sub">${v.website}</div>` : ""}
            </div>
            <div class="mgmt-item-actions">
                <button class="btn-edit" onclick="openVendorModal(${v.id})" title="Bearbeiten"><i class="fas fa-pen"></i></button>
                <button class="btn-danger" onclick="deleteVendor(${v.id})" title="Löschen"><i class="fas fa-trash"></i></button>
            </div>
        </div>`).join("");
}

function openVendorModal(vendorId = null) {
    document.getElementById("vendorId").value = vendorId || "";
    document.getElementById("vendorModalTitle").innerHTML =
        `<i class="fas fa-industry"></i> ${vendorId ? "Hersteller bearbeiten" : "Hersteller anlegen"}`;
    if (vendorId) {
        const v = _vendors.find(x => x.id === vendorId);
        document.getElementById("vendorName").value = v?.name || "";
        document.getElementById("vendorWebsite").value = v?.website || "";
        document.getElementById("vendorNotes").value = v?.notes || "";
    } else {
        document.getElementById("vendorName").value = "";
        document.getElementById("vendorWebsite").value = "";
        document.getElementById("vendorNotes").value = "";
    }
    document.getElementById("vendorModal").showModal();
}

function closeVendorModal() { document.getElementById("vendorModal").close(); }

async function saveVendor() {
    const id = document.getElementById("vendorId").value;
    const payload = {
        name: document.getElementById("vendorName").value.trim(),
        website: document.getElementById("vendorWebsite").value.trim() || null,
        notes: document.getElementById("vendorNotes").value.trim() || null,
    };
    if (!payload.name) { showToast("Name ist erforderlich", "error"); return; }
    try {
        const url = id ? `${API}/local/vendors/${id}` : `${API}/local/vendors`;
        const r = await fetch(url, {
            method: id ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (r.ok) {
            showToast(id ? "Hersteller aktualisiert" : "Hersteller angelegt", "success");
            closeVendorModal(); loadVendors();
        } else { showToast("Fehler beim Speichern", "error"); }
    } catch (e) { showToast("Fehler beim Speichern", "error"); }
}

async function deleteVendor(id) {
    if (!confirm("Hersteller wirklich löschen?")) return;
    await fetch(`${API}/local/vendors/${id}`, { method: "DELETE" });
    showToast("Hersteller gelöscht", "success"); loadVendors();
}

// Filaments
async function loadFilaments() {
    _filaments = await (await fetch(`${API}/local/filaments`)).json();
    renderFilaments();
}

function renderFilaments() {
    const container = document.getElementById("filamentsList");
    if (!_filaments.length) {
        container.innerHTML = '<p class="text-muted">Noch keine Filamente angelegt.</p>';
        return;
    }
    container.innerHTML = _filaments.map(f => {
        const color = f.color_hex ? (f.color_hex.startsWith("#") ? f.color_hex : `#${f.color_hex}`) : null;
        const priceKg = f.weight_per_spool > 0 && f.price_per_spool > 0
            ? (f.price_per_spool / f.weight_per_spool * 1000).toFixed(2) : null;
        return `
        <div class="mgmt-item">
            <div class="mgmt-item-info">
                <div class="mgmt-item-name">
                    ${color ? `<span class="spool-color" style="background:${color}"></span>` : ""}
                    ${f.name}
                    <span class="filament-type-badge">${f.material}</span>
                </div>
                <div class="mgmt-item-sub">${f.vendor_name || "Kein Hersteller"}${priceKg ? ` · ${priceKg} EUR/kg` : ""}</div>
            </div>
            <div class="mgmt-item-actions">
                <button class="btn-edit" onclick="openFilamentModal(${f.id})" title="Bearbeiten"><i class="fas fa-pen"></i></button>
                <button class="btn-danger" onclick="deleteFilament(${f.id})" title="Löschen"><i class="fas fa-trash"></i></button>
            </div>
        </div>`;
    }).join("");
}

function openFilamentModal(filamentId = null) {
    document.getElementById("filamentId").value = filamentId || "";
    document.getElementById("filamentModalTitle").innerHTML =
        `<i class="fas fa-layer-group"></i> ${filamentId ? "Filament bearbeiten" : "Filament anlegen"}`;

    // Hersteller-Dropdown befüllen
    const vendorSel = document.getElementById("filamentVendor");
    vendorSel.innerHTML = '<option value="">-- kein Hersteller --</option>' +
        _vendors.map(v => `<option value="${v.id}">${v.name}</option>`).join("");

    if (filamentId) {
        const f = _filaments.find(x => x.id === filamentId);
        document.getElementById("filamentName").value = f?.name || "";
        vendorSel.value = f?.vendor_id || "";
        document.getElementById("filamentMaterial").value = f?.material || "";
        document.getElementById("filamentColorName").value = f?.color_name || "";
        const hex = f?.color_hex || "";
        document.getElementById("filamentColorHex").value = hex;
        document.getElementById("filamentColorPicker").value = hex.startsWith("#") ? hex : (hex ? `#${hex}` : "#ffffff");
        document.getElementById("filamentDiameter").value = f?.diameter || 1.75;
        document.getElementById("filamentDensity").value = f?.density || 1.24;
        document.getElementById("filamentWeight").value = f?.weight_per_spool || 1000;
        document.getElementById("filamentPrice").value = f?.price_per_spool || 0;
        document.getElementById("filamentNotes").value = f?.notes || "";
    } else {
        ["filamentName","filamentColorName","filamentColorHex","filamentNotes"].forEach(id => document.getElementById(id).value = "");
        document.getElementById("filamentMaterial").value = "";
        document.getElementById("filamentColorPicker").value = "#ffffff";
        document.getElementById("filamentDiameter").value = 1.75;
        document.getElementById("filamentDensity").value = 1.24;
        document.getElementById("filamentWeight").value = 1000;
        document.getElementById("filamentPrice").value = 0;
        vendorSel.value = "";
    }
    // Color picker sync
    document.getElementById("filamentColorPicker").oninput = (e) => {
        document.getElementById("filamentColorHex").value = e.target.value;
    };
    document.getElementById("filamentColorHex").oninput = (e) => {
        const val = e.target.value;
        if (/^#[0-9a-fA-F]{6}$/.test(val)) document.getElementById("filamentColorPicker").value = val;
    };
    document.getElementById("filamentModal").showModal();
}

function closeFilamentModal() { document.getElementById("filamentModal").close(); }

async function saveFilament() {
    const id = document.getElementById("filamentId").value;
    const hex = document.getElementById("filamentColorHex").value.trim();
    const payload = {
        vendor_id: document.getElementById("filamentVendor").value ? parseInt(document.getElementById("filamentVendor").value) : null,
        name: document.getElementById("filamentName").value.trim(),
        material: document.getElementById("filamentMaterial").value.trim(),
        color_name: document.getElementById("filamentColorName").value.trim() || null,
        color_hex: hex || null,
        diameter: parseFloat(document.getElementById("filamentDiameter").value) || 1.75,
        density: parseFloat(document.getElementById("filamentDensity").value) || 1.24,
        weight_per_spool: parseFloat(document.getElementById("filamentWeight").value) || 1000,
        price_per_spool: parseFloat(document.getElementById("filamentPrice").value) || 0,
        notes: document.getElementById("filamentNotes").value.trim() || null,
    };
    if (!payload.name || !payload.material) { showToast("Name und Material erforderlich", "error"); return; }
    try {
        const url = id ? `${API}/local/filaments/${id}` : `${API}/local/filaments`;
        const r = await fetch(url, {
            method: id ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (r.ok) {
            showToast(id ? "Filament aktualisiert" : "Filament angelegt", "success");
            closeFilamentModal(); loadFilaments();
        } else { showToast("Fehler beim Speichern", "error"); }
    } catch (e) { showToast("Fehler beim Speichern", "error"); }
}

async function deleteFilament(id) {
    if (!confirm("Filament wirklich löschen?")) return;
    await fetch(`${API}/local/filaments/${id}`, { method: "DELETE" });
    showToast("Filament gelöscht", "success"); loadFilaments();
}

// Local Spools
async function loadLocalSpools() {
    _localSpools = await (await fetch(`${API}/local/spools`)).json();
    renderLocalSpools();
    // Locations für Datalist aktualisieren
    try {
        const locs = await (await fetch(`${API}/local/spools/locations`)).json();
        const dl = document.getElementById("locationList");
        if (dl) dl.innerHTML = locs.map(l => `<option value="${l}">`).join("");
    } catch(e) {}
}

function renderLocalSpools() {
    const grid = document.getElementById("localSpoolsGrid");
    if (!_localSpools.length) {
        grid.innerHTML = '<p class="text-muted">Noch keine Spulen angelegt. Zuerst Hersteller und Filament anlegen.</p>';
        return;
    }
    grid.innerHTML = _localSpools.map(s => {
        const color = s.color_hex ? (s.color_hex.startsWith("#") ? s.color_hex : `#${s.color_hex}`) : "#888";
        const vendor = s.vendor_name ? `${s.vendor_name} ` : "";
        const fname = s.filament_name || "";
        const label = s.label || `${vendor}${fname}`.trim() || `Spule #${s.id}`;
        const initial = s.initial_weight || 1000;
        const remaining = s.remaining_weight ?? initial;
        const pct = Math.min(100, Math.max(0, (remaining / initial) * 100));
        const priceKg = s.weight_per_spool > 0 && s.price_per_spool > 0
            ? (s.price_per_spool / s.weight_per_spool * 1000).toFixed(2) : null;
        return `
        <div class="local-spool-card ${s.is_active ? "is-active" : ""} ${s.is_empty ? "is-empty" : ""}" style="border-top-color:${color}">
            <div class="local-spool-badges">
                ${s.is_active ? '<span class="badge badge-active"><i class="fas fa-circle"></i> Aktiv</span>' : ""}
                ${s.is_empty ? '<span class="badge badge-empty">Leer</span>' : ""}
                ${s.material ? `<span class="badge badge-material">${s.material}</span>` : ""}
            </div>
            <div class="local-spool-name">
                <span class="spool-color" style="background:${color}"></span>${label}
            </div>
            <div class="local-spool-sub">
                ${vendor}${fname}${s.location ? ` · ${s.location}` : ""}
            </div>
            <div class="spool-detail">
                <span class="spool-detail-label">Verbleibend</span>
                <span class="spool-detail-value">${remaining.toFixed(0)}g / ${initial.toFixed(0)}g</span>
            </div>
            ${priceKg ? `<div class="spool-detail"><span class="spool-detail-label">Preis/kg</span><span class="spool-detail-value">${priceKg} EUR</span></div>` : ""}
            <div class="spool-progress">
                <div class="spool-progress-bar" style="width:${pct}%;background:${color}"></div>
            </div>
            <div class="local-spool-actions">
                <button class="btn-edit btn-small" onclick="openLocalSpoolModal(${s.id})"><i class="fas fa-pen"></i> Bearbeiten</button>
                <button class="btn-danger btn-small" onclick="deleteLocalSpool(${s.id})"><i class="fas fa-trash"></i></button>
            </div>
        </div>`;
    }).join("");
}

async function openLocalSpoolModal(spoolId = null) {
    // Filament-Dropdown befüllen
    const filSel = document.getElementById("localSpoolFilament");
    if (!_filaments.length) await loadFilaments();
    filSel.innerHTML = '<option value="">-- Filament wählen --</option>' +
        _filaments.map(f => {
            const vendor = f.vendor_name ? `${f.vendor_name} ` : "";
            return `<option value="${f.id}">${vendor}${f.name} [${f.material}]</option>`;
        }).join("");

    document.getElementById("localSpoolId").value = spoolId || "";
    document.getElementById("localSpoolModalTitle").innerHTML =
        `<i class="fas fa-circle-notch"></i> ${spoolId ? "Spule bearbeiten" : "Neue Spule"}`;

    if (spoolId) {
        const s = _localSpools.find(x => x.id === spoolId);
        filSel.value = s?.filament_id || "";
        document.getElementById("localSpoolLabel").value = s?.label || "";
        document.getElementById("localSpoolLocation").value = s?.location || "";
        document.getElementById("localSpoolInitial").value = s?.initial_weight || 1000;
        document.getElementById("localSpoolRemaining").value = s?.remaining_weight ?? s?.initial_weight ?? 1000;
        document.getElementById("localSpoolDate").value = s?.purchase_date || "";
        document.getElementById("localSpoolActive").checked = !!s?.is_active;
        document.getElementById("localSpoolEmpty").checked = !!s?.is_empty;
        document.getElementById("localSpoolNotes").value = s?.notes || "";
    } else {
        filSel.value = "";
        ["localSpoolLabel","localSpoolLocation","localSpoolNotes"].forEach(id => document.getElementById(id).value = "");
        document.getElementById("localSpoolInitial").value = 1000;
        document.getElementById("localSpoolRemaining").value = 1000;
        document.getElementById("localSpoolDate").value = "";
        document.getElementById("localSpoolActive").checked = false;
        document.getElementById("localSpoolEmpty").checked = false;
    }
    document.getElementById("localSpoolModal").showModal();
}

function closeLocalSpoolModal() { document.getElementById("localSpoolModal").close(); }

async function saveLocalSpool() {
    const id = document.getElementById("localSpoolId").value;
    const payload = {
        filament_id: document.getElementById("localSpoolFilament").value ? parseInt(document.getElementById("localSpoolFilament").value) : null,
        label: document.getElementById("localSpoolLabel").value.trim() || null,
        location: document.getElementById("localSpoolLocation").value.trim() || null,
        initial_weight: parseFloat(document.getElementById("localSpoolInitial").value) || 1000,
        remaining_weight: parseFloat(document.getElementById("localSpoolRemaining").value) || 1000,
        purchase_date: document.getElementById("localSpoolDate").value || null,
        is_active: document.getElementById("localSpoolActive").checked,
        is_empty: document.getElementById("localSpoolEmpty").checked,
        notes: document.getElementById("localSpoolNotes").value.trim() || null,
    };
    try {
        const url = id ? `${API}/local/spools/${id}` : `${API}/local/spools`;
        const r = await fetch(url, {
            method: id ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (r.ok) {
            showToast(id ? "Spule aktualisiert" : "Spule angelegt", "success");
            closeLocalSpoolModal(); loadLocalSpools();
        } else { showToast("Fehler beim Speichern", "error"); }
    } catch (e) { showToast("Fehler beim Speichern", "error"); }
}

async function deleteLocalSpool(id) {
    if (!confirm("Spule wirklich löschen?")) return;
    await fetch(`${API}/local/spools/${id}`, { method: "DELETE" });
    showToast("Spule gelöscht", "success"); loadLocalSpools();
}

// ── Settings ──────────────────────────────────────────────────────────────────
async function loadSettings() {
    try {
        const r = await fetch(`${API}/settings`);
        const s = await r.json();
        if (s.electricity_cost_per_kwh) document.getElementById("settingElectricity").value = s.electricity_cost_per_kwh.value;
        if (s.printer_power_watts) document.getElementById("settingPower").value = s.printer_power_watts.value;
        if (s.default_filament_cost_per_kg) document.getElementById("settingFilament").value = s.default_filament_cost_per_kg.value;
        const r2 = await fetch(`${API}/status`);
        const st = await r2.json();
        document.getElementById("connectionDetails").innerHTML = `
            <div class="conn-item"><span class="conn-label">Moonraker</span>
                <span>${st.moonraker_connected
                    ? '<span style="color:var(--success)"><i class="fas fa-check-circle"></i> Verbunden</span>'
                    : '<span style="color:var(--danger)"><i class="fas fa-times-circle"></i> Getrennt</span>'}</span></div>
            <div class="conn-item"><span class="conn-label">Spoolman</span>
                <span>${st.spoolman_connected
                    ? '<span style="color:var(--success)"><i class="fas fa-check-circle"></i> Verbunden</span>'
                    : '<span style="color:var(--danger)"><i class="fas fa-times-circle"></i> Getrennt</span>'}</span></div>
            <div class="conn-item"><span class="conn-label">Letzte Sync</span>
                <span>${st.last_sync?.sync_time || "Noch nie"}</span></div>
            <div class="conn-item"><span class="conn-label">Drucke in DB</span>
                <span style="font-weight:700">${st.total_jobs_in_db || 0}</span></div>`;
    } catch (e) { console.error("Settings error:", e); }
}

async function saveSettings() {
    try {
        const settings = {
            electricity_cost_per_kwh: parseFloat(document.getElementById("settingElectricity").value) || 0.30,
            printer_power_watts: parseFloat(document.getElementById("settingPower").value) || 200,
            default_filament_cost_per_kg: parseFloat(document.getElementById("settingFilament").value) || 25
        };
        const r = await fetch(`${API}/settings`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(settings)
        });
        showToast(r.ok ? "Einstellungen gespeichert" : "Fehler beim Speichern", r.ok ? "success" : "error");
    } catch (e) { showToast("Fehler beim Speichern", "error"); }
}

async function recalculateCosts() {
    try {
        const r = await fetch(`${API}/recalculate`, { method: "POST" });
        const d = await r.json();
        showToast(d.message || "Kosten neu berechnet", "success");
        loadDashboard(); loadJobs();
    } catch (e) { showToast("Fehler bei Neuberechnung", "error"); }
}

// ── CFS Slots (Spoolman) ──────────────────────────────────────────────────────
async function loadCfsSlots() {
    try {
        const r = await fetch(`${API}/cfs-slots`);
        _cfsData = await r.json();
        const container = document.getElementById("cfsSlotsList");
        if (!_cfsData.slots.length) {
            container.innerHTML = '<p class="text-muted">Keine Orte in Spoolman gefunden.</p>';
            return;
        }
        container.innerHTML = _cfsData.slots.map(slot => {
            const spoolsHtml = slot.spools.length
                ? slot.spools.map(s => `
                    <div class="cfs-spool-item">
                        <span class="spool-color" style="background:${s.color}"></span>
                        <span>${s.name}${s.remaining_weight != null ? ` – ${s.remaining_weight}g` : ""}</span>
                    </div>`).join("")
                : '<span class="text-muted" style="font-size:.8rem">Keine Spulen</span>';
            return `
                <div class="cfs-slot-row">
                    <div class="cfs-slot-header">
                        <i class="fas fa-box-open" style="color:var(--accent)"></i>
                        <span class="cfs-slot-label">${slot.slot_label}</span>
                        <span class="cfs-slot-count">${slot.spools.length} Spule${slot.spools.length !== 1 ? "n" : ""}</span>
                    </div>
                    <div class="cfs-spool-list">${spoolsHtml}</div>
                </div>`;
        }).join("");
    } catch (e) {
        document.getElementById("cfsSlotsList").innerHTML = '<p class="text-muted">Fehler beim Laden</p>';
    }
}
