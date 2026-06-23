"""Live Azure Resource Graph provider (SPEC §2) — not implemented yet.

The protocol seam exists so the tools and the factory stay mode-agnostic. The
real implementation will query Azure Resource Graph via
``azure-mgmt-resourcegraph``, authenticating with ``DefaultAzureCredential``
(``azure-identity``) against the operator's own tenant. Tracked separately.
"""

from __future__ import annotations

from providers.base import ResourceRow


class LiveProvider:
    """Placeholder ``Provider``; construction is fine, calls raise until built."""

    async def list_resources(self) -> list[ResourceRow]:
        raise NotImplementedError(
            "The live provider is not implemented yet; "
            "run with the default mock provider."
        )
