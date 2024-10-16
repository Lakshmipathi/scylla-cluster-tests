import time
from sdcm.tester import ClusterTester
from sdcm.cluster import MAX_TIME_WAIT_FOR_NEW_NODE_UP

class DFTest(ClusterTester):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # write 10GB of data
        self.stress_cmd_10gb = 'cassandra-stress write cl=ONE n=1048576 ' \
                               '-mode cql3 native -rate threads=10 -pop seq=1..1048576 ' \
                               '-col "size=FIXED(10240) n=FIXED(1)" ' \
                               '-schema "replication(strategy=NetworkTopologyStrategy,replication_factor=3)" ' 


    def setUp(self):
        super().setUp()
        self.start_time = time.time()

    def test_df_output(self):
        """
        3 nodes cluster, RF=3.
        Write data until 85% disk usage is reached.
        Sleep for 90 minutes.
        Add 4th node.
        """
        self.log.info("Running df command on all nodes:")
        self.get_df_output()
        self.run_stress_and_add_node()

    def run_stress_and_add_node(self):
        table_disk_usages = [30, 30, 25]
        
        for i, usage in enumerate(table_disk_usages, 1):
            self.log.info(f"populating keyspace {i} to reach {usage}% disk usage")
            self.run_stress_until_target(f"ks{i}", usage)

        self.log.info("Wait for 90 minutes")
        time.sleep(5400)  

        self.log.info("Adding a new node")
        self.add_new_node()

    def run_stress_until_target(self, keyspace, target_usage):
        current_usage = self.get_max_disk_usage()
        num = 0
        while current_usage < target_usage:
            num += 1
            stress_queue = self.run_stress_thread(stress_cmd=self.stress_cmd_10gb, stress_num=1, keyspace_num=num)
            self.verify_stress_thread(cs_thread_pool=stress_queue)
            self.get_stress_results(queue=stress_queue)

            current_usage = self.get_max_disk_usage()
            self.log.info(f"Current max disk usage after writing to {keyspace}{num}: {current_usage}%")

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
