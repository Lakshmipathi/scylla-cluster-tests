from __future__ import annotations

import dataclasses
import logging
import random
import threading
import time
import traceback
from dataclasses import dataclass, fields
from typing import Literal, TYPE_CHECKING, get_type_hints, get_origin

from prettytable import PrettyTable

from sdcm import wait

if TYPE_CHECKING:
    from sdcm.cluster import BaseScyllaCluster, BaseCluster


@dataclass
class ConfigParams:
    mode: Literal['random', 'table', 'partition', 'aggregate', 'table_and_aggregate']
    ks_cf: str = "random"
    interval: int = 10
    page_size: int = 10000
    pk_name: str = 'pk'
    ck_name: str = 'ck'
    data_column_name: str = 'v'
    validate_data: bool = False
    include_data_column: bool = False
    rows_count: int = 5000
    full_scan_operation_limit: int = 300  # timeout for SELECT * statement, 5 min by default
    full_scan_aggregates_operation_limit: int = 60*30  # timeout for SELECT count(* statement 30 min by default

    def __post_init__(self):
        types = get_type_hints(ConfigParams)
        errors = []
        for item in fields(ConfigParams):
            expected_type = types[item.name]
            value = getattr(self, item.name)
            if get_origin(expected_type) is Literal:
                if not value in expected_type.__args__:
                    errors.append(
                        f"field '{item.name}' must be one of '{expected_type.__args__}' but got '{value}'")
            elif not isinstance(value, expected_type):
                errors.append(f"field '{item.name}' must be an instance of {expected_type}, but got '{value}'")
        if errors:
            errors = '\n\t'.join(errors)
            raise ValueError(f"Config params validation errors:\n\t{errors}")


@dataclass
class ThreadParams(ConfigParams):
    db_cluster: [BaseScyllaCluster, BaseCluster] = None
    termination_event: threading.Event = None
    user: str = None
    user_password: str = None
    duration: int = None


@dataclass
class OperationThreadStats:
    """
    Keeps track of stats for multiple operations.
    """
    number_of_rows_read: int = 0
    read_pages: int = 0
    scans_counter: int = 0
    time_elapsed: int = 0
    total_thread_time: int = 0
    stats: list[OneOperationStat] = dataclasses.field(default_factory=list)

    def get_stats_pretty_table(self) -> PrettyTable | None:
        if not self.stats:
            return None

        pretty_table = PrettyTable(field_names=[field.name for field in dataclasses.fields(self.stats[0])])
        for stat in self.stats:
            pretty_table.add_row([stat.op_type, stat.duration, "\n".join(stat.exceptions), stat.nemesis_at_start,
                                  stat.nemesis_at_end, stat.success, stat.cmd])
        return pretty_table


@dataclass
class OneOperationStat:
    """
    Keeps track of stats for a single operation.
    """
    op_type: str = None
    duration: float = None
    exceptions: list = dataclasses.field(default_factory=list)
    nemesis_at_start: str = None
    nemesis_at_end: str = None
    success: bool = None
    cmd: str = None


class OperationThread:
    """
    Runs operations according to the parameters specified in the test
    config yaml files.

    Check ThreadParams class for parameters to tweak.

    Note: the seeded random generator is shared between the thread class and
    the operations instances. So if the operations queue is  Op1, Op2, Op3],
    all of them will be initialized with the same random generator instance
    as this thread. This way the CQL commands generated by the instances are
    also replicable.
    """

    def __init__(self, thread_params: ThreadParams, thread_name: str = ""):
        self.thread_params = thread_params
        self.thread_stats = OperationThreadStats()
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.debug("Thread params: %s", thread_params)
        nemesis_seed = self.thread_params.db_cluster.params.get("nemesis_seed")
        if isinstance(nemesis_seed, list):
            nemesis_seed = nemesis_seed[0]
        if isinstance(nemesis_seed, str):
            nemesis_seed = int(nemesis_seed.split()[0])
        self.generator = random.Random(int(nemesis_seed)) if nemesis_seed else random.Random()
        self._thread = threading.Thread(daemon=True, name=f"{self.__class__.__name__}_{thread_name}", target=self.run)
        self.termination_event = thread_params.termination_event

        # create different scan operations objects
        self.operation_params = {
            'generator': self.generator,
            'thread_params': self.thread_params,
            'thread_stats': self.thread_stats}

        # create mapping for different scan operations objects,
        # please see usage in get_next_scan_operation()
        self.operation_instance_map = {}

    def get_next_operation(self):
        """
        Returns operation object depends on 'mode' - Literal['random', 'table', 'partition', 'aggregate']
        Returns: OperationBase
        """
        self.log.debug("Operation instance map: %s", self.operation_instance_map)
        return self.operation_instance_map[self.thread_params.mode]()

    def _run_next_operation(self):
        self.thread_stats.read_pages = self.generator.choice([100, 1000, 0])
        try:
            scan_op = self.get_next_operation()
            self.log.debug("Going to run operation %s", scan_op.__class__.__name__)
            scan_op.run_scan_operation()

            self.log.debug("Thread operations queue depleted.")

        except Exception as exc:  # noqa: BLE001
            self.log.error(traceback.format_exc())
            self.log.error("Encountered exception while performing a operation:\n%s", exc)

        self.log.debug("Thread stats:\n%s", self.thread_stats.get_stats_pretty_table())

    def run(self):
        end_time = time.time() + self.thread_params.duration
        self._wait_until_user_table_exists()
        while time.time() < end_time and not self.termination_event.is_set():
            self._run_next_operation()
            time.sleep(self.thread_params.interval)
        # summary for Jenkins. may not log because nobody wait the thread.
        # Thread stats logs with debug level in each loop
        self.log.debug("Thread stats:\n%s", self.thread_stats.get_stats_pretty_table())

    def start(self):
        self._thread.start()

    def join(self, timeout=None):
        return self._thread.join(timeout)

    def _wait_until_user_table_exists(self, timeout_min: int = 20):
        text = f'Waiting until {self.thread_params.ks_cf} user table exists'
        db_node = random.choice(self.thread_params.db_cluster.nodes)

        if self.thread_params.ks_cf.lower() == 'random':
            wait.wait_for(func=lambda: len(self.thread_params.db_cluster.get_non_system_ks_cf_list(db_node)) > 0,
                          step=60, text=text, timeout=60 * timeout_min, throw_exc=False)
            self.thread_params.ks_cf = self.thread_params.db_cluster.get_non_system_ks_cf_list(db_node)[0]
        else:
            wait.wait_for(func=lambda: self.thread_params.ks_cf in (
                self.thread_params.db_cluster.get_non_system_ks_cf_list(db_node)
            ), step=60, text=text, timeout=60 * timeout_min, throw_exc=False)
