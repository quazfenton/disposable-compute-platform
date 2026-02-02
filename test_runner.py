#!/usr/bin/env python3
"""
Test runner for disposable compute platform
"""

import asyncio
import sys
from datetime import datetime

from src.main import platform
from src.models.session import SessionType


async def test_platform_functionality():
    """Test the main platform functionality"""
    print("Testing Disposable Compute Platform...")
    
    # Initialize platform
    await platform.initialize()
    print("✓ Platform initialized")
    
    # Test 1: Create a run-repo session
    print("\n1. Testing Run This Repo functionality...")
    try:
        run_repo_id = await platform.run_repo(
            repo_url="https://github.com/example/hello-world.git",
            ttl_minutes=10
        )
        print(f"✓ Created run-repo session: {run_repo_id}")
        
        # Check status
        status = await platform.get_session_status(run_repo_id)
        print(f"✓ Session status: {status['status']}")
    except Exception as e:
        print(f"✗ Run-repo test failed: {e}")
        return False
    
    # Test 2: Create a preview environment
    print("\n2. Testing Preview Environments functionality...")
    try:
        preview_id = await platform.create_preview_environment(
            repo_url="https://github.com/example/myapp.git",
            repo_ref="feature/test",
            pr_number=999
        )
        print(f"✓ Created preview session: {preview_id}")
        
        # Check status
        status = await platform.get_session_status(preview_id)
        print(f"✓ Session status: {status['status']}")
    except Exception as e:
        print(f"✗ Preview test failed: {e}")
        return False
    
    # Test 3: Create a forkable GUI session
    print("\n3. Testing Forkable GUI functionality...")
    try:
        gui_id = await platform.create_forkable_gui_session(
            app_type="generic-gui",
            repo_url="https://github.com/example/gui-app.git"
        )
        print(f"✓ Created GUI session: {gui_id}")
        
        # Check status
        status = await platform.get_session_status(gui_id)
        print(f"✓ Session status: {status['status']}")
    except Exception as e:
        print(f"✗ GUI test failed: {e}")
        return False
    
    # Test 4: Test session management
    print("\n4. Testing session management...")
    try:
        # Get all session statuses
        for session_id in [run_repo_id, preview_id, gui_id]:
            status = await platform.get_session_status(session_id)
            print(f"✓ Session {session_id[:12]}... status: {status['status']}")
    except Exception as e:
        print(f"✗ Session management test failed: {e}")
        return False
    
    # Test 5: Test destruction
    print("\n5. Testing session destruction...")
    try:
        await platform.destroy_session(run_repo_id)
        await platform.destroy_session(preview_id)
        await platform.destroy_session(gui_id)
        print("✓ All sessions destroyed successfully")
    except Exception as e:
        print(f"✗ Session destruction test failed: {e}")
        return False
    
    print("\n✓ All tests passed! Platform is working correctly.")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_platform_functionality())
    sys.exit(0 if success else 1)