"""Simple Terminal

$Id: term.py 817 2018-02-20 03:33:56Z rnee $
"""

import sys
import termios


def readkey():
    """read a key without echo or buffering"""
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
