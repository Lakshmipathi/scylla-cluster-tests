#!/usr/bin/env python

from sdcm.tester import ClusterTester
from sdcm.utils import loader_utils
import time
import json
import os

class SimpleLongevityTest(ClusterTester, loader_utils.LoaderUtilsMixin):
    """
    A simplified longevity test that runs a basic stress test for a specified duration.
    """

    # GCP credentials for the test
    GCP_CREDENTIALS = {
          "type": "service_account",
          "project_id": "scylla-kms-test-462610",
          "private_key_id": "cf4ceed77883015ec99a1cbaf61b64f44fc21a81",
          "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC/akiIEbFsRxVP\nWnOEosE2GvzaQlLsql04M1qhSHcUOcyqCG7pCgkQ9o8CxEt992gy0IPzp4uikwBv\n5X+1OescjhRnm2Tv77nmtV6LF+VWurvuzUG+Fz//TWC1Vs6wZGjiNZxcwgBEpn4i\nQ/VPRRcxuxeiot8tZF4RZtjDiQ6usM88sJayPKp4Y3XpK481oHNpgD8LuamFBHjg\nlPbj34QvkXFrush6o3TQNFSJ3o4227Snuo0KLFnQC7HIkm4TAPTIfBMD7aEB8QyJ\n84wnmnEHsVpTP7K0w4Vj5RnYWuxlmMfb7WBlQdlC5GNIGH2WCNHNn9rTH8YBeNVE\np0GpfqPfAgMBAAECggEAPKK1/EiijBrOcNdF3b/S9clBzQASlb74DbwS2yGB+0m+\nACTwwWi464M3VViKU4qCmwo7qn0qOiNYEZpBRM7moCKP6ywqIumtWZydqPE2aK15\nqBGkYEusLbs8xeUMT4tXQEVcVXPtMtINBdzCQkywJsROHep7ST1QoTGTvAlYOdTj\nSpm7lwU0I/3tg3HbtlxR6WNBbBvuckGmCqxD2Ryrl3n4gPDhnhOXzfAf6jtlpqJZ\nf1Kgzko7C4UuNrYAVUoXgHmj5kprZZZPE2LVmt5q+SIil3anrjMFsdGdBUWsGrfa\nkOiRO1V26Pq7XpqNRbiCS/BFUBFdapggTCjGCsAYdQKBgQDmxicLb2FPFSlyxQVw\naUebafijHiHgpsWH/tmuru4mXuhzhKuosnWQDgqAB7iXDuT6GEe+Zvao5XjWJdVM\n2eNa/OJHJDy6tKGhs1zlhbIVsvCOfA4ijppQnwj3OuZce2jbD6tg8qNEI2nB8vhA\nvA1A+7fX5w4JrvEqVUWlhudyQwKBgQDUVrwsVUnK28GWKqYj052nddnPhFev1Wv6\nBXUJolT2WvJTPbk5lENApkV0H8Eo+sUv2HcwdhPRznMlR0a7afQznnFHJIA2zjko\nXW+6VcZsakm+Jt/LMTUG3LqogfXypr4i3EMOfJrxG4mYit898H7txcJi13fM6IGt\nFun4kzJUNQKBgQDf/t3PH6EYHbZJjCsnXUj/9PA9g/XmFHoO8rNf9rN50w1VcyUb\nbXznAnn2o4fsN6zRg9e/XDl23qVXVwmeuq8Plf4ch3Pa1ZE9XteAgTDGFxWfd5JQ\nwJHQR01wi18lzTONzbvPMjR+4tC4TJniW6WRucJMch0SERhMutALRtJH+QKBgQC8\nfhZjAH8WHkhWBpwfV54u5tYoeeHhTAKjGq8Pk1P6sTdGH5fKfkvJGxCyifHNb/cV\nhwIfOeJUMAFVSVWHzwGhxPfn4IYUoLJqm68v6S7QVPYLX7TwSkk5Qz5LkbqD4fMN\nPRwlwwVEHV7i0/xinpf+eLwbRAysEIX04k9mgzx9NQKBgEQZluTgviLCYKgZcEXU\n92c+6C2awpAef8HpiEAhGpvdKnyWoNuSucw3420eD6MFD2Akyf18bv8YSFu/Hd5P\nahhwEdBg/        ldWSRjQE2zOvwNcSye2Eq25Sbotv+zkTYfuUilw7o8L2j8NMes/389O\nUtTGsm4MbQz5GViwChEajUyR\n-----END PRIVATE KEY-----\n",
          "client_email": "kms-demo-sa@scylla-kms-test-462610.iam.gserviceaccount.com",
          "client_id": "113836359378587064572",
          "auth_uri": "https://accounts.google.com/o/oauth2/auth",
          "token_uri": "https://oauth2.googleapis.com/token",
          "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
          "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/kms-demo-sa%40scylla-kms-test-462610.iam.gserviceaccount.com",
          "universe_domain": "googleapis.com"
    }

    def setUp(self):
        super().setUp()
        self.setup_gcp_credentials()

    def setup_gcp_credentials(self):
        """Setup GCP credentials file on all nodes."""
        # Create credentials file on all nodes
        for node in self.db_cluster.nodes:
            remote_path = '/etc/scylla/gcp_auth_file.json'
            temp_path = '/tmp/gcp_auth_file.json'
            with node.remoter.create_file(temp_path) as f:
                f.write(json.dumps(self.GCP_CREDENTIALS, indent=2))
            node.remoter.sudo(f'mv {temp_path} {remote_path}')
            node.remoter.sudo(f'chmod 444 {remote_path}')

    def test_simple_longevity(self):
        """
        Run a simple stress test for the duration specified in the test configuration.
        """
        # Get stress command from test configuration
        stress_cmd = self.params.get('stress_cmd')
        if not stress_cmd:
            self.log.error("No stress command found in test configuration")
            return

        # Run the stress command
        self.run_stress_thread(stress_cmd=stress_cmd[0])

        # Wait for the test duration
        self.wait_for_test_duration()

    def wait_for_test_duration(self):
        """Wait for the test duration specified in the configuration."""
        test_duration = self.params.get('test_duration', 900) // 60  # Convert seconds to minutes
        self.log.info("Waiting for test duration: %d minutes", test_duration)
        time.sleep(test_duration * 60)
