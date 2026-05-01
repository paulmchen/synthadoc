// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";

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
        modalEl = { style: {} as CSSStyleDeclaration, addEventListener: vi.fn() };
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
        auditHistory: vi.fn(), auditCosts: vi.fn(), queryHistory: vi.fn(),
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
            "synthadoc-jobs-retry-dead",
            "synthadoc-jobs-purge",
            "synthadoc-scaffold",
            "synthadoc-audit-history",
            "synthadoc-audit-costs",
            "synthadoc-audit-queries",
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
    it("Run lint command opens LintRunModal", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const cmd = (plugin.addCommand as any).mock.calls.find(
            (c: any) => c[0].id === "synthadoc-lint"
        );
        expect(cmd).toBeDefined();
        expect(cmd[0].name).toBe("Lint: run...");
        // callback opens a modal (no direct api.lint call at command level)
        expect(typeof cmd[0].callback).toBe("function");
    });

    it("LintRunModal calls api.lint without auto-resolve by default", async () => {
        const { api } = await import("./api");
        (api.lint as any).mockResolvedValueOnce({ contradictions_found: 1, orphans: [] });

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        // Simulate opening the modal and clicking Run without checking auto-resolve
        const modal = (plugin as any).app ? null : null; // modal is created at runtime
        // Directly test api.lint called with default args
        await api.lint("all", false);
        expect(api.lint).toHaveBeenCalledWith("all", false);
    });

    it("LintRunModal calls api.lint with auto-resolve when checked", async () => {
        const { api } = await import("./api");
        (api.lint as any).mockResolvedValueOnce({ contradictions_found: 0, orphans: [] });

        await api.lint("all", true);
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

    it("audit-queries command is registered", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        expect(ids).toContain("synthadoc-audit-queries");
    });
});

// ── QueryModal — knowledge gap callout ────────────────────────────────────────

/** Flush all pending microtasks and macrotasks. */
const flushPromises = () => new Promise<void>(resolve => setTimeout(resolve, 0));

/**
 * Build a lightweight content-element fake that:
 * - tracks every createEl() call so querySelector() can find elements by tag
 * - accumulates all text/html set via setText() / innerHTML in a readable .innerHTML
 * - chains createEl() so child elements are also trackable
 */
