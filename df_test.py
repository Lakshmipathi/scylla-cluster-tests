import time
from sdcm.tester import ClusterTester
from sdcm.cluster import MAX_TIME_WAIT_FOR_NEW_NODE_UP

class DFTest(ClusterTester):
    def test_df_output(self):
        self.log.info("Running df command on all nodes:")
        self.get_df_output()
        
        stress_cmd = 'cassandra-stress write cl=ONE n=10000000 -schema "replication(factor=3)" ' \
                     '-mode cql3 native -rate threads=10 -pop seq=1..10000000 ' \
                     '-col "size=FIXED(10000) n=FIXED(1)"'

        self.run_stress_and_add_nodes(stress_cmd)

        '''
        Add 4th node after 25% disk usage.
        Add 5th node after 50% disk usage.
        Add 6th node after 75% disk usage.
        '''
    def run_stress_and_add_nodes(self, stress_cmd):
        target_disk_usages = [25, 50, 75]
        current_disk_target = 0
        
        while len(self.db_cluster.nodes) < 6:
            stress_queue = self.run_stress_thread(stress_cmd=stress_cmd, stress_num=1, keyspace_num=1)
            self.verify_stress_thread(cs_thread_pool=stress_queue)
            self.get_stress_results(queue=stress_queue)

            usage = self.get_max_disk_usage()
            self.log.info(f"Current max disk usage: {usage}%")

            if current_disk_target < len(target_disk_usages) and usage >= target_disk_usages[current_disk_target]:
                self.add_new_node()
                current_disk_target += 1
                
        # Run stress command one final time on a 6-node cluster 
        stress_queue = self.run_stress_thread(stress_cmd=stress_cmd, stress_num=1, keyspace_num=1)
        self.verify_stress_thread(cs_thread_pool=stress_queue)
        self.get_stress_results(queue=stress_queue)
        self.get_df_output()

    def add_new_node(self):
        self.get_df_output()
        new_nodes = self.db_cluster.add_nodes(count=1, enable_auto_bootstrap=True)
        self.monitors.reconfigure_scylla_monitoring()
        new_node = new_nodes[0]
        self.db_cluster.wait_for_init(node_list=[new_node], timeout=MAX_TIME_WAIT_FOR_NEW_NODE_UP, check_node_health=False)
        self.db_cluster.wait_for_nodes_up_and_normal(nodes=[new_node])
        total_nodes_in_cluster = len(self.db_cluster.nodes)
        self.log.info(f"New node added, total nodes in cluster: {total_nodes_in_cluster}")
        self.get_df_output()

    def get_df_output(self):
        for node in self.db_cluster.nodes:
            result = node.remoter.run('df -h /var/lib/scylla')
            self.log.info(f"DF output for node {node.name}:\n{result.stdout}")

    def get_max_disk_usage(self):
        max_usage = 0
        for node in self.db_cluster.nodes:
            result = node.remoter.run("df -h /var/lib/scylla | sed 1d | awk '{print $5}' | sed 's/%//'")
            usage = int(result.stdout.strip())
            max_usage = max(max_usage, usage)
        return max_usage

    def get_email_data(self):
        self.log.info("Prepare data for email")
        grafana_dataset = {}

        email_data = self._get_common_email_data()

        try:
            grafana_dataset = self.monitors.get_grafana_screenshot_and_snapshot(
                self.start_time) if self.monitors else {}
        except Exception as error:  # pylint: disable=broad-except
            self.log.exception("Error in gathering Grafana screenshots and snapshots. Error:\n%s",
                               error, exc_info=error)

        benchmarks_results = self.db_cluster.get_node_benchmarks_results() if self.db_cluster else {}

        email_data.update({"grafana_screenshots": grafana_dataset.get("screenshots", []),
                           "grafana_snapshots": grafana_dataset.get("snapshots", []),
                           "node_benchmarks": benchmarks_results,
                           "scylla_ami_id": self.params.get("ami_id_db_scylla") or "-", })
        return email_data
