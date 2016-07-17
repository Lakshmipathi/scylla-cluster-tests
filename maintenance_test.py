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
# Copyright (c) 2016 ScyllaDB

import time

from avocado import main

from sdcm.tester import ClusterTester
from sdcm.nemesis import DrainerMonkey
from sdcm.nemesis import CorruptThenRepairMonkey
from sdcm.nemesis import CorruptThenRebuildMonkey


class MaintainanceTest(ClusterTester):

    """
    Test a Scylla cluster maintenance operations.

    :avocado: enable
    """

    def _base_procedure(self, nemesis_class):
        stress_queue = self.run_stress_thread(duration=240)
        self.db_cluster.wait_total_space_used_per_node()
        self.db_cluster.add_nemesis(nemesis_class)
        # Wait another 10 minutes
        time.sleep(10 * 60)
        self.db_cluster.start_nemesis(interval=10)
        time.sleep(180 * 60)
        # Kill c-s when done
        self.kill_stress_thread()
        self.verify_stress_thread(queue=stress_queue)

    def test_drain(self):
        """
        Drain a node an restart it.
        """
        self._base_procedure(DrainerMonkey)

    def test_repair(self):
        """
        Repair a node
        """
        self._base_procedure(CorruptThenRepairMonkey)

    def test_rebuild(self):
        """
        Rebuild all nodes
        """
        self._base_procedure(CorruptThenRebuildMonkey)


if __name__ == '__main__':
    main()
