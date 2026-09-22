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

    def test_close_open_line_without_trailing_space(self):
        content = [
            "Biomag",
            "10:00 -",
        ]
        closed = diary.close_open_line(content, "10:00", prefer_block_name="Biomag")
        self.assertIsNotNone(closed)
        self.assertTrue(closed[1].startswith("10:00 - "))

    def test_find_open_task_in_lines(self):
        content = [
            "Parte",
            "08:05 - 08:30",
            "",
            "Biomag",
            "10:00 - ",
        ]
        res = diary.find_open_task_in_lines(content)
        self.assertEqual(res, ("Biomag", "10:00"))

        closed_content = [
            "Parte",
            "08:05 - 08:30",
        ]
        self.assertIsNone(diary.find_open_task_in_lines(closed_content))

    def test_parse_and_format_time_range(self):
        self.assertEqual(diary.parse_time_range("08:15 - 09:30"), ("08:15", "09:30"))
        self.assertEqual(diary.parse_time_range("08:15 - "), ("08:15", None))
        self.assertEqual(diary.parse_time_range("08:15 -"), ("08:15", None))
        self.assertIsNone(diary.parse_time_range("* nota"))

        self.assertEqual(diary.format_time_range("8:15", "9:30"), "08:15 - 09:30")
        self.assertEqual(diary.format_time_range("8:15", None), "08:15 - ")

    def test_update_block_header(self):
        content = [
            "Parte",
            "08:05 - 08:30",
        ]
        block = diary.find_blocks(content)[0]
        updated = diary.update_block_header(content, block, "Parte Diario", "https://ejemplo.com")
        self.assertEqual(updated[0], "[Parte Diario](https://ejemplo.com)")
        self.assertEqual(updated[1], "08:05 - 08:30")

    def test_update_block_line(self):
        content = [
            "Parte",
            "08:05 - 08:30",
        ]
        updated = diary.update_block_line(content, 1, "08:05 - 09:00")
        self.assertEqual(updated[1], "08:05 - 09:00")

    def test_delete_block_line(self):
        content = [
            "Parte",
            "08:05 - 08:30",
            "* nota",
        ]
        updated = diary.delete_block_line(content, 2)
        self.assertEqual(len(updated), 2)
        self.assertEqual(updated[1], "08:05 - 08:30")

    def test_delete_block(self):
        content = [
            "Tarea 1",
            "08:00 - 09:00",
            "",
            "Tarea 2",
            "09:00 - 10:00",
            "",
            "Tarea 3",
            "10:00 - 11:00",
        ]
        blocks = diary.find_blocks(content)
        updated = diary.delete_block(content, blocks[1])
        new_blocks = diary.find_blocks(updated)
        self.assertEqual(len(new_blocks), 2)
        self.assertEqual(new_blocks[0].name, "Tarea 1")
        self.assertEqual(new_blocks[1].name, "Tarea 3")


    def test_find_highest_time_in_lines(self):
        lines = [
            "Tarea 1",
            "08:00 - 09:30",
            "",
            "Tarea 2",
            "10:15 - 11:45",
        ]
        self.assertEqual(diary.find_highest_time_in_lines(lines), "11:45")

        lines_with_open = [
            "Tarea 1",
            "08:00 - 09:30",
            "",
            "Tarea 2",
            "12:00 - ",
        ]
        self.assertEqual(diary.find_highest_time_in_lines(lines_with_open), "12:00")

        no_times = ["Tarea 1", "+15", "nota"]
        self.assertIsNone(diary.find_highest_time_in_lines(no_times))


if __name__ == "__main__":
    unittest.main()
