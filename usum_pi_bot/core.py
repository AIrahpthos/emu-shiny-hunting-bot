"""Hardware adaptation of Damon Murdoch's USUM static encounter sequence."""
import ipaddress
import socket
import struct
import time

BUTTONS = {name: 1 << i for i, name in enumerate(
    ('A', 'B', 'SELECT', 'START', 'RIGHT', 'LEFT', 'UP', 'DOWN', 'R', 'L', 'X', 'Y'))}


class Stopped(Exception):
    pass


class EncounterStartTimeout(TimeoutError):
    """No dark battle-start screen was observed before the deadline."""
    pass


def packet(buttons=(), x=0.0, y=0.0):
    mask = 0xFFF
    for name in buttons:
        mask &= ~BUTTONS[name]
    if not (-1 <= x <= 1 and -1 <= y <= 1):
        raise ValueError('Circle Pad coordinates must be between -1 and 1')
    circle = 0x7FF7FF if x == y == 0 else (
        (int(y * 0x5D0 + 0x800) << 12) | int(x * 0x5D0 + 0x800))
    return struct.pack('<5I', mask, 0x2000000, circle, 0x80800081, 0)


class Controller:
    def __init__(self, ip, stop):
        self.address = (str(ipaddress.IPv4Address(ip)), 4950)
        self.stop = stop
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def wait(self, seconds):
        if self.stop.wait(seconds):
            raise Stopped()

    def release(self):
        # Repeat releases to reduce the chance of a dropped UDP release packet.
        for _ in range(3):
            self.sock.sendto(packet(), self.address)

    def hold(self, buttons=(), seconds=0.15, x=0, y=0, cancel=None):
        data = packet(buttons, x, y)
        deadline = time.monotonic() + seconds
        try:
            while time.monotonic() < deadline:
                if self.stop.is_set():
                    raise Stopped()
                if cancel is not None and cancel.is_set():
                    return
                self.sock.sendto(data, self.address)
                self.wait(min(0.05, max(0, deadline - time.monotonic())))
        finally:
            self.release()

    def close(self):
        try:
            self.release()
        finally:
            self.sock.close()


def difference(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def trigger_encounter(controller, forward_seconds, cancel):
    """Advance to the encounter, then tap A until battle-start detection cancels input."""
    try:
        if cancel.is_set(): return
        controller.hold(('A',), .15, cancel=cancel)
        if cancel.is_set(): return
        if forward_seconds:
            controller.hold(seconds=forward_seconds, y=1, cancel=cancel)
        while not cancel.is_set():
            controller.hold(('A',), .10, cancel=cancel)
            # A release between presses is required to advance another prompt.
            if cancel.wait(.10): return
    finally:
        controller.release()


def wait_sample(sample, predicate, stop, timeout=20, stable=3):
    deadline = time.monotonic() + timeout
    matches = 0
    while time.monotonic() < deadline:
        if stop.is_set():
            raise Stopped()
        value = sample()
        matches = matches + 1 if predicate(value) else 0
        if matches >= stable:
            return value
        if stop.wait(0.05):
            raise Stopped()
    raise TimeoutError('Expected screen transition was not seen. Stopped without another reset.')


def measure(sample, stop, skip_changes=0, emit=None, on_dark=None):
    # Damon's sequence: dark screen -> first change -> second change.
    # Region averaging and consecutive matches tolerate capture noise.
    if type(skip_changes) is not int or not 0 <= skip_changes <= 20:
        raise ValueError('Screen changes to skip must be an integer from 0 to 20.')
    try:
        dark = wait_sample(sample, lambda p: max(p) <= 25, stop)
    except TimeoutError as e:
        raise EncounterStartTimeout('Battle-start dark screen was not observed.') from e
    # Stop and join the input worker before observing the timed transitions.
    if on_dark is not None:
        on_dark()
    previous = dark
    for index in range(skip_changes):
        previous = wait_sample(sample, lambda p: difference(p, previous) >= 35, stop)
        if emit: emit(f'Skipped cutscene screen change {index+1}/{skip_changes}.')
    first = wait_sample(sample, lambda p: difference(p, previous) >= 35, stop)
    if emit: emit('Encounter timing started. Waiting for the next screen change.')
    start = time.monotonic()
    wait_sample(sample, lambda p: difference(p, first) >= 35, stop)
    return time.monotonic() - start


def classify(seconds, baseline, threshold):
    if seconds < baseline - threshold:
        return 'uncertain'
    if seconds > baseline + threshold:
        return 'suspected shiny'
    return 'normal'


BOTTOM_WINDOW_PREFIX = 'cc3dsfs_bot'


def choose_bottom_window(windows):
    matches = [(hwnd,title) for hwnd,title in windows if title.startswith(BOTTOM_WINDOW_PREFIX)]
    if not matches:
        raise ValueError('Open the cc3dsfs bottom-screen viewer (cc3dsfs_bot).')
    if len(matches) > 1:
        raise ValueError('More than one cc3dsfs_bot window is open. Close the extra bottom-screen viewers.')
    return matches[0][0]
