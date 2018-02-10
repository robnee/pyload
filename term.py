# -------------------------------------------------------------------------------
#  Simple Terminal
# -------------------------------------------------------------------------------

import sys
import termios

# -------------------------------------------------------------------------------
# Read key in non-canonical mode (don't wait for newline)

"""
sub readkey
{
    my $term = POSIX::Termios->new();

    $term->getattr (fileno (STDIN));

    # Save current settings
    my $oterm = $term->getlflag();
    my $vtime = $term->getcc(VTIME);
    my $vmin = $term->getcc(VMIN);

    # non-canonical, wait VTIME=0.1 seconds, no min characters
    # VTIME=0 will end up using 100% cpu
    $term->setlflag ($oterm & ~ICANON);
    $term->setcc(VTIME, 1);
    $term->setcc(VMIN, 0);
    $term->setattr(fileno (STDIN), TCSANOW);

    my $key = '';
    sysread(STDIN, $key, 1);

    $term->setlflag($oterm);
    $term->setcc(VTIME, $vtime);
    $term->setcc(VMIN, $vmin);
    $term->setattr(fileno (STDIN), TCSANOW);

    return $key;
}

"""


def readkey():
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
