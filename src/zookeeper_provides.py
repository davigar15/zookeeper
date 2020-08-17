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
            unit_data = self._relation.data[self.model.unit]
            unit_data["port"] =  str(port)
            unit_data["rest_port"] = str(rest_port)
            unit_data["host"] = str(host)
