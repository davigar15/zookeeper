#!/usr/bin/env python3

import sys
import logging

sys.path.append("lib")

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    MaintenanceStatus,
)

from zookeeper_cluster import ZookeeperCluster
from zookeeper_provides import ZookeeperInterfaceProvides


logger = logging.getLogger(__name__)


class ZookeeperCharm(CharmBase):
    state = StoredState()

    def __init__(self, framework, key):
        super().__init__(framework, key)
        self.state.set_default(spec=None)

        # Observe Charm related events
        self.framework.observe(self.on.config_changed, self.on_config_changed)
        self.framework.observe(self.on.start, self.on_start)
        self.framework.observe(self.on.upgrade_charm, self.on_upgrade_charm)
        self.framework.observe(self.on.zookeeper_relation_joined, self.on_zookeeper_relation_joined)

        self.cluster = ZookeeperCluster(self, "cluster")
        self.zookeeper = ZookeeperInterfaceProvides(self, "zookeeper")
        self.framework.observe(self.cluster.on.members_changed, self.on_members_changed)

    def on_members_changed(self, event):
        unit = self.model.unit
        unit.status = MaintenanceStatus("Applying pod spec")
        self._apply_spec()
        unit.status = ActiveStatus("Ready")

    def _apply_spec(self):
        # Only apply the spec if this unit is a leader.
        if not self.framework.model.unit.is_leader():
            return
        new_spec = self.make_pod_spec()
        if new_spec == self.state.spec:
            return
        self.framework.model.pod.set_spec(new_spec)
        self.state.spec = new_spec

    def make_pod_spec(self):
        config = self.framework.model.config

        ports = [
            {
                "name": "client-port",
                "containerPort": config["client-port"],
                "protocol": "TCP",
            },
            {
                "name": "server-port",
                "containerPort": config["server-port"],
                "protocol": "TCP",
            },
            {
                "name": "leader-port",
                "containerPort": config["leader-port"],
                "protocol": "TCP",
            },
        ]

        kubernetes = {
            "readinessProbe": {
                "tcpSocket": {"port": config["client-port"]},
                "timeoutSeconds": 5,
                "periodSeconds": 5,
                "initialDelaySeconds": 10,
            },
            "livenessProbe": {
                "tcpSocket": {"port": config["client-port"]},
                "timeoutSeconds": 5,
                "initialDelaySeconds": 45,
            },
        }

        config_spec = {
            "ZOO_STANDALONE_ENABLED": self.cluster.is_single,
            "ZOO_ADMINSERVER_ENABLED": config["adminserver-enabled"],
            "ZOO_4LW_COMMANDS_WHITELIST": config["4lw-commands-whitelist"],
        }
        with open("files/start-zookeeper") as f:
            start_zookeeper = f.read()

        files = [
            {
                "name": "scripts",
                "mountPath": "/scripts",
                "files": {"start-zookeeper": start_zookeeper},
            },
        ]
        command = [
            "bash",
            "-c",
            " ".join(
                [
                    "cp /scripts/start-zookeeper /usr/bin/start-zookeeper &&",
                    "chmod +x /usr/bin/start-zookeeper &&",
                    "mkdir -p /opt/zookeeper/conf &&",
                    "start-zookeeper",
                    "--servers={}".format(self.cluster.units),
                    "--data_dir=/var/lib/zookeeper/data",
                    "--data_log_dir=/var/lib/zookeeper/data/log",
                    "--conf_dir=/opt/zookeeper/conf",
                    "--client_port={}".format(config["client-port"]),
                    "--election_port={}".format(config["leader-port"]),
                    "--server_port={}".format(config["server-port"]),
                    "--tick_time={}".format(config["tick-time"]),
                    "--init_limit={}".format(config["init-limit"]),
                    "--sync_limit={}".format(config["sync-limit"]),
                    "--heap={}".format(config["heap"]),
                    "--max_client_cnxns={}".format(config["max-client-cnxns"]),
                    "--snap_retain_count={}".format(config["snap-retain-count"]),
                    "--purge_interval={}".format(config["purge-interval"]),
                    "--max_session_timeout={}".format(config["max-session-timeout"]),
                    "--min_session_timeout={}".format(config["min-session-timeout"]),
                    "--log_level={}".format(config["log-level"]),
                ]
            ),
        ]

        spec = {
            "version": 2,
            "containers": [
                {
                    "name": self.framework.model.app.name,
                    "image": "{}:{}".format(config["image"], config["version"]),
                    "ports": ports,
                    "kubernetes": kubernetes,
                    "config": config_spec,
                    "files": files,
                    "command": command,
                }
            ],
        }

        return spec

    def on_config_changed(self, event):
        """Handle changes in configuration"""
        unit = self.model.unit
        unit.status = MaintenanceStatus("Applying new pod spec")
        self._apply_spec()
        unit.status = ActiveStatus("Ready")

    def on_start(self, event):
        """Called when the charm is being installed"""
        unit = self.model.unit
        unit.status = MaintenanceStatus("Applying pod spec")
        self._apply_spec()
        unit.status = ActiveStatus("Ready")

    def on_upgrade_charm(self, event):
        """Upgrade the charm."""
        unit = self.model.unit
        unit.status = MaintenanceStatus("Upgrading charm")
        self.on_start(event)

    def on_zookeeper_relation_joined(self, event):
        unit = self.model.unit
        if not unit.is_leader():
            return
        if not self.cluster.is_joined:
            event.defer()
        config = self.framework.model.config
        unit = MaintenanceStatus("Sending connection data")
        self.zookeeper.send_connection(
            config["client-port"], config["client-port"], self.cluster.address,
        )
        unit = ActiveStatus("Ready")


if __name__ == "__main__":
    main(ZookeeperCharm)
