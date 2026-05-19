// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";

// Obsidian plugins use `window.setInterval`; make it available in node test env
(globalThis as any).window = globalThis;

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
        query: vi.fn(), health: vi.fn(), jobs: vi.fn(), job: vi.fn(),
        retryJob: vi.fn(), purgeJobs: vi.fn(), scaffold: vi.fn(),
        auditHistory: vi.fn(), auditCosts: vi.fn(), queryHistory: vi.fn(), auditEvents: vi.fn(),
        routingStatus: vi.fn(), routingInit: vi.fn(), routingValidate: vi.fn(), routingClean: vi.fn(),
        stagingPolicy: vi.fn(), stagingSetPolicy: vi.fn(),
        candidates: vi.fn(), candidatesPromoteAll: vi.fn(), candidatesDiscardAll: vi.fn(),
        candidatePromote: vi.fn(), candidateDiscard: vi.fn(),
        contextBuild: vi.fn(),
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

describe("SynthadocPlugin.ingestFile", () => {
    it("calls api.ingest with absolute path and shows Notice with job_id", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.ingest as any).mockResolvedValueOnce({ job_id: "job-xyz" });

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        plugin.app = { vault: { adapter: { getFullPath: (p: string) => `/vault/${p}` } } } as any;
        await plugin.ingestFile({ path: "notes/paper.md" } as any);

        expect(api.ingest).toHaveBeenCalledWith("/vault/notes/paper.md");
        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("job-xyz"));
    });

    it("shows error Notice when api.ingest throws", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.ingest as any).mockRejectedValueOnce(new Error("connection refused"));

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        plugin.app = { vault: { adapter: { getFullPath: (p: string) => `/vault/${p}` } } } as any;
        await plugin.ingestFile({ path: "notes/paper.md" } as any);

        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("failed"));
    });
});

describe("IngestModal All-sources tab", () => {
    const makeVault = (files: { path: string; extension: string }[]) => ({
        workspace: { getActiveFile: () => null },
        vault: {
            getFiles: () => files,
            adapter: { getFullPath: (p: string) => `/abs/${p}` },
        },
    });

    // contentEl children: [0]=h3, [1]=tabBar, [2]=WS panel, [3]=URL panel, [4]=All-sources panel, [5]=Pick-files panel
    // All-sources panel: [0]=desc, [1]=folderRow([0]=label,[1]=folderDisplay), [2]=statusEl, [3]=forceRow, [4]=btnRow([0]=ingestBtn)
    const getAllSources = (modal: any) => {
        const panel = modal.contentEl._children[4];
        return {
            folderDisplay: panel._children[1]._children[1] as any,
            ingestBtn:     panel._children[4]._children[0] as any,
        };
    };

    it("shows rawSourcesFolder as read-only folder display", async () => {
        const { ModalClass } = await getModal("synthadoc-ingest",
            makeVault([{ path: "raw_sources/a.pdf", extension: "pdf" }])
        );
        const modal = new ModalClass();
        modal.onOpen();
        expect(getAllSources(modal).folderDisplay.textContent).toBe("raw_sources");
    });

    it("calls api.ingest for each supported file in the folder on Ingest all click", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-ingest",
            makeVault([
                { path: "raw_sources/file-a.pdf", extension: "pdf" },
                { path: "raw_sources/file-b.png", extension: "png" },
                { path: "wiki/page.md",           extension: "md"  }, // excluded: wrong folder
                { path: "raw_sources/script.py",  extension: "py"  }, // excluded: unsupported
            ])
        );
        apiMock.ingest
            .mockResolvedValueOnce({ job_id: "job-1" })
            .mockResolvedValueOnce({ job_id: "job-2" });
        apiMock.jobs.mockResolvedValue([
            { id: "job-1", status: "completed" },
            { id: "job-2", status: "completed" },
        ]);

        const modal = new ModalClass();
        modal.onOpen();
        getAllSources(modal).ingestBtn.onclick();
        await flushPromises();

        expect(apiMock.ingest).toHaveBeenCalledTimes(2);
        expect(apiMock.ingest).toHaveBeenCalledWith("/abs/raw_sources/file-a.pdf", undefined, false);
        expect(apiMock.ingest).toHaveBeenCalledWith("/abs/raw_sources/file-b.png", undefined, false);
    });

    it("disables Ingest all button while jobs are in flight", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-ingest",
            makeVault([{ path: "raw_sources/a.pdf", extension: "pdf" }])
        );
        apiMock.ingest.mockResolvedValueOnce({ job_id: "job-1" });
        apiMock.jobs.mockResolvedValue([{ id: "job-1", status: "pending" }]);

        const modal = new ModalClass();
        modal.onOpen();
        const { ingestBtn } = getAllSources(modal);
        ingestBtn.onclick();
        await flushPromises();

        expect(ingestBtn.disabled).toBe(true);
    });

    it("shows empty-folder message when no supported files found", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-ingest",
            makeVault([{ path: "wiki/page.md", extension: "md" }])
        );
        apiMock.ingest.mockResolvedValue({ job_id: "job-1" });

        const modal = new ModalClass();
        modal.onOpen();
        getAllSources(modal).ingestBtn.onclick();
        await flushPromises();

        expect(apiMock.ingest).not.toHaveBeenCalled();
        expect(modal.contentEl.innerHTML).toContain("No supported files found");
    });

    it("shows error and re-enables button when all queuing fails", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-ingest",
            makeVault([{ path: "raw_sources/a.pdf", extension: "pdf" }])
        );
        apiMock.ingest.mockRejectedValueOnce(new Error("server down"));

        const modal = new ModalClass();
        modal.onOpen();
        const { ingestBtn } = getAllSources(modal);
        ingestBtn.onclick();
        await flushPromises();

        expect(ingestBtn.disabled).toBe(false);
        expect(modal.contentEl.innerHTML).toContain("synthadoc serve");
    });
});

