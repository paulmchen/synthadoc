// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com
import { App, MarkdownRenderer, Modal, Notice, Plugin, PluginSettingTab, Setting, TFile } from "obsidian";
import { api, setBase } from "./api";

const SUPPORTED_EXTENSIONS = new Set([
    "md", "txt", "pdf", "docx", "xlsx", "csv",
    "png", "jpg", "jpeg", "webp", "gif", "tiff",
]);

// Filenames excluded from Pick-files scan: generated wiki output and known system/config files.
const PICK_FILES_EXCLUDED_NAMES = new Set([
    "log.md", "routing.md", "agents.md", "readme.md",
    "dashboard.md", "index.md", "overview.md", "claude.md",
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
            id: "synthadoc-query",
            name: "Query: ask the wiki...",
            callback: () => new QueryModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-ingest",
            name: "Ingest...",
            callback: () => new IngestModal(this.app, this.settings.rawSourcesFolder).open(),
        });

        this.addCommand({
            id: "synthadoc-jobs",
            name: "Jobs: list...",
            callback: () => new JobsModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-jobs-retry-dead",
            name: "Jobs: retry failed or dead jobs...",
            callback: () => new RetryJobModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-jobs-purge",
            name: "Jobs: purge old completed/dead...",
            callback: () => new PurgeJobsModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-lint-report",
            name: "Lint: report",
            callback: () => new LintReportModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-lint",
            name: "Lint: run...",
            callback: () => new LintRunModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-scaffold",
            name: "Wiki: regenerate scaffold...",
            callback: () => new ScaffoldModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-audit",
            name: "Audit...",
            callback: () => new AuditModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-routing",
            name: "Routing: manage ROUTING.md...",
            callback: () => new RoutingModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-staging",
            name: "Staging: manage staging policy...",
            callback: () => new StagingModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-candidates",
            name: "Candidates: review candidate pages...",
            callback: () => new CandidatesModal(this.app).open(),
        });
        this.addCommand({
            id: "synthadoc-context",
            name: "Context: build context pack...",
            callback: () => new ContextModal(this.app).open(),
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
            const absPath = (this.app.vault.adapter as any).getFullPath(file.path);
            const r = await api.ingest(absPath) as any;
            new Notice(`Synthadoc: ingest queued (job ${r.job_id})`);
        } catch { new Notice("Synthadoc: ingest failed — is the server running?"); }
    }

}

class IngestModal extends Modal {
    private _rawSourcesFolder: string;
    private _pollTimer: number | null = null;
    private _wsPollTimer: number | null = null;

    constructor(app: App, rawSourcesFolder?: string) {
        super(app);
        this._rawSourcesFolder = (rawSourcesFolder ?? "raw_sources").replace(/\/$/, "") || "raw_sources";
    }

    onOpen() {
        this.modalEl.style.width = "clamp(480px, 60vw, 820px)";
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Ingest" });
        makeDraggable(this.modalEl, titleEl);

        // Tab bar
        const tabBar = contentEl.createEl("div");
        tabBar.style.cssText = "display:flex;gap:0;margin-bottom:16px;border-bottom:1px solid var(--background-modifier-border)";

        type TabName = "Web search" | "URL" | "All raw_sources" | "Pick files";
        const tabNames: TabName[] = ["Web search", "URL", "All raw_sources", "Pick files"];
        const panels: Record<TabName, HTMLElement> = {} as any;
        const tabBtns: Record<TabName, HTMLElement> = {} as any;

        tabNames.forEach(name => {
            const btn = tabBar.createEl("div", { text: name });
            btn.style.cssText = "padding:6px 14px;cursor:pointer;font-size:13px;border-bottom:2px solid transparent;margin-bottom:-1px;color:var(--text-muted)";
            tabBtns[name] = btn;
            const panel = contentEl.createEl("div");
            panel.style.display = "none";
            panels[name] = panel;
        });

        const switchTab = (name: TabName) => {
            tabNames.forEach(t => {
                panels[t].style.display = "none";
                tabBtns[t].style.borderBottomColor = "transparent";
                tabBtns[t].style.color = "var(--text-muted)";
            });
            panels[name].style.display = "";
            tabBtns[name].style.borderBottomColor = "var(--interactive-accent)";
            tabBtns[name].style.color = "var(--text-normal)";
        };

        tabNames.forEach(name => { tabBtns[name].onclick = () => switchTab(name); });

        this._buildWebSearchTab(panels["Web search"]);
        this._buildUrlTab(panels["URL"]);
        this._buildAllSourcesTab(panels["All raw_sources"]);
        this._buildPickFilesTab(panels["Pick files"]);
        switchTab("Web search");
    }

    private _forceRow(panel: HTMLElement): () => boolean {
        const row = panel.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:6px;margin-bottom:10px;font-size:12px;color:var(--text-muted)";
        const cb = row.createEl("input", { type: "checkbox" }) as HTMLInputElement;
        const lbl = row.createEl("label", { text: "Force re-ingest (skip duplicate check)" });
        lbl.style.cssText = "cursor:pointer";
        lbl.onclick = () => { cb.checked = !cb.checked; };
        return () => !!cb.checked;
    }

