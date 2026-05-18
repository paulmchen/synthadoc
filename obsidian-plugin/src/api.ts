// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com
import { requestUrl } from "obsidian";

let BASE = "http://127.0.0.1:7070";

export function setBase(url: string): void {
    BASE = url.replace(/\/$/, "");
}

async function call(path: string, method = "GET", body?: object) {
    const res = await requestUrl({
        url: `${BASE}${path}`,
        method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
        throw: false,
    });
    if (res.status < 200 || res.status >= 300) {
        throw new Error(`synthadoc API ${res.status}`);
    }
    return res.json;
}

export const api = {
    health:       ()                          => call("/health"),
    status:       ()                          => call("/status"),
    query:        (question: string)          => call("/query",           "POST", { question }),
    ingest:       (source: string, maxResults?: number, force?: boolean) => call("/jobs/ingest", "POST", { source, ...(maxResults != null ? { max_results: maxResults } : {}), ...(force ? { force: true } : {}) }),
    lint:         (scope = "all", autoResolve = false) => call("/jobs/lint", "POST", { scope, auto_resolve: autoResolve }),
    lintReport:   ()                          => call("/lint/report"),
    jobs:         (status?: string)           => call(status ? `/jobs?status=${encodeURIComponent(status)}` : "/jobs"),
    retryJob:     (jobId: string)             => call(`/jobs/${jobId}/retry`, "POST"),
    deleteJob:    (jobId: string)             => call(`/jobs/${jobId}`, "DELETE"),
    purgeJobs:    (olderThan: number)         => call(`/jobs?older_than=${olderThan}`, "DELETE"),
    scaffold:     (domain: string)            => call("/jobs/scaffold",   "POST", { domain }),
    job:           (jobId: string)             => call(`/jobs/${jobId}`),
    auditHistory:  (limit = 50)               => call(`/audit/history?limit=${limit}`),
    auditCosts:    (days = 30)                => call(`/audit/costs?days=${days}`),
    queryHistory:  (limit = 50)               => call(`/audit/queries?limit=${limit}`),
    auditEvents:   (limit = 100)              => call(`/audit/events?limit=${limit}`),
    routingStatus:   () => call("/routing/status"),
    routingInit:     () => call("/routing/init",     "POST"),
    routingValidate: () => call("/routing/validate", "POST"),
    routingClean:    () => call("/routing/clean",    "POST"),

    stagingPolicy:    () => call("/staging/policy"),
    stagingSetPolicy: (policy: string, confidenceMin?: string) =>
        call("/staging/policy", "POST", confidenceMin ? { policy, confidence_min: confidenceMin } : { policy }),

    candidates:          () => call("/candidates"),
    candidatesPromoteAll: () => call("/candidates/promote-all", "POST"),
    candidatesDiscardAll: () => call("/candidates/discard-all", "POST"),
    candidatePromote:    (slug: string) => call(`/candidates/${encodeURIComponent(slug)}/promote`, "POST"),
    candidateDiscard:    (slug: string) => call(`/candidates/${encodeURIComponent(slug)}/discard`, "POST"),

    contextBuild: (goal: string, tokenBudget: number) =>
        call("/context/build", "POST", { goal, token_budget: tokenBudget }),
};
