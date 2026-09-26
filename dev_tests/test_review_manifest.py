"""Regression checks for manifest-verified frozen review candidates."""

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
spec = importlib.util.spec_from_file_location(
    "review_manifest_module",
    pathlib.Path(__file__).resolve().parents[1] / "evaluation" / "prepare_review.py",
)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)
class FrozenSourceChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.addCleanup(setattr, review, "ROOT", review.ROOT)
        review.ROOT = self.root
        self.task = self.root / "artifacts/local/frozen/example-20260927T000000000000Z/example"
        self.task.mkdir(parents=True)
        self.contents = {"task.toml": b"schema_version = '1.0'\n", "instruction.md": b"repair\n", "environment/data.bin": b"\x00\x01"}
        self.manifest_path = self.task.parent / "source-manifest.json"
        self.publish()
    def publish(self):
        entries, tree = [], hashlib.sha256()
        for name, data in sorted(self.contents.items()):
            target = self.task / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            entries.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            tree.update(name.encode() + b"\0" + data + b"\0")
        self.manifest = {"source": "tasks/example", "snapshot_tree_sha256": tree.hexdigest(), "files": entries}
        self.manifest_path.write_text(json.dumps(self.manifest))
    def validate(self, path=None):
        self.assertTrue(callable(getattr(review, "validate_review_source", None)), "frozen review source validation is not implemented")
        return review.validate_review_source(path or self.task)
    def test_accept_exact_frozen_candidate_and_record_provenance(self):
        found = self.validate()
        self.assertEqual(found["manifest_sha256"], hashlib.sha256(self.manifest_path.read_bytes()).hexdigest())
        self.assertEqual(found["snapshot_tree_sha256"], self.manifest["snapshot_tree_sha256"])
    def test_canonical_task_path_remains_allowed(self):
        task = self.root / "tasks/example"
        task.mkdir(parents=True)
        self.assertIsNone(self.validate(task))
    def test_unrelated_directory_is_rejected(self):
        with self.assertRaises(ValueError): self.validate(self.root / "elsewhere")
    def test_reject_same_length_file_change(self):
        (self.task / "instruction.md").write_bytes(b"change\n")
        with self.assertRaises(ValueError): self.validate()
    def test_reject_missing_file(self):
        (self.task / "instruction.md").unlink()
        with self.assertRaises(ValueError): self.validate()
    def test_reject_unlisted_ignored_runtime_file(self):
        cache = self.task / "__pycache__"
        cache.mkdir()
        (cache / "extra.pyc").write_bytes(b"cache")
        with self.assertRaises(ValueError): self.validate()
    def test_reject_manifest_disagreement(self):
        for change in ("tree", "size", "sha", "source", "duplicate", "traversal"):
            with self.subTest(change=change):
                self.publish()
                value = self.manifest
                if change == "tree": value["snapshot_tree_sha256"] = "0" * 64
                if change == "size": value["files"][0]["bytes"] += 1
                if change == "sha": value["files"][0]["sha256"] = "0" * 64
                if change == "source": value["source"] = "tasks/other"
                if change == "duplicate": value["files"].append(value["files"][0])
                if change == "traversal": value["files"][0]["path"] = "../escape"
                self.manifest_path.write_text(json.dumps(value))
                with self.assertRaises(ValueError): self.validate()
    def test_full_frozen_inventory_keeps_even_manifested_cached_files(self):
        self.contents["__pycache__/tracked.pyc"] = b"tracked"
        self.publish()
        self.validate()
        self.assertEqual(set(review.task_files(self.task, exclude_caches=False)), set(self.contents))


class NativeStageChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = pathlib.Path(self.temporary.name) / "home"
        self.home.mkdir()

    def create_stage(self, label="test-review"):
        self.assertTrue(callable(getattr(review, "create_native_review_parent", None)),
                        "native review staging is not implemented")
        with patch.object(review.Path, "home", return_value=self.home):
            return review.create_native_review_parent(label)

    def test_stage_is_created_beneath_native_home_state_directory(self):
        actual = self.create_stage()
        expected = self.home / ".local/state/klavis-terminal-bench/reviews/test-review"
        self.assertEqual(actual, expected)
        self.assertTrue(actual.is_dir())
        self.assertFalse((actual / "review-task").exists())

    def test_existing_stage_is_not_reused_or_overwritten(self):
        actual = self.create_stage()
        marker = actual / "keep.txt"
        marker.write_text("existing review")
        with self.assertRaises(FileExistsError): self.create_stage()
        self.assertEqual(marker.read_text(), "existing review")

    def test_symlinked_native_path_component_is_rejected(self):
        outside = pathlib.Path(self.temporary.name) / "elsewhere"
        outside.mkdir()
        try:
            (self.home / ".local").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Creating symlinks requires local permission: {error}")
        with self.assertRaises(ValueError): self.create_stage()
        self.assertEqual(list(outside.iterdir()), [])


class ReviewRuntimeChecks(unittest.TestCase):
    def runtime(self, cached_python_base):
        self.assertTrue(callable(getattr(review, "review_runtime", None)),
                        "cached Python review runtime is not implemented")
        return review.review_runtime(cached_python_base)

    def test_cached_base_uses_exact_pinned_image_and_minimal_apt_packages(self):
        self.assertEqual(self.runtime(True), {
            "base_image": "python:3.13-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26",
            "apt_packages": ["ca-certificates", "curl", "git", "procps"],
            "cached_python_base": True,
        })

    def test_default_base_and_packages_remain_unchanged(self):
        self.assertEqual(self.runtime(False), {
            "base_image": "ubuntu:24.04",
            "apt_packages": ["ca-certificates", "curl", "git", "nodejs", "npm", "procps", "python3"],
            "cached_python_base": False,
        })

    def test_cli_help_exposes_both_opt_in_runtime_options_without_preparing(self):
        completed = subprocess.run([sys.executable, "-B", review.__file__, "--help"],
                                   capture_output=True, text=True, check=True)
        self.assertIn("--native-stage", completed.stdout)
        self.assertIn("--cached-python-base", completed.stdout)
        self.assertIn("--preinstalled-codex", completed.stdout)

    def test_standalone_runtime_is_pinned_and_does_not_install_node(self):
        for cached in (True, False):
            with self.subTest(cached=cached):
                runtime = self.runtime(cached)
                dockerfile = review.review_dockerfile(runtime, preinstalled_codex=True)
                self.assertIn("ADD --checksum=sha256:" + review.CODEX_RELEASE["sha256"], dockerfile)
                self.assertIn(review.CODEX_RELEASE["url"], dockerfile)
                self.assertIn("COPY --from=codex-assets /opt/codex /opt/codex", dockerfile)
                self.assertIn("codex-cli 0.157.1", dockerfile)
                self.assertIn("/opt/codex/codex-path/rg", dockerfile)
                self.assertNotIn(" nodejs", dockerfile)
                self.assertNotIn(" npm", dockerfile)
                self.assertNotIn("auth.json", dockerfile)
                self.assertEqual(dockerfile.count("FROM " + runtime["base_image"]), 2)

    def test_standalone_install_is_opt_in(self):
        dockerfile = review.review_dockerfile(self.runtime(False))
        self.assertIn(" nodejs npm ", dockerfile)
        self.assertNotIn("codex-assets", dockerfile)


if __name__ == "__main__":
    unittest.main(verbosity=2)