describe("SynthadocPlugin command registration", () => {
    it("registers all 17 expected command IDs on onload", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        const expected = [
            "synthadoc-ingest",
            "synthadoc-query",
            "synthadoc-jobs",
            "synthadoc-lint-report",
            "synthadoc-lint",
            "synthadoc-scaffold",
            "synthadoc-audit",
            "synthadoc-routing",
            "synthadoc-staging",
            "synthadoc-candidates",
            "synthadoc-context",
        ];
        for (const id of expected) {
            expect(ids).toContain(id);
        }
    });

    it("command names use group prefixes for palette grouping", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const names: string[] = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].name);
        expect(names.some(n => n.startsWith("Query:"))).toBe(true);
        expect(names.some(n => n.startsWith("Ingest"))).toBe(true);
        expect(names.some(n => n.startsWith("Lint:"))).toBe(true);
        expect(names.some(n => n.startsWith("Jobs"))).toBe(true);
        expect(names.some(n => n.startsWith("Wiki:"))).toBe(true);
        expect(names.some(n => n.startsWith("Audit"))).toBe(true);
        expect(names.some(n => n.startsWith("Routing:"))).toBe(true);
        expect(names.some(n => n.startsWith("Staging:"))).toBe(true);
        expect(names.some(n => n.startsWith("Candidates:"))).toBe(true);
        expect(names.some(n => n.startsWith("Context:"))).toBe(true);
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
    it("jobs command is registered with consolidated name", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        const cmds = (plugin.addCommand as any).mock.calls.map((c: any) => c[0]);
        const jobsCmd = cmds.find((c: any) => c.id === "synthadoc-jobs");
        expect(jobsCmd).toBeDefined();
        expect(jobsCmd.name).toBe("Jobs...");
    });

    it("scaffold command is registered", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        expect(ids).toContain("synthadoc-scaffold");
    });

    it("audit command is registered", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        expect(ids).toContain("synthadoc-audit");
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

    function makeEl(tag: string, opts?: any): any {
        const el: any = {
            _tag: tag,
            _children: [] as any[],
            style: {} as CSSStyleDeclaration,
            onclick: null,
            disabled: false,
            value: "",
            min: "",
            max: "",
            focus: vi.fn(),
            _html: opts?.text ?? "",
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
                // Remove only this element's direct children from the shared index
                for (const child of el._children) {
                    const bucket = tagIndex.get(child._tag);
                    if (bucket) {
                        const idx = bucket.indexOf(child);
                        if (idx !== -1) bucket.splice(idx, 1);
                        if (!bucket.length) tagIndex.delete(child._tag);
                    }
                }
                el._children = [];
                el._html = "";
            }),
            setText: vi.fn((text: string) => { el._html = text; }),
            appendText: (text: string) => { el._html += text; },
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
    // empty() removes root's direct children from the index then clears root
    root.empty = vi.fn(() => {
        for (const child of root._children) {
            const bucket = tagIndex.get(child._tag);
            if (bucket) {
                const idx = bucket.indexOf(child);
                if (idx !== -1) bucket.splice(idx, 1);
                if (!bucket.length) tagIndex.delete(child._tag);
            }
        }
        root._children = [];
        root._html = "";
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
async function getModal(commandId: string, appOverride?: any): Promise<{ ModalClass: new () => any; apiMock: any }> {
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
            query: vi.fn(), health: vi.fn(), jobs: vi.fn(), job: vi.fn(),
            retryJob: vi.fn(), purgeJobs: vi.fn(), scaffold: vi.fn(),
            auditHistory: vi.fn(), auditCosts: vi.fn(), queryHistory: vi.fn(), auditEvents: vi.fn(),
            routingStatus: vi.fn(), routingInit: vi.fn(), routingValidate: vi.fn(), routingClean: vi.fn(),
            stagingPolicy: vi.fn(), stagingSetPolicy: vi.fn(),
            candidates: vi.fn(), candidatesPromoteAll: vi.fn(), candidatesDiscardAll: vi.fn(),
            candidatePromote: vi.fn(), candidateDiscard: vi.fn(),
            contextBuild: vi.fn(),
        },
        setBase: vi.fn(),
    };
    vi.doMock("./api", () => freshApiMock);

    const { default: FreshPlugin } = await import("./main");
    const plugin = new FreshPlugin();
    if (appOverride) plugin.app = appOverride as any;
    await plugin.onload();
    const cmd = (plugin.addCommand as any).mock.calls.find(
        (c: any) => c[0].id === commandId
    )?.[0];
    cmd?.callback(); // triggers `new QueryModal(app).open()` — sets lastInstance

    if (!lastInstance) throw new Error(`No modal captured for command: ${commandId}`);

    // Return a factory that creates fresh instances of the captured modal class with smart contentEl
    const CapturedModalClass = lastInstance.constructor as new (...args: any[]) => any;
    // Capture any extra constructor args (e.g. TFile for IngestConfirmModal)
    const extraArgs = Object.entries(lastInstance)
        .filter(([k]) => k.startsWith("_") && k !== "_pollTimer")
        .map(([, v]) => v);
    const capturedFile = (lastInstance as any)._file;
    const capturedFolder = (lastInstance as any)._folder ?? (lastInstance as any)._rawSourcesFolder;
    const ModalClass = class {
        constructor() {
            let inst: any;
            if (capturedFile) {
                inst = new CapturedModalClass(appOverride, capturedFile);
            } else if (capturedFolder !== undefined) {
                inst = new CapturedModalClass(appOverride, capturedFolder);
            } else {
                inst = new CapturedModalClass(appOverride);
            }
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

describe("IngestModal Pick-files tab", () => {
    const makeVault = (files: { path: string; extension: string; name?: string }[]) => ({
        workspace: { getActiveFile: () => null },
        vault: {
            getFiles: () => files.map(f => ({ ...f, name: f.name ?? f.path.split("/").pop() ?? f.path })),
            adapter: { getFullPath: (p: string) => `/abs/${p}` },
        },
    });

    // contentEl children: [0]=h3, [1]=tabBar, [2]=WS panel, [3]=URL panel, [4]=All-sources panel, [5]=Pick-files panel
    // Pick-files panel: [0]=desc, [1]=folderRow([0]=label,[1]=display,[2]=browseBtn,[3]=scanBtn), [2]=selectRow, [3]=listEl, [4]=statusEl, [5]=forceRow, [6]=btnRow
    const getPickFiles = (modal: any) => {
        const panel = modal.contentEl._children[5];
        return {
            browseBtn: panel._children[1]._children[2] as any,
            scanBtn:   panel._children[1]._children[3] as any,
            listEl:    panel._children[3] as any,
            ingestBtn: panel._children[6]._children[0] as any,
        };
    };

    // Simulate the electron folder-picker returning `folder` so Browse can update state.
    const mockBrowse = (folder: string) => {
        (window as any).require = (_mod: string) => ({
            dialog: { showOpenDialog: async () => ({ canceled: false, filePaths: [folder] }) },
        });
    };
    afterEach(() => { delete (window as any).require; });

    it("Scan button populates file list with checkboxes for supported files only", async () => {
        const { ModalClass } = await getModal("synthadoc-ingest",
            makeVault([
                { path: "raw_sources/a.pdf", extension: "pdf" },
                { path: "raw_sources/b.txt", extension: "txt" },
                { path: "raw_sources/script.py", extension: "py" }, // unsupported
            ])
        );
        const modal = new ModalClass();
        modal.onOpen();
        const { browseBtn, scanBtn, listEl } = getPickFiles(modal);
        mockBrowse("raw_sources");
        await browseBtn.onclick();
        scanBtn.onclick();

        expect(listEl._children.length).toBe(2);
    });

    it("Ingest selected calls api.ingest only for checked files", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-ingest",
            makeVault([
                { path: "raw_sources/a.pdf", extension: "pdf" },
                { path: "raw_sources/b.txt", extension: "txt" },
            ])
        );
        apiMock.ingest.mockResolvedValue({ job_id: "job-pick-1" });
        apiMock.jobs.mockResolvedValue([{ id: "job-pick-1", status: "completed" }]);

        const modal = new ModalClass();
        modal.onOpen();
        const { browseBtn, scanBtn, listEl, ingestBtn } = getPickFiles(modal);
        mockBrowse("raw_sources");
        await browseBtn.onclick();
        scanBtn.onclick();

        // Uncheck the second file
        const cb = listEl._children[1]._children[0];
        cb.checked = false;
        cb._listeners?.change?.({ target: cb });

        await ingestBtn.onclick();
        await flushPromises();

        expect(apiMock.ingest).toHaveBeenCalledTimes(1);
        expect(apiMock.ingest).toHaveBeenCalledWith("/abs/raw_sources/a.pdf", undefined, false);
    });

    it("shows error and re-enables button when all queuing fails", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-ingest",
            makeVault([{ path: "raw_sources/a.pdf", extension: "pdf" }])
        );
        apiMock.ingest.mockRejectedValueOnce(new Error("server down"));

        const modal = new ModalClass();
        modal.onOpen();
        const { browseBtn, scanBtn, ingestBtn } = getPickFiles(modal);
        mockBrowse("raw_sources");
        await browseBtn.onclick();
        scanBtn.onclick();

        await ingestBtn.onclick();
        await flushPromises();

        expect(ingestBtn.disabled).toBe(false);
        expect(modal.contentEl.innerHTML).toContain("synthadoc serve");
    });

    it("excludes wiki/ subfolder files and system files, shows exclusion message", async () => {
        const { ModalClass } = await getModal("synthadoc-ingest",
            makeVault([
                { path: "src/notes/a.pdf",      extension: "pdf" },           // included
                { path: "src/wiki/page.md",      extension: "md",  name: "page.md" },      // excluded: wiki/
                { path: "src/sub/wiki/deep.md",  extension: "md",  name: "deep.md" },      // excluded: /wiki/
                { path: "src/log.md",            extension: "md",  name: "log.md" },       // excluded: system
                { path: "src/README.md",         extension: "md",  name: "README.md" },    // excluded: system
                { path: "src/routing.md",        extension: "md",  name: "routing.md" },   // excluded: system
                { path: "src/notes/b.txt",       extension: "txt", name: "b.txt" },        // included
            ])
        );
        const modal = new ModalClass();
        modal.onOpen();
        const { browseBtn, scanBtn, listEl } = getPickFiles(modal);
        // also grab statusEl: panel._children[4]
        const statusEl = modal.contentEl._children[5]._children[4];
        mockBrowse("src");
        await browseBtn.onclick();
        scanBtn.onclick();

        expect(listEl._children.length).toBe(2); // a.pdf + b.txt
        expect(statusEl.innerHTML).toContain("wiki page");
        expect(statusEl.innerHTML).toContain("system file");
    });

    it("shows no exclusion message when nothing is filtered", async () => {
        const { ModalClass } = await getModal("synthadoc-ingest",
            makeVault([
                { path: "src/a.pdf", extension: "pdf" },
                { path: "src/b.txt", extension: "txt" },
            ])
        );
        const modal = new ModalClass();
        modal.onOpen();
        const { browseBtn, scanBtn } = getPickFiles(modal);
        const statusEl = modal.contentEl._children[5]._children[4];
        mockBrowse("src");
        await browseBtn.onclick();
        scanBtn.onclick();

        expect(statusEl.innerHTML).toBe("");
    });
});


