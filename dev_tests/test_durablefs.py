"""Hand-computed crash outcomes for the trusted in-memory filesystem."""
import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments/durable_ledger/durablefs.py"


class DurableFSTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE_PATH.is_file(), "MemoryDurableFS has not been implemented")
        spec = importlib.util.spec_from_file_location("durablefs_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.FS = module.MemoryDurableFS
        self.fs = self.FS()

    def durable_file(self, name="ledger", data=b"acknowledged"):
        self.fs.write(name, data)
        self.fs.fsync(name)
        self.fs.fsync_dir()

    def test_new_unsynced_file_disappears_on_crash(self):
        self.fs.write("ledger", b"unacknowledged")
        self.assertEqual(self.fs.read("ledger"), b"unacknowledged")
        self.fs.crash()
        self.assertEqual(self.fs.list_files(), [])

    def test_file_sync_does_not_publish_a_new_name(self):
        self.fs.write("ledger", b"data")
        self.fs.fsync("ledger")
        self.fs.crash()
        with self.assertRaises(FileNotFoundError):
            self.fs.read("ledger")

    def test_directory_sync_without_file_sync_recovers_an_empty_file(self):
        self.fs.write("ledger", b"not flushed")
        self.fs.fsync_dir()
        self.fs.crash()
        self.assertEqual(self.fs.list_files(), ["ledger"])
        self.assertEqual(self.fs.read("ledger"), b"")

    def test_both_sync_orders_make_new_contents_durable(self):
        for order in ("file-first", "directory-first"):
            with self.subTest(order=order):
                fs = self.FS()
                fs.write("ledger", b"saved")
                if order == "file-first":
                    fs.fsync("ledger")
                    fs.fsync_dir()
                else:
                    fs.fsync_dir()
                    fs.fsync("ledger")
                fs.crash()
                self.assertEqual(fs.read("ledger"), b"saved")

    def test_unsynced_overwrite_recovers_previous_contents(self):
        self.durable_file()
        self.fs.write("ledger", b"replacement")
        self.fs.crash()
        self.assertEqual(self.fs.read("ledger"), b"acknowledged")

    def test_directory_sync_does_not_flush_existing_file(self):
        self.durable_file()
        self.fs.write("ledger", b"replacement")
        self.fs.fsync_dir()
        self.fs.crash()
        self.assertEqual(self.fs.read("ledger"), b"acknowledged")

    def test_existing_file_sync_needs_no_directory_sync(self):
        self.durable_file()
        self.fs.write("ledger", b"replacement")
        self.fs.fsync("ledger")
        self.fs.crash()
        self.assertEqual(self.fs.read("ledger"), b"replacement")

    def test_rename_before_directory_sync_restores_old_names_and_inodes(self):
        self.durable_file("ledger", b"old")
        self.durable_file("next", b"new")
        self.fs.replace("next", "ledger")
        self.assertEqual(self.fs.list_files(), ["ledger"])
        self.assertEqual(self.fs.read("ledger"), b"new")
        self.fs.crash()
        self.assertEqual(self.fs.list_files(), ["ledger", "next"])
        self.assertEqual(self.fs.read("ledger"), b"old")
        self.assertEqual(self.fs.read("next"), b"new")

    def test_rename_after_directory_sync_installs_new_inode(self):
        self.durable_file("ledger", b"old")
        self.fs.write("next", b"new")
        self.fs.fsync("next")
        self.fs.replace("next", "ledger")
        self.fs.fsync_dir()
        self.fs.crash()
        self.assertEqual(self.fs.list_files(), ["ledger"])
        self.assertEqual(self.fs.read("ledger"), b"new")

    def test_publishing_unflushed_replacement_loses_old_contents(self):
        self.durable_file("ledger", b"old")
        self.fs.write("next", b"new")
        self.fs.replace("next", "ledger")
        self.fs.fsync_dir()
        self.fs.crash()
        self.assertEqual(self.fs.read("ledger"), b"")

    def test_sync_after_rename_targets_inode_not_old_destination(self):
        self.durable_file("ledger", b"old")
        self.durable_file("next", b"prepared")
        self.fs.replace("next", "ledger")
        self.fs.write("ledger", b"latest")
        self.fs.fsync("ledger")
        self.fs.crash()
        self.assertEqual(self.fs.read("ledger"), b"old")
        self.assertEqual(self.fs.read("next"), b"latest")

    def test_unsynced_unlink_restores_old_inode_after_name_reuse(self):
        self.durable_file("ledger", b"old")
        self.fs.unlink("ledger")
        self.fs.write("ledger", b"new inode")
        self.fs.fsync("ledger")
        self.fs.crash()
        self.assertEqual(self.fs.read("ledger"), b"old")

    def test_directory_sync_makes_unlink_durable(self):
        self.durable_file()
        self.fs.unlink("ledger")
        self.fs.fsync_dir()
        self.fs.crash()
        self.assertEqual(self.fs.list_files(), [])

    def test_append_creates_file_and_combines_bytes(self):
        self.fs.append("wal", b"one\x00")
        self.fs.append("wal", b"two\xff")
        self.assertEqual(self.fs.read("wal"), b"one\x00two\xff")
        self.fs.fsync("wal")
        self.fs.fsync_dir()
        self.fs.crash()
        self.assertEqual(self.fs.read("wal"), b"one\x00two\xff")

    def test_unsynced_append_is_discarded(self):
        self.durable_file("wal", b"one")
        self.fs.append("wal", b"two")
        self.fs.crash()
        self.assertEqual(self.fs.read("wal"), b"one")

    def test_empty_append_still_creates_a_visible_file(self):
        self.fs.append("empty", b"")
        self.assertEqual(self.fs.list_files(), ["empty"])
        self.assertEqual(self.fs.read("empty"), b"")

    def test_repeated_crashes_are_idempotent(self):
        self.durable_file()
        self.fs.append("ledger", b"unflushed")
        self.fs.crash()
        self.fs.crash()
        self.assertEqual(self.fs.read("ledger"), b"acknowledged")
        self.assertEqual(self.fs.list_files(), ["ledger"])

    def test_listing_is_sorted_and_detached(self):
        for name in ["z", "a", "middle"]:
            self.fs.write(name, b"")
        names = self.fs.list_files()
        self.assertEqual(names, ["a", "middle", "z"])
        names.clear()
        self.assertEqual(self.fs.list_files(), ["a", "middle", "z"])

    def test_invalid_names_rejected_by_every_name_operation(self):
        invalid = ["", ".", "..", "a/b", "a\\b", "a b", "a\n", "\x00", "é", "a" * 97]
        for name in invalid:
            for operation in (
                lambda: self.fs.read(name), lambda: self.fs.write(name, b"x"),
                lambda: self.fs.append(name, b"x"), lambda: self.fs.fsync(name),
                lambda: self.fs.unlink(name), lambda: self.fs.replace(name, "ok"),
                lambda: self.fs.replace("ok", name),
            ):
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        operation()
        self.assertEqual(self.fs.list_files(), [])

    def test_valid_boundary_names_are_supported(self):
        names = [".hidden", "a" * 96, "A_z-0.1", "..."]
        for name in names:
            self.fs.write(name, b"ok")
        self.assertEqual(self.fs.list_files(), sorted(names))

    def test_non_string_names_raise_type_error(self):
        for name in [None, 1, b"wal"]:
            with self.subTest(name=name), self.assertRaises(TypeError):
                self.fs.write(name, b"data")

    def test_non_bytes_data_does_not_mutate_existing_file(self):
        self.durable_file()
        for data in [None, "text", bytearray(b"bytes"), memoryview(b"bytes")]:
            for operation in [self.fs.write, self.fs.append]:
                with self.subTest(data=type(data).__name__), self.assertRaises(TypeError):
                    operation("ledger", data)
        self.assertEqual(self.fs.read("ledger"), b"acknowledged")

    def test_missing_file_operations_raise_without_changes(self):
        self.durable_file()
        for operation in [self.fs.read, self.fs.fsync, self.fs.unlink]:
            with self.subTest(operation=operation.__name__), self.assertRaises(FileNotFoundError):
                operation("missing")
        with self.assertRaises(FileNotFoundError):
            self.fs.replace("missing", "ledger")
        self.assertEqual(self.fs.read("ledger"), b"acknowledged")

    def test_replace_to_self_is_noop_but_requires_existing_file(self):
        self.durable_file()
        self.fs.replace("ledger", "ledger")
        self.assertEqual(self.fs.read("ledger"), b"acknowledged")
        with self.assertRaises(FileNotFoundError):
            self.fs.replace("missing", "missing")

    def test_export_image_contains_only_durable_names_and_bytes(self):
        self.durable_file("ledger", b"old")
        self.fs.write("ledger", b"unflushed")
        self.fs.write("temporary", b"unpublished")
        self.fs.fsync("temporary")
        image = self.fs.export_image()
        self.assertEqual(image, {"ledger": b"old"})
        image["ledger"] = b"external change"
        self.assertEqual(self.fs.export_image(), {"ledger": b"old"})

    def test_image_round_trip_is_durable_and_independent(self):
        image = {"ledger": b"saved", "empty": b""}
        restored = self.FS.from_image(image)
        image["ledger"] = b"external change"
        self.assertEqual(restored.operation_count, 0)
        restored.crash()
        self.assertEqual(restored.read("ledger"), b"saved")
        self.assertEqual(restored.read("empty"), b"")

    def test_invalid_image_names_and_contents_are_rejected(self):
        with self.assertRaises(ValueError):
            self.FS.from_image({"../escape": b"x"})
        with self.assertRaises(TypeError):
            self.FS.from_image({"wal": "not bytes"})

    def test_clone_preserves_both_states_without_sharing_mutations(self):
        self.durable_file("ledger", b"durable")
        self.fs.write("ledger", b"volatile")
        clone = self.fs.clone()
        self.assertEqual(clone.operation_count, self.fs.operation_count)
        self.assertEqual(clone.read("ledger"), b"volatile")
        clone.write("ledger", b"other")
        clone.fsync("ledger")
        self.fs.crash()
        clone.crash()
        self.assertEqual(self.fs.read("ledger"), b"durable")
        self.assertEqual(clone.read("ledger"), b"other")

    def test_hook_counts_successful_operations_and_excludes_host_helpers(self):
        seen = []
        fs = self.FS(after_operation=lambda name, count: seen.append((name, count)))
        fs.write("a", b"x")
        fs.append("a", b"y")
        fs.read("a")
        fs.fsync("a")
        fs.replace("a", "b")
        fs.list_files()
        fs.fsync_dir()
        fs.unlink("b")
        with self.assertRaises(FileNotFoundError):
            fs.read("missing")
        fs.export_image()
        fs.clone()
        fs.crash()
        self.assertEqual(seen, list(zip(
            ["write", "append", "read", "fsync", "replace", "list_files", "fsync_dir", "unlink"],
            range(1, 9),
        )))
        self.assertEqual(fs.operation_count, 8)

    def test_hook_exception_happens_after_sync_before_reply(self):
        class CrashBeforeReply(Exception):
            pass

        def interrupt(name, count):
            if name == "fsync":
                raise CrashBeforeReply

        fs = self.FS.from_image({"ledger": b"old"}, after_operation=interrupt)
        fs.write("ledger", b"new")
        with self.assertRaises(CrashBeforeReply):
            fs.fsync("ledger")
        fs.crash()
        self.assertEqual(fs.read("ledger"), b"new")
        self.assertEqual(fs.operation_count, 3)

    def test_clone_does_not_copy_original_hook(self):
        seen = []
        fs = self.FS(after_operation=lambda name, count: seen.append(name))
        clone = fs.clone()
        clone.write("wal", b"x")
        self.assertEqual(seen, [])

    def test_repeated_compaction_retains_bounded_payload_without_a_crash(self):
        size = 8192
        for generation in range(40):
            payload = bytes([generation]) * size
            self.fs.write("next", payload)
            self.fs.fsync("next")
            self.fs.replace("next", "checkpoint")
            self.fs.fsync_dir()
            # Crash a copy so the original must bound storage without a restart.
            restarted = self.fs.clone()
            restarted.crash()
            self.assertEqual(restarted.read("checkpoint"), payload)
            self.assertEqual(restarted.list_files(), ["checkpoint"])
        stats = self.fs.storage_stats()
        self.assertLessEqual(stats["content_bytes"], 4 * size)
        self.assertLessEqual(stats["inode_count"], 2)
        self.fs.write("checkpoint", b"unflushed")
        self.fs.crash()
        self.assertEqual(self.fs.read("checkpoint"), payload)

    def test_reclamation_preserves_unflushed_visible_file_as_empty_after_crash(self):
        self.durable_file("checkpoint", b"old checkpoint")
        self.fs.write("next", b"new checkpoint")
        self.fs.fsync("next")
        self.fs.replace("next", "checkpoint")
        self.fs.write("unflushed", b"unsaved")
        self.fs.fsync_dir()
        self.fs.crash()
        self.assertEqual(self.fs.read("checkpoint"), b"new checkpoint")
        self.assertEqual(self.fs.read("unflushed"), b"")

    def test_storage_metrics_are_detached_host_helpers_and_empty_after_retirement(self):
        seen = []
        fs = self.FS.from_image({"checkpoint": b"payload"},
                               after_operation=lambda name, count: seen.append(name))
        stats = fs.storage_stats()
        self.assertEqual(fs.operation_count, 0)
        self.assertEqual(seen, [])
        stats.clear()
        self.assertGreater(fs.storage_stats()["content_bytes"], 0)
        fs.unlink("checkpoint")
        # An unsynced deletion still needs all acknowledged bytes on crash.
        self.assertEqual(fs.export_image(), {"checkpoint": b"payload"})
        restarted = fs.clone()
        restarted.crash()
        self.assertEqual(restarted.read("checkpoint"), b"payload")
        fs.fsync_dir()
        self.assertEqual(fs.storage_stats(), {"inode_count": 0, "content_bytes": 0})
        fs.crash()
        self.assertEqual(fs.list_files(), [])


if __name__ == "__main__":
    unittest.main()
