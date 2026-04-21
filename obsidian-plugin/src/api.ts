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
    ingest:       (source: string, maxResults?: number) => call("/jobs/ingest", "POST", maxResults != null ? { source, max_results: maxResults } : { source }),
    lint:         (scope = "all", autoResolve = false) => call("/jobs/lint", "POST", { scope, auto_resolve: autoResolve }),
    lintReport:   ()                          => call("/lint/report"),
    jobs:         (status?: string)           => call(status ? `/jobs?status=${encodeURIComponent(status)}` : "/jobs"),
    retryJob:     (jobId: string)             => call(`/jobs/${jobId}/retry`, "POST"),
    purgeJobs:    (olderThan: number)         => call(`/jobs?older_than=${olderThan}`, "DELETE"),
    scaffold:     (domain: string)            => call("/jobs/scaffold",   "POST", { domain }),
    job:           (jobId: string)             => call(`/jobs/${jobId}`),
    auditHistory:  (limit = 50)               => call(`/audit/history?limit=${limit}`),
    auditCosts:    (days = 30)                => call(`/audit/costs?days=${days}`),
    queryHistory:  (limit = 50)               => call(`/audit/queries?limit=${limit}`),
};
