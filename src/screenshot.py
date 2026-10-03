import math
import time
from PIL import ImageGrab

import os

# Output Directory
OUTDIR = "out"

# Wait Limit
LIMIT = 100


def take_screenshot(window):

    # Bounding Box

    bbox = [
        window.left,  # Left
        window.top,  # Top
        window.left + window.width,  # Right
        window.top + window.height,  # Bottom
    ]

    # Take a screenshot of the window and return it
    return ImageGrab.grab(bbox=bbox, all_screens=True)


def save_screenshot(window, name="screenshot.png", format="PNG"):

    # Take a screenshot of the window
    image = take_screenshot(window)

    # Create the output directory
    os.makedirs(OUTDIR, exist_ok=True)

    # Create the output filename
    filename = os.path.join(OUTDIR, name)

    # Save the screenshot
    image.save(filename, format)


def wait_for_change(window, x=None, y=None, delay=0.1, limit=100):

    # X Coordinate not provided
    if x == None:
        # Center Pixel
        x = math.floor(window.width / 2)

    # Y Coordinate not provided
    if y == None:
        # Center Pixel (Bottom Screen)
        y = math.floor((window.height * 2) / 3)

    # Pixel tuple
    point = (x, y)

    screenshot = take_screenshot(window)
    first = screenshot.getpixel(point)
    pixel = first

    i = 0

    # Wait for change
    while pixel == first:

        # Limit exceeded
        if i > limit:
            raise Exception(f"Wait for change limit '{limit}' exceeded!")

        screenshot = take_screenshot(window)
        pixel = screenshot.getpixel(point)

        time.sleep(delay)

        i += 1

    # Colour changed
    return i


def check_for_colour(window, x=None, y=None, r=0, g=0, b=0):

    # X Coordinate not provided
    if x == None:
        # Center Pixel
        x = math.floor(window.width / 2)

    # Y Coordinate not provided
    if y == None:
        # Center Pixel (Bottom Screen)
        y = math.floor((window.height * 2) / 3)

    # Pixel tuple
    point = (x, y)

    # Target colour
    target = (r, g, b)

    screenshot = take_screenshot(window)
    pixel = screenshot.getpixel(point)

    # True/False if matches
    return pixel == target


def wait_for_colour(window, x=None, y=None, r=0, g=0, b=0, delay=0.1, limit=100):

    # X Coordinate not provided
    if x == None:
        # Center Pixel
        x = math.floor(window.width / 2)

    # Y Coordinate not provided
    if y == None:
        # Center Pixel (Bottom Screen)
        y = math.floor((window.height * 2) / 3)

    # Pixel tuple
    point = (x, y)

    # Target colour
    target = (r, g, b)

    # Placeholder pixel
    pixel = (None, None, None)

    i = 0

    # While the correct colour has not been found
    while pixel != target:

        # Limit exceeded
        if i > limit:
            raise Exception(f"Wait for colour limit '{limit}' exceeded!")

        screenshot = take_screenshot(window)
        pixel = screenshot.getpixel(point)

        time.sleep(delay)

        i += 1

    # Desired colour found
    return i

