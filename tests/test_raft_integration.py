import json
import socket
import tempfile
import threading
import time
import unittest
import uuid

from jiwa_jawa.raft_logger import RaftNode


def free_ports(count):
    sockets = []
    ports = []
    for _ in range(count):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sockets.append(sock)
        ports.append(sock.getsockname()[1])
    for sock in sockets:
        sock.close()
    return ports


def wait_until(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.04)
    return False


class RaftIntegrationTests(unittest.TestCase):
    def test_majority_commit_and_leader_failover(self):
        ports = free_ports(3)
        addresses = {f"logger-{index + 1}": ("127.0.0.1", port) for index, port in enumerate(ports)}
        with tempfile.TemporaryDirectory() as temporary:
            nodes = {}
            threads = {}
            for node_id, address in addresses.items():
                peers = {peer_id: peer_address for peer_id, peer_address in addresses.items() if peer_id != node_id}
                node = RaftNode(node_id, address, peers, f"{temporary}/{node_id}")
                nodes[node_id] = node
                thread = threading.Thread(target=node.run, daemon=True)
                threads[node_id] = thread
                thread.start()
            try:
                self.assertTrue(wait_until(lambda: sum(node.role == "leader" for node in nodes.values()) == 1))
                first = {
                    "event_id": str(uuid.uuid4()),
                    "type": "game_started",
                    "match_id": "match-raft-test",
                    "player_a": "Sari",
                    "player_b": "Bimo",
                }
                self.assertTrue(self._send_until_ack(first, list(addresses.values())))
                self.assertTrue(wait_until(lambda: sum(first["event_id"] in n.committed_events for n in nodes.values()) >= 2))

                old_leader_id = next(node_id for node_id, node in nodes.items() if node.role == "leader")
                self._stop(nodes[old_leader_id], addresses[old_leader_id], threads[old_leader_id])
                survivors = {node_id: node for node_id, node in nodes.items() if node_id != old_leader_id}
                self.assertTrue(wait_until(lambda: sum(node.role == "leader" for node in survivors.values()) == 1))

                second = {
                    "event_id": str(uuid.uuid4()),
                    "type": "game_ended",
                    "match_id": "match-raft-test",
                    "player_a": "Sari",
                    "player_b": "Bimo",
                    "winner": "A",
                }
                survivor_addresses = [addresses[node_id] for node_id in survivors]
                self.assertTrue(self._send_until_ack(second, survivor_addresses))
                self.assertTrue(wait_until(lambda: all(second["event_id"] in n.committed_events for n in survivors.values())))
                self.assertTrue(wait_until(lambda: all(n.rating.get("Sari") > 1200 for n in survivors.values())))
            finally:
                for node_id, node in nodes.items():
                    if threads[node_id].is_alive():
                        self._stop(node, addresses[node_id], threads[node_id])

    @staticmethod
    def _send_until_ack(event, addresses):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.25)
        request = json.dumps({"rpc": "client_append", "event": event}).encode()
        try:
            for _ in range(30):
                for address in addresses:
                    sock.sendto(request, address)
                try:
                    raw, _ = sock.recvfrom(60_000)
                except socket.timeout:
                    continue
                response = json.loads(raw.decode())
                if response.get("rpc") == "log_ack" and response.get("event_id") == event["event_id"]:
                    return True
            return False
        finally:
            sock.close()

    @staticmethod
    def _stop(node, address, thread):
        node.running = False
        wake = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        wake.sendto(b"{}", address)
        wake.close()
        thread.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
