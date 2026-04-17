// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com
import { describe, it, expect, vi, afterEach } from "vitest";

vi.mock("obsidian", () => ({
    Plugin: class {
        app: any;
        addCommand    = vi.fn();
        addRibbonIcon = vi.fn();
        addSettingTab = vi.fn();
        loadData      = vi.fn().mockResolvedValue({});
        saveData      = vi.fn().mockResolvedValue(undefined);
        constructor(app?: any) { this.app = app; }
    },
    PluginSettingTab: class {
        app: any; plugin: any;
        containerEl = { empty: vi.fn(), createEl: vi.fn().mockReturnValue({ style: {}, setText: vi.fn() }) };
        constructor(app: any, plugin: any) { this.app = app; this.plugin = plugin; }
        display() {}
    },
    Setting: class {
        constructor(_el: any) {}
        setName  = vi.fn().mockReturnThis();
        setDesc  = vi.fn().mockReturnThis();
        addText  = vi.fn().mockReturnThis();
    },
    Modal: class {
        app: any;
        modalEl = { style: {} as CSSStyleDeclaration };
        containerEl = { querySelector: vi.fn().mockReturnValue({ addEventListener: vi.fn() }) };
        contentEl = {
            createEl: vi.fn().mockReturnValue({
                style: {}, onclick: null, disabled: false, setText: vi.fn(), value: "",
            }),
            empty: vi.fn(),
        };
        open = vi.fn(); close = vi.fn();
        constructor(app: any) { this.app = app; }
    },
    SuggestModal: class {
        app: any;
        open = vi.fn();
        setPlaceholder = vi.fn();
        constructor(app: any) { this.app = app; }
    },
    Notice: vi.fn(),
    TFile: class {},
    App: class {},
    MarkdownRenderer: { render: vi.fn().mockResolvedValue(undefined) },
}));

vi.mock("./api", () => ({
    api: {
        ingest: vi.fn(), lint: vi.fn(), lintReport: vi.fn(), status: vi.fn(),
        query: vi.fn(), health: vi.fn(), jobs: vi.fn(),
        retryJob: vi.fn(), purgeJobs: vi.fn(), scaffold: vi.fn(),
        auditHistory: vi.fn(), auditCosts: vi.fn(),
    },
    setBase: vi.fn(),
}));

afterEach(() => vi.clearAllMocks());

describe("SynthadocPlugin.onload", () => {
    it("calls setBase with default serverUrl when no saved settings exist", async () => {
        const { setBase } = await import("./api");
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        expect(setBase).toHaveBeenCalledWith("http://127.0.0.1:7070");
    });

    it("calls setBase with persisted serverUrl from loadData", async () => {
        const { setBase } = await import("./api");
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        (plugin.loadData as any).mockResolvedValueOnce({ serverUrl: "http://127.0.0.1:7071" });
        await plugin.onload();
        expect(setBase).toHaveBeenCalledWith("http://127.0.0.1:7071");
    });
});

describe("SynthadocPlugin ribbon icon", () => {
    it("shows online status and page count when server is running", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.health as any).mockResolvedValueOnce({ status: "ok" });
        (api.status as any).mockResolvedValueOnce({ pages: 12 });

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const ribbonCallback = (plugin.addRibbonIcon as any).mock.calls[0][2];
        await ribbonCallback();

        expect(Notice).toHaveBeenCalledWith(expect.stringMatching(/✅ online/));
        expect(Notice).toHaveBeenCalledWith(expect.stringMatching(/12 pages/));
    });

    it("shows offline status when server is not running", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.health as any).mockRejectedValueOnce(new Error("refused"));
        (api.status as any).mockRejectedValueOnce(new Error("refused"));

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const ribbonCallback = (plugin.addRibbonIcon as any).mock.calls[0][2];
        await ribbonCallback();

        expect(Notice).toHaveBeenCalledWith(expect.stringMatching(/❌ offline/));
    });
});

describe("SynthadocPlugin ingest-current command", () => {
    it("opens IngestPickerModal when no file is active (does not ingest directly)", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        plugin.app = { workspace: { getActiveFile: () => null }, vault: { getFiles: () => [] } } as any;
        await plugin.onload();

        const cmd = (plugin.addCommand as any).mock.calls.find(
            (c: any) => c[0].id === "synthadoc-ingest-current"
        )?.[0];
        cmd?.callback();

        // Picker opened — no direct ingest call and no error notice
        expect(api.ingest).not.toHaveBeenCalled();
        expect(Notice).not.toHaveBeenCalled();
    });

    it("calls ingestFile directly when a file is active", async () => {
        const { api } = await import("./api");
        (api.ingest as any).mockResolvedValueOnce({ job_id: "job-abc" });

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        const fakeFile = { path: "raw_sources/paper.pdf" };
        plugin.app = { workspace: { getActiveFile: () => fakeFile } } as any;
        await plugin.onload();

        const cmd = (plugin.addCommand as any).mock.calls.find(
            (c: any) => c[0].id === "synthadoc-ingest-current"
        )?.[0];
        await cmd?.callback();

        expect(api.ingest).toHaveBeenCalledWith("raw_sources/paper.pdf");
    });
});

describe("SynthadocPlugin.ingestFile", () => {
    it("calls api.ingest with file path and shows Notice with job_id", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.ingest as any).mockResolvedValueOnce({ job_id: "job-xyz" });

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.ingestFile({ path: "notes/paper.md" } as any);

        expect(api.ingest).toHaveBeenCalledWith("notes/paper.md");
        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("job-xyz"));
    });

    it("shows error Notice when api.ingest throws", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.ingest as any).mockRejectedValueOnce(new Error("connection refused"));

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.ingestFile({ path: "notes/paper.md" } as any);

        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("failed"));
    });
});

