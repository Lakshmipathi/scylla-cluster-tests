#!/usr/bin/env python

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

from sdcm.tester import ClusterTester
from sdcm import nemesis

class ScyllaDumpDiagnosis(ClusterTester):

    def test_diagnosis_data(self):  # pylint: disable=invalid-name
        # populates 50GB
        write_queue = self.populate_data_parallel(50, blocking=False)
        self.db_cluster.wait_total_space_used_per_node(10 * (1024 ** 3))  # calculates 10gb in bytes

        # Send SIGQUIT
        current_nemesis = nemesis.ScyllaDumpDiagnosis(
            tester_obj=self, termination_event=self.db_cluster.nemesis_termination_event)
        current_nemesis.disrupt()

