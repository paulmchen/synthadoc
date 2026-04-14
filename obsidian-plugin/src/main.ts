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
            name: "Ingest current file as source",
            callback: () => {
                const file = this.app.workspace.getActiveFile();
                if (file) {
                    this.ingestFile(file);
                } else {
                    new IngestPickerModal(this.app, this).open();
                }
            },
        });

        this.addCommand({
            id: "synthadoc-ingest-all",
            name: "Ingest all sources",
            callback: () => this.ingestAllSources(),
        });

        this.addCommand({
            id: "synthadoc-query",
            name: "Query wiki...",
            callback: () => new QueryModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-jobs",
            name: "List jobs...",
            callback: () => new JobsModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-lint-report",
            name: "Lint report",
            callback: () => new LintReportModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-ingest-url",
            name: "Ingest from URL...",
            callback: () => new IngestUrlModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-web-search",
            name: "Web search...",
            callback: () => new WebSearchModal(this.app).open(),
        });

        this.addCommand({
            id: "synthadoc-lint",
            name: "Run lint",
            callback: async () => {
                new Notice("Synthadoc: running lint...");
                try {
                    const r = await api.lint() as any;
                    new Notice(`Synthadoc: lint done — ${r.contradictions_found} contradictions, ${r.orphans?.length ?? 0} orphans`);
                } catch { new Notice("Synthadoc: server not running — run 'synthadoc serve'"); }
            },
        });

        this.addCommand({
            id: "synthadoc-lint-auto-resolve",
            name: "Run lint with auto-resolve",
            callback: async () => {
                new Notice("Synthadoc: running lint with auto-resolve...");
                try {
                    const r = await api.lint("all", true) as any;
                    new Notice(`Synthadoc: lint done — ${r.contradictions_found} contradictions, ${r.orphans?.length ?? 0} orphans`);
                } catch { new Notice("Synthadoc: server not running — run 'synthadoc serve'"); }
            },
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
        this.plugin.ingestFile(file);
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

const STATUS_OPTIONS = ["all", "pending", "running", "completed", "failed", "dead"] as const;

const STATUS_EMOJI: Record<string, string> = {
    pending:   "⏳",
    running:   "▶",
    completed: "✅",
    failed:    "❌",
    dead:      "💀",
};

class JobsModal extends Modal {
    private currentStatus = "all";
    private tableEl: HTMLElement | null = null;

    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });

        const { contentEl } = this;
        contentEl.createEl("h3", { text: "Synthadoc: Jobs" });

        // Filter row
        const filterRow = contentEl.createEl("div");
        filterRow.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:12px";
        filterRow.createEl("label", { text: "Filter:" });
        const select = filterRow.createEl("select");
        for (const s of STATUS_OPTIONS) {
            const opt = select.createEl("option", { text: s, value: s });
            if (s === this.currentStatus) opt.selected = true;
        }
        const refreshBtn = filterRow.createEl("button", { text: "Refresh" });

        // Table container
        this.tableEl = contentEl.createEl("div");

        const load = async () => {
            if (!this.tableEl) return;
            this.tableEl.setText("Loading…");
            try {
                const status = this.currentStatus === "all" ? undefined : this.currentStatus;
                const jobs = await api.jobs(status) as any[];
                this.renderTable(jobs);
            } catch {
                this.tableEl.setText("Error: is synthadoc serve running?");
            }
        };

        select.onchange = () => { this.currentStatus = select.value; load(); };
        refreshBtn.onclick = () => load();
        load();
    }

    private renderTable(jobs: any[]) {
        if (!this.tableEl) return;
        this.tableEl.empty();

        if (jobs.length === 0) {
            this.tableEl.createEl("p", { text: "No jobs found." });
            return;
        }

        const table = this.tableEl.createEl("table");
        table.style.cssText = "width:100%;border-collapse:collapse;font-size:13px";

        const thead = table.createEl("thead");
        const hrow = thead.createEl("tr");
        for (const h of ["Status", "Operation", "Source", "Created"]) {
            const th = hrow.createEl("th", { text: h });
            th.style.cssText = "text-align:left;padding:4px 8px;border-bottom:1px solid var(--background-modifier-border)";
        }

        const tbody = table.createEl("tbody");
        for (const job of jobs) {
            const tr = tbody.createEl("tr");
            const source = job.payload?.source
                ? job.payload.source.split(/[\\/]/).pop()
                : job.operation === "lint" ? "(lint)" : "—";
            // SQLite stores UTC without a tz marker; appending +00:00 ensures JS parses it as UTC
            const created = job.created_at
                ? new Date(job.created_at.replace(" ", "T") + "+00:00").toLocaleString()
                : "—";
            const icon = STATUS_EMOJI[job.status] ?? "";
            for (const text of [`${icon} ${job.status}`, job.operation, source, created]) {
                const td = tr.createEl("td", { text });
                td.style.cssText = "padding:4px 8px;border-bottom:1px solid var(--background-modifier-border-subtle)";
            }
            // Show result details if completed
            if (job.status === "completed" && job.result) {
                const r = job.result;
                const detail: string[] = [];
                if (r.pages_created?.length) detail.push(`created: ${r.pages_created.join(", ")}`);
                if (r.pages_updated?.length) detail.push(`updated: ${r.pages_updated.join(", ")}`);
                if (r.pages_flagged?.length) detail.push(`flagged: ${r.pages_flagged.join(", ")}`);
                if (detail.length) {
                    const drow = tbody.createEl("tr");
                    const dtd = drow.createEl("td", { text: detail.join(" · ") });
                    dtd.colSpan = 4;
                    dtd.style.cssText = "padding:2px 8px 6px 8px;font-size:11px;color:var(--text-muted)";
                }
            }
            if (job.status === "failed" && job.error) {
                const erow = tbody.createEl("tr");
                const etd = erow.createEl("td", { text: `Error: ${job.error}` });
                etd.colSpan = 4;
                etd.style.cssText = "padding:2px 8px 6px 8px;font-size:11px;color:var(--text-error)";
            }
        }
    }

    onClose() { this.contentEl.empty(); }
}