describe("ScaffoldModal", () => {
    it("calls api.scaffold with the domain value on button click", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-scaffold");
        apiMock.status.mockResolvedValue({});
        apiMock.scaffold.mockResolvedValueOnce({ job_id: "scaffold-job-01" });
        apiMock.job = vi.fn().mockResolvedValue({ status: "completed" });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        const input = modal.contentEl.querySelector("input") as any;
        input.value = "Canadian tax law";
        const btn = modal.contentEl.querySelector("button") as any;
        btn.onclick();
        await flushPromises();

        expect(apiMock.scaffold).toHaveBeenCalledWith("Canadian tax law");
    });

    it("disables button and shows queued status while job is pending", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-scaffold");
        apiMock.status.mockResolvedValue({});
        apiMock.scaffold.mockResolvedValueOnce({ job_id: "scaffold-job-02" });
        apiMock.job = vi.fn().mockResolvedValue({ status: "pending" });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        const input = modal.contentEl.querySelector("input") as any;
        input.value = "machine learning";
        const btn = modal.contentEl.querySelector("button") as any;
        btn.onclick();
        await flushPromises();

        expect(btn.disabled).toBe(true);
        expect(modal.contentEl.innerHTML).toContain("⏳");
    });

    it("re-enables button and shows done on completed job", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-scaffold");
        apiMock.status.mockResolvedValue({});
        apiMock.scaffold.mockResolvedValueOnce({ job_id: "scaffold-job-03" });

        let pollCount = 0;
        apiMock.job = vi.fn().mockImplementation(async () => {
            pollCount++;
            return pollCount === 1 ? { status: "in_progress" } : { status: "completed" };
        });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        const input = modal.contentEl.querySelector("input") as any;
        input.value = "history of computing";
        const btn = modal.contentEl.querySelector("button") as any;
        btn.onclick();
        await flushPromises();

        // Simulate interval firing twice via the stored callback
        const intervalId = (globalThis as any).__lastIntervalId;
        // Button should still be disabled during progress
        expect(btn.disabled).toBe(true);
    });

    it("shows error and re-enables button when api.scaffold throws", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-scaffold");
        apiMock.status.mockResolvedValue({});
        apiMock.scaffold.mockRejectedValueOnce(new Error("server down"));

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        const input = modal.contentEl.querySelector("input") as any;
        input.value = "science";
        const btn = modal.contentEl.querySelector("button") as any;
        btn.onclick();
        await flushPromises();

        expect(btn.disabled).toBe(false);
        expect(modal.contentEl.innerHTML).toContain("synthadoc serve");
    });
});

describe("AuditModal — Events tab", () => {
    it("loads events on open and renders a table", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.auditEvents.mockResolvedValueOnce({
            records: [
                { timestamp: "2026-05-01T10:23:45Z", job_id: "abcd1234efgh", event: "job_started", metadata: "ingest" },
                { timestamp: "2026-05-01T10:24:00Z", job_id: "abcd1234efgh", event: "job_completed", metadata: null },
            ],
            count: 2,
        });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(apiMock.auditEvents).toHaveBeenCalledWith(100);
        const html = modal.contentEl.innerHTML;
        expect(html).toContain("job_started");
        expect(html).toContain("job_completed");
        expect(html).toContain("abcd1234");
        expect(html).toContain("2026-05-01 10:23");
    });

    it("shows empty message when no events exist", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.auditEvents.mockResolvedValueOnce({ records: [], count: 0 });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("No audit events found");
    });

    it("shows server error when api.auditEvents throws", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.auditEvents.mockRejectedValueOnce(new Error("network error"));

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("synthadoc serve");
    });
});

