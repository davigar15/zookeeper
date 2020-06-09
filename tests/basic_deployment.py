#!/usr/bin/python3
import unittest
import time
import socket
import zaza.model as model
from kazoo.client import KazooClient


def get_zookeeper_uri():
    zookeeper_uri = ""
    app = model.get_status().applications["zookeeper-k8s"]
    return app.public_address


class BasicDeployment(unittest.TestCase):
    def setUp(self):
        s = socket.socket()
        address = get_zookeeper_uri()
        port = 2181  # port number is a number, not string

        attempt = 0
        total_attempts = 10
        while attempt < total_attempts:
            try:
                s.connect((address, port))
                s.close()
                break
            except Exception as e:
                s.close()
                attempt += 1
                time.sleep(5)

    def test_get_zookeeper_uri(self):
        self.assertIsNotNone(get_zookeeper_uri())

    def test_zookeeper_connection(self):
        zookeeper_uri = get_zookeeper_uri()
        zk = KazooClient(zookeeper_uri)
        self.assertEqual(zk.state, "LOST")
        zk.start()
        self.assertEqual(zk.state, "CONNECTED")
        zk.stop()
        self.assertEqual(zk.state, "LOST")

    def test_zookeeper_create_node(self):
        zookeeper_uri = get_zookeeper_uri()
        zk = KazooClient(hosts=zookeeper_uri, read_only=True)
        zk.start()

        zk.ensure_path("/create/new")
        self.assertTrue(zk.exists("/create/new"))

        zk.create("/create/new/node", b"a value")
        self.assertTrue(zk.exists("/create/new/node"))

        zk.stop()

    def test_zookeeper_reading_data(self):
        zookeeper_uri = get_zookeeper_uri()
        zk = KazooClient(hosts=zookeeper_uri, read_only=True)
        zk.start()

        zk.ensure_path("/reading/data")
        zk.create("/reading/data/node", b"a value")

        data, stat = zk.get("/reading/data")
        self.assertEqual(data.decode("utf-8"), "")

        children = zk.get_children("/reading/data")
        self.assertEqual(len(children), 1)
        self.assertEqual("node", children[0])

        data, stat = zk.get("/reading/data/node")
        self.assertEqual(data.decode("utf-8"), "a value")
        zk.stop()

    def test_zookeeper_updating_data(self):
        zookeeper_uri = get_zookeeper_uri()
        zk = KazooClient(hosts=zookeeper_uri, read_only=True)
        zk.start()

        zk.ensure_path("/updating/data")
        zk.create("/updating/data/node", b"a value")

        data, stat = zk.get("/updating/data/node")
        self.assertEqual(data.decode("utf-8"), "a value")

        zk.set("/updating/data/node", b"b value")
        data, stat = zk.get("/updating/data/node")
        self.assertEqual(data.decode("utf-8"), "b value")
        zk.stop()

    def test_zookeeper_deleting_data(self):
        zookeeper_uri = get_zookeeper_uri()
        zk = KazooClient(hosts=zookeeper_uri, read_only=True)
        zk.start()

        zk.ensure_path("/deleting/data")
        zk.create("/deleting/data/node", b"a value")

        zk.delete("/deleting/data/node", recursive=True)

        self.assertFalse(zk.exists("/deleting/data/node"))
        self.assertTrue(zk.exists("/deleting/data"))
        data, stat = zk.get("/deleting/data")
        self.assertEqual(stat.numChildren, 0)
        zk.delete("/deleting", recursive=True)
        self.assertFalse(zk.exists("/deleting"))
        zk.stop()
