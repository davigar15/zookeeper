#!/usr/bin/env python3

import logging

from ops.charm import CharmBase
from zookeeper_cluster import ZookeeperCluster
from zookeeper_provides import ZookeeperInterfaceProvides

from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
)


from glob import glob
from pathlib import Path
from string import Template


logger = logging.getLogger(__name__)

REQUIRED_SETTINGS = ["zookeeper_image_path"]

INIT_COMMAND = "cp /scripts/docker-entrypoint.sh /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh && ls / && /docker-entrypoint.sh zkServer.sh start-foreground"


class ZookeeperCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        # Register all of the events we want to observe
        self.framework.observe(self.on.config_changed, self.configure_pod)
        self.framework.observe(self.on.start, self.configure_pod)
        self.framework.observe(self.on.upgrade_charm, self.configure_pod)

        self.framework.observe(
            self.on.zookeeper_relation_joined, self.on_zookeeper_relation_joined
        )

        self.cluster = ZookeeperCluster(self, "cluster")
        self.zookeeper = ZookeeperInterfaceProvides(self, "zookeeper")
        self.framework.observe(self.cluster.on.members_changed, self.configure_pod)

    def _check_settings(self):
        problems = []
        config = self.model.config

        for setting in REQUIRED_SETTINGS:
            if not config.get(setting):
                problem = f"missing config {setting}"
                problems.append(problem)

        return ";".join(problems)

    def _make_pod_image_details(self):
        image_details = {
            "imagePath": self.model.config["zookeeper_image_path"],
        }
        if self.model.config["zookeeper_image_username"]:
            image_details.update(
                {
                    "username": self.model.config["zookeeper_image_username"],
                    "password": self.model.config["zookeeper_image_password"],
                }
            )
        return image_details

    def _make_pod_ports(self):
        return [
            {
                "name": "client-port",
                "containerPort": self.model.config["client-port"],
                "protocol": "TCP",
            },
            {
                "name": "server-port",
                "containerPort": self.model.config["server-port"],
                "protocol": "TCP",
            },
            {
                "name": "leader-port",
                "containerPort": self.model.config["leader-port"],
                "protocol": "TCP",
            },
        ]

    def _make_pod_envconfig(self):
        config = self.model.config

        return {
            "ZOO_TICK_TIME": config["tick-time"],
            "ZOO_INIT_LIMIT": config["init-limit"],
            "ZOO_SYNC_LIMIT": config["sync-limit"],
            "ZOO_MAX_CLIENT_CNXNS": config["max-client-cnxns"],
            "ZOO_STANDALONE_ENABLED": config["standalone-enabled"],
            "ZOO_ADMINSERVER_ENABLED": config["adminserver-enabled"],
            "ZOO_AUTOPURGE_PURGEINTERVAL": config["autopurge-purgeinterval"],
            "ZOO_AUTOPURGE_SNAPRETAINCOUNT": config["autopurge-snapretaincount"],
            "ZOO_4LW_COMMANDS_WHITELIST": config["4lw-commands-whitelist"],
            "ZOO_CFG_EXTRA": config["cfg-extra"],
            "ZOO_LOG4J_PROP": config["log4j-prop"],
        }

    def _make_pod_command(self):
        return [
            "sh",
            "-c",
            f"export ZOO_MY_ID=$((${{HOSTNAME##*-}} + 1)) && {INIT_COMMAND}",
        ]

    def _make_pod_volume_config(self):
        return [
            {
                "name": "conf",
                "mountPath": "/conf",
                "files": [
                    {
                        "path": Path(filename).name,
                        "content": Template(Path(filename).read_text()).substitute(
                            self._make_pod_envconfig()
                        ),
                    }
                    for filename in glob("src/conf/*")
                ],
            },
            {
                "name": "scripts",
                "mountPath": "/scripts",
                "files": [
                    {"path": Path(filename).name, "content": Path(filename).read_text()}
                    for filename in glob("src/scripts/*")
                ],
            },
        ]

    # def _make_pod_ingress_resources(self):
    #     site_url = self.model.config["site_url"]

    #     if not site_url:
    #         return

    #     parsed = urlparse(site_url)

    #     if not parsed.scheme.startswith("http"):
    #         return

    #     max_file_size = self.model.config["max_file_size"]
    #     ingress_whitelist_source_range = self.model.config[
    #         "ingress_whitelist_source_range"
    #     ]

    #     annotations = {}
    #     annotations["nginx.ingress.kubernetes.io/proxy-body-size"] = f"{max_file_size}m"

    #     if ingress_whitelist_source_range:
    #         annotations[
    #             "nginx.ingress.kubernetes.io/whitelist-source-range"
    #         ] = ingress_whitelist_source_range

    #     ingress = {
    #         "name": "{}-ingress".format(self.app.name),
    #         "annotations": annotations,
    #         "spec": {
    #             "rules": [
    #                 {
    #                     "host": parsed.hostname,
    #                     "http": {
    #                         "paths": [
    #                             {
    #                                 "path": "/",
    #                                 "backend": {
    #                                     "serviceName": self.app.name,
    #                                     "servicePort": HTTP_PORT,
    #                                 },
    #                             }
    #                         ]
    #                     },
    #                 }
    #             ]
    #         },
    #     }

    #     if parsed.scheme == "https":
    #         ingress["spec"]["tls"] = [{"hosts": [parsed.hostname]}]
    #     else:
    #         ingress["annotations"]["nginx.ingress.kubernetes.io/ssl-redirect"] = "false"

    #     return [ingress]

    # def _make_pod_secrets(self):
    #     return [
    #         {
    #             "name": f"{self.app.name}-secrets",
    #             "type": "Opaque",
    #             "stringData": {
    #                 USER_SECRET_KEY_NAME: self.model.config["user"],
    #                 PASS_SECRET_KEY_NAME: self.model.config["pass"],
    #             },
    #         }
    #     ]
    def _make_pod_kubernetes(self):
        client_port = self.model.config["client-port"]
        return {
            "readinessProbe": {
                "tcpSocket": {"port": client_port},
                "timeoutSeconds": 5,
                "periodSeconds": 5,
                "initialDelaySeconds": 10,
            },
            "livenessProbe": {
                "tcpSocket": {"port": client_port},
                "timeoutSeconds": 5,
                "initialDelaySeconds": 45,
            },
        }

    def configure_pod(self, event):
        # Continue only if the unit is the leader
        if not self.unit.is_leader():
            self.unit.status = ActiveStatus()
            return
        # Check problems in the settings
        problems = self._check_settings()
        if problems:
            self.unit.status = BlockedStatus(problems)
            return

        self.unit.status = BlockedStatus("Assembling pod spec")
        image_details = self._make_pod_image_details()
        ports = self._make_pod_ports()
        env_config = self._make_pod_envconfig()
        command = self._make_pod_command()
        volume_config = self._make_pod_volume_config()
        # ingress_resources = self._make_pod_ingress_resources()
        # secrets = self._make_pod_secrets()
        kubernetes = self._make_pod_kubernetes()
        pod_spec = {
            "version": 3,
            "containers": [
                {
                    "name": self.framework.model.app.name,
                    "imageDetails": image_details,
                    "ports": ports,
                    "envConfig": env_config,
                    "command": command,
                    "volumeConfig": volume_config,
                    "kubernetes": kubernetes,
                }
            ],
            # "kubernetesResources": {
            #     "ingressResources": ingress_resources or [],
            #     "secrets": secrets,
            # },
        }
        logger.debug(pod_spec)
        self.model.pod.set_spec(pod_spec)
        self.unit.status = ActiveStatus()

    def on_zookeeper_relation_joined(self, event):
        if not self.unit.is_leader():
            return
        if not self.cluster.is_joined:
            event.defer()
            return
        config = self.framework.model.config
        unit = MaintenanceStatus("Sending connection data")
        self.zookeeper.send_connection(
            config["client-port"], config["client-port"], self.cluster.address,
        )
        self.unit.status = ActiveStatus("Ready")


