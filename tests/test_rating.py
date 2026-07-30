import unittest

from jiwa_jawa.rating import RatingBook


class RatingTests(unittest.TestCase):
    def test_expected_score_is_logistic(self):
        self.assertAlmostEqual(0.5, RatingBook.expected(1200, 1200))
        self.assertAlmostEqual(10 / 11, RatingBook.expected(1600, 1200), places=6)
        self.assertNotAlmostEqual(
            RatingBook.expected(1200, 1000) - RatingBook.expected(1200, 1100),
            RatingBook.expected(1200, 1100) - RatingBook.expected(1200, 1200),
        )

    def test_match_is_applied_only_once(self):
        book = RatingBook()
        self.assertTrue(book.record("m-1", "Sari", "Bimo", "A"))
        first = dict(book.ratings)
        self.assertFalse(book.record("m-1", "Sari", "Bimo", "A"))
        self.assertEqual(first, book.ratings)


if __name__ == "__main__":
    unittest.main()