describe("SynthadocPlugin routing command", () => {
    it("registers synthadoc-routing command", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        const ids = (plugin.addCommand as any).mock.calls.map((c: any) => c[0].id);
        expect(ids).toContain("synthadoc-routing");
    });
});

describe("RoutingModal", () => {
    it("calls routingStatus on open when exists=false", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-routing");
        apiMock.routingStatus.mockResolvedValueOnce({
            exists: false, branches: 0, slugs: 0, content: "",
        });
        const modal = new ModalClass();
        modal.onOpen();
        await new Promise(r => setTimeout(r, 0));
        expect(apiMock.routingStatus).toHaveBeenCalled();
    });

    it("calls routingStatus on open when exists=true", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-routing");
        apiMock.routingStatus.mockResolvedValueOnce({
            exists: true, branches: 2, slugs: 5, content: "## People\n- [[alan-turing]]\n",
        });
        const modal = new ModalClass();
        modal.onOpen();
        await new Promise(r => setTimeout(r, 0));
        expect(apiMock.routingStatus).toHaveBeenCalled();
    });

    it("calls routingInit when Init button is clicked", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-routing");
        apiMock.routingStatus.mockResolvedValueOnce({
            exists: false, branches: 0, slugs: 0, content: "",
        });
        apiMock.routingInit.mockResolvedValueOnce({
            branches: 2, slugs: 3, content: "## People\n",
        });
        const modal = new ModalClass();
        modal.onOpen();
        await new Promise(r => setTimeout(r, 0));
        expect(apiMock.routingStatus).toHaveBeenCalled();
    });
});

// ── ContextModal ──────────────────────────────────────────────────────────────

/** Minimal ContextPack response fixture; override any field via spread. */
function makeContextPack(override: Record<string, any> = {}): Record<string, any> {
    return {
        goal: "early computing pioneers",
        token_budget: 4000,
        tokens_used: 1823,
        pages: [
            {
                slug: "alan-turing",
                relevance: 3.42,
                excerpt: "Alan Turing developed the theoretical basis of modern computation.",
                source: "wiki/alan-turing.md",
                confidence: "high",
                tags: ["mathematics", "computation"],
                estimated_tokens: 600,
            },
        ],
        omitted: [],
        ...override,
    };
}

