from threading import Thread
import time
from sdcm.tester import ClusterTester
from sdcm.utils.common import FileFollowerThread
from sdcm.cluster import MAX_TIME_WAIT_FOR_NEW_NODE_UP

class DFOutputThread(FileFollowerThread):
    def __init__(self, node, interval=30):
        super().__init__()
        self.node = node
        self.interval = interval

    def run(self):
        while True:
            df_output = self.node.remoter.run('df -h').stdout
            self.log.info(f"DF output for node {self.node.name}:\n{df_output}")
            time.sleep(self.interval)

class DFTest(ClusterTester):
    def test_df_output(self):
        self.log.info("Running df command on all nodes:")
        self.get_df_output()
        
        # run stress command
        stress_cmd = 'cassandra-stress write cl=ONE n=10000000 -schema "replication(factor=3)" ' \
                         '-mode cql3 native -rate threads=10 -pop seq=1..10000000 ' \
                         '-col "size=FIXED(10000) n=FIXED(1)"'

        stress_queue = self.run_stress_thread(stress_cmd=stress_cmd,
                                              stress_num=1, keyspace_num=1)
        # TODO:FIX this part: Start threads for each node
        df_threads = []
        for node in self.db_cluster.nodes:
            df_thread = DFOutputThread(node)
            df_thread.start()
            df_threads.append(df_thread)

        # wait for stress cmd
        self.verify_stress_thread(cs_thread_pool=stress_queue)

        # Stop df threads
        for df_thread in df_threads:
            df_thread.stop()

        self.get_stress_results(queue=stress_queue)

        self.log.info("After stress test, running df command on all nodes:")
        self.get_df_output()

        # Add new node
        self.add_new_node()

        self.log.info("running df command on all nodes including the new node")
        self.get_df_output()

    def add_new_node(self):
        new_nodes = self.db_cluster.add_nodes(count=1, enable_auto_bootstrap=True)
        self.monitors.reconfigure_scylla_monitoring()
        new_node = new_nodes[0]
        self.db_cluster.wait_for_init(node_list=[new_node], timeout=MAX_TIME_WAIT_FOR_NEW_NODE_UP,check_node_health=False)
        self.db_cluster.wait_for_nodes_up_and_normal(nodes=[new_node])
        self.log.info("New node added")

    def get_df_output(self):
        for node in self.db_cluster.nodes:
            result = node.remoter.run('df -h /var/lib/scylla')
            self.log.info(f"DF output for node {node.name}:\n{result.stdout}")
