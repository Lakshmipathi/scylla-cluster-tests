
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright (c) 2025 ScyllaDB
import logging
from dataclasses import dataclass

from sdcm.utils.azure_utils import AzureService
from sdcm.keystore import KeyStore

LOGGER = logging.getLogger(__name__)


@dataclass
class KmsProvider:
    _resource_group_name: str
    _region: str
    _az: str
    _azure_service: AzureService = AzureService()

    def __post_init__(self):
        self._kms_config = KeyStore().get_azure_kms_config()

    @property
    def managed_identity_config(self):
        return {
            'resource_group': self._kms_config['resource_group'],
            'identity_name': self._kms_config['identity_name'],
            'principal_id': self._kms_config['managed_identity_principal_id']
        }

    @property
    def sct_service_principal_id(self):
        return self._kms_config['sct_service_principal_id']

    def _get_managed_identity_id(self) -> str:
        return f"/subscriptions/{self._azure_service.subscription_id}/resourcegroups/{self.managed_identity_config['resource_group']}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{self.managed_identity_config['identity_name']}"

    def get_or_create_keyvault_and_identity(self, test_id: str):
        """Use fixed vault with 3 pre-created keys, returns key based on test_id hash"""
        vault_name = f"{self._kms_config['shared_vault_name']}-{self._region}"
        try:
            vault = self._azure_service.keyvault.vaults.begin_create_or_update(
                resource_group_name=self._kms_config['resource_group'], vault_name=vault_name,
                parameters={
                    "location": self._region,
                    "properties": {
                        "tenant_id": self._azure_service.azure_credentials["tenant_id"],
                        "sku": {"name": "standard", "family": "A"},
                        "enabled_for_disk_encryption": True,
                        "enable_rbac_authorization": False,
                        "access_policies": [{
                            "tenant_id": self._azure_service.azure_credentials["tenant_id"],
                            "object_id": self.managed_identity_config['principal_id'],
                            "permissions": {
                                "keys": ["get", "encrypt", "decrypt", "wrapKey", "unwrapKey"],
                                "secrets": ["get"],
                                "certificates": ["get"]
                            }
                        }, {
                            # SCT service principal
                            "tenant_id": self._azure_service.azure_credentials["tenant_id"],
                            "object_id": self.sct_service_principal_id,
                            "permissions": {
                                "keys": ["create", "get", "list"],
                                "secrets": ["get"],
                                "certificates": ["get"]
                            }
                        }],
                    }
                }
            ).result()

            vault_uri = vault.properties.vault_uri

            # Pick one key, if required create keys.
            for i in range(1, 4):
                key_name = f"scylla-key-{i}"
                if not self._azure_service.get_vault_key(vault_uri, key_name):
                    self._azure_service.create_vault_key(vault_uri, key_name)
                    LOGGER.info(f"Created key: {key_name}")

            key_number = (hash(test_id) % 3) + 1
            key_uri = f"{vault_uri}keys/scylla-key-{key_number}"
            return {
                'identity_id': self._get_managed_identity_id(),
                'vault_uri': vault_uri,
                'key_uri': key_uri
            }
        except Exception as e:  # noqa: BLE001
            LOGGER.warning(f"Failed to setup Azure KMS: {e}")
            return None