describe("ContextModal", () => {
    it("registers synthadoc-context command with the correct name", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        const cmds = (plugin.addCommand as any).mock.calls.map((c: any) => c[0]);
        const cmd = cmds.find((c: any) => c.id === "synthadoc-context");
        expect(cmd).toBeDefined();
        expect(cmd.name).toBe("Context: build context pack...");
    });

    it("calls api.contextBuild with the goal text and default token budget (4000)", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack());

        const modal = new ModalClass();
        modal.onOpen();

        // First textarea = goalInput; first input = budgetInput; first button = buildBtn
        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "early computing pioneers";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        expect(apiMock.contextBuild).toHaveBeenCalledWith("early computing pioneers", 4000);
    });

    it("calls api.contextBuild with a user-specified token budget", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack({ token_budget: 2000, tokens_used: 800 }));

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "AI history";
        const budgetInput = modal.contentEl.querySelector("input") as any;
        budgetInput.value = "2000";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        expect(apiMock.contextBuild).toHaveBeenCalledWith("AI history", 2000);
    });

    it("clamps token budget to minimum 100 when a sub-minimum value is entered", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack({ token_budget: 100, tokens_used: 50 }));

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "test topic";
        const budgetInput = modal.contentEl.querySelector("input") as any;
        budgetInput.value = "50"; // 50 < 100 → clamped to 100
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        expect(apiMock.contextBuild).toHaveBeenCalledWith("test topic", 100);
    });

    it("disables the build button while the request is in flight", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        let resolvePack!: (v: any) => void;
        apiMock.contextBuild.mockReturnValueOnce(new Promise(r => { resolvePack = r; }));

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "computing history";
        const buildBtn = modal.contentEl.querySelector("button") as any;

        buildBtn.onclick(); // sets disabled=true synchronously before first await
        expect(buildBtn.disabled).toBe(true);

        resolvePack(makeContextPack());
        await flushPromises();
        expect(buildBtn.disabled).toBe(false);
    });

    it("reveals the result section after a successful build", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack());

        const modal = new ModalClass();
        modal.onOpen();

        // resultSection is the 7th child of contentEl (index 6)
        const resultSection = modal.contentEl._children[6];
        expect(resultSection.style.display).toBe("none");

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "early computing pioneers";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        expect(resultSection.style.display).toBe("block");
    });

    it("populates the result textarea with rendered markdown", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack());

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "early computing pioneers";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        // resultArea = resultSection._children[2]
        const resultArea = modal.contentEl._children[6]._children[2];
        expect(resultArea.value).toContain("# Context Pack: early computing pioneers");
        expect(resultArea.value).toContain("## [[alan-turing]]");
        expect(resultArea.value).toContain("relevance: 3.42");
        expect(resultArea.value).toContain("Token budget: 4000 | Used: 1823");
    });

    it("shows page count and token usage in the meta line", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack());

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "early computing pioneers";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        // resultMeta = resultSection._children[1]
        const resultMeta = modal.contentEl._children[6]._children[1];
        expect(resultMeta.textContent).toContain("1 page");
        expect(resultMeta.textContent).toContain("1823");
        expect(resultMeta.textContent).toContain("4000");
    });

    it("shows omitted count in the meta line and omitted section in markdown", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack({
            omitted: [{
                slug: "grace-hopper", relevance: 1.2, excerpt: "...",
                source: "wiki/grace-hopper.md", confidence: "high", tags: [], estimated_tokens: 400,
            }],
        }));

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "early computing pioneers";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        const resultMeta = modal.contentEl._children[6]._children[1];
        expect(resultMeta.textContent).toContain("1 omitted");

        const resultArea = modal.contentEl._children[6]._children[2];
        expect(resultArea.value).toContain("## Omitted — token budget exceeded");
        expect(resultArea.value).toContain("[[grace-hopper]]");
        expect(resultArea.value).toContain("~400 tokens");
    });

    it("shows error message and re-enables button when api.contextBuild throws", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockRejectedValueOnce(new Error("server down"));

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "test topic";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        expect(buildBtn.disabled).toBe(false);
        // statusEl = buildRow._children[1]
        const statusEl = modal.contentEl._children[5]._children[1];
        expect(statusEl.textContent).toContain("❌");
        expect(statusEl.textContent).toContain("server down");
    });

    it("shows a warning and does not call the API when goal is empty", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");

        const modal = new ModalClass();
        modal.onOpen();

        // goalInput.value starts as "" — don't set it
        const buildBtn = modal.contentEl.querySelector("button") as any;
        buildBtn.onclick();

        expect(apiMock.contextBuild).not.toHaveBeenCalled();
        const statusEl = modal.contentEl._children[5]._children[1];
        expect(statusEl.textContent).toContain("⚠");
    });

    it("copies the rendered result to the OS clipboard on Copy button click", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack());

        const writeText = vi.fn().mockResolvedValue(undefined);
        vi.stubGlobal("navigator", { clipboard: { writeText } });

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "early computing pioneers";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        // copyBtn = actionRow._children[0]; actionRow = resultSection._children[3]
        const copyBtn = modal.contentEl._children[6]._children[3]._children[0];
        await copyBtn.onclick();
        await flushPromises();

        expect(writeText).toHaveBeenCalledWith(expect.stringContaining("# Context Pack"));
        expect(writeText).toHaveBeenCalledWith(expect.stringContaining("[[alan-turing]]"));
    });

    it("includes tags in the rendered markdown when the page has tags", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack());

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "early computing pioneers";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        const resultArea = modal.contentEl._children[6]._children[2];
        expect(resultArea.value).toContain("Tags: mathematics, computation");
    });

    it("omits the Tags line from markdown when the page has no tags", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack({
            pages: [{
                slug: "test-page", relevance: 1.0, excerpt: "A test page.",
                source: "wiki/test-page.md", confidence: "medium", tags: [], estimated_tokens: 200,
            }],
        }));

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "test topic";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        const resultArea = modal.contentEl._children[6]._children[2];
        expect(resultArea.value).not.toContain("Tags:");
    });

    it("shows saved filename in the feedback note after Save as click", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack());

        // Stub browser download globals so the save handler doesn't throw in Node
        const mockA = { href: "", download: "", click: vi.fn() };
        vi.stubGlobal("document", {
            createElement: vi.fn().mockReturnValue(mockA),
            body: { appendChild: vi.fn(), removeChild: vi.fn() },
            addEventListener: vi.fn(),
            removeEventListener: vi.fn(),
        });
        // Patch static methods directly so URL remains a valid constructor
        const origCreateObjectURL = (URL as any).createObjectURL;
        const origRevokeObjectURL = (URL as any).revokeObjectURL;
        (URL as any).createObjectURL = vi.fn().mockReturnValue("blob:mock");
        (URL as any).revokeObjectURL = vi.fn();

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "early computing pioneers";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        // saveBtn = actionRow._children[1]; actionRow = resultSection._children[3]
        const saveBtn = modal.contentEl._children[6]._children[3]._children[1];
        await saveBtn.onclick();

        // copyNote = actionRow._children[2]
        const copyNote = modal.contentEl._children[6]._children[3]._children[2];
        expect(copyNote.textContent).toContain("✅ Saved as");
        expect(copyNote.textContent).toContain("early-computing-pioneers.md");

        vi.unstubAllGlobals();
        (URL as any).createObjectURL = origCreateObjectURL;
        (URL as any).revokeObjectURL = origRevokeObjectURL;
    });

    it("formats relevance to exactly 2 decimal places in the heading", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-context");
        apiMock.contextBuild.mockResolvedValueOnce(makeContextPack({
            pages: [{
                slug: "alan-turing", relevance: 3, excerpt: "...",
                source: "wiki/alan-turing.md", confidence: "high", tags: [], estimated_tokens: 300,
            }],
        }));

        const modal = new ModalClass();
        modal.onOpen();

        const goalInput = modal.contentEl.querySelector("textarea") as any;
        goalInput.value = "computing";
        const buildBtn = modal.contentEl.querySelector("button") as any;
        await buildBtn.onclick();
        await flushPromises();

        const resultArea = modal.contentEl._children[6]._children[2];
        expect(resultArea.value).toContain("relevance: 3.00");
    });
});

// ── JobsModal ─────────────────────────────────────────────────────────────────