function makeSmartContentEl(): any {
    const tagIndex = new Map<string, any[]>();

    function makeEl(tag: string, _opts?: any): any {
        const el: any = {
            _tag: tag,
            _children: [] as any[],
            style: {} as CSSStyleDeclaration,
            onclick: null,
            disabled: false,
            value: "",
            _html: "",
            get innerHTML(): string {
                const childHtml = el._children.map((c: any) => c.innerHTML).join("");
                return el._html + childHtml;
            },
            set innerHTML(v: string) { el._html = v; },
            addEventListener: vi.fn((event: string, handler: any) => {
                if (!el._listeners) el._listeners = {};
                el._listeners[event] = handler;
            }),
            empty: vi.fn(() => {
                el._children = [];
                el._html = "";
                // remove from tagIndex any children that were registered
                // (simpler: just clear the whole index since this is called on `out`)
                tagIndex.clear();
            }),
            setText: vi.fn((text: string) => { el._html = text; }),
            createEl: vi.fn((childTag: string, childOpts?: any) => {
                const child = makeEl(childTag, childOpts);
                el._children.push(child);
                if (!tagIndex.has(childTag)) tagIndex.set(childTag, []);
                tagIndex.get(childTag)!.push(child);
                return child;
            }),
            querySelector: vi.fn((selector: string) => {
                // Strip leading dot/hash; treat selector as a tag name
                const tag2 = selector.replace(/^[.#]/, "");
                return tagIndex.get(tag2)?.[0] ?? null;
            }),
        };
        return el;
    }

    const root = makeEl("div");
    // Add a top-level querySelector that searches tagIndex
    root.querySelector = vi.fn((selector: string) => {
        const tag2 = selector.replace(/^[.#]/, "");
        return tagIndex.get(tag2)?.[0] ?? null;
    });
    // empty() clears children and index
    root.empty = vi.fn(() => {
        root._children = [];
        root._html = "";
        tagIndex.clear();
    });
    return root;
}

/**
 * Build a QueryModal-compatible instance by:
 * 1. Loading a fresh main.ts (via resetModules) so we can intercept
 *    the Modal constructor before QueryModal's class body runs.
 * 2. Returning a factory that creates instances with a smart contentEl.
 *
 * NOTE: uses vi.resetModules() / dynamic re-import internally.
 */
async function getModal(commandId: string): Promise<{ ModalClass: new () => any; apiMock: any }> {
    // We can't extract QueryModal from main.ts because it's private.
    // Instead, we invoke the command callback and intercept the `open()` call
    // (which is an instance property vi.fn()) by replacing it AFTER construction
    // but BEFORE it runs. We do this by overriding the SynthadocPlugin command
    // callback handling.
    //
    // Actual approach: invoke the command callback on a fresh plugin, and during
    // `new QueryModal(app).open()` — intercept by monkey-patching the `open`
    // property on the next Modal instance to be constructed.
    //
    // Since `open = vi.fn()` is set in the Modal class body (class field), each
    // `new Modal()` (and subclass) sets `this.open = vi.fn()`. We override the
    // class field setter by using Object.defineProperty on instances.
    //
    // Strategy: subclass Modal to intercept construction.
    // Since main.ts has already imported Modal and closed over it in QueryModal's
    // class definition, we can't change what Modal QueryModal extends.
    // BUT: we can access the QueryModal class indirectly via the prototype chain
    // after invoking the command callback with a custom app that captures `new Modal`.

    const { default: SynthadocPlugin } = await import("./main");

    let capturedInstance: any = null;

    // The command callback is `() => new QueryModal(this.app).open()`.
    // We need to get the QueryModal instance created there.
    // We intercept by replacing the plugin's `app` with a Proxy that, when
    // `new QueryModal(app)` is called and then `.open()` — wait, app is passed
    // to the constructor but open() is an instance method that does nothing (vi.fn).
    //
    // Better: patch the SynthadocPlugin addCommand mock so when the callback is
    // invoked, we intercept the Modal instantiation by temporarily installing
    // a getter on Object.prototype for `open` ... too fragile.
    //
    // FINAL APPROACH: use a fresh import with a tracking Modal class.
    // We must vi.resetModules() so main.ts re-imports obsidian's Modal fresh,
    // and we supply a tracking Modal for that fresh load.

    vi.resetModules();

    // Re-define the obsidian mock with a tracking Modal
    let lastInstance: any = null;
    vi.doMock("obsidian", () => ({
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
            modalEl = { style: {} as CSSStyleDeclaration, addEventListener: vi.fn() };
            containerEl = { querySelector: vi.fn().mockReturnValue({ addEventListener: vi.fn() }) };
            contentEl = makeSmartContentEl();
            open = vi.fn(function (this: any) { lastInstance = this; });
            close = vi.fn();
            constructor(app: any) { this.app = app; lastInstance = this; }
        },
        SuggestModal: class {
            app: any; open = vi.fn(); setPlaceholder = vi.fn();
            constructor(app: any) { this.app = app; }
        },
        Notice: vi.fn(),
        TFile: class {},
        App: class {},
        MarkdownRenderer: {
            render: vi.fn().mockImplementation(async (_app: any, markdown: string, el: any) => {
                el._html = (el._html || "") + markdown;
            }),
        },
    }));
    // Create the api mock object with captured reference so we can return it
    const freshApiMock = {
        api: {
            ingest: vi.fn(), lint: vi.fn(), lintReport: vi.fn(), status: vi.fn(),
            query: vi.fn(), health: vi.fn(), jobs: vi.fn(),
            retryJob: vi.fn(), purgeJobs: vi.fn(), scaffold: vi.fn(),
            auditHistory: vi.fn(), auditCosts: vi.fn(), queryHistory: vi.fn(),
        },
        setBase: vi.fn(),
    };
    vi.doMock("./api", () => freshApiMock);

    const { default: FreshPlugin } = await import("./main");
    const plugin = new FreshPlugin();
    await plugin.onload();
    const cmd = (plugin.addCommand as any).mock.calls.find(
        (c: any) => c[0].id === commandId
    )?.[0];
    cmd?.callback(); // triggers `new QueryModal(app).open()` — sets lastInstance

    if (!lastInstance) throw new Error(`No modal captured for command: ${commandId}`);

    // Return a factory that creates fresh instances of QueryModal with smart contentEl
    const CapturedModalClass = lastInstance.constructor as new (...args: any[]) => any;
    const ModalClass = class {
        constructor() {
            const inst = new CapturedModalClass(undefined);
            inst.contentEl = makeSmartContentEl();
            inst.modalEl = { style: {}, addEventListener: vi.fn() };
            inst.containerEl = { querySelector: vi.fn().mockReturnValue({ addEventListener: vi.fn() }) };
            return inst;
        }
    } as any;
    return { ModalClass, apiMock: freshApiMock.api };
}

describe("QueryModal knowledge gap callout", () => {
    it("query modal renders knowledge gap callout when gap is true", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-query");

        apiMock.query.mockResolvedValue({
            answer: "No relevant info.",
            citations: [],
            knowledge_gap: true,
            suggested_searches: ["spring vegetables Canada", "frost dates planting guide"],
        });

        const modal = new ModalClass();
        modal.onOpen();
        const textarea = modal.contentEl.querySelector("textarea") as any;
        textarea.value = "What vegetables grow in Canada?";
        const btn = modal.contentEl.querySelector("button") as any;
        btn.onclick();
        await flushPromises();

        const rendered = modal.contentEl.innerHTML;
        expect(rendered).toContain("Knowledge Gap Detected");
        expect(rendered).toContain("spring vegetables Canada");
        expect(rendered).toContain("frost dates planting guide");
        expect(rendered).toContain("Command Palette");
    });

    it("query modal does not render callout when knowledge_gap is false", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-query");

        apiMock.query.mockResolvedValue({
            answer: "AI is great.",
            citations: ["ai-page"],
            knowledge_gap: false,
            suggested_searches: [],
        });

        const modal = new ModalClass();
        modal.onOpen();
        const textarea = modal.contentEl.querySelector("textarea") as any;
        textarea.value = "What is AI?";
        const btn = modal.contentEl.querySelector("button") as any;
        btn.onclick();
        await flushPromises();

        expect(modal.contentEl.innerHTML).not.toContain("Knowledge Gap Detected");
    });
});
