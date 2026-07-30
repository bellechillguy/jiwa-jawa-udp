import threading
import unittest

from jiwa_jawa.protocol import ReliableUDP


class KernelNetemProtocolTest(unittest.TestCase):
    def test_messages_survive_kernel_packet_loss(self):
        left = ReliableUDP(("127.0.0.1", 0), timeout=0.025, max_retries=300)
        right = ReliableUDP(("127.0.0.1", 0), timeout=0.025, max_retries=300)
        try:
            failure = []

            def send_all():
                try:
                    for number in range(20):
                        left.send({"number": number}, right.address)
                except Exception as exc:  # pragma: no cover
                    failure.append(exc)

            thread = threading.Thread(target=send_all)
            thread.start()
            messages = [right.receive(timeout=15).payload["number"] for _ in range(20)]
            thread.join(timeout=15)
            self.assertFalse(failure)
            self.assertEqual(list(range(20)), messages)
        finally:
            left.close()
            right.close()


if __name__ == "__main__":
    unittest.main()