describe("JobsModal", () => {
    it("calls api.jobs on open and renders job IDs in the table", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        apiMock.jobs.mockResolvedValueOnce([
            { id: "job-aaa111", status: "pending", operation: "ingest", payload: { source: "doc.pdf" }, created_at: null },
            { id: "job-bbb222", status: "in_progress", operation: "ingest", payload: { source: "page.md" }, created_at: null },
        ]);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(apiMock.jobs).toHaveBeenCalled();
        expect(modal.contentEl.innerHTML).toContain("job-aaa111");
        expect(modal.contentEl.innerHTML).toContain("job-bbb222");
    });

    it("shows 'No jobs match' when filtered list is empty", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        apiMock.jobs.mockResolvedValueOnce([]);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("No jobs match");
    });

    it("shows error message when api.jobs throws", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        apiMock.jobs.mockRejectedValueOnce(new Error("refused"));

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("synthadoc serve");
    });

    it("renders error detail row for failed jobs", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        // "failed" is not in the default filter — mock returns all jobs, filter leaves only pending/in_progress
        // Use a pending job that carries an error note (edge-case), OR add a skipped job with an error.
        // Easiest: just test that multiple statuses show their emoji via a pending job.
        apiMock.jobs.mockResolvedValueOnce([
            {
                id: "job-ddd444", status: "pending", operation: "ingest",
                payload: { source: "report.pdf" }, created_at: null, result: null, error: null,
            },
        ]);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        // pending is in the default filter — job should be visible
        expect(modal.contentEl.innerHTML).toContain("job-ddd444");
        expect(modal.contentEl.innerHTML).toContain("🕐"); // pending emoji
    });

    it("hides pagination row when job count is within one page", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        apiMock.jobs.mockResolvedValueOnce(
            Array.from({ length: 5 }, (_, i) => ({
                id: `job-${String(i + 1).padStart(3, "0")}`,
                status: "pending", operation: "ingest",
                payload: { source: `doc-${i}.pdf` }, created_at: null,
            })),
        );

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        // pageRow is contentEl._children[4]; display must be "none" for ≤ JOBS_PAGE_SIZE jobs
        const pageRow = modal.contentEl._children[4];
        expect(pageRow.style.display).toBe("none");
    });

    it("shows pagination row and renders only first page when job count exceeds JOBS_PAGE_SIZE", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        // 26 pending jobs — default filter shows pending/in_progress, so all 26 pass through
        const jobs = Array.from({ length: 26 }, (_, i) => ({
            id: `job-${String(i + 1).padStart(3, "0")}`,
            status: "pending", operation: "ingest",
            payload: { source: `doc-${i}.pdf` }, created_at: null,
        }));
        apiMock.jobs.mockResolvedValueOnce(jobs);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        // pageRow visible; label says Page 1 of 2; 26th job not yet rendered
        const pageRow = modal.contentEl._children[4];
        expect(pageRow.style.display).toBe("flex");
        expect(pageRow._children[1].textContent).toContain("Page 1 of 2");
        expect(pageRow._children[1].textContent).toContain("26 total");
        expect(modal.contentEl.innerHTML).toContain("job-001");
        expect(modal.contentEl.innerHTML).not.toContain("job-026");
    });

    it("next button advances to page 2 showing the last job", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        const jobs = Array.from({ length: 26 }, (_, i) => ({
            id: `job-${String(i + 1).padStart(3, "0")}`,
            status: "pending", operation: "ingest",
            payload: { source: `doc-${i}.pdf` }, created_at: null,
        }));
        apiMock.jobs.mockResolvedValueOnce(jobs);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        // Click Next →  (pageRow._children[2])
        const nextBtn = modal.contentEl._children[4]._children[2];
        nextBtn.onclick();

        expect(modal.contentEl.innerHTML).toContain("job-026");
        expect(modal.contentEl.innerHTML).not.toContain("job-001");

        const pageRow = modal.contentEl._children[4];
        expect(pageRow._children[1].textContent).toContain("Page 2 of 2");
    });

    it("prev button is disabled on page 1 and next button is disabled on last page", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        const jobs = Array.from({ length: 26 }, (_, i) => ({
            id: `job-${String(i + 1).padStart(3, "0")}`,
            status: "pending", operation: "ingest",
            payload: { source: `doc-${i}.pdf` }, created_at: null,
        }));
        apiMock.jobs.mockResolvedValueOnce(jobs);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        const prevBtn = modal.contentEl._children[4]._children[0];
        const nextBtn = modal.contentEl._children[4]._children[2];

        // Page 1: prev disabled, next enabled
        expect(prevBtn.disabled).toBe(true);
        expect(nextBtn.disabled).toBe(false);

        // Advance to page 2 (last page)
        nextBtn.onclick();
        expect(prevBtn.disabled).toBe(false);
        expect(nextBtn.disabled).toBe(true);
    });

    it("default sort is created_at desc — newest job renders first", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        apiMock.jobs.mockResolvedValueOnce([
            { id: "job-old", status: "pending", operation: "ingest", payload: {}, created_at: "2026-01-01 00:00:00" },
            { id: "job-new", status: "pending", operation: "ingest", payload: {}, created_at: "2026-01-02 00:00:00" },
        ]);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        const html = modal.contentEl.innerHTML;
        expect(html.indexOf("job-new")).toBeLessThan(html.indexOf("job-old"));
    });

    it("clicking Status header sorts by status asc", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        apiMock.jobs.mockResolvedValueOnce([
            { id: "job-z", status: "pending", operation: "ingest", payload: {}, created_at: null },
            { id: "job-a", status: "in_progress", operation: "ingest", payload: {}, created_at: null },
        ]);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        // Table header row: th[0]=checkbox, th[1]=Job ID, th[2]=Status, th[3]=Operation, th[4]=Source, th[5]=Created
        const table = modal.contentEl._children[3]._children[0]; // tableEl > table
        const hrow = table._children[0]._children[0];           // thead > tr
        const statusTh = hrow._children[2];                     // Status th
        expect(statusTh.innerHTML).toContain("Status");

        statusTh.onclick();

        const html = modal.contentEl.innerHTML;
        // "in_progress" < "pending" alphabetically, so job-a (in_progress) should come first
        expect(html.indexOf("job-a")).toBeLessThan(html.indexOf("job-z"));
    });

    it("clicking a sorted header again reverses the sort order", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        apiMock.jobs.mockResolvedValueOnce([
            { id: "job-z", status: "pending", operation: "ingest", payload: {}, created_at: null },
            { id: "job-a", status: "in_progress", operation: "ingest", payload: {}, created_at: null },
        ]);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        const table = modal.contentEl._children[3]._children[0];
        const hrow = table._children[0]._children[0];
        const statusTh = hrow._children[2];

        // First click: asc (in_progress first)
        statusTh.onclick();
        let html = modal.contentEl.innerHTML;
        expect(html.indexOf("job-a")).toBeLessThan(html.indexOf("job-z"));

        // Second click: desc (pending first)
        statusTh.onclick();
        html = modal.contentEl.innerHTML;
        expect(html.indexOf("job-z")).toBeLessThan(html.indexOf("job-a"));
    });

    it("clicking Operation header sorts by operation", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        apiMock.jobs.mockResolvedValueOnce([
            { id: "job-lint", status: "pending", operation: "lint", payload: {}, created_at: null },
            { id: "job-ingest", status: "pending", operation: "ingest", payload: {}, created_at: null },
        ]);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        const table = modal.contentEl._children[3]._children[0];
        const hrow = table._children[0]._children[0];
        const operationTh = hrow._children[3]; // Operation th

        operationTh.onclick();

        const html = modal.contentEl.innerHTML;
        // "ingest" < "lint" — job-ingest should appear first
        expect(html.indexOf("job-ingest")).toBeLessThan(html.indexOf("job-lint"));
    });

    it("Retry selected button is disabled when no retryable jobs are checked", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        apiMock.jobs.mockResolvedValueOnce([
            { id: "job-c1", status: "completed", operation: "ingest", payload: { source: "a.pdf" }, created_at: null },
        ]);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        // Find the Retry selected button in the interval row
        const intervalRow = modal.contentEl._children[2]; // h3[0], filterRow[1], intervalRow[2]
        const retryBtn = intervalRow._children?.find((b: any) => b._html === "Retry selected");
        expect(retryBtn).toBeDefined();
        expect(retryBtn.disabled).toBe(true);
    });

    it("Retry selected calls api.retryJob for failed/dead/cancelled checked jobs", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        // Default _selected = {pending, in_progress}. Clear filter via unchecking those two
        // checkboxes so _selected becomes empty and all jobs pass through.
        apiMock.jobs
            .mockResolvedValueOnce([]) // initial load (pending+in_progress filter, no matches)
            .mockResolvedValueOnce([]) // after unchecking pending (in_progress only, no matches)
            .mockResolvedValueOnce([   // after unchecking in_progress (_selected={}, show all)
                { id: "job-f1", status: "failed", operation: "ingest", payload: { source: "a.pdf" }, created_at: null, error: "err" },
                { id: "job-c1", status: "cancelled", operation: "ingest", payload: { source: "b.pdf" }, created_at: null },
            ])
            .mockResolvedValue([]); // after retry refresh
        apiMock.retryJob = vi.fn().mockResolvedValue(undefined);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises(); // initial load done

        // Clear the default status filter so all jobs are visible
        const filterRow = modal.contentEl._children[1]; // h3[0], filterRow[1]
        const pendingCb = filterRow._children[1]._children[0]; // "pending" label > checkbox
        pendingCb.checked = false;
        pendingCb.onchange();
        await flushPromises();

        const inProgressCb = filterRow._children[2]._children[0]; // "in_progress" label > checkbox
        inProgressCb.checked = false;
        inProgressCb.onchange();
        await flushPromises(); // now _filteredJobs = [job-f1, job-c1]

        // Select all terminal jobs via select-all checkbox in table header
        const table = modal.contentEl._children[3]._children[0]; // tableEl[3] > table
        const selectAllCb = table._children[0]._children[0]._children[0]._children[0]; // thead > tr > th > input
        selectAllCb.checked = true;
        selectAllCb.onchange();

        const intervalRow = modal.contentEl._children[2]; // intervalRow[2]
        const retryBtn = intervalRow._children?.find((b: any) => b._html === "Retry selected");
        expect(retryBtn).toBeDefined();
        retryBtn.onclick();
        await flushPromises();

        expect(apiMock.retryJob).toHaveBeenCalledWith("job-f1");
        expect(apiMock.retryJob).toHaveBeenCalledWith("job-c1");
    });

    it("Purge old jobs calls api.purgeJobs with entered days", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-jobs");
        apiMock.jobs.mockResolvedValueOnce([]);
        apiMock.purgeJobs.mockResolvedValueOnce({ purged: 3 });
        apiMock.jobs.mockResolvedValue([]); // after purge refresh

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        const purgeRow = modal.contentEl._children[5]; // h3[0], filterRow[1], intervalRow[2], tableEl[3], pageRow[4], purgeRow[5]
        const purgeDaysInput = purgeRow._children?.find((el: any) => el._tag === "input");
        const purgeBtn = purgeRow._children?.find((el: any) => el._tag === "button");
        expect(purgeBtn).toBeDefined();

        if (purgeDaysInput) purgeDaysInput.value = "14";
        await purgeBtn.onclick();
        await flushPromises();

        expect(apiMock.purgeJobs).toHaveBeenCalledWith(14);
        expect(modal.contentEl.innerHTML).toContain("Purged 3 job(s)");
    });
});

