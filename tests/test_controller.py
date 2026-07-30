import time
import unittest

from jiwa_jawa.controller import HostController, JoinController


def wait_until(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.03)
    return False


class ControllerTests(unittest.TestCase):
    def test_two_programs_share_authoritative_state(self):
        host = HostController(("127.0.0.1", 0), "Sari", logger_nodes=None, drop_rate=0.25)
        join = JoinController(("127.0.0.1", host.endpoint.address[1]), "Bimo", drop_rate=0.25)
        try:
            self.assertTrue(wait_until(lambda: host.snapshot() is not None and join.snapshot() is not None))
            host.submit({"type": "move", "src": "1,2", "dst": "2,2"})
            self.assertTrue(wait_until(lambda: join.snapshot() is not None and join.snapshot().version == 1))
            self.assertEqual(host.snapshot().to_dict(), join.snapshot().to_dict())
        finally:
            join.close()
            host.close()


if __name__ == "__main__":
    unittest.main()

