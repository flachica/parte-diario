import unittest
from parte_diario import diary


class TestDiary(unittest.TestCase):
    def test_find_blocks_and_names(self):
        content = [
            "Parte",
            "08:05 - 08:30",
            "",
            "[CTA](https://ejemplo.com/123)",
            "09:00 - ",
            "* una nota",
            "",
            "* nota suelta",
            "",
            "Alondra",
            "+15",
        ]
        blocks = diary.find_blocks(content)
        self.assertEqual(len(blocks), 4)
        self.assertEqual(blocks[0].name, "Parte")
        self.assertEqual(blocks[1].name, "CTA")
        self.assertEqual(blocks[2].name, "* nota suelta")
        self.assertEqual(blocks[3].name, "Alondra")

    def test_get_blocks_info(self):
        content = [
            "Parte",
            "08:05 - 08:30",
            "",
            "[CTA](https://ejemplo.com/123)",
            "09:00 - ",
            "",
            "* nota suelta",
            "",
            "Parte",
            "10:00 - 11:00",
        ]
        info = diary.get_blocks_info(content)
        self.assertEqual(len(info), 2)
        self.assertEqual(info[0], ("Parte", None))
        self.assertEqual(info[1], ("CTA", "https://ejemplo.com/123"))

    def test_close_open_line(self):
        content = [
            "Biomag",
            "10:00 - ",
        ]
        closed = diary.close_open_line(content, "10:00", prefer_block_name="Biomag")
        self.assertIsNotNone(closed)
        self.assertTrue(closed[1].startswith("10:00 - "))
        self.assertNotEqual(closed[1], "10:00 - ")


if __name__ == "__main__":
    unittest.main()
