#!/usr/bin/env python

import time
from sdcm.tester import ClusterTester
from sdcm.nemesis import StorageUtilizationNemesis
from sdcm.utils.common import skip_optional_stage


class StorageUtilizationNemesisTest(ClusterTester):
    """
    Uses StorageUtilizationNemesis to reach 93% storage and
    sleeps for 1 hour and performs configured node operation (add/remove)
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_time = time.time()

    def test_storage_utilization_nemesis(self):
        # Add the nemesis to the cluster
        self.log.info('Starting nemesis to fill storage')
        self.db_cluster.add_nemesis(nemesis=self.get_nemesis_class(), tester_obj=self)

        # Start the nemesis once to fill storage
        self.db_cluster.nemesis[0].disrupt()

        # Wait until we reach target storage
        target_usage = 93
        current_usage = self.get_current_storage_usage()
        while current_usage < target_usage:
            self.log.info(f'Current storage usage: {current_usage}%, waiting to reach {target_usage}%')
            time.sleep(30)  # Check every 30 seconds
            current_usage = self.get_current_storage_usage()

        self.log.info(f'Target storage of {target_usage}% reached. Sleeping for 1 hour...')
        self.get_current_storage_usage()
        time.sleep(3600)  # Sleep for 1 hour
        self.get_current_storage_usage()

        # Perform configured node operation
        storage_action = self.params.get('storage_nemesis_action')
        stress_queue = None
        if storage_action:
            stress_queue = self.run_stress_thread(stress_cmd=self.params.get('stress_cmd'), stress_num=1, keyspace_num=1)
            self.log.info('30min write load started.')
            time.sleep(180)
            self.log.info(f'Performing storage action: {storage_action}')
            if storage_action == 'add_node':
                self.add_new_node()
            elif storage_action == 'remove_node':
                self.remove_node()
            else:
                self.log.warning(f'Unknown storage action: {storage_action}')
            time.sleep(1800)
            self.get_current_storage_usage()

        # Wait for stress threads if they were started
        if stress_queue:
            self.verify_stress_thread(cs_thread_pool=stress_queue)
            self.get_stress_results(queue=stress_queue)

    def add_new_node(self):
        """
        Add a new node to the cluster
        """
        self.log.info('Adding new node to the cluster')
        new_node = self.db_cluster.add_nodes(count=1, enable_auto_bootstrap=True)[0]
        self.db_cluster.wait_for_init(node_list=[new_node])
        self.db_cluster.wait_for_nodes_up_and_normal(nodes=[new_node])
        total_nodes_in_cluster = len(self.db_cluster.nodes)
        self.log.info(f"New node added, total nodes in cluster: {total_nodes_in_cluster}")
        self.monitors.reconfigure_scylla_monitoring()

    def remove_node(self):
        """
        Remove a node from the cluster
        """
        self.log.info('Removing a node from the cluster')

    def get_current_storage_usage(self):
        """
        Helper method to get current storage usage across all nodes
        """
        max_usage = 0
        for node in self.db_cluster.nodes:
            result = node.remoter.run("df -h --output=pcent /var/lib/scylla | sed 1d | sed 's/%//'")
            usage = int(result.stdout.strip())
            max_usage = max(max_usage, usage)
            self.log.info(f"Node {node.name} storage usage: {usage}%")
        return max_usage

    def setUp(self):
        super().setUp()
        self.log.info('Initial storage usage:')
        self.get_current_storage_usage()
