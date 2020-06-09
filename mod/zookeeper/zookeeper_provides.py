from ops.framework import Object
import logging

logger = logging.getLogger(__name__)


class ZookeeperInterfaceProvides(Object):
    def __init__(self, charm, relation_name):
        super().__init__(charm, relation_name)
        self._relation_name = relation_name
        self._relation = self.model.get_relation(relation_name)

    def send_connection(self, port, rest_port, host=None):
        # Expose common settings via app relation data from a leader unit.
        if self.model.unit.is_leader():
            app_data = self._relation.data[self.model.app]
            app_data["port"] = "test" # str(port)
            # app_data["rest_port"] = str(rest_port)
            # app_data["host"] = str(host)

