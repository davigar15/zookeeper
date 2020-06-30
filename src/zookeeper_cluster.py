from ops.framework import Object, EventBase, EventSource, StoredState, ObjectEvents
import logging

logger = logging.getLogger(__name__)


class MembersChangedEvent(EventBase):
    """This event is emitted whenever there is a change in a set of cluster member FQDNs."""


class ZookeeperClusterEvents(ObjectEvents):
    members_changed = EventSource(MembersChangedEvent)


class ZookeeperCluster(Object):
    on = ZookeeperClusterEvents()
    state = StoredState()

    def __init__(self, charm, relation_name):
        super().__init__(charm, relation_name)
        self._relation_name = relation_name
        self._relation = self.framework.model.get_relation(self._relation_name)

        relation = charm.on[relation_name]
        self.framework.observe(relation.relation_joined, self.on_relation_joined)
        self.framework.observe(relation.relation_changed, self.on_relation_changed)
        self.framework.observe(relation.relation_departed, self.on_relation_departed)

    def on_relation_joined(self, event):
        logger.debug(
            "Relation joined. Self={}. Remote={}".format(
                self.model.unit.name, event.unit.name
            )
        )

    def on_relation_changed(self, event):
        logger.debug(
            "Relation changed. Self={}. Remote={}".format(
                self.model.unit.name, event.unit.name
            )
        )
        if event.unit:
            self.on.members_changed.emit()

    def on_relation_departed(self, event):
        logger.debug(
            "Relation departed. Self={}. Remote={}".format(
                self.model.unit.name, event.unit.name
            )
        )
        if event.unit:
            self.on.members_changed.emit()

    @property
    def is_joined(self):
        return self._relation is not None

    @property
    def num_units(self):
        return len(self._relation.units) + 1 if self.is_joined else 1

    @property
    def address(self):
        address = None
        try:
            binding = self.model.get_binding(self._relation_name)
            address = binding.network.ingress_address
        except Exception as e:
            logger.error("Cannot get the address: {}".format(e))

        return address

    @property
    def _relations(self):
        return self.framework.model.relations[self._relation_name]
