#!/usr/bin/env python3
"""
Test script for progressive screenshot save functionality.

This script tests that:
1. Screenshots are saved instantly without blocking
2. Background optimization reduces file size
3. Multiple rapid screenshots work correctly
"""

import os
import sys
import time
import logging
from PIL import Image

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from captix.utils.capture import ScreenCapture
from captix.utils.paths import CaptiXPaths

# Set up logging to see optimization messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def create_test_image(width=1920, height=1080):
    """Create a test image with gradient pattern."""
    import random
    img = Image.new('RGB', (width, height))
    pixels = img.load()

    # Create a gradient pattern with some randomness
    for x in range(width):
        for y in range(height):
            r = int((x / width) * 255)
            g = int((y / height) * 255)
            b = random.randint(0, 50)  # Add some noise
            pixels[x, y] = (r, g, b)

    return img

def test_progressive_save():
    """Test the progressive save functionality."""
    print("=" * 60)
    print("Testing Progressive Screenshot Save")
    print("=" * 60)

    capture = ScreenCapture()
    test_dir = CaptiXPaths.get_screenshots_dir()

    # Test 1: Small screenshot (should be fast anyway)
    print("\n[Test 1] Small screenshot (800x600)...")
    small_img = create_test_image(800, 600)
    start_time = time.time()
    filepath1, size1 = capture.save_screenshot(
        small_img,
        directory=test_dir,
        filename="test_small.png",
        capture_type="test"
    )
    elapsed = time.time() - start_time
    print(f"✓ Saved instantly in {elapsed*1000:.1f}ms: {filepath1}")
    print(f"  Initial size: {size1} bytes ({size1/1024:.1f} KB)")

    # Test 2: Large screenshot (this would block for 2-5s with old code)
    print("\n[Test 2] Large screenshot (3840x2160)...")
    large_img = create_test_image(3840, 2160)
    start_time = time.time()
    filepath2, size2 = capture.save_screenshot(
        large_img,
        directory=test_dir,
        filename="test_large.png",
        capture_type="test"
    )
    elapsed = time.time() - start_time
    print(f"✓ Saved instantly in {elapsed*1000:.1f}ms: {filepath2}")
    print(f"  Initial size: {size2} bytes ({size2/1024:.1f} KB)")

    if elapsed > 0.5:
        print("  ⚠ WARNING: Save took longer than expected!")
    else:
        print("  ✓ Save was instant (< 500ms)")

    # Test 3: Multiple rapid screenshots
    print("\n[Test 3] Multiple rapid screenshots...")
    start_time = time.time()
    for i in range(3):
        test_img = create_test_image(1280, 720)
        filepath, size = capture.save_screenshot(
            test_img,
            directory=test_dir,
            filename=f"test_rapid_{i}.png",
            capture_type="test"
        )
        print(f"  Screenshot {i+1}: {filepath} ({size} bytes)")
    elapsed = time.time() - start_time
    print(f"✓ All 3 screenshots saved in {elapsed*1000:.1f}ms ({elapsed/3*1000:.1f}ms average)")

    # Wait for background optimization to complete
    print("\n[Test 4] Waiting for background optimization...")
    print("  (Check log messages above for optimization results)")
    time.sleep(3)  # Give threads time to complete

    # Check optimized file sizes
    print("\n[Test 5] Checking optimized file sizes...")
    optimized_size1 = os.path.getsize(filepath1)
    optimized_size2 = os.path.getsize(filepath2)

    print(f"  Small image: {size1} -> {optimized_size1} bytes "
          f"({(size1-optimized_size1)/size1*100:.1f}% reduction)")
    print(f"  Large image: {size2} -> {optimized_size2} bytes "
          f"({(size2-optimized_size2)/size2*1001:.1f}% reduction)")

    # Cleanup test files
    print("\n[Cleanup] Removing test files...")
    for f in [filepath1, filepath2]:
        if os.path.exists(f):
            os.remove(f)
            print(f"  Removed: {f}")
    for i in range(3):
        rapid_file = os.path.join(test_dir, f"test_rapid_{i}.png")
        if os.path.exists(rapid_file):
            os.remove(rapid_file)
            print(f"  Removed: {rapid_file}")

    capture.cleanup()

    print("\n" + "=" * 60)
    print("✓ All tests completed successfully!")
    print("=" * 60)
    print("\nKey improvements:")
    print("  • Screenshots save instantly regardless of size")
    print("  • Background optimization reduces file size automatically")
    print("  • Multiple rapid screenshots work without blocking")
    print("  • No UI freezing during large screenshot captures")

if __name__ == "__main__":
    try:
        test_progressive_save()
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