describe("SynthadocPlugin web search command", () => {
    it("opens WebSearchModal — no longer shows coming-in-v2 notice", async () => {
        const { Notice } = await import("obsidian");

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const cmd = (plugin.addCommand as any).mock.calls.find(
            (c: any) => c[0].id === "synthadoc-web-search"
        )?.[0];
        // Invoking the callback should not throw and must not show the old stub notice
        cmd?.callback();

        expect(Notice).not.toHaveBeenCalledWith(expect.stringContaining("coming in v2"));
    });

    it("web-search command is registered on onload", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        expect(ids).toContain("synthadoc-web-search");
    });
});

describe("SynthadocPlugin.ingestAllSources", () => {
    it("queues every file under rawSourcesFolder and shows summary", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.ingest as any).mockResolvedValue({ job_id: "job-1" });

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        plugin.app = {
            vault: {
                getFiles: () => [
                    { path: "raw_sources/file-a.pdf", extension: "pdf" },
                    { path: "raw_sources/file-b.png", extension: "png" },
                    { path: "wiki/page.md",           extension: "md"  },  // excluded (wrong folder)
                    { path: "raw_sources/script.py",  extension: "py"  },  // excluded (unsupported)
                ],
            },
        } as any;
        await plugin.ingestAllSources();

        expect(api.ingest).toHaveBeenCalledTimes(2);
        expect(api.ingest).toHaveBeenCalledWith("raw_sources/file-a.pdf");
        expect(api.ingest).toHaveBeenCalledWith("raw_sources/file-b.png");
        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("2 job(s) queued"));
    });

    it("shows warning when no files found in folder", async () => {
        const { Notice } = await import("obsidian");

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        plugin.app = {
            vault: { getFiles: () => [{ path: "wiki/page.md", extension: "md" }] },
        } as any;
        await plugin.ingestAllSources();

        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("no files found"));
    });

    it("reports partial failures", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.ingest as any)
            .mockResolvedValueOnce({ job_id: "job-1" })
            .mockRejectedValueOnce(new Error("timeout"));

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        plugin.app = {
            vault: {
                getFiles: () => [
                    { path: "raw_sources/ok.pdf",  extension: "pdf" },
                    { path: "raw_sources/bad.pdf", extension: "pdf" },
                ],
            },
        } as any;
        await plugin.ingestAllSources();

        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("1 queued, 1 failed"));
    });
});

describe("SynthadocPlugin command registration", () => {
    it("registers all 14 expected command IDs on onload", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        const expected = [
            "synthadoc-ingest-current",
            "synthadoc-ingest-all",
            "synthadoc-query",
            "synthadoc-jobs",
            "synthadoc-lint-report",
            "synthadoc-ingest-url",
            "synthadoc-web-search",
            "synthadoc-lint",
            "synthadoc-lint-auto-resolve",
            "synthadoc-jobs-retry-dead",
            "synthadoc-jobs-purge",
            "synthadoc-scaffold",
            "synthadoc-audit-history",
            "synthadoc-audit-costs",
        ];
        for (const id of expected) {
            expect(ids).toContain(id);
        }
    });

    it("command names use group prefixes for palette sorting", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const names: string[] = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].name);
        expect(names.some(n => n.startsWith("Ingest:"))).toBe(true);
        expect(names.some(n => n.startsWith("Query:"))).toBe(true);
        expect(names.some(n => n.startsWith("Lint:"))).toBe(true);
        expect(names.some(n => n.startsWith("Jobs:"))).toBe(true);
        expect(names.some(n => n.startsWith("Wiki:"))).toBe(true);
        expect(names.some(n => n.startsWith("Audit:"))).toBe(true);
    });
});

describe("SynthadocPlugin lint commands", () => {
    it("Run lint calls api.lint without auto-resolve", async () => {
        const { api } = await import("./api");
        (api.lint as any).mockResolvedValueOnce({ contradictions_found: 1, orphans: [] });

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const cmd = (plugin.addCommand as any).mock.calls.find(
            (c: any) => c[0].id === "synthadoc-lint"
        );
        await cmd[0].callback();

        expect(api.lint).toHaveBeenCalledWith();
    });

    it("Run lint with auto-resolve calls api.lint with autoResolve=true", async () => {
        const { api } = await import("./api");
        (api.lint as any).mockResolvedValueOnce({ contradictions_found: 0, orphans: [] });

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const cmd = (plugin.addCommand as any).mock.calls.find(
            (c: any) => c[0].id === "synthadoc-lint-auto-resolve"
        );
        await cmd[0].callback();

        expect(api.lint).toHaveBeenCalledWith("all", true);
    });
});

describe("SynthadocPlugin new commands registered", () => {
    it("retry-dead command is registered", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        expect(ids).toContain("synthadoc-jobs-retry-dead");
    });

    it("purge command is registered", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        expect(ids).toContain("synthadoc-jobs-purge");
    });

    it("scaffold command is registered", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        expect(ids).toContain("synthadoc-scaffold");
    });

    it("audit-history command is registered", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        expect(ids).toContain("synthadoc-audit-history");
    });

    it("audit-costs command is registered", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        expect(ids).toContain("synthadoc-audit-costs");
    });
});
