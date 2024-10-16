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
        target_usage = 35
        target_used_size = self.calculate_target_used_size(target_usage)
        self.run_stress_until_target(target_used_size)

        self.log.info("Wait for 10 minutes")
        time.sleep(600)  

        self.log.info("Adding a new node")
        self.add_new_node()

    def run_stress_until_target(self, target_used_size):
        current_used = self.get_max_disk_used()
        num = 0
        while current_used < target_used_size:
            num += 1
            
            stress_queue = self.run_stress_thread(stress_cmd=self.stress_cmd_10gb, stress_num=1, keyspace_num=num)
            self.verify_stress_thread(cs_thread_pool=stress_queue)
            self.get_stress_results(queue=stress_queue)

            current_used = self.get_max_disk_used()
            current_usage = self.get_max_disk_usage()
            self.log.info(f"Current max disk usage after writing to keyspace{num}: {current_usage}% ({current_used:.2f} GB / {target_used_size:.2f} GB)")

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
            result = node.remoter.run("df -h --output=pcent /var/lib/scylla | sed 1d | sed 's/%//'")
            usage = float(result.stdout.strip())
            max_usage = max(max_usage, usage)
        return max_usage

    def get_max_disk_used(self):
        max_used = 0
        for node in self.db_cluster.nodes:
            result = node.remoter.run("df -h --output=used /var/lib/scylla | sed 1d | sed 's/G//'")
            used = float(result.stdout.strip())
            max_used = max(max_used, used)
        return max_used

    def get_disk_info(self, node):
        result = node.remoter.run("df -h --output=size,used,avail,pcent /var/lib/scylla | sed 1d")
        size, used, avail, pcent = result.stdout.strip().split()
        return {
            'total': float(size.rstrip('G')),
            'used': float(used.rstrip('G')),
            'available': float(avail.rstrip('G')),
            'used_percent': float(pcent.rstrip('%'))
        }

    def calculate_target_used_size(self, target_percent):
        max_total = 0
        for node in self.db_cluster.nodes:
            info = self.get_disk_info(node)
            max_total = max(max_total, info['total'])
        
        target_used_size = (target_percent / 100) * max_total
        current_used = self.get_max_disk_used()
        additional_usage_needed = target_used_size - current_used

        self.log.info(f"Current max disk usage: {self.get_max_disk_usage():.2f}%")
        self.log.info(f"Current max used space: {current_used:.2f} GB")
        self.log.info(f"Max total disk space: {max_total:.2f} GB")
        self.log.info(f"Target used space to reach {target_percent}%: {target_used_size:.2f} GB")
        self.log.info(f"Additional space to be used: {additional_usage_needed:.2f} GB")

        return target_used_size

