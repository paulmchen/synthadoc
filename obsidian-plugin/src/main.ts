// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com
import { App, MarkdownRenderer, Modal, Notice, Plugin, PluginSettingTab, Setting, SuggestModal, TFile } from "obsidian";
import { api, setBase } from "./api";

const SUPPORTED_EXTENSIONS = new Set([
    "md", "txt", "pdf", "docx", "xlsx", "csv",
    "png", "jpg", "jpeg", "webp", "gif", "tiff",
]);

interface SynthadocSettings {
    serverUrl: string;
    rawSourcesFolder: string;
}

const DEFAULT_SETTINGS: SynthadocSettings = {
    serverUrl: "http://127.0.0.1:7070",
    rawSourcesFolder: "raw_sources",
};

export default class SynthadocPlugin extends Plugin {
    settings: SynthadocSettings = DEFAULT_SETTINGS;

    async onload() {
        await this.loadSettings();
        setBase(this.settings.serverUrl);
        this.addSettingTab(new SynthadocSettingTab(this.app, this));

        this.addCommand({
            id: "synthadoc-ingest-current",
            name: "Ingest: current file",
            callback: () => {
                const file = this.app.workspace.getActiveFile();
                if (file) {
                    new IngestConfirmModal(this.app, file).open();
                } else {
                    new IngestPickerModal(this.app, this).open();
                }
            },
        });

        this.addCommand({
            id: "synthadoc-ingest-all",
            name: "Ingest: all sources in folder",
            callback: () => this.ingestAllSources(),
        });

        this.addCommand({
            id: "synthadoc-query",
            name: "Query: ask the wiki...",
            callback: () => new QueryModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-jobs",
            name: "Jobs: list...",
            callback: () => new JobsModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-lint-report",
            name: "Lint: report",
            callback: () => new LintReportModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-ingest-url",
            name: "Ingest: from URL...",
            callback: () => new IngestUrlModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-web-search",
            name: "Ingest: web search...",
            callback: () => new WebSearchModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-lint",
            name: "Lint: run...",
            callback: () => new LintRunModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-jobs-retry-dead",
            name: "Jobs: retry dead job...",
            callback: () => new RetryJobModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-jobs-purge",
            name: "Jobs: purge old completed/dead...",
            callback: () => new PurgeJobsModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-scaffold",
            name: "Wiki: regenerate scaffold...",
            callback: () => new ScaffoldModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-audit-history",
            name: "Audit: ingest history...",
            callback: () => new AuditHistoryModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-audit-costs",
            name: "Audit: cost summary...",
            callback: () => new AuditCostsModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-audit-queries",
            name: "Audit: query history...",
            callback: () => new QueryHistoryModal(this.app).open(),
        });

        this.addRibbonIcon("book-open", "Synthadoc status", async () => {
            const [healthRes, statusRes] = await Promise.allSettled([
                api.health(),
                api.status(),
            ]);
            const online = healthRes.status === "fulfilled";
            const engineLabel = online ? "✅ online" : "❌ offline — run 'synthadoc serve'";
            const pages = statusRes.status === "fulfilled"
                ? ` · ${(statusRes.value as any).pages} pages`
                : "";
            new Notice(`Synthadoc: ${engineLabel}${pages}`);
        });
    }

    async loadSettings() {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    }

    async saveSettings() {
        await this.saveData(this.settings);
    }

    async ingestFile(file: TFile) {
        try {
            const r = await api.ingest(file.path) as any;
            new Notice(`Synthadoc: ingest queued (job ${r.job_id})`);
        } catch { new Notice("Synthadoc: ingest failed — is the server running?"); }
    }

    async ingestAllSources() {
        const folder = this.settings.rawSourcesFolder.replace(/\/$/, "");
        const files = this.app.vault.getFiles().filter(f => {
            if (!f.path.startsWith(folder + "/")) return false;
            const ext = f.extension?.toLowerCase() ?? "";
            return SUPPORTED_EXTENSIONS.has(ext);
        });
        if (files.length === 0) {
            new Notice(`Synthadoc: no files found in '${folder}'`);
            return;
        }
        new Notice(`Synthadoc: queuing ${files.length} source(s)…`);
        let queued = 0;
        let failed = 0;
        for (const file of files) {
            try {
                await api.ingest(file.path);
                queued++;
            } catch {
                failed++;
            }
        }
        if (failed === 0) {
            new Notice(`Synthadoc: ${queued} job(s) queued`);
        } else {
            new Notice(`Synthadoc: ${queued} queued, ${failed} failed — is the server running?`);
        }
    }
}

class IngestConfirmModal extends Modal {
    private _file: TFile;
    private _pollTimer: number | null = null;

    constructor(app: App, file: TFile) {
        super(app);
        this._file = file;
    }

    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Ingest file" });
        makeDraggable(this.modalEl, titleEl);

        const infoEl = contentEl.createEl("div");
        infoEl.style.cssText = "margin-bottom:16px;padding:8px 10px;background:var(--background-secondary);border-radius:4px;-webkit-user-select:text;user-select:text";
        infoEl.createEl("div", { text: this._file.name }).style.cssText = "font-weight:bold;font-size:13px";
        infoEl.createEl("div", { text: this._file.path }).style.cssText = "font-size:11px;color:var(--text-muted);margin-top:2px";

        const btnRow = contentEl.createEl("div");
        btnRow.style.cssText = "display:flex;justify-content:flex-end";
        const btn = btnRow.createEl("button", { text: "Ingest" });

        const out = contentEl.createEl("div");
        out.style.cssText = "margin-top:12px;-webkit-user-select:text;user-select:text";

        const setStatus = (text: string, color?: string) => {
            out.empty();
            const p = out.createEl("p", { text });
            if (color) p.style.cssText = `color:${color}`;
        };

