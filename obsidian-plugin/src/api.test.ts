// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";

// vi.mock is hoisted — use vi.hoisted so the spy is available inside the factory
const { mockRequestUrl } = vi.hoisted(() => ({ mockRequestUrl: vi.fn() }));
vi.mock("obsidian", () => ({ requestUrl: mockRequestUrl }));

import { api, setBase } from "./api";

function mockResponse(body: unknown, status = 200) {
    mockRequestUrl.mockResolvedValueOnce({ status, json: body });
}

beforeEach(() => setBase("http://127.0.0.1:7070"));
afterEach(() => vi.clearAllMocks());

describe("setBase", () => {
    it("changes the base URL used by all api calls", async () => {
        setBase("http://127.0.0.1:7071");
        mockResponse({ status: "ok" });
        await api.health();
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7071/health" })
        );
    });

    it("strips trailing slash from base URL", async () => {
        setBase("http://127.0.0.1:7072/");
        mockResponse({ status: "ok" });
        await api.health();
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7072/health" })
        );
    });
});

describe("api.health", () => {
    it("calls GET /health and returns parsed json", async () => {
        mockResponse({ status: "ok" });
        const result = await api.health() as any;
        expect(result).toEqual({ status: "ok" });
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/health", method: "GET" })
        );
    });
});

describe("api.status", () => {
    it("calls GET /status and returns page count", async () => {
        mockResponse({ pages: 42, wiki: "/my/wiki" });
        const result = await api.status() as any;
        expect(result.pages).toBe(42);
    });
});

describe("api.query", () => {
    it("POSTs to /query with question in body", async () => {
        mockResponse({ answer: "AI is great", citations: ["ai-page"] });
        const result = await api.query("What is AI?") as any;
        expect(result.answer).toBe("AI is great");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                url: "http://127.0.0.1:7070/query",
                method: "POST",
                body: JSON.stringify({ question: "What is AI?" }),
            })
        );
    });
});

describe("api.ingest", () => {
    it("POSTs to /jobs/ingest with source in body and returns job_id", async () => {
        mockResponse({ job_id: "job-123" });
        const result = await api.ingest("paper.pdf") as any;
        expect(result.job_id).toBe("job-123");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                url: "http://127.0.0.1:7070/jobs/ingest",
                method: "POST",
                body: JSON.stringify({ source: "paper.pdf" }),
            })
        );
    });
});

describe("api.lintReport", () => {
    it("GETs /lint/report", async () => {
        mockResponse({ contradictions: ["grace-hopper"], orphans: ["quantum-computing"] });
        const r = await api.lintReport() as any;
        expect(r.contradictions).toEqual(["grace-hopper"]);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/lint/report", method: "GET" })
        );
    });
});

describe("api.jobs", () => {
    it("GETs /jobs when no status filter given", async () => {
        mockResponse([]);
        await api.jobs();
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/jobs", method: "GET" })
        );
    });

    it("GETs /jobs?status=completed when filter is provided", async () => {
        mockResponse([]);
        await api.jobs("completed");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/jobs?status=completed", method: "GET" })
        );
    });
});

describe("api.lint", () => {
    it("POSTs to /jobs/lint with scope and auto_resolve in body", async () => {
        mockResponse({ contradictions_found: 2, orphans: ["stale"] });
        await api.lint("contradictions");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                url: "http://127.0.0.1:7070/jobs/lint",
                method: "POST",
                body: JSON.stringify({ scope: "contradictions", auto_resolve: false }),
            })
        );
    });

    it("defaults scope to 'all' and auto_resolve to false", async () => {
        mockResponse({ contradictions_found: 0, orphans: [] });
        await api.lint();
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ body: JSON.stringify({ scope: "all", auto_resolve: false }) })
        );
    });

    it("passes auto_resolve=true when requested", async () => {
        mockResponse({ contradictions_found: 0, orphans: [] });
        await api.lint("all", true);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ body: JSON.stringify({ scope: "all", auto_resolve: true }) })
        );
    });
});

describe("error handling", () => {
    it("throws with status code when server returns non-OK", async () => {
        mockResponse({}, 500);
        await expect(api.health()).rejects.toThrow("synthadoc API 500");
    });

    it("throws on 404", async () => {
        mockResponse({}, 404);
        await expect(api.query("test")).rejects.toThrow("synthadoc API 404");
    });
});

describe("api.routingStatus", () => {
    it("GETs /routing/status", async () => {
        mockResponse({ exists: false, branches: 0, slugs: 0, content: "" });
        const r = await (api as any).routingStatus() as any;
        expect(r.exists).toBe(false);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/routing/status", method: "GET" })
        );
    });
});

describe("api.routingInit", () => {
    it("POSTs to /routing/init with no body", async () => {
        mockResponse({ branches: 2, slugs: 5, content: "## People\n- [[alan-turing]]\n" });
        const r = await (api as any).routingInit() as any;
        expect(r.branches).toBe(2);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/routing/init", method: "POST" })
        );
    });
});

describe("api.routingValidate", () => {
    it("POSTs to /routing/validate and returns dangling list", async () => {
        mockResponse({ clean: false, dangling: [{ branch: "People", slug: "john-mccarthy" }] });
        const r = await (api as any).routingValidate() as any;
        expect(r.clean).toBe(false);
        expect(r.dangling).toHaveLength(1);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/routing/validate", method: "POST" })
        );
    });
});

describe("api.routingClean", () => {
    it("POSTs to /routing/clean and returns removed list and content", async () => {
        mockResponse({ removed: [{ branch: "People", slug: "john-mccarthy" }], content: "## People\n" });
        const r = await (api as any).routingClean() as any;
        expect(r.removed).toHaveLength(1);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/routing/clean", method: "POST" })
        );
    });
});
