import threading
import unittest

from jiwa_jawa.protocol import ReliableUDP


class ProtocolTests(unittest.TestCase):
    def test_delivery_and_duplicate_suppression_with_simulated_loss(self):
        left = ReliableUDP(("127.0.0.1", 0), timeout=0.01, max_retries=250, drop_rate=0.5)
        right = ReliableUDP(("127.0.0.1", 0), timeout=0.01, max_retries=250, drop_rate=0.5)
        try:
            errors = []

            def sender():
                try:
                    for number in range(12):
                        left.send({"number": number}, right.address)
                except Exception as exc:  # pragma: no cover - failure is asserted below
                    errors.append(exc)

            thread = threading.Thread(target=sender)
            thread.start()
            received = [right.receive(timeout=8).payload["number"] for _ in range(12)]
            thread.join(timeout=8)
            self.assertFalse(errors)
            self.assertEqual(list(range(12)), received)
            self.assertTrue(right._inbox.empty())
        finally:
            left.close()
            right.close()


if __name__ == "__main__":
    unittest.main()

