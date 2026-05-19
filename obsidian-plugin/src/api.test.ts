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
    it("POSTs to /query with question and default timeout in body", async () => {
        mockResponse({ answer: "AI is great", citations: ["ai-page"] });
        const result = await api.query("What is AI?") as any;
        expect(result.answer).toBe("AI is great");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                url: "http://127.0.0.1:7070/query",
                method: "POST",
                body: JSON.stringify({ question: "What is AI?", timeout_seconds: 60 }),
            })
        );
    });

    it("POSTs to /query with custom timeout", async () => {
        mockResponse({ answer: "AI is great", citations: [] });
        await api.query("What is AI?", 120);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                body: JSON.stringify({ question: "What is AI?", timeout_seconds: 120 }),
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

describe("api.stagingPolicy", () => {
    it("GETs /staging/policy and returns policy and confidence_min", async () => {
        mockResponse({ policy: "off", confidence_min: null });
        const r = await (api as any).stagingPolicy() as any;
        expect(r.policy).toBe("off");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/staging/policy", method: "GET" })
        );
    });

    it("returns threshold policy with confidence_min when set", async () => {
        mockResponse({ policy: "threshold", confidence_min: "medium" });
        const r = await (api as any).stagingPolicy() as any;
        expect(r.policy).toBe("threshold");
        expect(r.confidence_min).toBe("medium");
    });
});

describe("api.stagingSetPolicy", () => {
    it("POSTs to /staging/policy with policy only when no confidence_min provided", async () => {
        mockResponse({ policy: "all", confidence_min: null });
        await (api as any).stagingSetPolicy("all");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                url: "http://127.0.0.1:7070/staging/policy",
                method: "POST",
                body: JSON.stringify({ policy: "all" }),
            })
        );
    });

    it("includes confidence_min in body when provided", async () => {
        mockResponse({ policy: "threshold", confidence_min: "medium" });
        await (api as any).stagingSetPolicy("threshold", "medium");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                body: JSON.stringify({ policy: "threshold", confidence_min: "medium" }),
            })
        );
    });

    it("omits confidence_min from body when not provided (policy=off)", async () => {
        mockResponse({ policy: "off", confidence_min: null });
        await (api as any).stagingSetPolicy("off");
        const call = mockRequestUrl.mock.calls[0][0];
        expect(JSON.parse(call.body)).not.toHaveProperty("confidence_min");
    });
});

describe("api.candidates", () => {
    it("GETs /candidates and returns the list", async () => {
        mockResponse([
            { slug: "early-internet-history", title: "Early Internet History", confidence: "medium", ingested_at: "2026-05-06T14:22:11" },
        ]);
        const r = await (api as any).candidates() as any;
        expect(r).toHaveLength(1);
        expect(r[0].slug).toBe("early-internet-history");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/candidates", method: "GET" })
        );
    });

    it("returns empty array when no candidates exist", async () => {
        mockResponse([]);
        const r = await (api as any).candidates() as any;
        expect(r).toEqual([]);
    });
});

describe("api.candidatesPromoteAll", () => {
    it("POSTs to /candidates/promote-all and returns promoted + updated counts", async () => {
        mockResponse({ promoted: 3, updated: 1 });
        const r = await (api as any).candidatesPromoteAll() as any;
        expect(r.promoted).toBe(3);
        expect(r.updated).toBe(1);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/candidates/promote-all", method: "POST" })
        );
    });
});

describe("api.candidatesDiscardAll", () => {
    it("POSTs to /candidates/discard-all and returns discarded count", async () => {
        mockResponse({ discarded: 2 });
        const r = await (api as any).candidatesDiscardAll() as any;
        expect(r.discarded).toBe(2);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/candidates/discard-all", method: "POST" })
        );
    });
});

describe("api.candidatePromote", () => {
    it("POSTs to /candidates/{slug}/promote", async () => {
        mockResponse({ promoted: "early-internet-history", new: true, updated: false });
        await (api as any).candidatePromote("early-internet-history");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                url: "http://127.0.0.1:7070/candidates/early-internet-history/promote",
                method: "POST",
            })
        );
    });

    it("URL-encodes slugs that contain special characters", async () => {
        mockResponse({ promoted: "page with spaces", new: true, updated: false });
        await (api as any).candidatePromote("page with spaces");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                url: "http://127.0.0.1:7070/candidates/page%20with%20spaces/promote",
            })
        );
    });
});

describe("api.candidateDiscard", () => {
    it("POSTs to /candidates/{slug}/discard", async () => {
        mockResponse({ discarded: "punch-card-era" });
        await (api as any).candidateDiscard("punch-card-era");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                url: "http://127.0.0.1:7070/candidates/punch-card-era/discard",
                method: "POST",
            })
        );
    });
});

describe("api.retryJob", () => {
    it("POSTs to /jobs/{jobId}/retry", async () => {
        mockResponse({ job_id: "abc-123", status: "pending" });
        await api.retryJob("abc-123");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/jobs/abc-123/retry", method: "POST" })
        );
    });
});

describe("api.deleteJob", () => {
    it("DELETEs /jobs/{jobId}", async () => {
        mockResponse({ deleted: "abc-123" });
        await api.deleteJob("abc-123");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/jobs/abc-123", method: "DELETE" })
        );
    });
});