        btn.onclick = async () => {
            btn.disabled = true;
            setStatus("⏳ Queuing…");
            try {
                const r = await api.ingest(this._file.path) as any;
                const jobId: string = r.job_id;
                setStatus(`⏳ Queued — job ${jobId.slice(0, 8)}`);

                this._pollTimer = window.setInterval(async () => {
                    try {
                        const job = await api.job(jobId) as any;
                        const status: string = job.status;

                        if (status === "pending") { setStatus(`⏳ Queued — job ${jobId.slice(0, 8)}`); return; }
                        if (status === "in_progress") { setStatus(`⏳ Ingesting… (job ${jobId.slice(0, 8)})`); return; }

                        window.clearInterval(this._pollTimer!);
                        this._pollTimer = null;
                        btn.disabled = false;

                        if (status === "completed") {
                            const res = job.result ?? {};
                            const parts: string[] = [];
                            if (res.pages_created?.length) parts.push(`created: ${res.pages_created.join(", ")}`);
                            if (res.pages_updated?.length) parts.push(`updated: ${res.pages_updated.join(", ")}`);
                            if (res.pages_flagged?.length) parts.push(`flagged: ${res.pages_flagged.join(", ")}`);
                            out.empty();
                            out.createEl("p", { text: "✅ Done." }).style.cssText = "font-weight:bold;margin-bottom:4px";
                            if (parts.length) out.createEl("p", { text: parts.join(" · ") }).style.cssText = "font-size:12px;color:var(--text-muted)";
                            new Notice(`Synthadoc: ingest done — ${this._file.name}`);
                        } else if (status === "skipped") {
                            setStatus("⏭️ Skipped — already ingested.", "var(--text-muted)");
                        } else {
                            setStatus(`❌ ${status}${job.error ? `: ${job.error}` : ""}`, "var(--text-error)");
                        }
                    } catch { /* server unreachable — keep polling */ }
                }, 2000);
            } catch {
                setStatus("❌ Error: is synthadoc serve running?", "var(--text-error)");
                btn.disabled = false;
            }
        };
    }

    onClose() {
        if (this._pollTimer !== null) {
            window.clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
        this.contentEl.empty();
    }
}

class IngestPickerModal extends SuggestModal<TFile> {
    private plugin: SynthadocPlugin;

    constructor(app: App, plugin: SynthadocPlugin) {
        super(app);
        this.plugin = plugin;
        this.setPlaceholder("Select a source file to ingest…");
    }

    getSuggestions(query: string): TFile[] {
        const folder = this.plugin.settings.rawSourcesFolder.replace(/\/$/, "");
        const q = query.toLowerCase();
        return this.app.vault.getFiles().filter(f => {
            if (!f.path.startsWith(folder + "/")) return false;
            const ext = f.extension?.toLowerCase() ?? "";
            if (!SUPPORTED_EXTENSIONS.has(ext)) return false;
            return q ? f.name.toLowerCase().includes(q) : true;
        });
    }

    renderSuggestion(file: TFile, el: HTMLElement): void {
        el.createEl("div", { text: file.name });
        el.createEl("div", { text: file.path, cls: "synthadoc-muted" }).style.fontSize = "11px";
    }

    onChooseSuggestion(file: TFile): void {
        new IngestConfirmModal(this.app, file).open();
    }
}

class SynthadocSettingTab extends PluginSettingTab {
    plugin: SynthadocPlugin;

