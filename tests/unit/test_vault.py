"""
Unit tests for ObsidianVault operations.
Tests file locking, atomic writes, and concurrent access safety.
"""

import pytest
import threading
import time


class TestObsidianVaultBasicOperations:
    """Test basic vault read/write operations."""

    def test_read_nonexistent_node(self, vault):
        """Should raise FileNotFoundError for missing nodes."""
        with pytest.raises(FileNotFoundError):
            vault.read_node("nonexistent.md")

    def test_write_and_read_node(self, vault, sample_node_content):
        """Should write and read a node correctly."""
        # Write
        result = vault.write_node(
            sample_node_content["path"],
            sample_node_content["content"],
            sample_node_content["frontmatter"],
        )
        assert result["status"] == "written"
        assert result["content_length"] == len(sample_node_content["content"])

        # Read back
        node = vault.read_node(sample_node_content["path"])
        assert node["path"] == sample_node_content["path"]
        assert node["frontmatter"]["title"] == "Test Node"
        assert node["content"] == sample_node_content["content"]

    def test_write_without_frontmatter(self, vault):
        """Should write plain markdown without frontmatter."""
        content = "# Plain Content\n\nNo frontmatter here."
        vault.write_node("plain.md", content)

        node = vault.read_node("plain.md")
        assert node["frontmatter"] == {}
        assert node["content"] == content

    def test_update_frontmatter(self, vault, sample_node_content):
        """Should partially update frontmatter."""
        # Create initial node
        vault.write_node(
            sample_node_content["path"],
            sample_node_content["content"],
            sample_node_content["frontmatter"],
        )

        # Update frontmatter
        result = vault.update_frontmatter(
            sample_node_content["path"], {"status": "completed", "result": "pass"}
        )
        assert result["status"] == "updated"

        # Verify
        node = vault.read_node(sample_node_content["path"])
        assert node["frontmatter"]["status"] == "completed"
        assert node["frontmatter"]["result"] == "pass"
        assert node["frontmatter"]["title"] == "Test Node"  # Original preserved
        assert "modified" in node["frontmatter"]

    def test_list_nodes(self, vault):
        """Should list all markdown files."""
        vault.write_node("a.md", "Content A")
        vault.write_node("b.md", "Content B")
        vault.write_node("subdir/c.md", "Content C")

        nodes = vault.list_nodes()
        assert len(nodes) == 3
        assert "a.md" in nodes
        assert "b.md" in nodes
        assert "subdir/c.md" in nodes

    def test_list_nodes_empty_directory(self, vault):
        """Should return empty list for nonexistent directory."""
        nodes = vault.list_nodes("nonexistent")
        assert nodes == []

    def test_find_wiki_links(self, vault):
        """Should extract wiki-links from content."""
        content = """
# Test

See [[Related_Node]] for more info.
Also check [[Another Node]] and [[Third_Node]].
"""
        vault.write_node("links.md", content)
        links = vault.find_wiki_links("links.md")
        assert "Related_Node" in links
        assert "Another Node" in links
        assert "Third_Node" in links


class TestObsidianVaultConcurrency:
    """Test concurrent access safety with file locking."""

    def test_concurrent_writes_same_node(self, vault):
        """Should handle concurrent writes without corruption."""
        node_path = "concurrent.md"
        vault.write_node(node_path, "Initial", {"version": 0})

        errors = []
        results = []

        def writer(thread_id):
            try:
                for i in range(5):
                    result = vault.update_frontmatter(node_path, {"version": thread_id * 100 + i})
                    results.append(result)
                    time.sleep(0.01)  # Small delay to increase contention
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without errors
        assert len(errors) == 0, f"Errors during concurrent writes: {errors}"

        # Node should be readable and valid YAML
        node = vault.read_node(node_path)
        assert "version" in node["frontmatter"]
        assert "modified" in node["frontmatter"]

    def test_concurrent_writes_different_nodes(self, vault):
        """Should handle concurrent writes to different nodes."""
        results = []
        errors = []

        def writer(node_id):
            try:
                for i in range(3):
                    vault.write_node(
                        f"node_{node_id}.md", f"Content {i}", {"writer": node_id, "iteration": i}
                    )
                    results.append((node_id, i))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"

        # All nodes should exist and be valid
        for i in range(5):
            node = vault.read_node(f"node_{i}.md")
            assert node["frontmatter"]["writer"] == i


class TestObsidianVaultAtomicWrites:
    """Test atomic write operations."""

    def test_atomic_write_no_partial_files(self, vault):
        """Should not leave partial files on crash."""
        # Write a large file
        large_content = "X" * 10000
        vault.write_node("large.md", large_content)

        # Check no temp files left behind
        temp_files = list(vault.vault_path.glob(".tmp_*"))
        assert len(temp_files) == 0, f"Temp files found: {temp_files}"

    def test_write_verification(self, vault):
        """Should verify written content matches."""
        content = "Verified content"
        result = vault.write_node("verified.md", content)
        assert result["status"] == "written"

        # Read and verify
        node = vault.read_node("verified.md")
        assert node["content"] == content

    def test_yaml_corruption_recovery(self, vault):
        """Should handle corrupted YAML gracefully."""
        # Write a node with bad YAML manually
        bad_content = "---\ninvalid: yaml: [unclosed\n---\n\nContent here"
        file_path = vault.vault_path / "corrupt.md"
        file_path.write_text(bad_content)

        # Should still return node with parse_error
        node = vault.read_node("corrupt.md")
        assert "parse_error" in node
        assert node["content"] == bad_content  # Raw content returned


class TestObsidianVaultPathSecurity:
    """Test path traversal and security."""

    def test_path_traversal_blocked(self, vault):
        """Should prevent path traversal attacks."""
        # Try to write outside vault
        with pytest.raises((ValueError, FileNotFoundError)):
            vault.write_node("../outside.md", "Hacked!")

    def test_absolute_path_blocked(self, vault):
        """Should reject absolute paths."""
        with pytest.raises((ValueError, FileNotFoundError)):
            vault.write_node("/etc/passwd", "Hacked!")
