from enum import Enum
import time
from sdcm.tester import ClusterTester
from sdcm.utils.full_storage_utils import DiskUtils, StressUtils
from sdcm.utils.tablets.common import wait_for_tablets_balanced

class ScalingActionType(Enum):
    SCALE_OUT = "scale_out"
    SCALE_IN = "scale_in"

class FullStorageUtilizationTest(ClusterTester):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sleep_time_fill_disk = 1800
        self.total_large_ks = 0
        self.total_small_ks = 0
        self.softlimit = self.params.get('diskusage_softlimit')
        self.hardlimit = self.params.get('diskusage_hardlimit')
        self.stress_cmd_w = self.params.get('stress_cmd_w')
        self.stress_cmd_r = self.params.get('stress_cmd_r')
        self.add_node_cnt = self.params.get('add_node_cnt')
        self.scaling_action_type = self.params.get('scaling_action_type')

    def setUp(self):
        super().setUp()
        self.start_time = time.time()
        # Initialize num_stress_threads
        self.num_stress_threads = StressUtils.calculate_stress_threads(self.db_cluster.nodes[0])

    def start_throttle_write(self):
        self.stress_cmd_w = self.stress_cmd_w.replace("<THREADS_PLACE_HOLDER>", str(self.num_stress_threads))
        self.run_stress_thread(stress_cmd=self.stress_cmd_w)
        self.metric_has_data(metric_query='sct_cassandra_stress_write_gauge{type="ops", keyspace="keyspace1"}', n=5)


    def start_throttle_read(self):
        self.stress_cmd_r = self.stress_cmd_r.replace("<THREADS_PLACE_HOLDER>", str(self.num_stress_threads))
        self.run_stress_thread(stress_cmd=self.stress_cmd_r)
        self.metric_has_data(metric_query='sct_cassandra_stress_write_gauge{type="ops", keyspace="keyspace1"}', n=5)

    def start_throttle_rw(self):
        self.start_throttle_write()
        self.start_throttle_read()
        
    def scale_out(self):
        self.start_throttle_rw()
        self.log.info("Started adding a new node")
        start_time = time.time()
        self.add_new_node()
        duration = time.time() - start_time
        self.log.info(f"Adding a node finished with time: {duration}")

    def scale_in(self):        
        self.start_throttle_rw()
        self.log.info("Started removing a node")
        start_time = time.time()
        self.remove_node()
        duration = time.time() - start_time
        self.log.info(f"Removing a node finished with time: {duration}")

    def drop_data(self, keyspace_name):
        """Drop keyspace and clear snapshots."""
        node = self.db_cluster.nodes[0]
        self.log.info("Dropping some data")
        query = f"DROP KEYSPACE {keyspace_name}"
        with self.db_cluster.cql_connection_patient(node) as session:
            session.execute(query)
        DiskUtils.log_disk_usage(self.db_cluster.nodes, self.log)     

    def perform_scale_in(self):
        """
        Scale in handling based on hardlimit threshold.
        At 90% utilization: scale out, drop data, then scale in.
        At 67% utilization: directly scale in.
        """
        if self.hardlimit == 90:
            self.scale_out()           
            # Remove 20% of data from the cluster
            self.drop_data("keyspace_large1")
            self.drop_data("keyspace_large2")
            self.scale_in()
        elif self.hardlimit == 27:
            self.scale_in()

    def perform_action(self):
        DiskUtils.log_disk_usage(self.db_cluster.nodes, self.log)
        if self.scaling_action_type == ScalingActionType.SCALE_OUT.value:
            self.scale_out()
        elif self.scaling_action_type == ScalingActionType.SCALE_IN.value:
            self.perform_scale_in()
        else:
            self.log.info(f"Invalid ActionType {self.scaling_action_type}")
        DiskUtils.log_disk_usage(self.db_cluster.nodes, self.log)     

    def test_storage_utilization(self):
        """
        Write data until disk usage reaches target, then perform scaling action.
        """
        self.run_stress(self.softlimit, sleep_time=self.sleep_time_fill_disk)
        self.run_stress(self.hardlimit, sleep_time=self.sleep_time_fill_disk)
        self.perform_action()        

    def run_stress(self, target_usage, sleep_time=600):
        target_used_size = DiskUtils.calculate_target_used_size(
            self.db_cluster.nodes, target_usage, self.log)
        StressUtils.run_stress_until_target(self, target_used_size, target_usage)

        DiskUtils.log_disk_usage(self.db_cluster.nodes, self.log)
        self.log.info(f"Wait for {sleep_time} seconds")
        time.sleep(sleep_time)  
        DiskUtils.log_disk_usage(self.db_cluster.nodes, self.log)

    def add_new_node(self):
        new_nodes = self.db_cluster.add_nodes(count=self.add_node_cnt, enable_auto_bootstrap=True)
        self.db_cluster.wait_for_init(node_list=new_nodes)
        self.db_cluster.wait_for_nodes_up_and_normal(nodes=new_nodes)
        total_nodes_in_cluster = len(self.db_cluster.nodes)
        self.log.info(f"New node added, total nodes in cluster: {total_nodes_in_cluster}")
        self.monitors.reconfigure_scylla_monitoring()
        wait_for_tablets_balanced(self.db_cluster.nodes[0])
        
    def remove_node(self):  
        self.log.info('Removing a second node from the cluster')
        node_to_remove = self.db_cluster.nodes[1]
        self.log.info(f"Node to be removed: {node_to_remove.name}")
        self.db_cluster.decommission(node_to_remove)
        self.log.info(f"Node {node_to_remove.name} has been removed from the cluster")
        self.monitors.reconfigure_scylla_monitoring()
        wait_for_tablets_balanced(self.db_cluster.nodes[0])
