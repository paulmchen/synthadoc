# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from synthadoc.skills.base import BaseSkill, ExtractedContent


class WebSearchSkill(BaseSkill):
    async def extract(self, source: str) -> ExtractedContent:
        raise NotImplementedError(
            "web_search is a v2 feature. Full implementation coming in a future release."
        )
