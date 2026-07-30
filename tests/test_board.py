import unittest

from jiwa_jawa.board import GameState, InvalidAction, Piece


class BoardTests(unittest.TestCase):
    def test_initial_board_has_sixteen_pieces_per_player(self):
        state = GameState.initial("Sari", "Bimo")
        self.assertEqual(37, len(__import__("jiwa_jawa.board", fromlist=["NODES"]).NODES))
        self.assertEqual(16, state.piece_count("A"))
        self.assertEqual(16, state.piece_count("B"))
        self.assertEqual(5, 37 - len(state.pieces))

    def test_capture_removes_the_jumped_piece(self):
        state = GameState({"A": "A", "B": "B"}, {(0, 2): Piece("A"), (1, 2): Piece("B")})
        action = state.apply("A", {"type": "move", "src": "0,2", "dst": "2,2"})
        self.assertEqual("1,2", action["capture"])
        self.assertNotIn((1, 2), state.pieces)
        self.assertEqual(Piece("A"), state.pieces[(2, 2)])

    def test_piece_cannot_move_backward_before_promotion(self):
        state = GameState({"A": "A", "B": "B"}, {(2, 2): Piece("A"), (6, 0): Piece("B")})
        with self.assertRaises(InvalidAction):
            state.apply("A", {"type": "move", "src": "2,2", "dst": "1,2"})

    def test_piece_becomes_king_on_opponent_far_edge(self):
        state = GameState({"A": "A", "B": "B"}, {(5, 1): Piece("A"), (-2, 0): Piece("B")})
        action = state.apply("A", {"type": "move", "src": "5,1", "dst": "6,0"})
        self.assertTrue(action["promoted"])
        self.assertTrue(state.pieces[(6, 0)].king)

    def test_missed_capture_gives_opponent_three_dam_pieces(self):
        state = GameState(
            {"A": "A", "B": "B"},
            {
                (0, 2): Piece("A"),
                (0, 0): Piece("A"),
                (0, 4): Piece("A"),
                (1, 4): Piece("A"),
                (1, 2): Piece("B"),
                (6, 0): Piece("B"),
            },
        )
        action = state.apply("A", {"type": "move", "src": "0,0", "dst": "1,0"})
        self.assertTrue(action["missed_capture"])
        self.assertEqual("B", state.dam_player)
        state.apply("B", {"type": "dam", "targets": ["0,2", "0,4", "1,4"]})
        self.assertEqual(1, state.piece_count("A"))
        self.assertIsNone(state.dam_player)
        self.assertEqual("B", state.turn)


if __name__ == "__main__":
    unittest.main()

