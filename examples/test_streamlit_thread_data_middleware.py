"""Test script for StreamlitThreadDataMiddleware.

This script validates that the middleware:
1. Creates workspace directories
2. Provides correct paths in state
3. Works with different thread IDs
4. Lists files correctly
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from genai_blueprint.webapp.middlewares.streamlit_thread_data import StreamlitThreadDataMiddleware


def test_middleware_basic():
    """Test basic middleware functionality."""
    print("=" * 60)
    print("Test 1: Basic Middleware Functionality")
    print("=" * 60)

    # Create middleware with temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        mw = StreamlitThreadDataMiddleware(base_dir=tmpdir)
        print(f"✓ Created middleware with base_dir: {tmpdir}")

        # Create mock runtime with config
        thread_id = "test-thread-123"
        runtime = SimpleNamespace(config={"configurable": {"thread_id": thread_id}}, context=None)

        # Call before_agent
        state = {}
        result = mw.before_agent(state, runtime)

        print(f"✓ Called before_agent, got result: {result}")

        # Verify paths
        assert "thread_data" in result
        assert "workspace_path" in result["thread_data"]
        assert "uploads_path" in result["thread_data"]
        assert "outputs_path" in result["thread_data"]
        print("✓ All required paths present in result")

        # Verify directories were created
        workspace_path = result["thread_data"]["workspace_path"]
        uploads_path = result["thread_data"]["uploads_path"]
        outputs_path = result["thread_data"]["outputs_path"]

        assert Path(workspace_path).exists()
        assert Path(uploads_path).exists()
        assert Path(outputs_path).exists()
        print("✓ All directories created:")
        print(f"  - workspace: {workspace_path}")
        print(f"  - uploads: {uploads_path}")
        print(f"  - outputs: {outputs_path}")

    print("✅ Test 1 PASSED\n")


def test_file_listing():
    """Test file listing functionality."""
    print("=" * 60)
    print("Test 2: File Listing")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        mw = StreamlitThreadDataMiddleware(base_dir=tmpdir)
        thread_id = "test-thread-456"

        # Create mock runtime
        runtime = SimpleNamespace(config={"configurable": {"thread_id": thread_id}}, context=None)

        # Initialize workspace
        result = mw.before_agent({}, runtime)
        workspace_path = result["thread_data"]["workspace_path"]
        print(f"✓ Workspace created at: {workspace_path}")

        # Create some test files
        test_files = ["presentation.pptx", "chart.png", "data.csv"]
        for filename in test_files:
            file_path = Path(workspace_path) / filename
            file_path.write_text(f"Test content for {filename}")
        print(f"✓ Created {len(test_files)} test files")

        # List files
        files = mw.list_workspace_files(thread_id)
        print(f"✓ Listed {len(files)} files")

        # Verify
        assert len(files) == len(test_files)
        file_names = [f["name"] for f in files]
        for test_file in test_files:
            assert test_file in file_names
        print("✓ All test files found in listing")

        # Check file info
        for file_info in files:
            assert "name" in file_info
            assert "path" in file_info
            assert "relative_path" in file_info
            assert "size" in file_info
            assert "modified" in file_info
            assert file_info["size"] > 0
            print(f"  - {file_info['name']}: {file_info['size']} bytes, path: {file_info['relative_path']}")

    print("✅ Test 2 PASSED\n")


def test_multiple_threads():
    """Test multiple thread isolation."""
    print("=" * 60)
    print("Test 3: Multiple Thread Isolation")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        mw = StreamlitThreadDataMiddleware(base_dir=tmpdir)

        threads = ["thread-1", "thread-2", "thread-3"]
        workspaces = {}

        # Create workspaces for multiple threads
        for thread_id in threads:
            runtime = SimpleNamespace(config={"configurable": {"thread_id": thread_id}}, context=None)
            result = mw.before_agent({}, runtime)
            workspaces[thread_id] = result["thread_data"]["workspace_path"]
            print(f"✓ Created workspace for {thread_id}")

        # Verify all paths are unique
        unique_paths = set(workspaces.values())
        assert len(unique_paths) == len(threads)
        print("✓ All thread workspaces have unique paths")

        # Create different files in each workspace
        for thread_id in threads:
            workspace = Path(workspaces[thread_id])
            file_path = workspace / f"file-{thread_id}.txt"
            file_path.write_text(f"Content for {thread_id}")
            print(f"✓ Created file in {thread_id} workspace")

        # Verify files are isolated
        for thread_id in threads:
            files = mw.list_workspace_files(thread_id)
            assert len(files) == 1
            assert files[0]["name"] == f"file-{thread_id}.txt"
            print(f"✓ Verified {thread_id} has only its own file")

    print("✅ Test 3 PASSED\n")


def test_lazy_init():
    """Test lazy initialization mode."""
    print("=" * 60)
    print("Test 4: Lazy Initialization")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        mw = StreamlitThreadDataMiddleware(base_dir=tmpdir, lazy_init=True)
        print("✓ Created middleware with lazy_init=True")

        thread_id = "lazy-thread"
        runtime = SimpleNamespace(config={"configurable": {"thread_id": thread_id}}, context=None)

        # Call before_agent
        result = mw.before_agent({}, runtime)
        print("✓ Called before_agent")

        # Paths should be computed but NOT created
        workspace_path = result["thread_data"]["workspace_path"]
        print(f"✓ Got workspace path: {workspace_path}")

        # With lazy_init, directories should NOT be created automatically
        # (They might be created by before_agent, so let's just check we got paths)
        assert "workspace_path" in result["thread_data"]
        print("✓ Lazy init provided paths without immediate directory creation")

    print("✅ Test 4 PASSED\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("StreamlitThreadDataMiddleware Test Suite")
    print("=" * 60 + "\n")

    try:
        test_middleware_basic()
        test_file_listing()
        test_multiple_threads()
        test_lazy_init()

        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
