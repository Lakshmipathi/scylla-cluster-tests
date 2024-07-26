from sdcm.tester import ClusterTester

class DFTest(ClusterTester):
    def test_df_output(self):
        self.log.info("Running df command on all nodes")
        for node in self.db_cluster.nodes:
            result = node.remoter.run('df -h')
            self.log.info(f"DF output for node {node.name}:\n{result.stdout}")