class LintReportModal extends Modal {
    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });

        const { contentEl } = this;
        contentEl.createEl("h3", { text: "Synthadoc: Lint report" });
        const out = contentEl.createEl("div");
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
    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });

        const { contentEl } = this;
        contentEl.createEl("h3", { text: "Synthadoc: Ingest from URL" });

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;gap:8px;margin-bottom:12px";
        const input = row.createEl("input", { type: "url", placeholder: "https://..." });
        input.style.cssText = "flex:1;padding:4px 8px";
        const btn = row.createEl("button", { text: "Ingest" });

        const out = contentEl.createEl("p");

        const submit = async () => {
            const url = input.value.trim();
            if (!url) return;
            btn.disabled = true;
            out.setText("Queuing…");
            try {
                const r = await api.ingest(url) as any;
                out.setText(`Queued — job ${r.job_id}`);
                new Notice(`Synthadoc: ingest queued (job ${r.job_id})`);
            } catch {
                out.setText("Error: is synthadoc serve running?");
            } finally { btn.disabled = false; }
        };

        btn.onclick = submit;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
    }
    onClose() { this.contentEl.empty(); }
}

class WebSearchModal extends Modal {
    onOpen() {
        const bg = this.containerEl.querySelector(".modal-bg") as HTMLElement | null;
        if (bg) bg.addEventListener("click", (e) => e.stopImmediatePropagation(), { capture: true });

        const { contentEl } = this;
        contentEl.createEl("h3", { text: "Synthadoc: Web search" });
        contentEl.createEl("p", {
            text: "Type a topic — Synthadoc will search the web and compile results into your wiki.",
            cls: "synthadoc-muted",
        }).style.cssText = "font-size:12px;margin-bottom:12px";

        const input = contentEl.createEl("textarea", { placeholder: "e.g. Bank of Canada rate outlook 2025\nOntario housing market trends" });
        input.style.cssText = "width:100%;min-height:80px;padding:6px 8px;resize:vertical;margin-bottom:8px;box-sizing:border-box";

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;justify-content:flex-end;margin-bottom:12px";
        const btn = row.createEl("button", { text: "Search" });

        const out = contentEl.createEl("p");

        const submit = async () => {
            const topic = input.value.trim();
            if (!topic) return;
            btn.disabled = true;
            out.setText("Queuing web search…");
            try {
                const r = await api.ingest(`search for: ${topic}`) as any;
                out.setText(`Queued — job ${r.job_id}. Pages will appear in your wiki as results are ingested.`);
                new Notice(`Synthadoc: web search queued (job ${r.job_id})`);
            } catch {
                out.setText("Error: is synthadoc serve running?");
            } finally { btn.disabled = false; }
        };

        btn.onclick = submit;
        input.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); });
        setTimeout(() => input.focus(), 50);
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
        contentEl.createEl("h3", { text: "Synthadoc: Query your wiki" });

        const input = contentEl.createEl("textarea", { placeholder: "Ask a question…\n(Ctrl+Enter or Cmd+Enter to submit)" });
        input.style.cssText = "width:100%;min-height:72px;padding:6px 8px;resize:vertical;margin-bottom:8px;box-sizing:border-box";

        const row = contentEl.createEl("div");
        row.style.cssText = "display:flex;justify-content:flex-end;margin-bottom:12px";
        const btn = row.createEl("button", { text: "Ask" });

        const out = contentEl.createEl("div");
        out.style.cssText = "max-height:60vh;overflow-y:auto;padding:4px 0";

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
