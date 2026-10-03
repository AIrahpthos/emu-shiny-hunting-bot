import math, os, time, random
from datetime import datetime

import src.screenshot as screenshot
import src.gamepad as gamepad
import src.window as window

from vgamepad import XUSB_BUTTON as button

from src.gamepad import JOYSTICK_COORDINATES as joystick
from src.log import write_log, LOG_FILE

# Menu Button Press
MENU_PRESS = 0.1

# ~1.1s delay for shinies
SHINY_DELAY = 1.1

# Encounters Text FIle
ENCOUNTERS_FILE = "encounters.txt"

# Eggs Hatched Text File
HATCHED_FILE = "hatched.txt"


def quick_release_bot(window, game=None, autostart=None):

    def release_mon(gp):
        # Open menu, release pokemon, close menu
        gamepad.press_and_release_sequence(
            gp,
            [
                [button.XUSB_GAMEPAD_B],
                [button.XUSB_GAMEPAD_DPAD_UP],
                [button.XUSB_GAMEPAD_DPAD_UP],
                [button.XUSB_GAMEPAD_B],
                [button.XUSB_GAMEPAD_DPAD_UP],
                [button.XUSB_GAMEPAD_B],
                [button.XUSB_GAMEPAD_B],
                [button.XUSB_GAMEPAD_B],
            ],
            1,
        )

    # Bot Version
    version = "1.0.0"

    # Create the log file (or clear it)
    with open(LOG_FILE, "w") as file:
        write_log(f"Starting Quick Release Bot v{version} ...")

    # Create & configure virtual gamepad
    gp = gamepad.get_gamepad()

    print("Start this script from the top-left most position in the leftmost box.")
    print("Please ensure boxes are full from the top-left to top-right first.")

    count = 1
    try:
        count = int(input("Enter the number of Pokemon to release: "))
        print(f"{count} pokemon will be released.")
    except Exception as e:
        print(f"Releasing selected Pokemon only.")

    # Move controller right
    move_right = True

    # Release 'count' pokemon:
    for index in range(count):

        # Box slot number
        slot = index + 1

        print(f"Releasing pokemon {index + 1} ...")

        # Release Pokemon
        release_mon(gp)

        # Moving to new box
        if slot % 30 == 0:
            gamepad.press_and_release_sequence(
                gp,
                [
                    # Switch page
                    [button.XUSB_GAMEPAD_RIGHT_SHOULDER],
                    # Reset to left
                    [button.XUSB_GAMEPAD_DPAD_RIGHT],
                    [button.XUSB_GAMEPAD_DPAD_RIGHT],
                    [button.XUSB_GAMEPAD_DPAD_RIGHT],
                    # Reset to top
                    [button.XUSB_GAMEPAD_DPAD_DOWN],
                    [button.XUSB_GAMEPAD_DPAD_DOWN],
                    [button.XUSB_GAMEPAD_DPAD_DOWN],
                ],
            )

        # Moving to new row
        elif slot % 6 == 0:
            gamepad.press_and_release(gp, [button.XUSB_GAMEPAD_DPAD_DOWN])
            # Toggle move left/right
            move_right = not move_right
            # Wait 1 second
            time.sleep(1)

        # Not last release
        elif slot != count:
            if move_right:
                gamepad.press_and_release(gp, [button.XUSB_GAMEPAD_DPAD_RIGHT])
            else:
                gamepad.press_and_release(gp, [button.XUSB_GAMEPAD_DPAD_LEFT])

    time.sleep(1)


def static_encounter_bot(citra, game=None, autostart=None):

    def input_loop(gp):

        # Move control stick forward (For ultra space encounters, etc.)
        gamepad.left_stick_and_release(gp, joystick["neutral"], joystick["up"], 1)

        # Wait for fade to black / dark blue
        screenshot.wait_for_colour(citra)
        screenshot.wait_for_change(citra)

        # Time until battle menu
        start = datetime.now()
        screenshot.wait_for_change(citra)
        end = datetime.now()

        # Save screenshot of the last encounter
        screenshot.save_screenshot(citra, "lastencounter.png")

        # Seconds to load battle menu
        duration = end - start

        # Return seconds
        return duration.total_seconds()

    # Bot Version
    version = "1.0.0"

    # Reset times
    fastest = None
    encounters = 0

    # Create the log file (or clear it)
    with open(LOG_FILE, "w") as file:
        write_log(f"Starting Static Encounter Bot v{version} ...")

    # Create the encounters file, if empty
    if not os.path.exists(ENCOUNTERS_FILE):
        with open(ENCOUNTERS_FILE, "w") as file:
            file.write("0")

    # Parse the number of encounters from the file
    with open(ENCOUNTERS_FILE, "r") as file:
        encounters = int(file.read())

    write_log(f"Current encounters: {encounters} ...")

    # Create & configure virtual gamepad
    gp = gamepad.get_gamepad()

    # Start loop
    while True:

        # Encounter start time
        start = datetime.now()

        try:
            # Increment counter
            encounters += 1

            write_log(f"Starting encounter {encounters} ...")

            # Random ~0-4s delay
            offset = random.uniform(0.0, 4.0)

            # Reset game (With random delay)
            gamepad.soft_reset(gp, offset=offset)

            # Perform input loop
            seconds = input_loop(gp)

            write_log(f"Battle menu loaded in {seconds}s.")

            # First encounter
            if fastest == None:
                input("First encounter: press enter to continue")
                fastest = seconds

            # Update fastest time
            elif fastest > seconds:
                write_log(f"Fastest load time updated.")
                fastest = seconds

            # Encounter is too quick (error)
            elif seconds + SHINY_DELAY < fastest:
                raise Exception("Load time was too quick!")

            # Potential shiny detected
            elif seconds > fastest + SHINY_DELAY:
                write_log(f"Potential shiny detected after {encounters} encounters.")
                return encounters

        except Exception as e:  # Failure

            # Error msg string
            errmsg = str(e)

            # Window has crashed
            if errmsg.startswith(
                "Error code from Windows: 1400 - Invalid window handle."
            ):

                # Error Message
                message = "Encounter failed: Window has crashed."

                # Autostart Enabled
                if autostart:
                    write_log(f"{message} Restarting ...")
                    citra = window.start_window(autostart)
                else:  # Cannot Restart
                    raise Exception(message)
            else:  # Generic error
                write_log(f"Encounter failed: {e} Resetting ...")

        try:
            # Parse the number of encounters from the file
            with open(ENCOUNTERS_FILE, "w") as file:
                file.write(str(encounters))
        except Exception as e:  # Failure
            write_log(f"Failed to update encounters: {e}")

        # Encounter end time
        end = datetime.now()

        # Get total duration, seconds
        total_duration = end - start
        total_seconds = total_duration.total_seconds()

        write_log(f"Resetting encounter {encounters} after {total_seconds}s.")

