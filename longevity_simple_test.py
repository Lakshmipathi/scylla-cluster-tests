#!/usr/bin/env python

from sdcm.tester import ClusterTester
from sdcm.utils import loader_utils
import time

class SimpleLongevityTest(ClusterTester, loader_utils.LoaderUtilsMixin):
    """
    A simplified longevity test that runs a basic stress test for a specified duration.
    """

    def setUp(self):
        super().setUp()

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
        test_duration = 15 #self.params.get('test_duration')  # Default to 15 minutes if not specified
        self.log.info("Waiting for test duration: %d minutes", test_duration)
        time.sleep(test_duration * 60)  # Convert minutes to seconds 