if __name__ == "__main__":
    main(ZookeeperCharm)

    #!/usr/bin/env python3

    # import logging

    # from ops.charm import CharmBase
    # from ops.framework import StoredState
    # from ops.main import main
    # from ops.model import (
    #     ActiveStatus,
    #     MaintenanceStatus,
    # )

    # from zookeeper_cluster import ZookeeperCluster
    # from zookeeper_provides import ZookeeperInterfaceProvides

    # logger = logging.getLogger(__name__)

    # class ZookeeperCharm(CharmBase):
    #     state = StoredState()

    #     def __init__(self, framework, key):
    #         super().__init__(framework, key)
    #         self.state.set_default(spec=None)

    #         # Observe Charm related events
    #         self.framework.observe(self.on.config_changed, self.on_config_changed)
    #         self.framework.observe(self.on.start, self.on_start)
    #         self.framework.observe(self.on.upgrade_charm, self.on_upgrade_charm)
    #         self.framework.observe(self.on.zookeeper_relation_joined, self.on_zookeeper_relation_joined)

    #         self.cluster = ZookeeperCluster(self, "cluster")
    #         self.zookeeper = ZookeeperInterfaceProvides(self, "zookeeper")
    #         self.framework.observe(self.cluster.on.members_changed, self.on_members_changed)

    #     def on_members_changed(self, event):
    #         unit = self.model.unit
    #         unit.status = MaintenanceStatus("Applying pod spec")
    #         self._apply_spec()
    #         unit.status = ActiveStatus("Ready")

    #     def _apply_spec(self):
    #         # Only apply the spec if this unit is a leader.
    #         if not self.framework.model.unit.is_leader():
    #             return
    #         new_spec = self.make_pod_spec()
    #         if new_spec == self.state.spec:
    #             return
    #         self.framework.model.pod.set_spec(new_spec)
    #         self.state.spec = new_spec

    #     def make_pod_spec(self):
    #         config = self.framework.model.config

    #         ports =

    #         kubernetes = {
    #             "readinessProbe": {
    #                 "tcpSocket": {"port": config["client-port"]},
    #                 "timeoutSeconds": 5,
    #                 "periodSeconds": 5,
    #                 "initialDelaySeconds": 10,
    #             },
    #             "livenessProbe": {
    #                 "tcpSocket": {"port": config["client-port"]},
    #                 "timeoutSeconds": 5,
    #                 "initialDelaySeconds": 45,
    #             },
    #         }

    #         config_spec = {
    #             "ZOO_STANDALONE_ENABLED": self.cluster.num_units > 1,
    #             "ZOO_ADMINSERVER_ENABLED": config["adminserver-enabled"],
    #             "ZOO_4LW_COMMANDS_WHITELIST": config["4lw-commands-whitelist"],
    #         }
    #         with open("files/start-zookeeper") as f:
    #             start_zookeeper = f.read()

    #         files = [
    #             {
    #                 "name": "scripts",
    #                 "mountPath": "/scripts",
    #                 "files": {"start-zookeeper": start_zookeeper},
    #             },
    #         ]
    #         command = [
    #             "bash",
    #             "-c",
    #             " ".join(
    #                 [
    #                     "cp /scripts/start-zookeeper /usr/bin/start-zookeeper &&",
    #                     "chmod +x /usr/bin/start-zookeeper &&",
    #                     "mkdir -p /opt/zookeeper/conf &&",
    #                     "start-zookeeper",
    #                     "--servers={}".format(self.cluster.num_units),
    #                     "--data_dir=/var/lib/zookeeper/data",
    #                     "--data_log_dir=/var/lib/zookeeper/data/log",
    #                     "--conf_dir=/opt/zookeeper/conf",
    #                     "--client_port={}".format(config["client-port"]),
    #                     "--election_port={}".format(config["leader-port"]),
    #                     "--server_port={}".format(config["server-port"]),
    #                     "--tick_time={}".format(config["tick-time"]),
    #                     "--init_limit={}".format(config["init-limit"]),
    #                     "--sync_limit={}".format(config["sync-limit"]),
    #                     "--heap={}".format(config["heap"]),
    #                     "--max_client_cnxns={}".format(config["max-client-cnxns"]),
    #                     "--snap_retain_count={}".format(config["snap-retain-count"]),
    #                     "--purge_interval={}".format(config["purge-interval"]),
    #                     "--max_session_timeout={}".format(config["max-session-timeout"]),
    #                     "--min_session_timeout={}".format(config["min-session-timeout"]),
    #                     "--log_level={}".format(config["log-level"]),
    #                 ]
    #             ),
    #         ]

    #         spec = {
    #             "version": 2,
    #             "containers": [
    #                 {
    #                     "name": self.framework.model.app.name,
    #                     "image": "{}:{}".format(config["image"], config["version"]),
    #                     "ports": ports,
    #                     "kubernetes": kubernetes,
    #                     "config": config_spec,
    #                     "files": files,
    #                     "command": command,
    #                 }
    #             ],
    #         }

    #         return spec

    #     def on_config_changed(self, event):
    #         """Handle changes in configuration"""
    #         unit = self.model.unit
    #         unit.status = MaintenanceStatus("Applying new pod spec")
    #         self._apply_spec()
    #         unit.status = ActiveStatus("Ready")

    #     def on_start(self, event):
    #         """Called when the charm is being installed"""
    #         unit = self.model.unit
    #         unit.status = MaintenanceStatus("Applying pod spec")
    #         self._apply_spec()
    #         unit.status = ActiveStatus("Ready")

    #     def on_upgrade_charm(self, event):
    #         """Upgrade the charm."""
    #         unit = self.model.unit
    #         unit.status = MaintenanceStatus("Upgrading charm")
    #         self.on_start(event)


# if __name__ == "__main__":
#     main(ZookeeperCharm)