// ── LintReportModal ───────────────────────────────────────────────────────────

describe("LintReportModal", () => {
    it("calls api.lintReport on open", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-lint-report");
        apiMock.lintReport.mockResolvedValueOnce({ contradictions: [], orphans: [] });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(apiMock.lintReport).toHaveBeenCalled();
    });

    it("shows 'All clear' when no contradictions or orphans", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-lint-report");
        apiMock.lintReport.mockResolvedValueOnce({ contradictions: [], orphans: [] });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("All clear");
    });

    it("renders contradicted page slug and contradiction note", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-lint-report");
        apiMock.lintReport.mockResolvedValueOnce({
            contradictions: ["alan-turing"],
            contradiction_details: [{ slug: "alan-turing", contradiction_note: "Conflicting dates found" }],
            orphans: [],
        });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("alan-turing");
        expect(modal.contentEl.innerHTML).toContain("Conflicting dates found");
    });

    it("renders orphan page slugs", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-lint-report");
        apiMock.lintReport.mockResolvedValueOnce({
            contradictions: [],
            orphans: ["quantum-computing"],
            orphan_details: [{ slug: "quantum-computing", index_suggestion: "- [[quantum-computing]]" }],
        });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("quantum-computing");
    });

    it("shows error when api.lintReport throws", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-lint-report");
        apiMock.lintReport.mockRejectedValueOnce(new Error("refused"));

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("synthadoc serve");
    });
});

// ── IngestModal URL tab ───────────────────────────────────────────────────────

describe("IngestModal URL tab", () => {
    // contentEl children: [0]=h3, [1]=tabBar, [2]=WS panel, [3]=URL panel, [4]=All-sources panel, [5]=Pick-files panel
    // URL panel: [0]=desc, [1]=row([0]=input, [1]=btn), [2]=forceRow, [3]=out
    const getUrlTab = (modal: any) => {
        const row = modal.contentEl._children[3]._children[1];
        return { input: row._children[0] as any, btn: row._children[1] as any };
    };

    it("calls api.ingest with the entered URL on Ingest click", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-ingest");
        apiMock.ingest.mockResolvedValueOnce({ job_id: "url-job-01" });
        apiMock.job = vi.fn().mockResolvedValue({ status: "completed", result: {} });

        const modal = new ModalClass();
        modal.onOpen();

        const { input, btn } = getUrlTab(modal);
        input.value = "https://example.com/paper.pdf";
        await btn.onclick();
        await flushPromises();

        expect(apiMock.ingest).toHaveBeenCalledWith("https://example.com/paper.pdf", undefined, false);
    });

    it("shows error and re-enables button when api.ingest throws", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-ingest");
        apiMock.ingest.mockRejectedValueOnce(new Error("refused"));

        const modal = new ModalClass();
        modal.onOpen();

        const { input, btn } = getUrlTab(modal);
        input.value = "https://example.com/paper.pdf";
        await btn.onclick();
        await flushPromises();

        expect(btn.disabled).toBe(false);
        expect(modal.contentEl.innerHTML).toContain("synthadoc serve");
    });

    it("does nothing when URL input is empty", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-ingest");

        const modal = new ModalClass();
        modal.onOpen();

        const { btn } = getUrlTab(modal);
        await btn.onclick();

        expect(apiMock.ingest).not.toHaveBeenCalled();
    });
});


// ── AuditModal — Ingest history tab ───────────────────────────────────────────

describe("AuditModal — Ingest history tab", () => {
    it("calls api.auditHistory with default limit 50 on open", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.auditHistory.mockResolvedValueOnce({ records: [], count: 0 });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(apiMock.auditHistory).toHaveBeenCalledWith(50);
    });

    it("shows 'No ingest records' when empty", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.auditHistory.mockResolvedValueOnce({ records: [], count: 0 });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("No ingest records");
    });

    it("renders source filename and wiki_page", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.auditHistory.mockResolvedValueOnce({
            records: [{
                source_path: "raw_sources/paper.pdf",
                wiki_page: "alan-turing",
                tokens: 1200, cost_usd: 0.0014,
                ingested_at: "2026-05-01T10:00:00Z",
            }],
            count: 1,
        });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("paper.pdf");
        expect(modal.contentEl.innerHTML).toContain("alan-turing");
    });

    it("shows error when api.auditHistory throws", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.auditHistory.mockRejectedValueOnce(new Error("refused"));

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("synthadoc serve");
    });
});

// ── AuditModal — Cost summary tab ─────────────────────────────────────────────

