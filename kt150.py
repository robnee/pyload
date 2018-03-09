#! /usr/bin/python3

"""Microchip ICSP driver

$Id: flash.py 740 2017-11-25 02:25:22Z rnee $

Uses PIC 16F819 as the hardware interface via the standard BLOAD 4pin serial
interface.

icsp.pl [-p=port] [-b=rate] [-q] [-f] [-w] [-t] <filename.hex>

-p  followed by =port.  default is /dev/ttyS0
-b  Followed by =rate.  default is 38400
-q  Quiet mode.  Don't dump hex files
-f  Fast mode.  Do minimal verification
-w  Write Only mode.  Fastest but does no verification

The Host controller understands the following commands

Sn	- Start programming.  Hold MCLR on target low and send MCHP signiture
En	- End programming.  Release MCLR on target
X		- Reset the Address counter to zero
I		- Increment the Address counter
Jnn   - Jump the Address counter a given number of locations
Bn	- Bulk erase program memory
An	- Bulk erase data memory
Cnn	- Set address to 8000h and Load config word
Lnn	- Load program word at current address
Mnn	- Load program word at current address and increment program counter
Pn	- Program commit
R		- Read program memory
Fnn	- Fetch program memory words
Gnn	- Get data memory words
Dn	- Load data byte for programming
V		- ICSP version
K		- NOP.  Just returns the K prompt

V0.1 04/18/2013

Working version

12/22/2015

Add dedicated comm_close function and write and read count totals in the logs

1/11/2016

When requesting read from eeprom data memory only read half a page at a time.
The bytes in these half pages are padded with a zero by to form a word for writing
to hex file.

1/18/2016

Utilize data latches for all devices.  Program command takes 5ms min so triggering
it only when the latches are full is more efficient.
Use the M command (Load Program and Increment) to speed up loading the latches
Add icsp_command api to simplify the redundant parts of dispatching a command
Add comparison of firmware file to what was just written
Fix padding of config page when read from chip
Improve progress messages
Use v1.3 of programming spec which requires specifying method to A, B, S, E, and P
commands so that the controller does not need to remember state.  Host software
now takes care of that.
D command no long triggers programming and increment.  Separate P and I commands
most follow.

1/31/2016

Fix problem in icsp_load_data which was unnecessarily trying to convert byte
data using chr.  Pattern now matches other icsp_load_xxx functions.
"""

import os
import sys
import time
import argparse
import importlib


class ImportHack:
    """Fix iOS external file importing"""
    def __init__(self):
        # update or append instance
        for i, mp in enumerate(sys.meta_path):
            if mp.__class__.__name__ == 'ImportHack':
                sys.meta_path[i] = self
                return
        
        sys.meta_path.append(self)

    @staticmethod
    def find_spec(fullname, path, target):
        """Try to open file and return a Finder"""
        loc = __file__.rpartition('/')[0] + '/' + fullname + '.py'
        try:
            # test if target exists in same location without use of additional imports
            f = open(loc)
            f.close()
            return importlib.util.spec_from_file_location(fullname, loc)
        except:
            pass

# ImportHack()


import serial
import picdevice
import intelhex as hexfile
import mock
import comm
import icsp

# -------------------------------------------------------------------------------
# Processor memory layout

DEFAULT_BAUD = 38400
DEFAULT_PORT = 'COM6'

# Communications settings

DATA = 8
TOUT = 1

# These can be set to enable mocking the target and setting where output files go
MOCK = False
TMP = '.'
# TMP = os.environ['HOME'] + '/Documents/'


def read_info(com, programming_method):
    """read config info"""
    icsp.load_config(com)
    icsp.jump(com, 6)

    chip_id = int.from_bytes(icsp.read_page(com, b'F', 1), 'little')
    cfg1 = int.from_bytes(icsp.read_page(com, b'F', 1), 'little')
    cfg2 = int.from_bytes(icsp.read_page(com, b'F', 1), 'little')
    cal1 = int.from_bytes(icsp.read_page(com, b'F', 1), 'little')
    cal2 = int.from_bytes(icsp.read_page(com, b'F', 1), 'little')

    # enhanced and midrange have different id/rev bits
    device_id = chip_id >> (5 if programming_method == icsp.ENH else 4)
    device_rev = chip_id & (0x1F if programming_method == icsp.ENH else 0x0F)

    return device_id, device_rev, cfg1, cfg2, cal1, cal2


