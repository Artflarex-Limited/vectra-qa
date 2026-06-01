"""
HashiCorp Vault client for dynamic secrets in Vectra QA.
Supports KV v2 for LLM API keys and database dynamic secrets.
"""

import os
from typing import Optional, Dict
from contextlib import asynccontextmanager

import structlog

logger = structlog.get_logger()

# Optional import — vault is optional dependency
try:
    import hvac
    VAULT_AVAILABLE = True
except ImportError:
    VAULT_AVAILABLE = False
    hvac = None


class VaultKV2Manager:
    """Manages secrets via Vault KV v2 engine."""

    def __init__(self, vault_addr: str = None, vault_token: str = None, mount_point: str = "secret"):
        if not VAULT_AVAILABLE:
            raise RuntimeError("hvac not installed. Run: pip install hvac>=2.0.0")

        self.client = hvac.Client(
            url=vault_addr or os.getenv("VAULT_ADDR", "http://127.0.0.1:8200"),
            token=vault_token or os.getenv("VAULT_TOKEN")
        )
        self.mount_point = mount_point

    def get_secret(self, path: str) -> Dict[str, str]:
        """Read a secret from KV v2."""
        response = self.client.secrets.kv.v2.read_secret_version(
            path=path,
            mount_point=self.mount_point
        )
        return response['data']['data']

    def set_secret(self, path: str, secret_dict: Dict[str, str]):
        """Write a secret to KV v2."""
        self.client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret=secret_dict,
            mount_point=self.mount_point
        )

    def get_llm_api_key(self, provider: str) -> str:
        """Get LLM API key from Vault."""
        secret = self.get_secret(path=f"llm/{provider}")
        return secret['api_key']


class VaultDatabaseManager:
    """Manages dynamic database credentials from Vault."""

    def __init__(self, vault_addr: str = None, vault_token: str = None, db_role: str = "readonly"):
        if not VAULT_AVAILABLE:
            raise RuntimeError("hvac not installed. Run: pip install hvac>=2.0.0")

        self.client = hvac.Client(
            url=vault_addr or os.getenv("VAULT_ADDR", "http://127.0.0.1:8200"),
            token=vault_token or os.getenv("VAULT_TOKEN")
        )
        self.db_role = db_role
        self.lease_id = None
        self._credentials = None

    def get_credentials(self) -> Dict[str, str]:
        """Fetch dynamic credentials from Vault database secrets engine."""
        response = self.client.secrets.database.generate_credentials(
            name=self.db_role,
            mount_point='database'
        )
        self.lease_id = response['lease_id']
        self._credentials = {
            'username': response['data']['username'],
            'password': response['data']['password']
        }
        return self._credentials

    def revoke_credentials(self):
        """Revoke credentials immediately."""
        if self.lease_id:
            self.client.sys.revoke_lease(self.lease_id)
            self.lease_id = None
            self._credentials = None

    @property
    def is_valid(self) -> bool:
        """Check if current credentials are still valid."""
        return self._credentials is not None and self.lease_id is not None


# Global vault client
_vault_client: Optional[VaultKV2Manager] = None


def get_vault_client() -> Optional[VaultKV2Manager]:
    """Get or create the Vault KV client singleton."""
    global _vault_client
    if _vault_client is None:
        if not VAULT_AVAILABLE:
            logger.warning("vault_client_unavailable_hvac_not_installed")
            return None
        try:
            _vault_client = VaultKV2Manager()
        except Exception as e:
            logger.error("vault_client_init_failed", error=str(e))
            return None
    return _vault_client


def is_vault_available() -> bool:
    """Check if Vault is configured and reachable."""
    if not VAULT_AVAILABLE:
        return False
    client = get_vault_client()
    if client is None:
        return False
    try:
        client.client.sys.health_status()
        return True
    except Exception:
        return False