    constructor(app: App, plugin: SynthadocPlugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    display(): void {
        const { containerEl } = this;
        containerEl.empty();
        containerEl.createEl("h2", { text: "Synthadoc settings" });

        new Setting(containerEl)
            .setName("Server URL")
            .setDesc("URL of the synthadoc HTTP server for this vault (e.g. http://127.0.0.1:7070)")
            .addText(text => text
                .setPlaceholder("http://127.0.0.1:7070")
                .setValue(this.plugin.settings.serverUrl)
                .onChange(async (value) => {
                    this.plugin.settings.serverUrl = value;
                    setBase(value);
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName("Raw sources folder")
            .setDesc("Vault-relative folder scanned by 'Ingest all sources' (default: raw_sources)")
            .addText(text => text
                .setPlaceholder("raw_sources")
                .setValue(this.plugin.settings.rawSourcesFolder)
                .onChange(async (value) => {
                    this.plugin.settings.rawSourcesFolder = value;
                    await this.plugin.saveSettings();
                }));
    }
}

const STATUS_EMOJI: Record<string, string> = {
    pending:     "🕐",
    in_progress: "⏳",
    completed:   "✅",
    failed:      "❌",
    skipped:     "⏭️",
    dead:        "💀",
};

const STATUS_FILTER_OPTIONS = ["pending", "in_progress", "completed", "failed", "skipped", "dead"] as const;

function makeDraggable(modalEl: HTMLElement, handle: HTMLElement): void {
    if (typeof document === "undefined" || typeof handle.addEventListener !== "function") return;
    modalEl.style.position = "fixed";
    handle.style.cursor = "grab";
    let dragging = false;
    let startX = 0, startY = 0, origLeft = 0, origTop = 0;

    const startDrag = (e: MouseEvent) => {
        dragging = true;
        startX = e.clientX;
        startY = e.clientY;
        const rect = modalEl.getBoundingClientRect();
        origLeft = rect.left;
        origTop = rect.top;
        modalEl.style.transform = "none";
        modalEl.style.left = origLeft + "px";
        modalEl.style.top = origTop + "px";
        modalEl.style.margin = "0";
        handle.style.cursor = "grabbing";
        e.preventDefault();
    };

    // Drag from the title bar
    handle.addEventListener("mousedown", startDrag);

    // Also drag from the modal frame/padding — but not from inside the content area
    modalEl.addEventListener("mousedown", (e: MouseEvent) => {
        if (handle.contains(e.target as Node)) return; // already handled above
        if (handle.parentElement && handle.parentElement.contains(e.target as Node)) return; // inside content
        startDrag(e);
    });

    document.addEventListener("mousemove", (e: MouseEvent) => {
        if (!dragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        modalEl.style.left = (origLeft + dx) + "px";
        modalEl.style.top  = (origTop  + dy) + "px";
    });

    document.addEventListener("mouseup", () => {
        if (dragging) {
            dragging = false;
            handle.style.cursor = "grab";
        }
    });
}

class JobsModal extends Modal {
    private _selected: Set<string> = new Set(["pending", "in_progress"]);
    private _intervalSecs = 10;
    private _countdown = 10;
    private _countdownTimer: number | null = null;
    private _tableEl: HTMLElement | null = null;
    private _countdownEl: HTMLElement | null = null;

    onOpen() {
        this.modalEl.style.width = "clamp(560px, 65vw, 900px)";
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Jobs" });
        makeDraggable(this.modalEl, titleEl);

        // Status checkboxes
        const filterRow = contentEl.createEl("div");
        filterRow.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:8px";
        const filterLabel = filterRow.createEl("span", { text: "Show:" });
        filterLabel.style.cssText = "font-size:12px;font-weight:600;margin-right:2px";

        for (const status of STATUS_FILTER_OPTIONS) {
            const label = filterRow.createEl("label");
            label.style.cssText = "display:flex;align-items:center;gap:4px;font-size:12px;cursor:pointer;user-select:none";
            const cb = label.createEl("input", { type: "checkbox" }) as HTMLInputElement;
            cb.checked = this._selected.has(status);
            label.appendText(status.replace("_", " "));
            cb.onchange = () => {
                if (cb.checked) this._selected.add(status);
                else this._selected.delete(status);
                this._resetAndLoad();
            };
        }

        // Interval + countdown row
        const intervalRow = contentEl.createEl("div");
        intervalRow.style.cssText = "display:flex;align-items:center;gap:6px;margin-bottom:10px;font-size:12px;color:var(--text-muted)";
        intervalRow.createEl("span", { text: "Auto-refresh every" });
        const intervalInput = intervalRow.createEl("input", { type: "number" }) as HTMLInputElement;
        intervalInput.value = String(this._intervalSecs);
        intervalInput.min = "5";
        intervalInput.max = "30";
        intervalInput.style.cssText = "width:46px;padding:2px 5px;font-size:12px";
        intervalRow.createEl("span", { text: "s  ·" });
        this._countdownEl = intervalRow.createEl("span");

        intervalInput.onchange = () => {
            const v = Math.min(30, Math.max(5, parseInt(intervalInput.value) || 10));
            intervalInput.value = String(v);
            this._intervalSecs = v;
            this._resetAndLoad();
        };

        // Table
        this._tableEl = contentEl.createEl("div");
        this._tableEl.style.cssText = "-webkit-user-select:text;user-select:text";

        this._resetAndLoad();
    }

    private _resetAndLoad() {
        this._stopTimer();
        this._countdown = this._intervalSecs;
        this._tickCountdown();
        this._load();
        this._countdownTimer = window.setInterval(() => {
            this._countdown--;
            this._tickCountdown();
            if (this._countdown <= 0) {
                this._countdown = this._intervalSecs;
                this._load();
            }
        }, 1000);
    }

    private _tickCountdown() {
        if (this._countdownEl) {
            this._countdownEl.setText(`refreshing in ${this._countdown}s`);
        }
    }

    private _stopTimer() {
        if (this._countdownTimer !== null) {
            window.clearInterval(this._countdownTimer);
            this._countdownTimer = null;
        }
    }

    private async _load() {
        if (!this._tableEl) return;
        try {
            const allJobs = await api.jobs() as any[];
            const filtered = this._selected.size === 0
                ? allJobs
                : allJobs.filter((j: any) => this._selected.has(j.status));
            this._renderTable(filtered);
        } catch {
            if (this._tableEl) this._tableEl.setText("Error: is synthadoc serve running?");
        }
    }

    private _renderTable(jobs: any[]) {
        if (!this._tableEl) return;
        this._tableEl.empty();

        if (jobs.length === 0) {
            this._tableEl.createEl("p", { text: "No jobs match the selected filters.", cls: "synthadoc-muted" });
            return;
        }

        const table = this._tableEl.createEl("table");
        table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px;-webkit-user-select:text;user-select:text";

        const hrow = table.createEl("thead").createEl("tr");
        for (const h of ["Job ID", "Status", "Operation", "Source", "Created"]) {
            const th = hrow.createEl("th", { text: h });
            th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border)";
        }

        const tbody = table.createEl("tbody");
        for (const job of jobs) {
            const tr = tbody.createEl("tr");
            const source = job.payload?.source
                ? job.payload.source.split(/[\\/]/).pop()
                : job.operation === "lint" ? "(lint)" : "—";
            // SQLite stores UTC without tz marker; append +00:00 so JS parses as UTC
            const created = job.created_at
                ? new Date(job.created_at.replace(" ", "T") + "+00:00").toLocaleString()
                : "—";
            const icon = STATUS_EMOJI[job.status] ?? "";

            // Job ID cell — monospace, full ID visible and selectable for copy
            const idTd = tr.createEl("td");
            idTd.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle);font-family:monospace;font-size:11px;color:var(--text-muted)";
            idTd.setText(job.id ?? "—");

            for (const text of [`${icon} ${job.status}`, job.operation, source, created]) {
                const td = tr.createEl("td", { text });
                td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
            }
            if (job.status === "completed" && job.result) {
                const r = job.result;
                const detail: string[] = [];
                if (r.pages_created?.length) detail.push(`created: ${r.pages_created.join(", ")}`);
                if (r.pages_updated?.length) detail.push(`updated: ${r.pages_updated.join(", ")}`);
                if (r.pages_flagged?.length) detail.push(`flagged: ${r.pages_flagged.join(", ")}`);
                if (detail.length) {
                    const dtd = tbody.createEl("tr").createEl("td", { text: detail.join(" · ") });
                    dtd.colSpan = 5;
                    dtd.style.cssText = "padding:2px 8px 6px 8px;font-size:11px;color:var(--text-muted)";
                }
            }
            if (job.status === "failed" && job.error) {
                const etd = tbody.createEl("tr").createEl("td", { text: `Error: ${job.error}` });
                etd.colSpan = 5;
                etd.style.cssText = "padding:2px 8px 6px 8px;font-size:11px;color:var(--text-error)";
            }
        }
    }

    onClose() {
        this._stopTimer();
        this.contentEl.empty();
    }
}

class LintRunModal extends Modal {
    private _pollTimer: number | null = null;

    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Run lint" });
        makeDraggable(this.modalEl, titleEl);

        const optRow = contentEl.createEl("div");
        optRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:8px";
        const cb = optRow.createEl("input", { type: "checkbox" }) as HTMLInputElement;
        cb.id = "lint-auto-resolve";
        const lbl = optRow.createEl("label", { text: "Auto-resolve contradictions" });
        lbl.htmlFor = "lint-auto-resolve";
        lbl.style.cssText = "font-size:13px;cursor:pointer";

        const hint = contentEl.createEl("p", {
            text: "Auto-resolve rewrites contradicted pages to reconcile conflicts automatically. Leave unchecked to review the report first.",
        });
        hint.style.cssText = "font-size:11px;color:var(--text-muted);margin-bottom:16px;-webkit-user-select:text;user-select:text";

        const btnRow = contentEl.createEl("div");
        btnRow.style.cssText = "display:flex;justify-content:flex-end";
        const btn = btnRow.createEl("button", { text: "Run lint" });

        const out = contentEl.createEl("div");
        out.style.cssText = "margin-top:12px;-webkit-user-select:text;user-select:text";

        btn.onclick = async () => {
            const autoResolve = cb.checked;
            btn.disabled = true;
            cb.disabled = true;
            out.empty();
            out.createEl("p", { text: autoResolve ? "⏳ Enqueueing lint with auto-resolve…" : "⏳ Enqueueing lint…" });
            try {
                const r = await api.lint("all", autoResolve) as any;
                const jobId: string = r.job_id;
                out.empty();
                out.createEl("p", { text: `⏳ Lint running… (job ${jobId.slice(0, 8)})` });

                this._pollTimer = window.setInterval(async () => {
                    try {
                        const job = await api.job(jobId) as any;
                        const status: string = job.status;

                        if (status === "in_progress" || status === "pending") {
                            out.empty();
                            out.createEl("p", { text: `⏳ Lint ${status === "pending" ? "queued" : "running"}… (job ${jobId.slice(0, 8)})` });
                            return;
                        }

                        // Job settled — stop polling
                        window.clearInterval(this._pollTimer!);
                        this._pollTimer = null;

                        if (status === "completed") {
                            // Fetch the actual lint report for contradiction/orphan counts
                            try {
                                const report = await api.lintReport() as any;
                                const contradictions: string[] = report.contradictions ?? [];
                                const orphans: string[] = report.orphans ?? [];
                                out.empty();
                                const summary = out.createEl("p");
                                summary.style.cssText = "font-weight:bold;margin-bottom:6px";
                                summary.setText(`✅ Done — ${contradictions.length} contradiction(s), ${orphans.length} orphan(s).`);
                                if (contradictions.length > 0) {
                                    out.createEl("p", { text: `Contradictions: ${contradictions.join(", ")}` }).style.cssText = "font-size:12px;color:var(--text-error)";
                                }
                                if (orphans.length > 0) {
                                    out.createEl("p", { text: `Orphans: ${orphans.join(", ")}` }).style.cssText = "font-size:12px;color:var(--text-muted)";
                                }
                                new Notice(`Synthadoc: lint done — ${contradictions.length} contradictions, ${orphans.length} orphans`);
                            } catch {
                                out.empty();
                                out.createEl("p", { text: "✅ Lint complete. Could not load report." });
                            }
                        } else {
                            out.empty();
                            out.createEl("p", { text: `❌ Lint ${status}${job.error ? `: ${job.error}` : ""}` }).style.cssText = "color:var(--text-error)";
                        }
                        btn.disabled = false;
                        cb.disabled = false;
                    } catch {
                        // server unreachable — keep polling silently
                    }
                }, 2000);
            } catch {
                out.empty();
                out.createEl("p", { text: "❌ Error: is synthadoc serve running?" });
                btn.disabled = false;
                cb.disabled = false;
            }
        };
    }

    onClose() {
        if (this._pollTimer !== null) {
            window.clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
        this.contentEl.empty();
    }
}

class LintReportModal extends Modal {
    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Lint report" });
        makeDraggable(this.modalEl, titleEl);
        const out = contentEl.createEl("div");
        out.style.cssText = "-webkit-user-select:text;user-select:text";
        out.createEl("p", { text: "Loading…", cls: "synthadoc-muted" });

        api.lintReport().then((r: any) => {
            out.empty();
            const contradictions: string[] = r.contradictions ?? [];
            const orphanDetails: Array<{ slug: string; index_suggestion: string }> =
                r.orphan_details ?? (r.orphans ?? []).map((s: string) => ({ slug: s, index_suggestion: `- [[${s}]]` }));

            if (contradictions.length === 0 && orphanDetails.length === 0) {
                out.createEl("p", { text: "✅ All clear — no contradictions or orphan pages." });
                return;
            }

            if (contradictions.length > 0) {
                out.createEl("h4", { text: `❌ Contradicted pages (${contradictions.length})` });
                const ul = out.createEl("ul");
                contradictions.forEach(slug => {
                    const li = ul.createEl("li");
                    li.createEl("code", { text: slug });
                    li.appendText(" — open the page, resolve the conflict, set status: active");
                });
            }

            if (orphanDetails.length > 0) {
                out.createEl("h4", { text: `🔗 Orphan pages (${orphanDetails.length})` });
                const ul = out.createEl("ul");
                orphanDetails.forEach(({ slug, index_suggestion }) => {
                    const li = ul.createEl("li");
                    li.createEl("code", { text: slug });
                    li.appendText(" — no inbound links");
                    const sug = li.createEl("div");
                    sug.style.cssText = "font-size:11px;color:var(--text-muted);margin-top:2px";
                    sug.appendText("Suggested index entry: ");
                    sug.createEl("code", { text: index_suggestion });
                });
            }
        }).catch(() => {
            out.empty();
            out.createEl("p", { text: "Error: is synthadoc serve running?" });
        });
    }
    onClose() { this.contentEl.empty(); }
}

class IngestUrlModal extends Modal {
    private _pollTimer: number | null = null;

    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Ingest from URL" });
        makeDraggable(this.modalEl, titleEl);

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;gap:8px;margin-bottom:12px";
        const input = row.createEl("input", { type: "url", placeholder: "https://..." });
        input.style.cssText = "flex:1;padding:4px 8px";
        const btn = row.createEl("button", { text: "Ingest" });

        const out = contentEl.createEl("div");
        out.style.cssText = "margin-top:4px;-webkit-user-select:text;user-select:text";

        const setStatus = (text: string, color?: string) => {
            out.empty();
            const p = out.createEl("p", { text });
            if (color) p.style.cssText = `color:${color}`;
        };

        const startPolling = (jobId: string) => {
            this._pollTimer = window.setInterval(async () => {
                try {
                    const job = await api.job(jobId) as any;
                    const status: string = job.status;

                    if (status === "pending") {
                        setStatus(`⏳ Queued — job ${jobId.slice(0, 8)}`);
                        return;
                    }
                    if (status === "in_progress") {
                        setStatus(`⏳ Ingesting… (job ${jobId.slice(0, 8)})`);
                        return;
                    }

                    // Settled
                    window.clearInterval(this._pollTimer!);
                    this._pollTimer = null;
                    btn.disabled = false;
                    input.disabled = false;

                    if (status === "completed") {
                        const r = job.result ?? {};
                        const parts: string[] = [];
                        if (r.pages_created?.length) parts.push(`created: ${r.pages_created.join(", ")}`);
                        if (r.pages_updated?.length) parts.push(`updated: ${r.pages_updated.join(", ")}`);
                        if (r.pages_flagged?.length) parts.push(`flagged: ${r.pages_flagged.join(", ")}`);
                        out.empty();
                        out.createEl("p", { text: "✅ Done." }).style.cssText = "font-weight:bold;margin-bottom:4px";
                        if (parts.length) out.createEl("p", { text: parts.join(" · ") }).style.cssText = "font-size:12px;color:var(--text-muted)";
                        new Notice(`Synthadoc: ingest done (job ${jobId.slice(0, 8)})`);
                    } else if (status === "skipped") {
                        setStatus(`⏭️ Skipped — already ingested.`, "var(--text-muted)");
                    } else {
                        setStatus(`❌ ${status}${job.error ? `: ${job.error}` : ""}`, "var(--text-error)");
                    }
                } catch {
                    // server unreachable — keep polling silently
                }
            }, 2000);
        };

        const submit = async () => {
            const url = input.value.trim();
            if (!url) return;
            btn.disabled = true;
            input.disabled = true;
            setStatus("⏳ Queuing…");
            try {
                const r = await api.ingest(url) as any;
                const jobId: string = r.job_id;
                setStatus(`⏳ Queued — job ${jobId.slice(0, 8)}`);
                startPolling(jobId);
            } catch {
                setStatus("❌ Error: is synthadoc serve running?", "var(--text-error)");
                btn.disabled = false;
                input.disabled = false;
            }
        };

        btn.onclick = submit;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
    }

    onClose() {
        if (this._pollTimer !== null) {
            window.clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
        this.contentEl.empty();
    }
}

class WebSearchModal extends Modal {
    private _pollTimer: number | null = null;
    private _pollInterval = 2000;

    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Web search" });
        makeDraggable(this.modalEl, titleEl);
        contentEl.createEl("p", {
            text: "Type a topic — Synthadoc will search the web and compile results into your wiki.",
            cls: "synthadoc-muted",
        }).style.cssText = "font-size:12px;margin-bottom:12px";

        const input = contentEl.createEl("textarea", { placeholder: "e.g. Bank of Canada rate outlook 2025\nOntario housing market trends" });
        input.style.cssText = "width:100%;min-height:80px;padding:6px 8px;resize:vertical;margin-bottom:8px;box-sizing:border-box";

        const settingsRow = contentEl.createEl("div");
        settingsRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:12px";
        settingsRow.createEl("label", { text: "Max results:" });
        const maxResultsInput = settingsRow.createEl("input", { type: "number" }) as HTMLInputElement;
        maxResultsInput.value = "20";
        maxResultsInput.min = "1";
        maxResultsInput.max = "50";
        maxResultsInput.step = "1";
        maxResultsInput.style.cssText = "width:60px;padding:4px 6px";
        settingsRow.createEl("span", { text: "URLs" }).style.marginRight = "16px";
        settingsRow.createEl("label", { text: "Poll interval:" });
        const intervalInput = settingsRow.createEl("input", { type: "number" }) as HTMLInputElement;
        intervalInput.value = "2000";
        intervalInput.min = "500";
        intervalInput.max = "10000";
        intervalInput.step = "500";
        intervalInput.style.cssText = "width:70px;padding:4px 6px";
        settingsRow.createEl("span", { text: "ms" });

        const btnRow = contentEl.createEl("div");
        btnRow.style.cssText = "display:flex;justify-content:flex-end;margin-bottom:12px";
        const btn = btnRow.createEl("button", { text: "Search" });

        const statusEl = contentEl.createEl("p");
        statusEl.style.cssText = "font-size:12px;min-height:20px;margin-bottom:4px;-webkit-user-select:text;user-select:text";

        const pagesEl = contentEl.createEl("div");
        pagesEl.style.cssText = "-webkit-user-select:text;user-select:text";
        const errorsEl = contentEl.createEl("div");
        errorsEl.style.cssText = "-webkit-user-select:text;user-select:text";

        const submit = async () => {
            const topic = input.value.trim();
            if (!topic) return;
            btn.disabled = true;
            input.disabled = true;
            this._pollInterval = Math.min(10000, Math.max(500, parseInt(intervalInput.value) || 2000));
            const maxResults = Math.min(50, Math.max(1, parseInt(maxResultsInput.value) || 20));
            statusEl.setText("Queuing web search…");
            pagesEl.empty();
            errorsEl.empty();
            try {
                const r = await api.ingest(`search for: ${topic}`, maxResults) as any;
                const jobId: string = r.job_id;
                new Notice(`Synthadoc: web search queued (job ${jobId})`);
                this._startPolling(jobId, statusEl, pagesEl, errorsEl);
            } catch {
                statusEl.setText("Error: is synthadoc serve running?");
                btn.disabled = false;
                input.disabled = false;
            }
        };

        btn.onclick = submit;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); });
        setTimeout(() => input.focus(), 50);
    }

    private _startPolling(
        jobId: string,
        statusEl: HTMLElement,
        pagesEl: HTMLElement,
        errorsEl: HTMLElement,
    ) {
        const pages = new Set<string>();
        const errors: string[] = [];
        let childJobIds: string[] = [];
        let childDone = 0;

        const poll = async () => {
            try {
                const job = await api.job(jobId) as any;
                const phase = job.progress?.phase;
                const isDone = ["completed", "failed", "dead", "skipped"].includes(job.status);

                if (job.result?.child_job_ids?.length && childJobIds.length === 0) {
                    childJobIds = job.result.child_job_ids;
                }

                // Phase status — only shown while parent is still running
                if (!isDone) {
                    if (phase === "searching") {
                        statusEl.setText("Searching the web…");
                    } else if (phase === "found_urls") {
                        const total = job.progress?.total ?? 0;
                        statusEl.setText(`Found ${total} URL${total !== 1 ? "s" : ""} — ingesting…`);
                    }
                }

                if (childJobIds.length > 0) {
                    const allJobs = await api.jobs() as any[];
                    childDone = 0;
                    for (const cj of allJobs) {
                        if (!childJobIds.includes(cj.id)) continue;
                        if (cj.status === "completed") {
                            childDone++;
                            for (const s of (cj.result?.pages_created ?? [])) pages.add(s);
                            for (const s of (cj.result?.pages_updated ?? [])) pages.add(s);
                        } else if (["failed", "dead", "skipped"].includes(cj.status) && cj.error) {
                            const src = cj.payload?.source ?? cj.id;
                            const msg = `${src}: ${cj.error}`;
                            if (!errors.includes(msg)) errors.push(msg);
                        }
                    }
                    // Always show ingesting progress once child jobs are known
                    const settled = childDone + errors.length;
                    if (settled < childJobIds.length) {
                        statusEl.setText(`Ingesting ${childJobIds.length} URL${childJobIds.length !== 1 ? "s" : ""}… (${settled} done)`);
                    }
                }

                if (pages.size > 0) {
                    pagesEl.empty();
                    pagesEl.createEl("p", { text: `Pages (${pages.size}):` }).style.cssText = "font-size:12px;font-weight:bold;margin-bottom:2px";
                    const ul = pagesEl.createEl("ul");
                    ul.style.cssText = "font-size:12px;margin:0;padding-left:18px;-webkit-user-select:text;user-select:text";
                    for (const slug of pages) ul.createEl("li", { text: slug });
                }

                if (errors.length > 0) {
                    errorsEl.empty();
                    errorsEl.createEl("p", { text: `Errors (${errors.length}):` }).style.cssText = "font-size:12px;font-weight:bold;margin-bottom:2px;color:var(--text-error)";
                    const ul = errorsEl.createEl("ul");
                    ul.style.cssText = "font-size:12px;margin:0;padding-left:18px;color:var(--text-error);-webkit-user-select:text;user-select:text";
                    for (const err of errors) ul.createEl("li", { text: err });
                }

                const allChildrenSettled = childJobIds.length > 0 && (childDone + errors.length) >= childJobIds.length;
                if (isDone && (childJobIds.length === 0 || allChildrenSettled)) {
                    this._stopPolling();
                    if (job.status === "completed" || allChildrenSettled) {
                        statusEl.setText(`Done — ${pages.size} page(s) written.`);
                        new Notice(`Synthadoc: web search complete — ${pages.size} page(s)`);
                    } else {
                        statusEl.setText(`Search ${job.status}${job.error ? `: ${job.error}` : ""}`);
                    }
                    return;
                }
            } catch {
                // Server unreachable — keep polling silently
            }
            this._pollTimer = window.setTimeout(poll, this._pollInterval);
        };

        this._pollTimer = window.setTimeout(poll, this._pollInterval);
    }

    private _stopPolling() {
        if (this._pollTimer !== null) {
            window.clearTimeout(this._pollTimer);
            this._pollTimer = null;
        }
    }

    onClose() {
        this._stopPolling();
        this.contentEl.empty();
    }
}

