# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
def test_coding_tool_quota_exception_message():
    from synthadoc.errors import CodingToolQuotaExhaustedException
    e = CodingToolQuotaExhaustedException("claude-code")
    assert "claude-code" in str(e)
    assert "quota" in str(e).lower()