def read_firmware(com, device_param):
    """read firmware from target and tweak so that it can be written in standard
    Microchip format.  Certain words such as chip id and calibration for example
    need to be blanked."""
    prog_pages = icsp.read_program(com, device_param)
    data_pages = icsp.read_data(com, device_param)

    firmware = prog_pages + data_pages

    # Get config page data and tweak to read-only regions
    conf_data = icsp.read_config(com, device_param)
    conf_page = hexfile.Page(conf_data)

    # blank out any empty user ID locations
    for i in range(0, 4):
        if conf_page[i] == 0x3FFF:
            conf_page[i] = None

    # Blank out 0x04 and 0x05, reserved
    conf_page[4], conf_page[5] = None, None
    # blank out chip id
    conf_page[6] = None
    # blank out calibration words
    conf_page[9], conf_page[10] = None, None

    firmware[device_param['conf_page']] = conf_page

    return firmware


def display_status(com):
    status = icsp.get_status(com)
    icsp.sync(com)

    print("TRIS      VCD 21V  TR  |LAT      VCD 21V  TR ")
    print("     76543210 76543210 |    76543210 76543210")
    print('     {0:08b} '.format(status[0]), end='')
    print('{0:08b} |'.format(status[1]), end='')
    print('    {0:08b} '.format(status[2]), end='')
    print('{0:08b} '.format(status[3]), end='')

    print()