class RetryJobModal extends Modal {
    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Retry dead job" });
        makeDraggable(this.modalEl, titleEl);

        const out = contentEl.createEl("div");
        out.createEl("p", { text: "Loading dead jobs…", cls: "synthadoc-muted" });

        api.jobs("dead").then((jobs: any[]) => {
            out.empty();
            if (!jobs.length) {
                out.createEl("p", { text: "No dead jobs." });
                return;
            }
            const table = out.createEl("table");
            table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px;-webkit-user-select:text;user-select:text";
            const hrow = table.createEl("thead").createEl("tr");
            for (const h of ["Job ID", "Operation", "Source", "Error", ""]) {
                const th = hrow.createEl("th", { text: h });
                th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border)";
            }
            const tbody = table.createEl("tbody");
            for (const job of jobs) {
                const tr = tbody.createEl("tr");
                const source = job.payload?.source
                    ? job.payload.source.split(/[\\/]/).pop()
                    : job.operation;
                for (const text of [job.id, job.operation, source, job.error ?? "—"]) {
                    const td = tr.createEl("td", { text });
                    td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
                }
                const btnTd = tr.createEl("td");
                btnTd.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
                const btn = btnTd.createEl("button", { text: "Retry" });
                btn.onclick = async () => {
                    btn.disabled = true;
                    btn.setText("…");
                    try {
                        await api.retryJob(job.id);
                        new Notice(`Synthadoc: job ${job.id} re-queued`);
                        tr.remove();
                    } catch {
                        new Notice("Synthadoc: retry failed — is the server running?");
                        btn.disabled = false;
                        btn.setText("Retry");
                    }
                };
            }
        }).catch(() => {
            out.empty();
            out.createEl("p", { text: "Error: is synthadoc serve running?" });
        });
    }
    onClose() { this.contentEl.empty(); }
}

