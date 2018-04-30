"""Simple Terminal

$Id: term.py 892 2018-04-20 01:57:54Z rnee $
"""

import os
import sys


def readkey():
    """ Read a single key with support for Linux and Windows """
    if os.name == 'nt':
        import msvcrt
        return msvcrt.getch()
    else:
        """read a key without echo or buffering"""
        import termios
        stdin = sys.stdin
        fd = stdin.fileno()

        # Do in two lines so we get two copies
        new = termios.tcgetattr(fd)
        old = termios.tcgetattr(fd)

        new[3] &= ~termios.ICANON
        new[6][termios.VTIME] = b'\x01'
        new[6][termios.VMIN] = b'\x00'

        try:
            termios.tcsetattr(fd, termios.TCSAFLUSH, new)
            char = stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old)

        return char


def terminal(com):
    """Simple terminal for debugging"""

    com.set_timeout(0)

    print("-----------------------------------------------------------------------")

    try:
        while True:
            # Process serial input
            while com.avail() > 0:
                count, data = com.read()
                if count > 0:
                    print(str(data, 'ascii'), end='')
                    sys.stdout.flush()

            # Process terminal input
            key = readkey()
            if key:
                # Treat ^B as a break character
                if key == b'\002':
                    print("[BREAK]")
                    com.pulse_break(100)
                else:
                    # print "[$key]";
                    com.write(bytes(key, 'ascii'))
    except KeyboardInterrupt:
        pass
