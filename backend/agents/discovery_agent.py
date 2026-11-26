"""Job Discovery Agent: gathers candidate opportunities from authorized ATS, API, RSS, and career sources."""

import logging
from typing import List, Optional

from backend.services.discovery_sources import DiscoverySourcesClient, RawDiscoveredJob

logger = logging.getLogger(__name__)


class JobDiscoveryAgent:
    """Discovers public Data Analyst, Data Scientist, and AI/ML opportunities ethically."""

    def __init__(self, sources_client: Optional[DiscoverySourcesClient] = None) -> None:
        self.sources_client = sources_client or DiscoverySourcesClient()

    def discover(self) -> tuple[List[RawDiscoveredJob], List[str]]:
        """Execute discovery across all configured authorized connectors."""
        jobs, sources_checked = self.sources_client.fetch_all()
        logger.info(
            "JobDiscoveryAgent fetched %d candidate listings across %d sources.",
            len(jobs),
            len(sources_checked),
        )
        return jobs, sources_checked
