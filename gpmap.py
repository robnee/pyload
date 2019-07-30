#! /usr/bin/python3

"""
Read hex file and dump memory map

$Id: gpmap.py 893 2018-04-20 01:58:27Z rnee $
"""

import sys
import argparse
import intelhex as hexfile


def main():
    """ main """
    parser = argparse.ArgumentParser(prog='gpmap', description='Intel hexfile memory mapper')
    parser.add_argument('-v', '--verbose', action='store_true', help='display long format memory map')
    parser.add_argument('--version', action='version', version='$Id: gpmap.py 893 2018-04-20 01:58:27Z rnee $')

    parser.add_argument('filename', default=None, nargs='?', action='store', help='HEX filename')

    args = parser.parse_args()

    # Check for commands that don't require a filename
    if args.filename is None:
        parser.print_help()
        sys.exit()

    with open(args.filename) as fp:
        file_firmware = hexfile.Hexfile()
        file_firmware.read(fp)
        if args.verbose:
            print(file_firmware.display())
        else:
            file_firmware.memory_map()


if __name__ == "__main__":
    main()