def main():
    parser = argparse.ArgumentParser(prog='flash', description='icsp programming tool.')
    parser.add_argument('-p', '--port', default=DEFAULT_PORT, help='serial device')
    parser.add_argument('-b', '--baud', default=DEFAULT_BAUD, help='baud rate')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('-i', '--id', action='store_true', help='read chip id info from target')
    group.add_argument('-w', '--write', action='store_true', help='write firmware to target')
    group.add_argument('-r', '--read', action='store_true', help='Read target and save to file')

    parser.add_argument('-q', '--quiet', action='store_true', help="quiet mode. don't dump hex files")
    parser.add_argument('-e', '--enh', action='store_true', help='Enhanced midrange programming method')
    parser.add_argument('-f', '--fast', action='store_true', help='Fast mode.  Do minimal verification')
    parser.add_argument('-l', '--log', nargs='?', const='bload.log', default=None,
                        help='Log all I/O to file')
    parser.add_argument('-t', '--test', action='store_true', help='Test')
    parser.add_argument('--version', action='version',
                        version='$Id: flash.py 740 2017-11-25 02:25:22Z rnee $')
    parser.add_argument('filename', default=None, nargs='?', action='store', help='HEX filename')

    args = parser.parse_args()

    args.write = not args.read and not args.id

    programming_method = icsp.ENH if args.enh else icsp.MID

    if args.log:
        if os.path.exists(args.log):
            os.unlink(args.log)
        logf = open(args.log, 'a')
    else:
        logf = None
    # logf = sys.stdout

    # Check for a filename
    if not args.id and args.filename is None:
        parser.print_help()
        sys.exit()

    # unless we are reading out the chip firmware read a new file to load
    if not args.read and not args.id:
        with open(args.filename) as fp:
            file_firmware = hexfile.Hexfile()
            file_firmware.read(fp)
            if not args.quiet:
                print(args.filename)
                print(file_firmware.display())

    # Init comm (holds target in reset)
    print(f'Initializing communications on {args.port} at {args.baud} ...')
    if MOCK:
        # read firmware to simulate target and load and create mock target
        firmware = hexfile.Hexfile()
        with open(TMP + 'icsp.hex') as fp:
            firmware.read(fp)

        ser = mock.ICSPHost(firmware)
    else:
        ser = serial.Serial(args.port, baudrate=args.baud, bytesize=DATA, timeout=TOUT)

    # Create wrapper
    com = comm.Comm(ser, logf)

    # Bring target out of reset
    print('Reset...')
    time.sleep(0.050)
    com.pulse_dtr(0.250)
    time.sleep(0.050)

    # Trigger and look for prompt
    for _ in range(5):
        com.flush()
        com.write(b'K')
        (count, value) = com.read(1)
        if value == b'K':
            break
    else:
        com.close()

        print(f'[{count}, {value}] Could not find ICSP on {args.port}\n')
        sys.exit()

    print('Connected...')

    # flush input buffer so that we can start out synchronized
    com.flush()

    # Get host controller version
    print('Getting Version...')
    ver = icsp.get_version(com)
    print('KT150 firmware version:', ver)
    print('Method: ', icsp.FAMILY_NAMES[programming_method])

    display_status(com)
    print('Start...')
    icsp.start(com)
    icsp.sync(com)
    display_status(com)

    print("\nDevice Info:")
    device_id, device_rev, cfg1, cfg2, cal1, cal2 = read_info(com, programming_method)

    if device_id not in picdevice.PARAM:
        print(" ID: %04X rev %x not in device list" % (device_id, device_rev))

        print("End...")
        icsp.release(com)

        sys.exit()

    device_param = picdevice.PARAM[device_id]
    device_name = device_param['name']

    print(f" ID: {device_id:04X} {device_name} rev {device_rev:02X}")
    print(f"CFG: {cfg1:04X} {cfg2:04X}")
    print(f"CAL: {cal1:04X} {cal2:04X}")

    # Set ranges and addresses based on the bootloader config and device information
    min_page = 0
    max_page = device_param['max_page']
    min_data = device_param['min_data']
    max_data = device_param['max_data']
    conf_page_num = device_param['conf_page']

    if args.read:
        print("Reset Address...")
        icsp.reset_address(com)

        print("Reading Firmware...")
        chip_firmware = read_firmware(com, device_param)
        print()

        with open(args.filename, mode='w') as fp:
            chip_firmware.write(fp)

        if not args.quiet:
            print(chip_firmware.display())
    elif args.write:
        # Erase entire device including userid locations
        print("Erase Device...")
        icsp.load_config(com)
        icsp.erase_program(com)
        icsp.erase_data(com)

        icsp.reset_address(com)

        sys.stderr.flush()
        print(f"Writing Program 0x0 .. 0x{max_page:#0X} ...")
        icsp.write_program_pages(com, file_firmware, device_param)

        print(f"Writing Data {min_data:#0X} .. {max_data:#0X} ...")
        icsp.write_data_pages(com, file_firmware, device_param)

        print("Writing Config 0x%X ..." % conf_page_num)
        icsp.reset_address(com)
        icsp.write_config(com, file_firmware, device_param)

        print("Reading Firmware...")
        icsp.reset_address(com)
        verify_firmware = read_firmware(com, device_param)
        print()

        # Compare protected regions to ensure they are compatible
        print("Comparing firmware pages 0x%X .. 0x%X, 0x%X .. 0x%X, 0x%X..." %
              (min_page, max_page, min_data, max_data, conf_page_num))
        check_list = list(range(min_page, max_page + 1)) + list(range(min_data, max_data)) + [conf_page_num]
        error_list = file_firmware.compare(verify_firmware, check_list)

        if error_list:
            print("\nWARNING!\nError verifying firmware.")

            for page_num in error_list:
                if file_firmware[page_num]:
                    print("File:")
                    print(file_firmware[page_num].display(page_num))
                if verify_firmware[page_num]:
                    print("Chip:")
                    print(verify_firmware[page_num].display(page_num))
        else:
            print(" OK")

    print("End...")
    icsp.release(com)

    com.close()


if __name__ == '__main__':
    start = time.time()
    main()
    print(f"elapsed time: {time.time() - start:0.2f} seconds")