class PurgeJobsModal extends Modal {
    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Purge old jobs" });
        makeDraggable(this.modalEl, titleEl);
        contentEl.createEl("p", {
            text: "Removes completed and dead jobs older than the specified number of days.",
            cls: "synthadoc-muted",
        }).style.cssText = "font-size:12px;margin-bottom:12px";

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Older than (days):" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "7";
        input.style.cssText = "width:70px;padding:4px 8px";
        const btn = row.createEl("button", { text: "Purge" });

        const out = contentEl.createEl("p");

        btn.onclick = async () => {
            const days = parseInt(input.value) || 7;
            btn.disabled = true;
            out.setText("Purging…");
            try {
                const r = await api.purgeJobs(days) as any;
                out.setText(`Purged ${r.purged} job(s) older than ${days} day(s).`);
                new Notice(`Synthadoc: purged ${r.purged} job(s)`);
            } catch {
                out.setText("Error: is synthadoc serve running?");
            } finally { btn.disabled = false; }
        };
    }
    onClose() { this.contentEl.empty(); }
}

class ScaffoldModal extends Modal {
    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Regenerate scaffold" });
        makeDraggable(this.modalEl, titleEl);
        contentEl.createEl("p", {
            text: "Rewrites index.md, AGENTS.md, and purpose.md for your wiki domain using the LLM. Existing wiki pages are preserved.",
            cls: "synthadoc-muted",
        }).style.cssText = "font-size:12px;margin-bottom:12px";

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;gap:8px;margin-bottom:12px";
        const input = row.createEl("input", { type: "text", placeholder: "e.g. Canadian tax law" });
        input.style.cssText = "flex:1;padding:4px 8px";
        const btn = row.createEl("button", { text: "Scaffold" });

