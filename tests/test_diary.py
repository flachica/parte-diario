import unittest
from datetime import datetime
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

    def test_minutes_between(self):
        self.assertEqual(diary.minutes_between("08:15", "08:52"), 37)
        self.assertEqual(diary.minutes_between("08:00", "08:00"), 0)
        self.assertEqual(diary.minutes_between("23:30", "00:30"), 60)

    def test_get_tasks_summary_closed_ranges_and_adjustments(self):
        content = [
            "[Todoencloud](https://odoo.sdi.es/task/1)",
            "+10",
            "",
            "Rev. Context Engineering",
            "+7",
            "",
            "daily hermes",
            "08:17 - 08:33",
            "",
            "biomag",
            "09:22 - 11:29",
            "-30",
            "12:56 - 14:23",
            "15:26 - 15:44",
            "",
            "Renumeracion sensedi",
            "+30",
            "11:29 - 11:29",
        ]
        items = diary.get_tasks_summary(content, file_date="2026-09-22")
        self.assertEqual(len(items), 5)
        # Todoencloud: +10 min
        self.assertEqual(items[0].name, "Todoencloud")
        self.assertEqual(items[0].url, "https://odoo.sdi.es/task/1")
        self.assertEqual(items[0].minutes, 10)
        # Rev. Context Engineering: +7 min
        self.assertEqual(items[1].name, "Rev. Context Engineering")
        self.assertIsNone(items[1].url)
        self.assertEqual(items[1].minutes, 7)
        # daily hermes: 16 min
        self.assertEqual(items[2].name, "daily hermes")
        self.assertEqual(items[2].minutes, 16)
        # biomag: 127 - 30 + 87 + 18 = 202 min
        self.assertEqual(items[3].name, "biomag")
        self.assertEqual(items[3].minutes, 202)
        # Renumeracion sensedi: 30 + 0 = 30 min
        self.assertEqual(items[4].name, "Renumeracion sensedi")
        self.assertEqual(items[4].minutes, 30)

    def test_get_tasks_summary_skips_notes_and_merges_duplicates(self):
        content = [
            "* Nota suelta que debe ser ignorada",
            "",
            "[Tarea](https://ejemplo.com/1)",
            "08:00 - 08:30",
            "* una nota de la tarea",
            "",
            "Tarea",
            "09:00 - 09:15",
            "",
            "> Cita ignorada",
            "",
            "Tarea Solo Nota",
            "* otra nota",
        ]
        items = diary.get_tasks_summary(content, file_date="2026-09-22")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "Tarea")
        self.assertEqual(items[0].url, "https://ejemplo.com/1")
        self.assertEqual(items[0].minutes, 45)  # 30 + 15

    def test_get_tasks_summary_open_task(self):
        from datetime import datetime
        ref_time = datetime(2026, 9, 23, 10, 30)
        content = [
            "Tarea En Curso",
            "10:00 - ",
        ]
        # Si la fecha es hoy, calcula el tiempo transcurrido hasta reference_time
        items_today = diary.get_tasks_summary(content, file_date="2026-09-23", reference_time=ref_time)
        self.assertEqual(len(items_today), 1)
        self.assertTrue(items_today[0].is_open)
        self.assertEqual(items_today[0].minutes, 30)

        # Si la fecha es de un día pasado, no añade tiempo arbitrario
        items_past = diary.get_tasks_summary(content, file_date="2026-09-20", reference_time=ref_time)
        self.assertEqual(len(items_past), 1)
        self.assertTrue(items_past[0].is_open)
        self.assertEqual(items_past[0].minutes, 0)

    def test_find_first_start_time_for_task(self):
        lines = [
            "Espartero",
            "08:45 - 10:00",
            "10:33 - 11:02",
            "11:20 - 11:52",
            "11:59 - ",
        ]
        first = diary.find_first_start_time_for_task(lines, "Espartero")
        self.assertEqual(first, "08:45")

        # Tarea que no existe
        self.assertIsNone(diary.find_first_start_time_for_task(lines, "Inexistente"))

        # Tarea con link markdown
        lines_link = [
            "[Mi Tarea](https://ejemplo.com)",
            "09:15 - 10:00",
        ]
        self.assertEqual(diary.find_first_start_time_for_task(lines_link, "Mi Tarea"), "09:15")
        self.assertEqual(diary.find_first_start_time_for_task(lines_link, "Otro", url="https://ejemplo.com"), "09:15")

    def test_get_task_total_minutes(self):
        lines = [
            "Espartero",
            "08:45 - 10:00",  # 75 min
            "-15",            # -15 min
            "10:33 - 11:02",  # 29 min
            "11:20 - 11:52",  # 32 min
            "11:59 - ",       # tramo abierto
        ]
        # A las 11:59 (0 min en el tramo abierto)
        ref_start = datetime(2026, 9, 23, 11, 59)
        total_at_start = diary.get_task_total_minutes(
            lines,
            "Espartero",
            file_date="2026-09-23",
            reference_time=ref_start,
        )
        # 75 - 15 + 29 + 32 = 121
        self.assertEqual(total_at_start, 121)

        # 30 minutos después (12:29)
        ref_later = datetime(2026, 9, 23, 12, 29)
        total_later = diary.get_task_total_minutes(
            lines,
            "Espartero",
            file_date="2026-09-23",
            reference_time=ref_later,
        )
        self.assertEqual(total_later, 121 + 30)


if __name__ == "__main__":
    unittest.main()