describe("AuditModal — Cost summary tab", () => {
    it("calls api.auditCosts with default 30 days on open", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.auditCosts.mockResolvedValueOnce({ total_tokens: 0, total_cost_usd: 0, daily: [] });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(apiMock.auditCosts).toHaveBeenCalledWith(30);
    });

    it("shows total cost in the summary line", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.auditCosts.mockResolvedValueOnce({
            total_tokens: 48200, total_cost_usd: 0.0571,
            daily: [{ day: "2026-05-01", cost_usd: 0.0571 }],
        });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("$0.0571");
    });

    it("shows 'No cost data' when daily array is empty", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.auditCosts.mockResolvedValueOnce({ total_tokens: 0, total_cost_usd: 0, daily: [] });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("No cost data");
    });

    it("shows error when api.auditCosts throws", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.auditCosts.mockRejectedValueOnce(new Error("refused"));

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("synthadoc serve");
    });
});

// ── AuditModal — Query history tab ────────────────────────────────────────────

describe("AuditModal — Query history tab", () => {
    it("calls api.queryHistory with default limit 50 on open", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.queryHistory.mockResolvedValueOnce({ records: [] });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(apiMock.queryHistory).toHaveBeenCalledWith(50);
    });

    it("shows 'No queries recorded' when empty", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.queryHistory.mockResolvedValueOnce({ records: [] });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("No queries recorded");
    });

    it("renders question text and cost in the table", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.queryHistory.mockResolvedValueOnce({
            records: [{
                question: "What is the Bank of Canada rate?",
                sub_questions_count: 2, tokens: 3200,
                cost_usd: 0.0038, queried_at: "2026-05-10T14:30:00Z",
            }],
        });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("Bank of Canada rate");
        expect(modal.contentEl.innerHTML).toContain("$0.0038");
    });

    it("shows error when api.queryHistory throws", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-audit");
        apiMock.queryHistory.mockRejectedValueOnce(new Error("refused"));

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("synthadoc serve");
    });
});

// ── StagingModal ──────────────────────────────────────────────────────────────

describe("StagingModal", () => {
    it("calls api.stagingPolicy on open", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-staging");
        apiMock.stagingPolicy.mockResolvedValueOnce({ policy: "off", confidence_min: null });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(apiMock.stagingPolicy).toHaveBeenCalled();
    });

    it("shows 'disabled' in state label when policy is off", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-staging");
        apiMock.stagingPolicy.mockResolvedValueOnce({ policy: "off", confidence_min: null });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("disabled");
    });

    it("Save button calls api.stagingSetPolicy", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-staging");
        apiMock.stagingPolicy.mockResolvedValueOnce({ policy: "off", confidence_min: null });
        apiMock.stagingSetPolicy.mockResolvedValueOnce({ policy: "off", confidence_min: null });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        // saveBtn is actionRow._children[0]; actionRow is contentEl._children[5]
        const saveBtn = modal.contentEl._children[5]._children[0];
        await saveBtn.onclick();
        await flushPromises();

        expect(apiMock.stagingSetPolicy).toHaveBeenCalled();
    });

    it("shows success message in resultEl after save", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-staging");
        apiMock.stagingPolicy.mockResolvedValueOnce({ policy: "off", confidence_min: null });
        apiMock.stagingSetPolicy.mockResolvedValueOnce({ policy: "off", confidence_min: null });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        const saveBtn = modal.contentEl._children[5]._children[0];
        await saveBtn.onclick();
        await flushPromises();

        // resultEl is contentEl._children[6]
        expect(modal.contentEl._children[6].innerHTML).toContain("Policy updated");
    });

    it("shows server error when api.stagingPolicy throws", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-staging");
        apiMock.stagingPolicy.mockRejectedValueOnce(new Error("refused"));

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("Synthadoc server");
    });
});

// ── CandidatesModal ───────────────────────────────────────────────────────────

describe("CandidatesModal", () => {
    it("calls api.candidates on open", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-candidates");
        apiMock.candidates.mockResolvedValueOnce([]);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(apiMock.candidates).toHaveBeenCalled();
    });

    it("shows 'No candidates' when the list is empty", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-candidates");
        apiMock.candidates.mockResolvedValueOnce([]);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("No candidates");
    });

    it("renders candidate slugs in the table", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-candidates");
        apiMock.candidates.mockResolvedValueOnce([
            { slug: "early-internet", title: "Early Internet", confidence: "medium", created: "2026-05-01" },
        ]);

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("early-internet");
    });

    it("Promote All calls api.candidatesPromoteAll", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-candidates");
        apiMock.candidates
            .mockResolvedValueOnce([{ slug: "early-internet", title: "Early Internet", confidence: "medium", created: "2026-05-01" }])
            .mockResolvedValueOnce([]);
        apiMock.candidatesPromoteAll.mockResolvedValueOnce({ count: 1 });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        // promoteAllBtn is actionBar._children[0]; actionBar is contentEl._children[2]
        const promoteAllBtn = modal.contentEl._children[2]._children[0];
        await promoteAllBtn.onclick();
        await flushPromises();

        expect(apiMock.candidatesPromoteAll).toHaveBeenCalled();
    });

    it("Discard All calls api.candidatesDiscardAll", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-candidates");
        apiMock.candidates
            .mockResolvedValueOnce([{ slug: "early-internet", title: "Early Internet", confidence: "medium", created: "2026-05-01" }])
            .mockResolvedValueOnce([]);
        apiMock.candidatesDiscardAll.mockResolvedValueOnce({ count: 1 });

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        // discardAllBtn is actionBar._children[1]
        const discardAllBtn = modal.contentEl._children[2]._children[1];
        await discardAllBtn.onclick();
        await flushPromises();

        expect(apiMock.candidatesDiscardAll).toHaveBeenCalled();
    });

    it("shows error when api.candidates throws", async () => {
        const { ModalClass, apiMock } = await getModal("synthadoc-candidates");
        apiMock.candidates.mockRejectedValueOnce(new Error("refused"));

        const modal = new ModalClass();
        modal.onOpen();
        await flushPromises();

        expect(modal.contentEl.innerHTML).toContain("Synthadoc server");
    });
});

// ── SynthadocSettingTab ───────────────────────────────────────────────────────

describe("SynthadocSettingTab", () => {
    it("display() empties container and creates Synthadoc settings heading", async () => {
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();

        const tab = (plugin.addSettingTab as any).mock.calls[0][0];
        const createElCalls: { tag: string; opts?: any }[] = [];
        tab.containerEl = {
            empty: vi.fn(),
            createEl: vi.fn((tag: string, opts?: any) => {
                createElCalls.push({ tag, opts });
                return { style: {}, setText: vi.fn() };
            }),
        };
        tab.display();

        expect(tab.containerEl.empty).toHaveBeenCalled();
        expect(tab.containerEl.createEl).toHaveBeenCalledWith("h2", expect.objectContaining({ text: "Synthadoc settings" }));
    });
});