describe("api.purgeJobs", () => {
    it("DELETEs /jobs?older_than with specified days", async () => {
        mockResponse({ purged: 5 });
        await api.purgeJobs(7);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/jobs?older_than=7", method: "DELETE" })
        );
    });
});

describe("api.scaffold", () => {
    it("POSTs to /jobs/scaffold with domain in body", async () => {
        mockResponse({ job_id: "scaffold-job-1" });
        await api.scaffold("Robotics");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                url: "http://127.0.0.1:7070/jobs/scaffold",
                method: "POST",
                body: JSON.stringify({ domain: "Robotics" }),
            })
        );
    });
});

describe("api.job", () => {
    it("GETs /jobs/{jobId} and returns job detail", async () => {
        mockResponse({ job_id: "abc-123", status: "completed", source: "paper.pdf" });
        const r = await api.job("abc-123") as any;
        expect(r.job_id).toBe("abc-123");
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/jobs/abc-123", method: "GET" })
        );
    });
});

describe("api.auditHistory", () => {
    it("GETs /audit/history with default limit of 50", async () => {
        mockResponse([]);
        await api.auditHistory();
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/audit/history?limit=50", method: "GET" })
        );
    });

    it("GETs /audit/history with custom limit", async () => {
        mockResponse([]);
        await api.auditHistory(10);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/audit/history?limit=10" })
        );
    });
});

describe("api.auditCosts", () => {
    it("GETs /audit/costs with default 30-day window", async () => {
        mockResponse({ total_usd: 1.23 });
        await api.auditCosts();
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/audit/costs?days=30", method: "GET" })
        );
    });

    it("GETs /audit/costs with custom days", async () => {
        mockResponse({ total_usd: 0.45 });
        await api.auditCosts(7);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/audit/costs?days=7" })
        );
    });
});

describe("api.queryHistory", () => {
    it("GETs /audit/queries with default limit of 50", async () => {
        mockResponse([]);
        await api.queryHistory();
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/audit/queries?limit=50", method: "GET" })
        );
    });

    it("GETs /audit/queries with custom limit", async () => {
        mockResponse([]);
        await api.queryHistory(20);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/audit/queries?limit=20" })
        );
    });
});

describe("api.auditEvents", () => {
    it("GETs /audit/events with default limit of 100", async () => {
        mockResponse([]);
        await api.auditEvents();
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/audit/events?limit=100", method: "GET" })
        );
    });

    it("GETs /audit/events with custom limit", async () => {
        mockResponse([]);
        await api.auditEvents(25);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({ url: "http://127.0.0.1:7070/audit/events?limit=25" })
        );
    });
});

describe("api.ingest with maxResults", () => {
    it("includes max_results in body when maxResults is provided", async () => {
        mockResponse({ job_id: "job-456" });
        await api.ingest("paper.pdf", 20);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                body: JSON.stringify({ source: "paper.pdf", max_results: 20 }),
            })
        );
    });

    it("omits max_results from body when maxResults is not provided", async () => {
        mockResponse({ job_id: "job-789" });
        await api.ingest("paper.pdf");
        const call = mockRequestUrl.mock.calls[0][0];
        expect(JSON.parse(call.body)).not.toHaveProperty("max_results");
    });
});

describe("api.contextBuild", () => {
    it("POSTs to /context/build with goal and token_budget", async () => {
        mockResponse({
            goal: "early computing pioneers",
            token_budget: 4000,
            tokens_used: 1823,
            pages: [],
            omitted: [],
        });
        const r = await (api as any).contextBuild("early computing pioneers", 4000) as any;
        expect(r.goal).toBe("early computing pioneers");
        expect(r.token_budget).toBe(4000);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                url: "http://127.0.0.1:7070/context/build",
                method: "POST",
                body: JSON.stringify({ goal: "early computing pioneers", token_budget: 4000 }),
            })
        );
    });

    it("returns pages and omitted arrays from the response", async () => {
        mockResponse({
            goal: "test",
            token_budget: 2000,
            tokens_used: 800,
            pages: [{ slug: "alan-turing", relevance: 3.5, excerpt: "...", source: "wiki/alan-turing.md", confidence: "high", tags: [], estimated_tokens: 600 }],
            omitted: [{ slug: "grace-hopper", relevance: 1.2, excerpt: "...", source: "wiki/grace-hopper.md", confidence: "high", tags: [], estimated_tokens: 400 }],
        });
        const r = await (api as any).contextBuild("test", 2000) as any;
        expect(r.pages).toHaveLength(1);
        expect(r.pages[0].slug).toBe("alan-turing");
        expect(r.omitted).toHaveLength(1);
        expect(r.omitted[0].slug).toBe("grace-hopper");
    });

    it("sends a custom token_budget when specified", async () => {
        mockResponse({ goal: "AI", token_budget: 1500, tokens_used: 900, pages: [], omitted: [] });
        await (api as any).contextBuild("AI", 1500);
        expect(mockRequestUrl).toHaveBeenCalledWith(
            expect.objectContaining({
                body: JSON.stringify({ goal: "AI", token_budget: 1500 }),
            })
        );
    });
});