        const out = contentEl.createEl("p");

        // Pre-fill domain from status if available
        api.status().then((s: any) => {
            if (s?.wiki) {
                const parts = s.wiki.replace(/\\/g, "/").split("/");
                input.value = parts[parts.length - 1].replace(/-/g, " ");
            }
        }).catch(() => {/* ignore */});

        const submit = async () => {
            const domain = input.value.trim();
            if (!domain) return;
            btn.disabled = true;
            out.setText("Queuing scaffold job…");
            try {
                const r = await api.scaffold(domain) as any;
                out.setText(`Queued — job ${r.job_id}. index.md, AGENTS.md, and purpose.md will be updated shortly.`);
                new Notice(`Synthadoc: scaffold queued (job ${r.job_id})`);
            } catch {
                out.setText("Error: is synthadoc serve running?");
            } finally { btn.disabled = false; }
        };

        btn.onclick = submit;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
        setTimeout(() => input.focus(), 50);
    }
    onClose() { this.contentEl.empty(); }
}

class AuditHistoryModal extends Modal {
    onOpen() {
        this.modalEl.style.width = "clamp(520px, 65vw, 900px)";
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Ingest history" });
        makeDraggable(this.modalEl, titleEl);

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Last" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "50";
        input.style.cssText = "width:60px;padding:4px 8px";
        row.createEl("span", { text: "records" });
        const btn = row.createEl("button", { text: "Load" });

        const tableEl = contentEl.createEl("div");

        const load = async () => {
            const limit = parseInt(input.value) || 50;
            tableEl.setText("Loading…");
            try {
                const r = await api.auditHistory(limit) as any;
                tableEl.empty();
                if (!r.records.length) {
                    tableEl.createEl("p", { text: "No ingest records yet." });
                    return;
                }
                const table = tableEl.createEl("table");
                table.style.cssText = "width:100%;border-collapse:collapse;font-size:12px;-webkit-user-select:text;user-select:text";
                const hrow = table.createEl("thead").createEl("tr");
                for (const h of ["Source", "Wiki page", "Tokens", "Cost (USD)", "Ingested at"]) {
                    const th = hrow.createEl("th", { text: h });
                    th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border)";
                }
                const tbody = table.createEl("tbody");
                for (const rec of r.records) {
                    const tr = tbody.createEl("tr");
                    const src = rec.source_path.split(/[\\/]/).pop() ?? rec.source_path;
                    const ts = rec.ingested_at
                        ? new Date(rec.ingested_at).toLocaleString()
                        : "—";
                    for (const text of [
                        src,
                        rec.wiki_page,
                        (rec.tokens ?? 0).toLocaleString(),
                        `$${(rec.cost_usd ?? 0).toFixed(4)}`,
                        ts,
                    ]) {
                        const td = tr.createEl("td", { text });
                        td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
                    }
                }
            } catch {
                tableEl.setText("Error: is synthadoc serve running?");
            }
        };

