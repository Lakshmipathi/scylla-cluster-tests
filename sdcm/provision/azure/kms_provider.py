
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

    def __init__(self, resource_group_name: str, region: str, az: str, azure_service: AzureService = AzureService()):
        self._resource_group_name = resource_group_name
        self._region = region
        self._az = az
        self._azure_service = azure_service
        self._kms_config = KeyStore().get_azure_kms_config()

    def _get_managed_identity_id(self) -> str:
        return f"/subscriptions/{self._azure_service.subscription_id}/resourcegroups/{self._kms_config['resource_group']}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{self._kms_config['identity_name']}"

    def get_or_create_keyvault_and_identity(self):
        """Return managed identity info for VM attachment"""
        try:
            vault_info = {
                'identity_id': self._get_managed_identity_id()
            }
            LOGGER.info(f"Returning managed identity for VM attachment")
            return vault_info
        except Exception as e:  # noqa: BLE001
            LOGGER.warning(f"Failed to get managed identity info: {e}")
            return None
