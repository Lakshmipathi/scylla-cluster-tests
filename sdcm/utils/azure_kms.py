import logging
from datetime import datetime, timedelta
from sdcm.utils.azure_utils import AzureService
from sdcm.keystore import KeyStore

LOGGER = logging.getLogger(__name__)


class AzureKms:
    def __init__(self, region: str):
        self.region = region
        self.azure_service = AzureService()
        self._kms_config = KeyStore().get_azure_kms_config()
        self.vault_name = f"{self._kms_config['shared_vault_name']}-{region}"
        self.vault_uri = f"https://{self.vault_name}.vault.azure.net/"

    def ensure_shared_infrastructure(self):
        try:
            self._get_or_create_vault()
            self._get_or_create_keys()
            LOGGER.info(f"Azure KMS infrastructure ready: {self.vault_uri}")
            return True
        except Exception as e:
            LOGGER.error(f"Failed to ensure Azure KMS infrastructure: {e}")
            return False

    def _get_or_create_vault(self):
        try:
            vault = self.azure_service.keyvault.vaults.get(
                resource_group_name=self._kms_config["resource_group"],
                vault_name=self.vault_name
            )
            LOGGER.info(f"Using existing vault: {self.vault_name}")
            return vault
        except Exception:
            pass

        vault = self.azure_service.keyvault.vaults.begin_create_or_update(
            resource_group_name=self._kms_config["resource_group"],
            vault_name=self.vault_name,
            parameters={
                "location": self.region,
                "properties": {
                    "tenant_id": self.azure_service.azure_credentials["tenant_id"],
                    "sku": {"name": "standard", "family": "A"},
                    "enabled_for_disk_encryption": True,
                    "enable_rbac_authorization": False,
                    "access_policies": [{
                        "tenant_id": self.azure_service.azure_credentials["tenant_id"],
                        "object_id": self._kms_config["managed_identity_principal_id"],
                        "permissions": {
                            "keys": ["get", "encrypt", "decrypt", "wrapKey", "unwrapKey"],
                            "secrets": ["get"],
                            "certificates": ["get"]
                        }
                    }, {
                        "tenant_id": self.azure_service.azure_credentials["tenant_id"],
                        "object_id": self._kms_config["sct_service_principal_id"],
                        "permissions": {
                            "keys": ["create", "get", "list", "update", "import", "delete"],
                            "secrets": ["get"],
                            "certificates": ["get"]
                        }
                    }]
                }
            }
        ).result()
        LOGGER.info(f"Created vault: {self.vault_name}")
        return vault

    def _get_or_create_keys(self):
        for i in range(1, self._kms_config["num_of_keys"] + 1):
            key_name = f"scylla-key-{i}"
            existing_key = self.azure_service.get_vault_key(self.vault_uri, key_name)
            if not existing_key:
                self.azure_service.create_vault_key(self.vault_uri, key_name)
                LOGGER.info(f"Created key: {key_name}")
            else:
                LOGGER.info(f"Using existing key: {key_name}")

    def get_key_for_test(self, test_id: str) -> str:
        key_number = (hash(test_id) % self._kms_config["num_of_keys"]) + 1
        key_name = f"scylla-key-{key_number}"
        return f"{self.vault_uri}keys/{key_name}"

    def should_rotate_key(self, key_name: str, test_id: str) -> bool:
        """Check if key needs rotation based on tags coordination"""
        key_info = self.azure_service.get_vault_key(self.vault_uri, key_name)

        if not key_info or not key_info.get('tags'):
            LOGGER.info(f"Key {key_name} has no tags, rotation needed")
            return True

        tags = key_info['tags']
        rotating_job = tags.get('rotating_job')
        last_rotation = tags.get('last_rotation')

        if rotating_job and rotating_job != test_id:
            LOGGER.info(f"Key {key_name} is being rotated by job {rotating_job}, skipping")
            return False

        if last_rotation:
            try:
                last_time = datetime.fromisoformat(last_rotation.replace('Z', '+00:00'))
                time_since_rotation = datetime.now(last_time.tzinfo) - last_time
                if time_since_rotation < timedelta(hours=1):
                    LOGGER.info(f"Key {key_name} was rotated {time_since_rotation} ago, skipping")
                    return False
            except (ValueError, TypeError) as e:
                LOGGER.warning(f"Invalid last_rotation timestamp for {key_name}: {e}")

        return True

    def rotate_kms_key(self, test_id: str) -> str:
        current_key_uri = self.get_key_for_test(test_id)
        key_name = current_key_uri.split('/')[-1]

        if not self.should_rotate_key(key_name, test_id):
            return current_key_uri

        lock_tags = {
            'rotating_job': test_id,
            'rotation_started': datetime.now().isoformat()
        }
        if not self.azure_service.update_key_tags(self.vault_uri, key_name, lock_tags):
            LOGGER.error(f"Failed to set rotation lock for {key_name}")
            return current_key_uri

        try:
            self.azure_service.create_vault_key(self.vault_uri, key_name)
            LOGGER.info(f"Rotated key {key_name} to new version for test {test_id}")

            completion_tags = {
                'last_rotation': datetime.now().isoformat(),
                'rotated_by': test_id,
                'rotating_job': None
            }
            self.azure_service.update_key_tags(self.vault_uri, key_name, completion_tags)

        except Exception as e:
            clear_lock_tags = {'rotating_job': None}
            self.azure_service.update_key_tags(self.vault_uri, key_name, clear_lock_tags)
            raise e

        return current_key_uri