        btn.onclick = load;
        load();
    }
    onClose() { this.contentEl.empty(); }
}

class AuditCostsModal extends Modal {
    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Cost summary" });
        makeDraggable(this.modalEl, titleEl);

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Last" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "30";
        input.style.cssText = "width:60px;padding:4px 8px";
        row.createEl("span", { text: "days" });
        const btn = row.createEl("button", { text: "Load" });

        const out = contentEl.createEl("div");

        const load = async () => {
            const days = parseInt(input.value) || 30;
            out.setText("Loading…");
            try {
                const r = await api.auditCosts(days) as any;
                out.empty();

                const summary = out.createEl("div");
                summary.style.cssText = "margin-bottom:16px";
                summary.createEl("p", {
                    text: `Total: ${(r.total_tokens ?? 0).toLocaleString()} tokens · $${(r.total_cost_usd ?? 0).toFixed(4)} USD`,
                }).style.cssText = "font-weight:bold;-webkit-user-select:text;user-select:text";

                if (r.daily?.length) {
                    const table = out.createEl("table");
                    table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px;-webkit-user-select:text;user-select:text";
                    const hrow = table.createEl("thead").createEl("tr");
                    for (const h of ["Day", "Cost (USD)"]) {
                        const th = hrow.createEl("th", { text: h });
                        th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border)";
                    }
                    const tbody = table.createEl("tbody");
                    for (const d of r.daily) {
                        const tr = tbody.createEl("tr");
                        for (const text of [d.day, `$${(d.cost_usd ?? 0).toFixed(4)}`]) {
                            const td = tr.createEl("td", { text });
                            td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
                        }
                    }
                } else {
                    out.createEl("p", { text: "No cost data for this period.", cls: "synthadoc-muted" });
                }
            } catch {
                out.setText("Error: is synthadoc serve running?");
            }
        };

        btn.onclick = load;
        load();
    }
    onClose() { this.contentEl.empty(); }
}

