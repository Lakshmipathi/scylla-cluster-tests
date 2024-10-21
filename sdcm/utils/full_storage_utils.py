class DiskUtils:
    @staticmethod
    def get_disk_info(node):
        """Get disk usage information for a specific node."""
        result = node.remoter.run("df -h -BG --output=size,used,avail,pcent /var/lib/scylla | sed 1d | sed 's/G//g' | sed 's/%//'")
        size, used, avail, pcent = result.stdout.strip().split()
        return {
            'total': int(size),
            'used': int(used),
            'available': int(avail),
            'used_percent': int(pcent)
        }

    @staticmethod
    def get_max_disk_usage(nodes):
        """Get maximum disk usage across all nodes."""
        max_usage = 0
        max_used = 0
        for node in nodes:
            info = DiskUtils.get_disk_info(node)
            max_usage = max(max_usage, info["used_percent"])
            max_used = max(max_used, info["used"])
        return max_usage, max_used

    @staticmethod
    def calculate_target_used_size(nodes, target_percent, logger):
        """Calculate target disk usage size based on percentage."""
        max_total = 0
        for node in nodes:
            info = DiskUtils.get_disk_info(node)
            max_total = max(max_total, info['total'])
        
        target_used_size = (target_percent / 100) * max_total
        current_usage, current_used = DiskUtils.get_max_disk_usage(nodes)
        additional_usage_needed = target_used_size - current_used

        logger.info(f"Current max disk usage: {current_usage:.2f}%")
        logger.info(f"Current max used space: {current_used:.2f} GB")
        logger.info(f"Max total disk space: {max_total:.2f} GB")
        logger.info(f"Target used space to reach {target_percent}%: {target_used_size:.2f} GB")
        logger.info(f"Additional space to be used: {additional_usage_needed:.2f} GB")

        return target_used_size

    @staticmethod
    def log_disk_usage(nodes, logger):
        """Log disk usage information for all nodes."""
        for node in nodes:
            info = DiskUtils.get_disk_info(node)
            logger.info(f"Disk usage for node {node.name}:")
            logger.info(f"  Total: {info['total']} GB")
            logger.info(f"  Used: {info['used']} GB")
            logger.info(f"  Available: {info['available']} GB")
            logger.info(f"  Used %: {info['used_percent']}%")


class StressUtils:
    @staticmethod
    def calculate_stress_threads(node):
        """Calculate number of stress threads based on CPU cores."""
        cores = node.cpu_cores
        if not cores:
            return 10
        return int(cores) * 8

    @staticmethod
    def prepare_dataset_layout(dataset_size, num_threads, row_size=10240):
        """Prepare cassandra-stress command for dataset layout."""
        n = dataset_size * 1024 * 1024 * 1024 // row_size
        seq_end = n * 100

        return f'cassandra-stress write cl=ONE n={n} -mode cql3 native -rate threads={num_threads} ' \
               f'-pop dist="uniform(1..{seq_end})" ' \
               f'-col "size=FIXED({row_size}) n=FIXED(1)" ' \
               f'-schema "replication(strategy=NetworkTopologyStrategy,replication_factor=3)"'

    @staticmethod
    def run_stress_until_target(cluster_tester, target_used_size, target_usage):
        """Run stress test until target disk usage is reached."""
        current_usage, current_used = DiskUtils.get_max_disk_usage(cluster_tester.db_cluster.nodes)
        smaller_dataset = False
        
        space_needed = target_used_size - current_used
        # Calculate chunk size as 10% of space needed
        chunk_size = int(space_needed * 0.1)
        
        while current_used < target_used_size and current_usage < target_usage:
            # Write smaller dataset near the threshold (15% or 30GB of the target)
            smaller_dataset = (((target_used_size - current_used) < 30) or 
                             ((target_usage - current_usage) <= 15))
            
            if not smaller_dataset:
                cluster_tester.total_large_ks += 1
            else:
                cluster_tester.total_small_ks += 1

            # Use 1GB chunks near threshold, otherwise use 10% of remaining space
            dataset_size = 1 if smaller_dataset else chunk_size
            ks_name = "keyspace_small" if smaller_dataset else "keyspace_large"
            num = cluster_tester.total_small_ks if smaller_dataset else cluster_tester.total_large_ks
            
            cluster_tester.log.info(f"Writing chunk of size: {dataset_size} GB")
            stress_cmd = StressUtils.prepare_dataset_layout(dataset_size, cluster_tester.num_stress_threads)
            stress_queue = cluster_tester.run_stress_thread(
                stress_cmd=stress_cmd,
                keyspace_name=f"{ks_name}{num}",
                stress_num=1,
                keyspace_num=num
            )

            cluster_tester.verify_stress_thread(cs_thread_pool=stress_queue)
            cluster_tester.get_stress_results(queue=stress_queue)

            cluster_tester.db_cluster.flush_all_nodes()

            current_usage, current_used = DiskUtils.get_max_disk_usage(cluster_tester.db_cluster.nodes)
            cluster_tester.log.info(
                f"Current max disk usage after writing to keyspace{num}: "
                f"{current_usage}% ({current_used} GB / {target_used_size} GB)"
            )