    private _buildWebSearchTab(panel: HTMLElement) {
        panel.createEl("p", {
            text: "Type a topic — Synthadoc will search the web and compile results into your wiki.",
        }).style.cssText = "font-size:12px;margin-bottom:10px;color:var(--text-muted)";

        const textarea = panel.createEl("textarea", { placeholder: "e.g. Bank of Canada rate outlook 2025\nOntario housing market trends" }) as HTMLTextAreaElement;
        textarea.style.cssText = "width:100%;min-height:72px;padding:6px 8px;resize:vertical;margin-bottom:8px;box-sizing:border-box";

        const settingsRow = panel.createEl("div");
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

        const isForced = this._forceRow(panel);

        const btnRow = panel.createEl("div");
        btnRow.style.cssText = "display:flex;justify-content:flex-end;margin-bottom:10px";
        const btn = btnRow.createEl("button", { text: "Search" }) as HTMLButtonElement;

        const statusEl = panel.createEl("p");
        statusEl.style.cssText = "font-size:12px;min-height:20px;margin-bottom:4px;-webkit-user-select:text;user-select:text";
        const pagesEl = panel.createEl("div");
        pagesEl.style.cssText = "-webkit-user-select:text;user-select:text";
        const errorsEl = panel.createEl("div");
        errorsEl.style.cssText = "-webkit-user-select:text;user-select:text";

        const stopPolling = () => {
            if (this._wsPollTimer !== null) { window.clearTimeout(this._wsPollTimer); this._wsPollTimer = null; }
        };

        const startPolling = (jobId: string, pollInterval: number) => {
            const pages = new Set<string>();
            const errors: string[] = [];
            let childJobIds: string[] = [];
            const settledChildren = new Set<string>();
            const TERMINAL = ["completed", "failed", "dead", "skipped", "cancelled"];

            const poll = async () => {
                try {
                    const job = await api.job(jobId) as any;
                    const phase = job.progress?.phase;
                    const isDone = ["completed", "failed", "dead", "skipped"].includes(job.status);
                    if (job.result?.child_job_ids?.length && childJobIds.length === 0) childJobIds = job.result.child_job_ids;
                    if (!isDone) {
                        if (phase === "searching") statusEl.setText("Searching the web…");
                        else if (phase === "found_urls") {
                            const total = job.progress?.total ?? 0;
                            statusEl.setText(`Found ${total} URL${total !== 1 ? "s" : ""} — ingesting…`);
                        } else if (job.status === "pending") {
                            statusEl.setText("⏳ Queued — waiting for worker (other jobs are running)…");
                        } else if (job.status === "in_progress") {
                            statusEl.setText("⏳ Starting web search…");
                        }
                    }
                    if (childJobIds.length > 0) {
                        const allJobs = await api.jobs() as any[];
                        for (const cj of allJobs) {
                            if (!childJobIds.includes(cj.id) || !TERMINAL.includes(cj.status) || settledChildren.has(cj.id)) continue;
                            settledChildren.add(cj.id);
                            if (cj.status === "completed") {
                                for (const s of (cj.result?.pages_created ?? [])) pages.add(s);
                                for (const s of (cj.result?.pages_updated ?? [])) pages.add(s);
                            } else if (cj.error) {
                                const msg = `${cj.payload?.source ?? cj.id}: ${cj.error}`;
                                if (!errors.includes(msg)) errors.push(msg);
                            }
                        }
                        const remaining = childJobIds.length - settledChildren.size;
                        if (remaining > 0) statusEl.setText(isDone ? `Wrapping up — ${remaining} ingest${remaining !== 1 ? "s" : ""} still running…` : `Ingesting ${childJobIds.length} URL${childJobIds.length !== 1 ? "s" : ""}… (${settledChildren.size} done)`);
                    }
                    if (pages.size > 0) {
                        pagesEl.empty();
                        pagesEl.createEl("p", { text: `Pages (${pages.size}):` }).style.cssText = "font-size:12px;font-weight:bold;margin-bottom:2px";
                        const ul = pagesEl.createEl("ul");
                        ul.style.cssText = "font-size:12px;margin:0;padding-left:18px";
                        for (const s of pages) ul.createEl("li", { text: s });
                    }
                    if (errors.length > 0) {
                        errorsEl.empty();
                        errorsEl.createEl("p", { text: `Errors (${errors.length}):` }).style.cssText = "font-size:12px;font-weight:bold;margin-bottom:2px;color:var(--text-error)";
                        const ul = errorsEl.createEl("ul");
                        ul.style.cssText = "font-size:12px;margin:0;padding-left:18px;color:var(--text-error)";
                        for (const e of errors) ul.createEl("li", { text: e });
                    }
                    const allChildrenSettled = childJobIds.length > 0 && settledChildren.size >= childJobIds.length;
                    if (isDone && (childJobIds.length === 0 || allChildrenSettled)) {
                        stopPolling();
                        btn.disabled = false;
                        textarea.disabled = false;
                        if (job.status === "completed" || allChildrenSettled) {
                            statusEl.style.cssText += ";font-weight:bold;color:var(--text-success)";
                            statusEl.setText(`Done — ${pages.size} page(s) written.`);
                            new Notice(`Synthadoc: web search complete — ${pages.size} page(s)`);
                        } else {
                            statusEl.setText(`Search ${job.status}${job.error ? `: ${job.error}` : ""}`);
                        }
                        return;
                    }
                } catch { /* server unreachable — keep polling */ }
                this._wsPollTimer = window.setTimeout(poll, pollInterval);
            };
            this._wsPollTimer = window.setTimeout(poll, pollInterval);
        };

        const submit = async () => {
            const topic = textarea.value.trim();
            if (!topic) return;
            btn.disabled = true;
            textarea.disabled = true;
            const pollInterval = Math.min(10000, Math.max(500, parseInt(intervalInput.value) || 2000));
            const maxResults = Math.min(50, Math.max(1, parseInt(maxResultsInput.value) || 20));
            statusEl.setText("Queuing web search…");
            pagesEl.empty();
            errorsEl.empty();
            try {
                const r = await api.ingest(`search for: ${topic}`, maxResults, isForced()) as any;
                new Notice(`Synthadoc: web search queued (job ${r.job_id})`);
                startPolling(r.job_id, pollInterval);
            } catch {
                statusEl.setText("Error: is synthadoc serve running?");
                btn.disabled = false;
                textarea.disabled = false;
            }
        };

        btn.onclick = submit;
        textarea.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); });
    }

    private _buildUrlTab(panel: HTMLElement) {
        panel.createEl("p", {
            text: "Paste a URL — Synthadoc will fetch, parse, and convert it into a wiki article. Supports web pages, PDFs, and YouTube videos.",
        }).style.cssText = "font-size:12px;margin-bottom:10px;color:var(--text-muted)";

        const row = panel.createEl("div");
        row.style.cssText = "display:flex;gap:8px;margin-bottom:10px";
        const input = row.createEl("input", { type: "url", placeholder: "https://..." }) as HTMLInputElement;
        input.style.cssText = "flex:1;padding:4px 8px";
        const btn = row.createEl("button", { text: "Ingest" }) as HTMLButtonElement;

        const isForced = this._forceRow(panel);

        const out = panel.createEl("div");
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
                    if (status === "pending") { setStatus(`⏳ Queued — job ${jobId.slice(0, 8)}`); return; }
                    if (status === "in_progress") { setStatus(`⏳ Ingesting… (job ${jobId.slice(0, 8)})`); return; }
                    window.clearInterval(this._pollTimer!);
                    this._pollTimer = null;
                    btn.disabled = false;
                    input.disabled = false;
                    if (status === "completed") {
                        const parts = jobResultSummary(job.result ?? {});
                        out.empty();
                        out.createEl("p", { text: "✅ Done." }).style.cssText = "font-weight:bold;margin-bottom:4px";
                        if (parts.length) out.createEl("p", { text: parts.join(" · ") }).style.cssText = "font-size:12px;color:var(--text-muted)";
                        new Notice(`Synthadoc: ingest done (job ${jobId.slice(0, 8)})`);
                    } else if (status === "skipped") {
                        setStatus("⏭️ Skipped — already ingested.", "var(--text-muted)");
                    } else {
                        setStatus(`❌ ${status}${job.error ? `: ${job.error}` : ""}`, "var(--text-error)");
                    }
                } catch { /* server unreachable — keep polling silently */ }
            }, 2000);
        };

        const submit = async () => {
            const url = input.value.trim();
            if (!url) return;
            btn.disabled = true;
            input.disabled = true;
            setStatus("⏳ Queuing…");
            try {
                const r = await api.ingest(url, undefined, isForced()) as any;
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

    private _buildAllSourcesTab(panel: HTMLElement) {
        panel.createEl("p", {
            text: "Ingest every supported file in your configured raw sources folder in one click. Files already ingested are skipped unless Force re-ingest is checked.",
        }).style.cssText = "font-size:12px;margin-bottom:10px;color:var(--text-muted)";

        const folderRow = panel.createEl("div");
        folderRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        folderRow.createEl("label", { text: "Folder" }).style.cssText = "white-space:nowrap;font-size:13px;color:var(--text-muted)";
        const folderDisplay = folderRow.createEl("span");
        folderDisplay.style.cssText = "flex:1;padding:4px 8px;font-size:13px;color:var(--text-muted);background:var(--background-secondary);border-radius:4px;-webkit-user-select:text;user-select:text";
        folderDisplay.textContent = this._rawSourcesFolder;

        const statusEl = panel.createEl("div");
        statusEl.style.cssText = "min-height:40px;margin-bottom:12px;font-size:13px;-webkit-user-select:text;user-select:text";

        const isForced = this._forceRow(panel);

        const btnRow = panel.createEl("div");
        btnRow.style.cssText = "display:flex;gap:8px;justify-content:flex-end;align-items:center";
        const ingestBtn = btnRow.createEl("button", { text: "Ingest all" }) as HTMLButtonElement;
        ingestBtn.style.cssText = "font-weight:bold";

        const jobsLink = btnRow.createEl("a", { text: "View jobs list →" });
        jobsLink.style.cssText = "display:none;font-size:12px;cursor:pointer;color:var(--link-color)";
        jobsLink.onclick = () => {
            this.close();
            setTimeout(() => (this.app as any).commands?.executeCommandById("synthadoc:synthadoc-jobs"), 150);
        };

        const setStatus = (html: string) => { statusEl.innerHTML = html; };

        ingestBtn.onclick = async () => {
            const folder = this._rawSourcesFolder;

            const files = (this.app.vault.getFiles() as any[]).filter((f: any) => {
                if (!f.path.startsWith(folder + "/")) return false;
                return SUPPORTED_EXTENSIONS.has((f.extension ?? "").toLowerCase());
            });

            if (!files.length) {
                setStatus(`<span style="color:var(--text-muted)">No supported files found in <em>${folder}</em>.</span>`);
                return;
            }

            ingestBtn.disabled = true;
            jobsLink.style.display = "none";
            setStatus(`⏳ Queuing ${files.length} file(s)…`);

            const force = isForced();
            const jobIds: string[] = [];
            let queueFailed = 0;
            for (const file of files) {
                try {
                    const absPath = (this.app.vault.adapter as any).getFullPath(file.path);
                    const r = await api.ingest(absPath, undefined, force) as any;
                    if (r?.job_id) jobIds.push(r.job_id);
                } catch { queueFailed++; }
            }

            if (!jobIds.length) {
                setStatus(`<span style="color:var(--text-error)">❌ All ${files.length} file(s) failed to queue — is synthadoc serve running?</span>`);
                ingestBtn.disabled = false;
                return;
            }

            setStatus(`⏳ Queued ${jobIds.length} job(s)${queueFailed ? ` (${queueFailed} failed to queue)` : ""}. Monitoring progress…`);

            const pending = new Set(jobIds);
            let done = 0;

            this._pollTimer = window.setInterval(async () => {
                try {
                    const allJobs = await api.jobs() as any[];
                    for (const jobId of [...pending]) {
                        const job = allJobs.find((j: any) => j.id === jobId);
                        if (!job) { pending.delete(jobId); done++; continue; }
                        if (["completed", "failed", "dead", "skipped"].includes(job.status)) {
                            pending.delete(jobId);
                            done++;
                        }
                    }
                    setStatus(`⏳ ${jobIds.length - done} running, ${done} of ${jobIds.length} settled…`);

                    if (pending.size === 0) {
                        window.clearInterval(this._pollTimer!);
                        this._pollTimer = null;
                        setStatus(`✅ All ${jobIds.length} job(s) complete.${queueFailed ? ` (${queueFailed} file(s) failed to queue.)` : ""}`);
                        ingestBtn.disabled = false;
                        jobsLink.style.display = "";
                    }
                } catch { /* server unreachable — keep polling */ }
            }, 2000);
        };
    }

    private _buildPickFilesTab(panel: HTMLElement) {
        panel.createEl("p", {
            text: "Browse to any folder, scan for supported files, then select which ones to ingest. Great for one-off ingestion from a custom location.",
        }).style.cssText = "font-size:12px;margin-bottom:10px;color:var(--text-muted)";

        const folderRow = panel.createEl("div");
        folderRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:8px";
        folderRow.createEl("label", { text: "Folder" }).style.cssText = "white-space:nowrap;font-size:13px";
        let selectedFolder = "";   // vault-relative (or "" for vault root)
        let selectedAbsPath = "";  // full OS path — shown in display and used as guard
        const folderDisplay = folderRow.createEl("input") as HTMLInputElement;
        folderDisplay.type = "text";
        folderDisplay.readOnly = true;
        folderDisplay.placeholder = "Click Browse… to select a folder";
        folderDisplay.style.cssText = "flex:1;min-width:0;padding:4px 8px;font-size:13px;color:var(--text-muted);background:var(--background-secondary);border:1px solid transparent;border-radius:4px;cursor:default;outline:none";

        const browseBtn = folderRow.createEl("button", { text: "Browse…" }) as HTMLButtonElement;
        browseBtn.onclick = async () => {
            try {
                const remote = (window as any).require?.("@electron/remote")
                    ?? (window as any).require?.("electron")?.remote;
                if (!remote?.dialog) { new Notice("Folder picker unavailable in this environment"); return; }
                const result = await remote.dialog.showOpenDialog({ properties: ["openDirectory"], title: "Select source folder" });
                if (!result.canceled && result.filePaths?.[0]) {
                    const absPath: string = result.filePaths[0];
                    const basePath: string = (this.app.vault.adapter as any).getBasePath?.() ?? "";
                    const rel = (basePath && absPath.toLowerCase().startsWith(basePath.toLowerCase()))
                        ? absPath.slice(basePath.length).replace(/^[/\\]+/, "").replace(/\\/g, "/")
                        : absPath.replace(/\\/g, "/");
                    selectedAbsPath = absPath;
                    selectedFolder = rel;          // may be "" when vault root is selected
                    folderDisplay.value = absPath; // always show the full OS path
                    folderDisplay.style.color = "var(--text-normal)";
                    scanBtn.disabled = false;
                }
            } catch { new Notice("Could not open folder picker"); }
        };

        const scanBtn = folderRow.createEl("button", { text: "Scan" }) as HTMLButtonElement;
        scanBtn.disabled = true;

        const selectRow = panel.createEl("div");
        selectRow.style.cssText = "display:flex;gap:8px;align-items:center;margin-bottom:4px;font-size:12px";
        const selAllBtn = selectRow.createEl("button", { text: "Select all" }) as HTMLButtonElement;
        const deselAllBtn = selectRow.createEl("button", { text: "Deselect all" }) as HTMLButtonElement;
        const countLabel = selectRow.createEl("span");
        countLabel.style.cssText = "font-size:12px;color:var(--text-muted);margin-left:auto";

        const listEl = panel.createEl("div");
        listEl.style.cssText = "overflow-y:auto;max-height:180px;border:1px solid var(--background-modifier-border);border-radius:4px;padding:4px;margin-bottom:8px;font-size:12px";
        listEl.createEl("span", { text: "Click Browse… to select a folder, then click Scan." }).style.cssText = "color:var(--text-muted);padding:4px;display:block";

        const statusEl = panel.createEl("div");
        statusEl.style.cssText = "min-height:28px;margin-bottom:8px;font-size:13px;-webkit-user-select:text;user-select:text";

        const isForced = this._forceRow(panel);

        const btnRow = panel.createEl("div");
        btnRow.style.cssText = "display:flex;gap:8px;justify-content:flex-end;align-items:center";
        const ingestBtn = btnRow.createEl("button", { text: "Ingest selected" }) as HTMLButtonElement;
        ingestBtn.style.cssText = "font-weight:bold";
        ingestBtn.disabled = true;

        const jobsLink = btnRow.createEl("a", { text: "View jobs list →" });
        jobsLink.style.cssText = "display:none;font-size:12px;cursor:pointer;color:var(--link-color)";
        jobsLink.onclick = () => {
            this.close();
            setTimeout(() => (this.app as any).commands?.executeCommandById("synthadoc:synthadoc-jobs"), 150);
        };

        let scannedFiles: any[] = [];
        let checkboxRefs: HTMLInputElement[] = [];

        const updateCount = () => {
            countLabel.textContent = checkboxRefs.length ? `${checkboxRefs.filter(c => c.checked).length} / ${checkboxRefs.length} selected` : "";
            ingestBtn.disabled = checkboxRefs.filter(c => c.checked).length === 0;
        };

        const renderFiles = (files: any[]) => {
            scannedFiles = files;
            checkboxRefs = [];
            listEl.empty();
            if (!files.length) {
                listEl.createEl("span", { text: "No supported files found." }).style.cssText = "color:var(--text-muted);padding:4px;display:block";
                updateCount();
                return;
            }
            files.forEach(f => {
                const row = listEl.createEl("div");
                row.style.cssText = "display:flex;align-items:center;gap:6px;padding:2px 4px;border-radius:3px";
                const cb = row.createEl("input", { type: "checkbox" }) as HTMLInputElement;
                checkboxRefs.push(cb);
                cb.checked = true;
                cb.addEventListener("change", updateCount);
                const lbl = row.createEl("label");
                lbl.style.cssText = "cursor:pointer;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
                lbl.createEl("span", { text: f.name }).style.fontWeight = "500";
                lbl.createEl("span", { text: "  " + f.path }).style.cssText = "color:var(--text-muted);font-size:11px";
                lbl.onclick = () => { cb.checked = !cb.checked; updateCount(); };
            });
            updateCount();
        };

        const scan = () => {
            if (!selectedAbsPath) return;  // Browse has not been used yet
            const folder = selectedFolder.trim().replace(/\/$/, "");
            // folder is "" when the vault root itself was selected — matches all vault files
            let wikiExcluded = 0;
            let systemExcluded = 0;
            const files = (this.app.vault.getFiles() as any[]).filter((f: any) => {
                if (folder && !f.path.startsWith(folder + "/")) return false;
                if (!SUPPORTED_EXTENSIONS.has((f.extension ?? "").toLowerCase())) return false;
                // Exclude files inside any wiki/ subfolder (those are generated wiki pages)
                const relative = folder ? f.path.slice(folder.length + 1) : f.path;
                if (relative.startsWith("wiki/") || relative.includes("/wiki/")) {
                    wikiExcluded++;
                    return false;
                }
                // Exclude known system / config filenames
                if (PICK_FILES_EXCLUDED_NAMES.has((f.name ?? "").toLowerCase())) {
                    systemExcluded++;
                    return false;
                }
                return true;
            });
            renderFiles(files);
            const parts: string[] = [];
            if (wikiExcluded > 0) parts.push(`${wikiExcluded} wiki page${wikiExcluded !== 1 ? "s" : ""}`);
            if (systemExcluded > 0) parts.push(`${systemExcluded} system file${systemExcluded !== 1 ? "s" : ""}`);
            if (parts.length > 0) {
                statusEl.innerHTML = `<span style="color:var(--text-muted);font-size:12px">ℹ Excluded ${parts.join(" and ")} — not source files</span>`;
            } else {
                statusEl.innerHTML = "";
            }
            jobsLink.style.display = "none";
        };

        scanBtn.onclick = scan;
        selAllBtn.onclick = () => { checkboxRefs.forEach(c => { c.checked = true; }); updateCount(); };
        deselAllBtn.onclick = () => { checkboxRefs.forEach(c => { c.checked = false; }); updateCount(); };

        const setStatus = (html: string) => { statusEl.innerHTML = html; };

        ingestBtn.onclick = async () => {
            const selectedFiles = scannedFiles.filter((_, i) => checkboxRefs[i]?.checked);
            if (!selectedFiles.length) return;

            ingestBtn.disabled = true;
            scanBtn.disabled = true;
            browseBtn.disabled = true;
            jobsLink.style.display = "none";
            setStatus(`⏳ Queuing ${selectedFiles.length} file(s)…`);

            const force = isForced();
            const jobIds: string[] = [];
            let queueFailed = 0;
            for (const file of selectedFiles) {
                try {
                    const absPath = (this.app.vault.adapter as any).getFullPath(file.path);
                    const r = await api.ingest(absPath, undefined, force) as any;
                    if (r?.job_id) jobIds.push(r.job_id);
                } catch { queueFailed++; }
            }

            if (!jobIds.length) {
                setStatus(`<span style="color:var(--text-error)">❌ All ${selectedFiles.length} file(s) failed to queue — is synthadoc serve running?</span>`);
                ingestBtn.disabled = false;
                scanBtn.disabled = false;
                browseBtn.disabled = false;
                updateCount();
                return;
            }

            setStatus(`⏳ Queued ${jobIds.length} job(s)${queueFailed ? ` (${queueFailed} failed to queue)` : ""}. Monitoring…`);

            const pending = new Set(jobIds);
            let done = 0;

            this._pollTimer = window.setInterval(async () => {
                try {
                    const allJobs = await api.jobs() as any[];
                    for (const jobId of [...pending]) {
                        const job = allJobs.find((j: any) => j.id === jobId);
                        if (!job) { pending.delete(jobId); done++; continue; }
                        if (["completed", "failed", "dead", "skipped"].includes(job.status)) {
                            pending.delete(jobId);
                            done++;
                        }
                    }
                    setStatus(`⏳ ${jobIds.length - done} running, ${done} of ${jobIds.length} settled…`);

                    if (pending.size === 0) {
                        window.clearInterval(this._pollTimer!);
                        this._pollTimer = null;
                        setStatus(`✅ All ${jobIds.length} job(s) complete.${queueFailed ? ` (${queueFailed} file(s) failed to queue.)` : ""}`);
                        ingestBtn.disabled = false;
                        scanBtn.disabled = false;
                        browseBtn.disabled = false;
                        updateCount();
                        jobsLink.style.display = "";
                    }
                } catch { /* server unreachable — keep polling */ }
            }, 2000);
        };
    }

    onClose() {
        if (this._pollTimer !== null) { window.clearInterval(this._pollTimer); this._pollTimer = null; }
        if (this._wsPollTimer !== null) { window.clearTimeout(this._wsPollTimer); this._wsPollTimer = null; }
        this.contentEl.empty();
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
    cancelled:   "🚫",
};

const STATUS_FILTER_OPTIONS = ["pending", "in_progress", "completed", "failed", "skipped", "dead", "cancelled"] as const;

function jobResultSummary(r: Record<string, any>): string[] {
    const parts: string[] = [];
    if (r.pages_created?.length) parts.push(`created: ${r.pages_created.join(", ")}`);
    if (r.pages_updated?.length) parts.push(`updated: ${r.pages_updated.join(", ")}`);
    if (r.pages_flagged?.length) parts.push(`flagged: ${r.pages_flagged.join(", ")}`);
    if (r.skip_reason) parts.push(`skipped: ${r.skip_reason}`);
    return parts;
}

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

const TERMINAL_STATUSES = new Set(["completed", "failed", "skipped", "dead", "cancelled"]);
const JOBS_PAGE_SIZE = 25;

class JobsModal extends Modal {
    private _selected: Set<string> = new Set(["pending", "in_progress"]);
    private _intervalSecs = 10;
    private _countdown = 10;
    private _countdownTimer: number | null = null;
    private _tableEl: HTMLElement | null = null;
    private _countdownEl: HTMLElement | null = null;
    private _deleteBtn: HTMLButtonElement | null = null;
    private _checkedIds: Set<string> = new Set();
    private _page = 0;
    private _filteredJobs: any[] = [];
    private _prevBtn: HTMLButtonElement | null = null;
    private _nextBtn: HTMLButtonElement | null = null;
    private _pageLabel: HTMLElement | null = null;
    private _pageRow: HTMLElement | null = null;
    private _sortBy: "created_at" | "status" | "operation" = "created_at";
    private _sortOrder: "asc" | "desc" = "desc";

    onOpen() {
        this.modalEl.style.width = "clamp(760px, 80vw, 1100px)";
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
                this._page = 0;
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

        // Delete button — right-aligned on the interval row, always visible
        this._deleteBtn = intervalRow.createEl("button", { text: "Delete selected" }) as HTMLButtonElement;
        this._deleteBtn.disabled = true;
        this._deleteBtn.style.cssText = "font-size:12px;margin-left:auto";
        this._deleteBtn.onclick = () => this._deleteSelected();

        // Table
        this._tableEl = contentEl.createEl("div");
        this._tableEl.style.cssText = "overflow-y:auto;max-height:50vh;-webkit-user-select:text;user-select:text";

        // Pagination row — hidden when all results fit on one page
        this._pageRow = contentEl.createEl("div");
        this._pageRow.style.cssText = "display:none;gap:8px;align-items:center;margin-top:8px;font-size:12px;color:var(--text-muted);";
        this._prevBtn = this._pageRow.createEl("button", { text: "← Prev" }) as HTMLButtonElement;
        this._pageLabel = this._pageRow.createEl("span");
        this._nextBtn = this._pageRow.createEl("button", { text: "Next →" }) as HTMLButtonElement;
        this._prevBtn.onclick = () => { this._page--; this._renderTable(); };
        this._nextBtn.onclick = () => { this._page++; this._renderTable(); };

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
            this._filteredJobs = this._selected.size === 0
                ? allJobs
                : allJobs.filter((j: any) => this._selected.has(j.status));
            this._renderTable();
        } catch {
            if (this._tableEl) this._tableEl.setText("Error: is synthadoc serve running?");
        }
    }

    private _updateDeleteBtn() {
        if (this._deleteBtn) this._deleteBtn.disabled = this._checkedIds.size === 0;
    }

    private async _deleteSelected() {
        if (!this._deleteBtn || this._checkedIds.size === 0) return;
        this._deleteBtn.disabled = true;
        const ids = [...this._checkedIds];
        await Promise.allSettled(ids.map(id => api.deleteJob(id)));
        this._checkedIds.clear();
        this._load();
    }

    private _sortedJobs(): any[] {
        const col = this._sortBy;
        const dir = this._sortOrder === "asc" ? 1 : -1;
        return [...this._filteredJobs].sort((a, b) => {
            const av: string = a[col] ?? "";
            const bv: string = b[col] ?? "";
            return av < bv ? -dir : av > bv ? dir : 0;
        });
    }

    private _renderTable() {
        if (!this._tableEl) return;
        this._tableEl.empty();

        const sorted = this._sortedJobs();
        const total = sorted.length;
        const totalPages = Math.max(1, Math.ceil(total / JOBS_PAGE_SIZE));
        this._page = Math.min(this._page, totalPages - 1);
        const jobs = sorted.slice(this._page * JOBS_PAGE_SIZE, (this._page + 1) * JOBS_PAGE_SIZE);

        // Update pagination controls
        if (this._prevBtn) this._prevBtn.disabled = this._page === 0;
        if (this._nextBtn) this._nextBtn.disabled = this._page >= totalPages - 1;
        if (this._pageRow) this._pageRow.style.display = totalPages > 1 ? "flex" : "none";
        if (this._pageLabel) this._pageLabel.textContent = `Page ${this._page + 1} of ${totalPages} (${total} total)`;

        // Remove stale checked IDs no longer in the filtered list (handles deletions / filter changes)
        const allFilteredIds = new Set(this._filteredJobs.map((j: any) => j.id));
        for (const id of this._checkedIds) {
            if (!allFilteredIds.has(id)) this._checkedIds.delete(id);
        }
        this._updateDeleteBtn();

        if (total === 0) {
            this._tableEl.createEl("p", { text: "No jobs match the selected filters.", cls: "synthadoc-muted" });
            return;
        }

        const terminalJobs = jobs.filter((j: any) => TERMINAL_STATUSES.has(j.status));
        const hasTerminal = terminalJobs.length > 0;

        const table = this._tableEl.createEl("table");
        table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px;-webkit-user-select:text;user-select:text";

        const hrow = table.createEl("thead").createEl("tr");

        // Select-all checkbox header cell
        const selectAllTh = hrow.createEl("th");
        selectAllTh.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border);width:28px";
        let selectAllCb: HTMLInputElement | null = null;
        if (hasTerminal) {
            selectAllCb = selectAllTh.createEl("input", { type: "checkbox" }) as HTMLInputElement;
            selectAllCb.title = "Select all";
            selectAllCb.checked = terminalJobs.every((j: any) => this._checkedIds.has(j.id));
            selectAllCb.indeterminate = !selectAllCb.checked && terminalJobs.some((j: any) => this._checkedIds.has(j.id));
        }

        const SORT_HEADERS: { label: string; col: "status" | "operation" | "created_at" | null }[] = [
            { label: "Job ID", col: null },
            { label: "Status", col: "status" },
            { label: "Operation", col: "operation" },
            { label: "Source", col: null },
            { label: "Created", col: "created_at" },
        ];
        for (const { label, col } of SORT_HEADERS) {
            const th = hrow.createEl("th");
            th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border)";
            if (col) {
                const indicator = this._sortBy === col ? (this._sortOrder === "asc" ? " ▲" : " ▼") : " ⇅";
                th.setText(label + indicator);
                th.style.cursor = "pointer";
                th.title = `Sort by ${label}`;
                th.onclick = () => {
                    if (this._sortBy === col) {
                        this._sortOrder = this._sortOrder === "asc" ? "desc" : "asc";
                    } else {
                        this._sortBy = col;
                        this._sortOrder = "asc";
                    }
                    this._page = 0;
                    this._renderTable();
                };
            } else {
                th.setText(label);
            }
        }

        const rowCheckboxes: HTMLInputElement[] = [];

        const tbody = table.createEl("tbody");
        for (const job of jobs) {
            const tr = tbody.createEl("tr");
            const isTerminal = TERMINAL_STATUSES.has(job.status);
            const source = job.payload?.source
                ? job.payload.source.split(/[\\/]/).pop()
                : job.operation === "lint" ? "(lint)" : "—";
            // SQLite stores UTC without tz marker; append +00:00 so JS parses as UTC
            const created = job.created_at
                ? new Date(job.created_at.replace(" ", "T") + "+00:00").toLocaleString()
                : "—";
            const icon = STATUS_EMOJI[job.status] ?? "";

            // Checkbox cell
            const cbTd = tr.createEl("td");
            cbTd.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle);width:28px";
            if (isTerminal) {
                const cb = cbTd.createEl("input", { type: "checkbox" }) as HTMLInputElement;
                cb.checked = this._checkedIds.has(job.id);
                cb.onchange = () => {
                    if (cb.checked) this._checkedIds.add(job.id);
                    else this._checkedIds.delete(job.id);
                    if (selectAllCb) {
                        selectAllCb.checked = terminalJobs.every((j: any) => this._checkedIds.has(j.id));
                        selectAllCb.indeterminate = !selectAllCb.checked && terminalJobs.some((j: any) => this._checkedIds.has(j.id));
                    }
                    this._updateDeleteBtn();
                };
                rowCheckboxes.push(cb);
            }

            // Job ID cell — monospace, full ID visible and selectable for copy
            const idTd = tr.createEl("td");
            idTd.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle);font-family:monospace;font-size:11px;color:var(--text-muted)";
            idTd.setText(job.id ?? "—");

            for (const text of [`${icon} ${job.status}`, job.operation, source, created]) {
                const td = tr.createEl("td", { text });
                td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
            }
            if (job.status === "completed" && job.result) {
                const detail = jobResultSummary(job.result);
                if (detail.length) {
                    const dtd = tbody.createEl("tr").createEl("td", { text: detail.join(" · ") });
                    dtd.colSpan = 6;
                    dtd.style.cssText = "padding:2px 8px 6px 8px;font-size:11px;color:var(--text-muted)";
                }
            }
            if ((job.status === "failed" || job.status === "dead") && job.error) {
                const etd = tbody.createEl("tr").createEl("td", { text: `Error: ${job.error}` });
                etd.colSpan = 6;
                etd.style.cssText = "padding:2px 8px 6px 8px;font-size:11px;color:var(--text-error)";
            }
            if (job.status === "skipped" && job.error) {
                const wtd = tbody.createEl("tr").createEl("td", { text: `Skipped: ${job.error}` });
                wtd.colSpan = 6;
                wtd.style.cssText = "padding:2px 8px 6px 8px;font-size:11px;color:var(--text-warning)";
            }
        }

        if (selectAllCb) {
            selectAllCb.onchange = () => {
                for (const job of terminalJobs) {
                    if (selectAllCb!.checked) this._checkedIds.add(job.id);
                    else this._checkedIds.delete(job.id);
                }
                for (const cb of rowCheckboxes) cb.checked = selectAllCb!.checked;
                this._updateDeleteBtn();
            };
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
        btnRow.style.cssText = "display:flex;align-items:center;gap:8px;justify-content:flex-end";
        const reportLink = btnRow.createEl("a", { text: "Lint report →" });
        reportLink.style.cssText = "display:none;font-size:12px;cursor:pointer;color:var(--link-color)";
        reportLink.onclick = () => {
            this.close();
            setTimeout(() => new LintReportModal(this.app).open(), 150);
        };
        const btn = btnRow.createEl("button", { text: "Run lint" });

        const out = contentEl.createEl("div");
        out.style.cssText = "margin-top:12px;-webkit-user-select:text;user-select:text";

        btn.onclick = async () => {
            const autoResolve = cb.checked;
            btn.disabled = true;
            cb.disabled = true;
            reportLink.style.display = "none";
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
                                const details: any[] = report.contradiction_details ?? [];
                                const contradictions: string[] = report.contradictions ?? [];
                                const orphans: string[] = report.orphans ?? [];
                                out.empty();
                                const summary = out.createEl("p");
                                summary.style.cssText = "font-weight:bold;margin-bottom:6px";
                                summary.setText(`✅ Done — ${contradictions.length} contradiction(s), ${orphans.length} orphan(s).`);
                                for (const d of details) {
                                    const block = out.createEl("div");
                                    block.style.cssText = "margin-bottom:6px";
                                    block.createEl("span", { text: `❌ ${d.slug}` }).style.cssText = "font-size:12px;color:var(--text-error);font-weight:600";
                                    if (d.contradiction_note) {
                                        block.createEl("div", { text: `Why flagged: ${d.contradiction_note}` }).style.cssText = "font-size:11px;color:var(--text-muted);margin-top:2px";
                                    }
                                    if (d.unresolved_note) {
                                        block.createEl("div", { text: `⚠ Auto-resolve failed: ${d.unresolved_note}` }).style.cssText = "font-size:11px;color:var(--text-warning);margin-top:2px";
                                    }
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
                        reportLink.style.display = "";
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
            const details: any[] = r.contradiction_details ?? contradictions.map((s: string) => ({ slug: s }));
            const orphanDetails: Array<{ slug: string; index_suggestion: string }> =
                r.orphan_details ?? (r.orphans ?? []).map((s: string) => ({ slug: s, index_suggestion: `- [[${s}]]` }));

            if (contradictions.length === 0 && orphanDetails.length === 0) {
                out.createEl("p", { text: "✅ All clear — no contradictions or orphan pages." });
                return;
            }

            if (details.length > 0) {
                out.createEl("h4", { text: `❌ Contradicted pages (${details.length})` });
                const ul = out.createEl("ul");
                details.forEach(({ slug, contradiction_note, unresolved_note }) => {
                    const li = ul.createEl("li");
                    li.createEl("code", { text: slug });
                    li.appendText(" — open the page, resolve the conflict, set status: active");
                    if (contradiction_note) {
                        const n = li.createEl("div", { text: `Why flagged: ${contradiction_note}` });
                        n.style.cssText = "font-size:11px;color:var(--text-muted);margin-top:2px";
                    }
                    if (unresolved_note) {
                        const n = li.createEl("div", { text: `⚠ Auto-resolve failed: ${unresolved_note}` });
                        n.style.cssText = "font-size:11px;color:var(--text-warning);margin-top:2px";
                    }
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

class RetryJobModal extends Modal {
    private _pollTimer: number | null = null;

    onOpen() {
        this.modalEl.style.width = "clamp(560px, 70vw, 960px)";
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Retry failed or dead jobs" });
        makeDraggable(this.modalEl, titleEl);

        const listEl = contentEl.createEl("div");
        listEl.style.cssText = "max-height:40vh;overflow-y:auto;margin-bottom:12px";

        const statusEl = contentEl.createEl("p");
        statusEl.style.cssText = "font-size:12px;min-height:18px;margin-bottom:8px;-webkit-user-select:text;user-select:text";

        const btnRow = contentEl.createEl("div");
        btnRow.style.cssText = "display:flex;gap:8px;justify-content:flex-end";
        const retryBtn = btnRow.createEl("button", { text: "Retry selected" });
        const refreshBtn = btnRow.createEl("button", { text: "Refresh" });

        // Track checkboxes: jobId → checkbox element
        const checkboxMap = new Map<string, HTMLInputElement>();

        const load = async () => {
            listEl.empty();
            checkboxMap.clear();
            statusEl.setText("Loading…");
            try {
                const [failed, dead] = await Promise.all([
                    api.jobs("failed") as Promise<any[]>,
                    api.jobs("dead") as Promise<any[]>,
                ]);
                const jobs = [...failed, ...dead];
                statusEl.setText("");

                if (!jobs.length) {
                    listEl.createEl("p", { text: "No failed or dead jobs." }).style.cssText = "color:var(--text-muted);font-size:13px";
                    retryBtn.disabled = true;
                    return;
                }

                retryBtn.disabled = false;
                const table = listEl.createEl("table");
                table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px;-webkit-user-select:text;user-select:text";
                const hrow = table.createEl("thead").createEl("tr");
                for (const h of ["", "Status", "Job ID", "Operation", "Source", "Error"]) {
                    const th = hrow.createEl("th", { text: h });
                    th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border)";
                }
                const tbody = table.createEl("tbody");
                for (const job of jobs) {
                    const tr = tbody.createEl("tr");
                    const source = job.payload?.source
                        ? job.payload.source.split(/[\\/]/).pop()
                        : job.operation;
                    const icon = STATUS_EMOJI[job.status] ?? "";

                    // Checkbox
                    const cbTd = tr.createEl("td");
                    cbTd.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
                    const cb = cbTd.createEl("input", { type: "checkbox" }) as HTMLInputElement;
                    cb.checked = true;
                    checkboxMap.set(job.id, cb);

                    for (const text of [`${icon} ${job.status}`, job.id, job.operation, source, job.error ?? "—"]) {
                        const td = tr.createEl("td", { text });
                        td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle);font-size:12px";
                    }
                }
            } catch {
                listEl.empty();
                listEl.createEl("p", { text: "Error: is synthadoc serve running?" }).style.cssText = "color:var(--text-error)";
                retryBtn.disabled = true;
            }
        };

        refreshBtn.onclick = load;

        retryBtn.onclick = async () => {
            const selected = [...checkboxMap.entries()]
                .filter(([, cb]) => cb.checked)
                .map(([id]) => id);
            if (!selected.length) {
                statusEl.setText("No jobs selected.");
                return;
            }

            retryBtn.disabled = true;
            refreshBtn.disabled = true;
            statusEl.setText(`⏳ Re-queuing ${selected.length} job(s)…`);

            // Re-queue all selected
            let queued = 0;
            for (const jobId of selected) {
                try {
                    await api.retryJob(jobId);
                    queued++;
                } catch { /* ignore individual failures — status will show */ }
            }
            statusEl.setText(`⏳ ${queued} job(s) re-queued — monitoring progress…`);

            // Poll until all re-queued jobs have settled
            const pending = new Set(selected);
            this._pollTimer = window.setInterval(async () => {
                try {
                    const allJobs = await api.jobs() as any[];
                    let inProgress = 0;
                    let done = 0;
                    for (const jobId of [...pending]) {
                        const job = allJobs.find((j: any) => j.id === jobId);
                        if (!job) { pending.delete(jobId); done++; continue; }
                        if (["completed", "failed", "dead", "skipped"].includes(job.status)) {
                            pending.delete(jobId);
                            done++;
                        } else {
                            inProgress++;
                        }
                    }
                    statusEl.setText(`⏳ ${inProgress} running, ${done} settled of ${selected.length}…`);
                    if (pending.size === 0) {
                        window.clearInterval(this._pollTimer!);
                        this._pollTimer = null;
                        statusEl.setText(`✅ All ${selected.length} job(s) settled. Refreshing list…`);
                        retryBtn.disabled = false;
                        refreshBtn.disabled = false;
                        await load();
                    }
                } catch { /* server unreachable — keep polling */ }
            }, 2000);
        };

        load();
    }

    onClose() {
        if (this._pollTimer !== null) {
            window.clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
        this.contentEl.empty();
    }
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
    private _pollTimer: number | null = null;

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
        out.style.cssText = "font-size:12px;min-height:18px;-webkit-user-select:text;user-select:text";

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
            input.disabled = true;
            out.setText("⏳ Queuing scaffold job…");
            try {
                const r = await api.scaffold(domain) as any;
                const jobId: string = r.job_id;
                out.setText(`⏳ Queued — job ${jobId.slice(0, 8)}…`);
                new Notice(`Synthadoc: scaffold queued (job ${jobId})`);

                this._pollTimer = window.setInterval(async () => {
                    try {
                        const job = await api.job(jobId) as any;
                        const status: string = job.status;

                        if (status === "pending") { out.setText(`⏳ Queued — job ${jobId.slice(0, 8)}…`); return; }
                        if (status === "in_progress") { out.setText(`⏳ Generating scaffold… (job ${jobId.slice(0, 8)})`); return; }

                        window.clearInterval(this._pollTimer!);
                        this._pollTimer = null;
                        btn.disabled = false;
                        input.disabled = false;

                        if (status === "completed") {
                            out.setText("✅ Done — index.md, AGENTS.md, and purpose.md updated.");
                            new Notice("Synthadoc: scaffold complete");
                        } else if (status === "skipped") {
                            out.setText("⏭️ Skipped — already up to date.");
                        } else {
                            out.setText(`❌ ${status}${job.error ? `: ${job.error}` : ""}`);
                        }
                    } catch { /* server unreachable — keep polling */ }
                }, 2000);
            } catch {
                out.setText("❌ Error: is synthadoc serve running?");
                btn.disabled = false;
                input.disabled = false;
            }
        };

        btn.onclick = submit;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
        setTimeout(() => input.focus(), 50);
    }

    onClose() {
        if (this._pollTimer !== null) {
            window.clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
        this.contentEl.empty();
    }
}

class AuditModal extends Modal {
    onOpen() {
        this.modalEl.style.width = "clamp(560px, 70vw, 960px)";
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });
        const { contentEl } = this;
        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Audit" });
        makeDraggable(this.modalEl, titleEl);

        const tabBar = contentEl.createEl("div");
        tabBar.style.cssText = "display:flex;gap:0;margin-bottom:16px;border-bottom:1px solid var(--background-modifier-border)";

        type TabName = "Query history" | "Ingest history" | "Events" | "Cost summary";
        const tabNames: TabName[] = ["Query history", "Ingest history", "Events", "Cost summary"];
        const panels: Record<TabName, HTMLElement> = {} as any;
        const tabBtns: Record<TabName, HTMLElement> = {} as any;

        tabNames.forEach(name => {
            const btn = tabBar.createEl("div", { text: name });
            btn.style.cssText = "padding:6px 14px;cursor:pointer;font-size:13px;border-bottom:2px solid transparent;margin-bottom:-1px;color:var(--text-muted)";
            tabBtns[name] = btn;
            const panel = contentEl.createEl("div");
            panel.style.display = "none";
            panels[name] = panel;
        });

        const switchTab = (name: TabName) => {
            tabNames.forEach(t => {
                panels[t].style.display = "none";
                tabBtns[t].style.borderBottomColor = "transparent";
                tabBtns[t].style.color = "var(--text-muted)";
            });
            panels[name].style.display = "";
            tabBtns[name].style.borderBottomColor = "var(--interactive-accent)";
            tabBtns[name].style.color = "var(--text-normal)";
        };

        tabNames.forEach(name => { tabBtns[name].onclick = () => switchTab(name); });

        this._buildQueryHistoryTab(panels["Query history"]);
        this._buildIngestHistoryTab(panels["Ingest history"]);
        this._buildEventsTab(panels["Events"]);
        this._buildCostSummaryTab(panels["Cost summary"]);
        switchTab("Query history");
    }

    private _buildQueryHistoryTab(panel: HTMLElement) {
        const row = panel.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Last" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "50";
        input.style.cssText = "width:60px;padding:4px 8px";
        row.createEl("span", { text: "records" });
        const btn = row.createEl("button", { text: "Load" });

        const tableEl = panel.createEl("div");

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
                    const ts = rec.queried_at ? new Date(rec.queried_at).toLocaleString() : "—";
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

    private _buildIngestHistoryTab(panel: HTMLElement) {
        const row = panel.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Last" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "50";
        input.style.cssText = "width:60px;padding:4px 8px";
        row.createEl("span", { text: "records" });
        const btn = row.createEl("button", { text: "Load" });

        const tableEl = panel.createEl("div");

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
                    const ts = rec.ingested_at ? new Date(rec.ingested_at).toLocaleString() : "—";
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

    private _buildEventsTab(panel: HTMLElement) {
        const row = panel.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Last" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "100";
        input.min = "1";
        input.max = "1000";
        input.style.cssText = "width:70px;padding:4px 8px";
        row.createEl("span", { text: "events (max 1000)" });
        const btn = row.createEl("button", { text: "Load" });

        const tableEl = panel.createEl("div");
        tableEl.style.cssText = "max-height:60vh;overflow-y:auto";

        const load = async () => {
            let limit = parseInt(input.value) || 100;
            if (limit < 1) limit = 1;
            if (limit > 1000) limit = 1000;
            input.value = String(limit);
            tableEl.setText("Loading…");
            try {
                const r = await api.auditEvents(limit) as any;
                tableEl.empty();
                if (!r.records.length) {
                    tableEl.createEl("p", { text: "No audit events found." });
                    return;
                }
                const table = tableEl.createEl("table");
                table.style.cssText = "width:100%;border-collapse:collapse;font-size:12px;-webkit-user-select:text;user-select:text";
                const hrow = table.createEl("thead").createEl("tr");
                for (const h of ["Timestamp", "Job ID", "Event", "Metadata"]) {
                    const th = hrow.createEl("th", { text: h });
                    th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border);white-space:nowrap";
                }
                const tbody = table.createEl("tbody");
                for (const rec of r.records) {
                    const tr = tbody.createEl("tr");
                    const ts = rec.timestamp ? rec.timestamp.slice(0, 16).replace("T", " ") : "—";
                    const jobId = rec.job_id ? rec.job_id.slice(0, 8) : "—";
                    for (const text of [ts, jobId, rec.event ?? "—", rec.metadata ?? "—"]) {
                        const td = tr.createEl("td", { text });
                        td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle);font-size:11px";
                    }
                }
            } catch {
                tableEl.setText("Error: is synthadoc serve running?");
            }
        };

        btn.onclick = load;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
        load();
    }

    private _buildCostSummaryTab(panel: HTMLElement) {
        const row = panel.createEl("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        row.createEl("label", { text: "Last" });
        const input = row.createEl("input", { type: "number" }) as HTMLInputElement;
        input.value = "30";
        input.style.cssText = "width:60px;padding:4px 8px";
        row.createEl("span", { text: "days" });
        const btn = row.createEl("button", { text: "Load" });

        const out = panel.createEl("div");

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
        row.style.cssText = "display:flex;align-items:center;gap:8px;justify-content:flex-end;margin-bottom:12px";
        const timeoutLabel = row.createEl("label", { text: "Timeout (s):" });
        timeoutLabel.style.cssText = "font-size:12px;color:var(--text-muted);white-space:nowrap";
        const timeoutInput = row.createEl("input", { type: "number" }) as HTMLInputElement;
        timeoutInput.value = "60";
        timeoutInput.min = "10";
        timeoutInput.max = "300";
        timeoutInput.step = "10";
        timeoutInput.style.cssText = "width:60px;padding:4px 6px;font-size:12px";
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
                const timeoutSecs = Math.min(300, Math.max(10, parseInt(timeoutInput.value) || 60));
                const r = await api.query(input.value, timeoutSecs) as any;
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
                        "> **From Obsidian:** Open Command Palette (`Cmd+P` / `Ctrl+P`) → **Synthadoc: Ingest...** → Web search tab",
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

class RoutingModal extends Modal {
    onOpen(): void {
        const { contentEl, modalEl } = this;
        modalEl.style.width = "clamp(560px, 65vw, 900px)";

        const bg = this.containerEl.querySelector(".modal-bg");
        if (bg) bg.addEventListener("click", e => e.stopImmediatePropagation(), { capture: true });

        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Routing" });
        makeDraggable(modalEl, titleEl);

        const contentBox = contentEl.createEl("pre");
        contentBox.style.cssText = "display:none;border:1px solid var(--background-modifier-border);"
            + "border-radius:4px;padding:8px;margin-bottom:12px;font-size:12px;"
            + "white-space:pre-wrap;overflow-y:auto;max-height:45vh;";

        const statusMsg = contentEl.createEl("p");
        statusMsg.style.cssText = "margin-bottom:12px;font-size:13px;";

        const btnRow = contentEl.createEl("div");
        btnRow.style.cssText = "display:flex;gap:8px;margin-bottom:10px;";
        const initBtn     = btnRow.createEl("button", { text: "Init" });
        const validateBtn = btnRow.createEl("button", { text: "Validate" });
        const cleanBtn    = btnRow.createEl("button", { text: "Clean" });

        const descEl = contentEl.createEl("div");
        descEl.style.cssText = "font-size:12px;color:var(--text-muted);margin-bottom:12px;";
        descEl.innerHTML =
            `<div style="display:grid;grid-template-columns:68px 1fr;gap:3px 10px;">` +
            `<strong>Init</strong><span>Bootstrap ROUTING.md from current index.md branch structure (run once)</span>` +
            `<strong>Validate</strong><span>Report dangling slugs (pages listed in ROUTING.md that no longer exist)</span>` +
            `<strong>Clean</strong><span>Auto-remove dangling slugs from ROUTING.md</span>` +
            `</div>`;

        const resultEl = contentEl.createEl("div");
        resultEl.style.cssText = "font-size:13px;min-height:24px;";
        const setResult = (html: string) => { resultEl.innerHTML = html; };

        const applyInitialized = (content: string) => {
            contentBox.style.display = "block";
            contentBox.textContent = content;
            statusMsg.style.display = "none";
            initBtn.disabled = true;
            validateBtn.disabled = false;
            cleanBtn.disabled = false;
        };

        const applyUninitialized = () => {
            contentBox.style.display = "none";
            statusMsg.style.display = "block";
            statusMsg.textContent = "ROUTING.md not found. Run Init to generate it from your current index.md.";
            initBtn.disabled = false;
            validateBtn.disabled = true;
            cleanBtn.disabled = true;
        };

        api.routingStatus().then((r: any) => {
            r.exists ? applyInitialized(r.content) : applyUninitialized();
        }).catch(() => {
            initBtn.disabled = true;
            validateBtn.disabled = true;
            cleanBtn.disabled = true;
            setResult("❌ Cannot reach Synthadoc server. Is it running?");
        });

        initBtn.onclick = async () => {
            initBtn.disabled = true;
            setResult("⏳ Initializing…");
            try {
                const r = await api.routingInit() as any;
                applyInitialized(r.content);
                setResult(`✅ ROUTING.md created — ${r.branches} branches, ${r.slugs} slugs.`);
            } catch (e: any) {
                initBtn.disabled = false;
                const msg = /409/.test(e.message) ? "ROUTING.md already exists. Delete it first to re-init."
                          : /400/.test(e.message) ? "index.md not found — run scaffold first."
                          : e.message ?? "Unexpected error.";
                setResult(`❌ ${msg}`);
            }
        };

        validateBtn.onclick = async () => {
            setResult("⏳ Validating…");
            try {
                const r = await api.routingValidate() as any;
                if (r.clean) {
                    setResult("✅ ROUTING.md is clean — no dangling slugs.");
                } else {
                    const n = r.dangling.length;
                    const rows = r.dangling
                        .map((d: any) => `&nbsp;&nbsp;[${d.branch}]&nbsp;&nbsp;[[${d.slug}]]`)
                        .join("<br>");
                    setResult(`⚠️ ${n} dangling slug${n === 1 ? "" : "s"} found:<br>`
                        + `<code style="font-size:12px;">${rows}</code>`);
                }
            } catch (e: any) {
                const msg = /404/.test(e.message) ? "ROUTING.md not found — run Init first."
                          : e.message ?? "Unexpected error.";
                setResult(`❌ ${msg}`);
            }
        };

        cleanBtn.onclick = async () => {
            setResult("⏳ Cleaning…");
            try {
                const r = await api.routingClean() as any;
                if (r.removed.length === 0) {
                    setResult("✅ ROUTING.md is clean — nothing to remove.");
                } else {
                    const n = r.removed.length;
                    const rows = r.removed
                        .map((d: any) => `&nbsp;&nbsp;[${d.branch}]&nbsp;&nbsp;[[${d.slug}]]`)
                        .join("<br>");
                    contentBox.textContent = r.content;
                    setResult(`✅ Removed ${n} dangling entr${n === 1 ? "y" : "ies"} from ROUTING.md:<br>`
                        + `<code style="font-size:12px;">${rows}</code><br>ROUTING.md updated.`);
                }
            } catch (e: any) {
                const msg = /404/.test(e.message) ? "ROUTING.md not found — run Init first."
                          : e.message ?? "Unexpected error.";
                setResult(`❌ ${msg}`);
            }
        };
    }

    onClose(): void {
        this.contentEl.empty();
    }
}

// ── Shared UI helper ─────────────────────────────────────────────────────────

function makeSegmented(
    parent: HTMLElement,
    options: { value: string; label: string }[],
    initial: string,
    onChange: (value: string) => void,
): { getValue: () => string; setValue: (v: string) => void } {
    const wrap = parent.createEl("div");
    wrap.style.cssText = "display:inline-flex;border:1px solid var(--background-modifier-border);"
        + "border-radius:6px;overflow:hidden;";

    let current = initial;
    const btns: Record<string, HTMLButtonElement> = {};

    const activate = (val: string) => {
        current = val;
        for (const [v, btn] of Object.entries(btns)) {
            const active = v === val;
            btn.style.background = active ? "var(--interactive-accent)" : "var(--background-primary)";
            btn.style.color = active ? "var(--text-on-accent)" : "var(--text-normal)";
            btn.style.fontWeight = active ? "600" : "400";
        }
    };

    for (const opt of options) {
        const btn = wrap.createEl("button", { text: opt.label }) as HTMLButtonElement;
        btn.style.cssText = "border:none;border-radius:0;padding:5px 14px;font-size:13px;cursor:pointer;transition:background 0.1s;";
        btns[opt.value] = btn;
        btn.onclick = () => {
            activate(opt.value);
            onChange(opt.value);
        };
    }

    activate(initial);
    return {
        getValue: () => current,
        setValue: (v: string) => activate(v),
    };
}

// ── StagingModal ─────────────────────────────────────────────────────────────

class StagingModal extends Modal {
    onOpen(): void {
        const { contentEl, modalEl } = this;
        modalEl.style.width = "clamp(480px, 55vw, 760px)";

        const bg = this.containerEl.querySelector(".modal-bg");
        if (bg) bg.addEventListener("click", e => e.stopImmediatePropagation(), { capture: true });

        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Staging Policy" });
        makeDraggable(modalEl, titleEl);

        const stateEl = contentEl.createEl("div");
        stateEl.style.cssText = "margin-bottom:16px;padding:10px 12px;border-radius:6px;"
            + "background:var(--background-secondary);font-size:13px;min-height:36px;";

        // Policy row
        const policyRow = contentEl.createEl("div");
        policyRow.style.cssText = "display:flex;align-items:center;gap:12px;margin-bottom:14px;";
        policyRow.createEl("span", { text: "Policy" }).style.cssText
            = "font-size:13px;font-weight:600;min-width:90px;";
        const policySeg = makeSegmented(
            policyRow,
            [
                { value: "off", label: "Off" },
                { value: "all", label: "All" },
                { value: "threshold", label: "Threshold" },
            ],
            "off",
            (val) => {
                confidenceRow.style.display = val === "threshold" ? "flex" : "none";
            },
        );

        // Confidence row (visible only when threshold)
        const confidenceRow = contentEl.createEl("div");
        confidenceRow.style.cssText = "display:none;align-items:center;gap:12px;margin-bottom:14px;";
        confidenceRow.createEl("span", { text: "Min confidence" }).style.cssText
            = "font-size:13px;font-weight:600;min-width:90px;";
        const confidenceSeg = makeSegmented(
            confidenceRow,
            [
                { value: "high", label: "High" },
                { value: "medium", label: "Medium" },
                { value: "low", label: "Low" },
            ],
            "high",
            () => {},
        );

        // Description
        const descEl = contentEl.createEl("div");
        descEl.style.cssText = "font-size:12px;color:var(--text-muted);margin-bottom:14px;"
            + "display:grid;grid-template-columns:80px 1fr;gap:3px 10px;";
        descEl.innerHTML =
            `<strong>Off</strong><span>All new pages go directly to the wiki (default).</span>` +
            `<strong>All</strong><span>Every new page goes to staging — you review and promote manually.</span>` +
            `<strong>Threshold</strong><span>Pages whose confidence is below the minimum are staged for review.</span>`;

        // Action row
        const actionRow = contentEl.createEl("div");
        actionRow.style.cssText = "display:flex;gap:8px;align-items:center;margin-bottom:12px;";
        const saveBtn = actionRow.createEl("button", { text: "Save" }) as HTMLButtonElement;
        saveBtn.style.cssText = "font-weight:bold;";

        const resultEl = contentEl.createEl("div");
        resultEl.style.cssText = "font-size:13px;min-height:22px;margin-bottom:12px;";
        const setResult = (html: string) => { resultEl.innerHTML = html; };

        // Footer link
        const footer = contentEl.createEl("div");
        footer.style.cssText = "border-top:1px solid var(--background-modifier-border);padding-top:10px;font-size:12px;";
        const candLink = footer.createEl("a", { text: "Candidate pages →" });
        candLink.style.cssText = "cursor:pointer;color:var(--link-color);";
        candLink.onclick = () => {
            this.close();
            setTimeout(() => (this.app as any).commands?.executeCommandById("synthadoc:synthadoc-candidates"), 150);
        };

        // Load current state
        const applyState = (policy: string, confMin: string) => {
            policySeg.setValue(policy);
            confidenceSeg.setValue(confMin || "high");
            confidenceRow.style.display = policy === "threshold" ? "flex" : "none";
            const labels: Record<string, string> = {
                off: "Staging is <strong>disabled</strong>. All new pages publish directly.",
                all: "Staging is <strong>enabled (all)</strong>. Every new page goes to staging.",
                threshold: `Staging is <strong>enabled (threshold)</strong>. Pages below <em>${confMin || "high"}</em> confidence are staged.`,
            };
            stateEl.innerHTML = labels[policy] ?? policy;
        };

        api.stagingPolicy().then((r: any) => {
            applyState(r.policy, r.confidence_min);
        }).catch(() => {
            setResult("❌ Cannot reach Synthadoc server. Is it running?");
            saveBtn.disabled = true;
        });

        saveBtn.onclick = async () => {
            saveBtn.disabled = true;
            setResult("⏳ Saving…");
            const policy = policySeg.getValue();
            const confMin = policy === "threshold" ? confidenceSeg.getValue() : undefined;
            try {
                const r = await api.stagingSetPolicy(policy, confMin) as any;
                applyState(r.policy, r.confidence_min);
                setResult(`✅ Policy updated to <strong>${r.policy}</strong>${r.policy === "threshold" ? ` (min confidence: ${r.confidence_min})` : ""}.`);
            } catch (e: any) {
                setResult(`❌ ${e.message ?? "Failed to save."}`);
            } finally {
                saveBtn.disabled = false;
            }
        };
    }

    onClose(): void {
        this.contentEl.empty();
    }
}

// ── CandidatesModal ───────────────────────────────────────────────────────────

const CAND_PAGE_SIZE = 50;

const CONF_BADGE: Record<string, string> = {
    high:   "background:#2d6a2d;color:#b6ffb6;",
    medium: "background:#7a6000;color:#fff3b0;",
    low:    "background:#7a2020;color:#ffb6b6;",
};

class CandidatesModal extends Modal {
    private _candidates: any[] = [];
    private _page = 0;
    private _selected: Set<string> = new Set();

    onOpen(): void {
        const { contentEl, modalEl } = this;
        modalEl.style.width = "clamp(560px, 70vw, 1000px)";

        const bg = this.containerEl.querySelector(".modal-bg");
        if (bg) bg.addEventListener("click", e => e.stopImmediatePropagation(), { capture: true });

        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Candidate Pages" });
        makeDraggable(modalEl, titleEl);

        const resultEl = contentEl.createEl("div");
        resultEl.style.cssText = "font-size:13px;min-height:22px;margin-bottom:8px;";
        const setResult = (html: string) => { resultEl.innerHTML = html; };

        // Top action bar
        const actionBar = contentEl.createEl("div");
        actionBar.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center;";

        const promoteAllBtn  = actionBar.createEl("button", { text: "Promote All" }) as HTMLButtonElement;
        const discardAllBtn  = actionBar.createEl("button", { text: "Discard All" }) as HTMLButtonElement;
        discardAllBtn.style.color = "var(--text-error)";
        const sep = actionBar.createEl("span", { text: "|" });
        sep.style.cssText = "color:var(--text-muted);margin:0 2px;";
        const promoteSelBtn  = actionBar.createEl("button", { text: "Promote Selected" }) as HTMLButtonElement;
        const discardSelBtn  = actionBar.createEl("button", { text: "Discard Selected" }) as HTMLButtonElement;
        discardSelBtn.style.color = "var(--text-error)";

        // Table container
        const tableWrap = contentEl.createEl("div");
        tableWrap.style.cssText = "overflow-y:auto;max-height:50vh;margin-bottom:10px;"
            + "border:1px solid var(--background-modifier-border);border-radius:4px;";

        // Pagination row
        const pageRow = contentEl.createEl("div");
        pageRow.style.cssText = "display:flex;gap:8px;align-items:center;margin-bottom:12px;font-size:12px;color:var(--text-muted);";
        const prevBtn = pageRow.createEl("button", { text: "← Prev" }) as HTMLButtonElement;
        const pageLabel = pageRow.createEl("span");
        const nextBtn = pageRow.createEl("button", { text: "Next →" }) as HTMLButtonElement;

        // Footer
        const footer = contentEl.createEl("div");
        footer.style.cssText = "border-top:1px solid var(--background-modifier-border);padding-top:10px;font-size:12px;";
        const stagingLink = footer.createEl("a", { text: "← Staging policy" });
        stagingLink.style.cssText = "cursor:pointer;color:var(--link-color);";
        stagingLink.onclick = () => {
            this.close();
            setTimeout(() => (this.app as any).commands?.executeCommandById("synthadoc:synthadoc-staging"), 150);
        };

        const render = () => {
            tableWrap.empty();
            const total = this._candidates.length;
            const totalPages = Math.max(1, Math.ceil(total / CAND_PAGE_SIZE));
            this._page = Math.min(this._page, totalPages - 1);
            const slice = this._candidates.slice(this._page * CAND_PAGE_SIZE, (this._page + 1) * CAND_PAGE_SIZE);

            prevBtn.disabled = this._page === 0;
            nextBtn.disabled = this._page >= totalPages - 1;
            pageRow.style.display = totalPages > 1 ? "flex" : "none";
            pageLabel.textContent = `Page ${this._page + 1} of ${totalPages} (${total} total)`;

            const allBtnsDisabled = total === 0;
            promoteAllBtn.disabled = allBtnsDisabled;
            discardAllBtn.disabled = allBtnsDisabled;

            if (total === 0) {
                tableWrap.createEl("div", { text: "No candidates. All new pages are publishing directly." })
                    .style.cssText = "padding:20px;text-align:center;color:var(--text-muted);font-size:13px;";
                promoteSelBtn.disabled = true;
                discardSelBtn.disabled = true;
                return;
            }

            const table = tableWrap.createEl("table");
            table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px;";

            const thead = table.createEl("thead");
            const hrow = thead.createEl("tr");
            hrow.style.cssText = "background:var(--background-secondary);";
            const thCheck = hrow.createEl("th");
            thCheck.style.cssText = "padding:6px 8px;width:32px;";
            const allCheckbox = thCheck.createEl("input", { type: "checkbox" }) as HTMLInputElement;
            allCheckbox.title = "Select all on this page";
            hrow.createEl("th", { text: "Slug" }).style.cssText = "padding:6px 8px;text-align:left;";
            hrow.createEl("th", { text: "Title" }).style.cssText = "padding:6px 8px;text-align:left;";
            hrow.createEl("th", { text: "Confidence" }).style.cssText = "padding:6px 8px;text-align:center;";
            hrow.createEl("th", { text: "Ingested" }).style.cssText = "padding:6px 8px;text-align:left;";

            const tbody = table.createEl("tbody");
            const rowCheckboxes: HTMLInputElement[] = [];

            for (const c of slice) {
                const tr = tbody.createEl("tr");
                tr.style.cssText = "border-top:1px solid var(--background-modifier-border);";
                tr.onmouseenter = () => { tr.style.background = "var(--background-modifier-hover)"; };
                tr.onmouseleave = () => { tr.style.background = ""; };

                const tdCheck = tr.createEl("td");
                tdCheck.style.cssText = "padding:6px 8px;text-align:center;";
                const cb = tdCheck.createEl("input", { type: "checkbox" }) as HTMLInputElement;
                cb.checked = this._selected.has(c.slug);
                cb.onchange = () => {
                    cb.checked ? this._selected.add(c.slug) : this._selected.delete(c.slug);
                    updateSelBtns();
                    allCheckbox.indeterminate = rowCheckboxes.some(x => x.checked) && !rowCheckboxes.every(x => x.checked);
                    allCheckbox.checked = rowCheckboxes.every(x => x.checked);
                };
                rowCheckboxes.push(cb);

                tr.createEl("td", { text: c.slug }).style.cssText
                    = "padding:6px 8px;font-family:var(--font-monospace);font-size:12px;";
                tr.createEl("td", { text: c.title }).style.cssText = "padding:6px 8px;";

                const tdConf = tr.createEl("td");
                tdConf.style.cssText = "padding:6px 8px;text-align:center;";
                if (c.confidence) {
                    const badge = tdConf.createEl("span", { text: c.confidence });
                    badge.style.cssText = `border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;`
                        + (CONF_BADGE[c.confidence] ?? "background:var(--background-modifier-border);color:var(--text-normal);");
                }

                tr.createEl("td", { text: c.created ? c.created.slice(0, 10) : "—" })
                    .style.cssText = "padding:6px 8px;color:var(--text-muted);";
            }

            allCheckbox.checked = slice.length > 0 && slice.every(c => this._selected.has(c.slug));
            allCheckbox.onchange = () => {
                for (const c of slice) {
                    allCheckbox.checked ? this._selected.add(c.slug) : this._selected.delete(c.slug);
                }
                for (const cb of rowCheckboxes) cb.checked = allCheckbox.checked;
                updateSelBtns();
            };

            updateSelBtns();
        };

        const updateSelBtns = () => {
            const hasSel = this._selected.size > 0;
            promoteSelBtn.disabled = !hasSel;
            discardSelBtn.disabled = !hasSel;
        };

        const reload = async () => {
            setResult("⏳ Loading…");
            try {
                this._candidates = await api.candidates() as any[];
                this._selected.clear();
                setResult(`${this._candidates.length} candidate${this._candidates.length === 1 ? "" : "s"} awaiting review.`);
                render();
            } catch {
                setResult("❌ Cannot reach Synthadoc server. Is it running?");
                promoteAllBtn.disabled = true;
                discardAllBtn.disabled = true;
                promoteSelBtn.disabled = true;
                discardSelBtn.disabled = true;
            }
        };

        prevBtn.onclick = () => { this._page--; render(); };
        nextBtn.onclick = () => { this._page++; render(); };

        promoteAllBtn.onclick = async () => {
            promoteAllBtn.disabled = true;
            setResult("⏳ Promoting all…");
            try {
                const r = await api.candidatesPromoteAll() as any;
                setResult(`✅ Promoted ${r.count} page${r.count === 1 ? "" : "s"} to wiki.`);
                await reload();
            } catch (e: any) {
                setResult(`❌ ${e.message ?? "Failed."}`);
                promoteAllBtn.disabled = false;
            }
        };

        discardAllBtn.onclick = async () => {
            discardAllBtn.disabled = true;
            setResult("⏳ Discarding all…");
            try {
                const r = await api.candidatesDiscardAll() as any;
                setResult(`✅ Discarded ${r.count} candidate${r.count === 1 ? "" : "s"}.`);
                await reload();
            } catch (e: any) {
                setResult(`❌ ${e.message ?? "Failed."}`);
                discardAllBtn.disabled = false;
            }
        };

        promoteSelBtn.onclick = async () => {
            const slugs = [...this._selected];
            promoteSelBtn.disabled = true;
            setResult(`⏳ Promoting ${slugs.length} page${slugs.length === 1 ? "" : "s"}…`);
            const failed: string[] = [];
            for (const slug of slugs) {
                try { await api.candidatePromote(slug); }
                catch { failed.push(slug); }
            }
            const ok = slugs.length - failed.length;
            setResult(`✅ Promoted ${ok}${failed.length ? `; ❌ ${failed.length} failed: ${failed.join(", ")}` : ""}.`);
            await reload();
        };

        discardSelBtn.onclick = async () => {
            const slugs = [...this._selected];
            discardSelBtn.disabled = true;
            setResult(`⏳ Discarding ${slugs.length} page${slugs.length === 1 ? "" : "s"}…`);
            const failed: string[] = [];
            for (const slug of slugs) {
                try { await api.candidateDiscard(slug); }
                catch { failed.push(slug); }
            }
            const ok = slugs.length - failed.length;
            setResult(`✅ Discarded ${ok}${failed.length ? `; ❌ ${failed.length} failed: ${failed.join(", ")}` : ""}.`);
            await reload();
        };

        reload();
    }

    onClose(): void {
        this._candidates = [];
        this._selected.clear();
        this.contentEl.empty();
    }
}

// ── ContextModal ──────────────────────────────────────────────────────────────

const DEFAULT_TOKEN_BUDGET = 4000;

function renderContextPackMarkdown(pack: any): string {
    const now = new Date().toISOString().slice(0, 19);
    const omittedNote = pack.omitted?.length
        ? ` | Omitted: ${pack.omitted.length} page(s) (budget exceeded)`
        : "";
    const lines: string[] = [
        `# Context Pack: ${pack.goal}`,
        `Generated: ${now}`,
        `Token budget: ${pack.token_budget} | Used: ${pack.tokens_used}${omittedNote}`,
        "",
        "---",
        "",
    ];
    for (const p of pack.pages ?? []) {
        lines.push(`## [[${p.slug}]] — relevance: ${Number(p.relevance).toFixed(2)}`);
        lines.push(`> ${p.excerpt}`);
        lines.push(
            `Source: \`${p.source}\` | Confidence: ${p.confidence}` +
            (p.tags?.length ? ` | Tags: ${(p.tags as string[]).join(", ")}` : ""),
        );
        lines.push("");
    }
    if (pack.omitted?.length) {
        lines.push("---", "", "## Omitted — token budget exceeded");
        for (const p of pack.omitted) {
            lines.push(`- [[${p.slug}]] — ~${p.estimated_tokens} tokens`);
        }
    }
    return lines.join("\n");
}

class ContextModal extends Modal {
    private _result = "";

    onOpen(): void {
        const { contentEl, modalEl } = this;
        modalEl.style.width = "clamp(560px, 65vw, 900px)";

        const bg = this.containerEl.querySelector(".modal-bg");
        if (bg) bg.addEventListener("click", e => e.stopImmediatePropagation(), { capture: true });

        const titleEl = contentEl.createEl("h3", { text: "Synthadoc: Context Pack" });
        makeDraggable(modalEl, titleEl);

        // Description
        const desc = contentEl.createEl("p");
        desc.style.cssText = "font-size:13px;color:var(--text-muted);margin-bottom:14px;line-height:1.5;";
        desc.textContent =
            "A context pack assembles the most relevant wiki pages into a single cited Markdown " +
            "document within a token budget. Use it to ground an external LLM prompt, save evidence " +
            "alongside a draft you are writing, or pipe it into another tool.";

        // Goal input
        const goalLabel = contentEl.createEl("div", { text: "Goal / question" });
        goalLabel.style.cssText = "font-size:12px;font-weight:600;margin-bottom:4px;";
        const goalInput = contentEl.createEl("textarea") as HTMLTextAreaElement;
        goalInput.placeholder = "e.g. early computing pioneers";
        goalInput.rows = 3;
        goalInput.style.cssText = "width:100%;box-sizing:border-box;resize:vertical;font-size:13px;"
            + "margin-bottom:12px;padding:6px 8px;border-radius:4px;"
            + "border:1px solid var(--background-modifier-border);background:var(--background-primary);";

        // Token budget row
        const budgetRow = contentEl.createEl("div");
        budgetRow.style.cssText = "display:flex;align-items:center;gap:10px;margin-bottom:14px;";
        budgetRow.createEl("span", { text: "Token budget" }).style.cssText
            = "font-size:12px;font-weight:600;white-space:nowrap;";
        const budgetInput = budgetRow.createEl("input") as HTMLInputElement;
        budgetInput.type = "number";
        budgetInput.min = "100";
        budgetInput.max = "32000";
        budgetInput.step = "100";
        budgetInput.value = String(DEFAULT_TOKEN_BUDGET);
        budgetInput.style.cssText = "width:90px;padding:4px 6px;font-size:13px;border-radius:4px;"
            + "border:1px solid var(--background-modifier-border);background:var(--background-primary);";
        budgetRow.createEl("span", { text: "tokens" }).style.cssText
            = "font-size:12px;color:var(--text-muted);";

        // Build button + status
        const buildRow = contentEl.createEl("div");
        buildRow.style.cssText = "display:flex;align-items:center;gap:10px;margin-bottom:14px;";
        const buildBtn = buildRow.createEl("button", { text: "Build Context Pack" }) as HTMLButtonElement;
        buildBtn.style.cssText = "font-weight:bold;";
        const statusEl = buildRow.createEl("span");
        statusEl.style.cssText = "font-size:12px;color:var(--text-muted);";

        // Result section (hidden until first build)
        const resultSection = contentEl.createEl("div");
        resultSection.style.display = "none";

        const divider = resultSection.createEl("hr");
        divider.style.cssText = "margin:0 0 10px;border:none;border-top:1px solid var(--background-modifier-border);";

        const resultMeta = resultSection.createEl("div");
        resultMeta.style.cssText = "font-size:12px;color:var(--text-muted);margin-bottom:6px;";

        const resultArea = resultSection.createEl("textarea") as HTMLTextAreaElement;
        resultArea.readOnly = true;
        resultArea.rows = 22;
        resultArea.style.cssText = "width:100%;box-sizing:border-box;resize:vertical;font-size:12px;"
            + "font-family:var(--font-monospace);padding:8px;border-radius:4px;"
            + "border:1px solid var(--background-modifier-border);background:var(--background-secondary);"
            + "margin-bottom:10px;";

        // Action buttons row
        const actionRow = resultSection.createEl("div");
        actionRow.style.cssText = "display:flex;gap:8px;align-items:center;";

        const copyBtn = actionRow.createEl("button", { text: "Copy to Clipboard" }) as HTMLButtonElement;
        const saveBtn = actionRow.createEl("button", { text: "Save as .md" }) as HTMLButtonElement;
        const copyNote = actionRow.createEl("span");
        copyNote.style.cssText = "font-size:12px;color:var(--text-muted);";

        // Copy handler
        copyBtn.onclick = async () => {
            try {
                await navigator.clipboard.writeText(this._result);
                copyNote.textContent = "✅ Copied!";
                setTimeout(() => { copyNote.textContent = ""; }, 2500);
            } catch {
                copyNote.textContent = "❌ Copy failed — select and copy manually.";
            }
        };

        // Save as handler — uses Electron native dialog so status shows only after user confirms
        saveBtn.onclick = async () => {
            const slug = goalInput.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40) || "context-pack";
            const filename = `${slug}.md`;
            saveBtn.disabled = true;
            copyNote.textContent = "💾 Saving…";
            try {
                const electron = (window as any).require("electron");
                const nodefs = (window as any).require("fs");
                const nodepath = (window as any).require("path");
                const result = await electron.remote.dialog.showSaveDialog({
                    defaultPath: filename,
                    filters: [{ name: "Markdown", extensions: ["md"] }],
                });
                if (!result.canceled && result.filePath) {
                    await nodefs.promises.writeFile(result.filePath, this._result, "utf-8");
                    copyNote.textContent = `✅ Saved as ${nodepath.basename(result.filePath)}`;
                    setTimeout(() => { copyNote.textContent = ""; }, 3000);
                } else {
                    copyNote.textContent = "";
                }
            } catch {
                // Fallback for non-Electron environments
                const blob = new Blob([this._result], { type: "text/markdown;charset=utf-8" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                copyNote.textContent = `✅ Saved as ${filename}`;
                setTimeout(() => { copyNote.textContent = ""; }, 3000);
            } finally {
                saveBtn.disabled = false;
            }
        };

        // Build handler
        const runBuild = async () => {
            const goal = goalInput.value.trim();
            if (!goal) {
                statusEl.textContent = "⚠ Enter a goal or question first.";
                return;
            }
            const budget = Math.max(100, parseInt(budgetInput.value, 10) || DEFAULT_TOKEN_BUDGET);
            budgetInput.value = String(budget);

            buildBtn.disabled = true;
            statusEl.textContent = "⏳ Building…";
            resultSection.style.display = "none";

            try {
                const pack = await api.contextBuild(goal, budget) as any;
                this._result = renderContextPackMarkdown(pack);
                resultArea.value = this._result;
                resultMeta.textContent =
                    `${pack.pages?.length ?? 0} page(s) included · ${pack.tokens_used} / ${pack.token_budget} tokens used`
                    + (pack.omitted?.length ? ` · ${pack.omitted.length} omitted` : "");
                resultSection.style.display = "block";
                statusEl.textContent = "";
                copyNote.textContent = "";
            } catch (e: any) {
                statusEl.textContent = `❌ ${e.message ?? "Failed to build context pack."}`;
            } finally {
                buildBtn.disabled = false;
            }
        };

        buildBtn.onclick = runBuild;

        // Ctrl/Cmd+Enter submits
        goalInput.addEventListener("keydown", (e: KeyboardEvent) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                runBuild();
            }
        });

        goalInput.focus();
    }

    onClose(): void {
        this._result = "";
        this.contentEl.empty();
    }
}