class QueryHistoryModal extends Modal {
    onOpen() {
        this.modalEl.style.width = "clamp(520px, 65vw, 900px)";
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Query history" });
        makeDraggable(this.modalEl, titleEl);

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Last" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "50";
        input.style.cssText = "width:60px;padding:4px 8px";
        row.createEl("span", { text: "records" });
        const btn = row.createEl("button", { text: "Load" });

        const tableEl = contentEl.createEl("div");

        const load = async () => {
            const limit = parseInt(input.value) || 50;
            tableEl.setText("Loading…");
            try {
                const r = await api.queryHistory(limit) as any;
                tableEl.empty();
                if (!r.records.length) {
                    tableEl.createEl("p", { text: "No queries recorded yet." });
                    return;
                }
                const table = tableEl.createEl("table");
                table.style.cssText = "width:100%;border-collapse:collapse;font-size:12px;-webkit-user-select:text;user-select:text";
                const hrow = table.createEl("thead").createEl("tr");
                for (const h of ["Question", "Sub-Qs", "Tokens", "Cost (USD)", "Asked at"]) {
                    const th = hrow.createEl("th", { text: h });
                    th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border)";
                }
                const tbody = table.createEl("tbody");
                for (const rec of r.records) {
                    const tr = tbody.createEl("tr");
                    const ts = rec.queried_at
                        ? new Date(rec.queried_at).toLocaleString()
                        : "—";
                    for (const text of [
                        rec.question.length > 80 ? rec.question.slice(0, 77) + "…" : rec.question,
                        String(rec.sub_questions_count ?? 1),
                        (rec.tokens ?? 0).toLocaleString(),
                        `$${(rec.cost_usd ?? 0).toFixed(4)}`,
                        ts,
                    ]) {
                        const td = tr.createEl("td", { text });
                        td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
                    }
                }
            } catch {
                tableEl.setText("Error: is synthadoc serve running?");
            }
        };

        btn.onclick = load;
        load();
    }
    onClose() { this.contentEl.empty(); }
}

class QueryModal extends Modal {
    onOpen() {
        // Scale with viewport: min 520px, 60% of screen width, max 860px
        this.modalEl.style.width = "clamp(520px, 60vw, 860px)";

        // Block the backdrop's built-in click-to-close so the user must close explicitly
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Query your wiki" });
        makeDraggable(this.modalEl, titleEl);

        const input = contentEl.createEl("textarea", { placeholder: "Ask a question…\n(Ctrl+Enter or Cmd+Enter to submit)" });
        input.style.cssText = "width:100%;min-height:72px;padding:6px 8px;resize:vertical;margin-bottom:8px;box-sizing:border-box";

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;justify-content:flex-end;margin-bottom:12px";
        const btn = row.createEl("button", { text: "Ask" });

        const out = contentEl.createEl("div");
        out.style.cssText = "max-height:60vh;overflow-y:auto;padding:4px 0;-webkit-user-select:text;user-select:text";

        // Handle internal [[wikilinks]] rendered by MarkdownRenderer inside the modal.
        // Obsidian's normal link handler doesn't fire inside modals, so we intercept
        // clicks here, open the file via the workspace API, then close the modal.
        out.addEventListener("click", (e) => {
            const link = (e.target as HTMLElement).closest("a");
            if (!link) return;
            const href = link.getAttribute("data-href") || link.getAttribute("href") || "";
            if (!href || href.startsWith("http://") || href.startsWith("https://")) return;
            e.preventDefault();
            e.stopPropagation();
            this.app.workspace.openLinkText(href, "", false);
            this.close();
        });

        const submit = async () => {
            if (!input.value.trim()) return;
            btn.disabled = true;
            out.empty();
            out.createEl("p", { text: "Searching…", cls: "synthadoc-muted" });
            try {
                const r = await api.query(input.value) as any;
                out.empty();
                await MarkdownRenderer.render(this.app, r.answer, out, "", this);
                if (r.citations?.length) {
                    const cite = out.createEl("p");
                    cite.style.cssText = "font-size:11px;color:var(--text-muted);margin-top:8px";
                    cite.setText("Sources: " + r.citations.join(", "));
                }
                if (r.knowledge_gap && r.suggested_searches?.length) {
                    const searchCmds = (r.suggested_searches as string[])
                        .map((s: string) => `synthadoc ingest "search for: ${s}"`)
                        .join("\n");
                    const callout = [
                        "> [!tip] Knowledge Gap Detected",
                        "> Your wiki doesn't have enough on this topic yet. Enrich it with a web search:",
                        ">",
                        "> **From Obsidian:** Open Command Palette (`Cmd+P` / `Ctrl+P`) → **Synthadoc: Ingest: web search**",
                        ">",
                        "> **From the terminal:**",
                        "> ```bash",
                        ...searchCmds.split("\n").map((cmd: string) => `> ${cmd}`),
                        "> ```",
                        ">",
                        "> After ingesting, re-run your query to get a richer answer.",
                    ].join("\n");
                    const gapEl = out.createEl("div");
                    gapEl.style.cssText = "margin-top:16px";
                    await MarkdownRenderer.render(this.app, callout, gapEl, "", this);
                }
            } catch {
                out.empty();
                out.createEl("p", { text: "Error: is synthadoc serve running?" });
            } finally { btn.disabled = false; }
        };

        btn.onclick = submit;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); });
    }
    onClose() { this.contentEl.empty(); }
}
