#! /usr/bin/python3

"""
Microchip ICSP driver

$Id: flash.py 910 2018-05-15 02:28:20Z rnee $

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
import time
import argparse
import serial

import picdevice
import intelhex
import comm
import icsp

# -------------------------------------------------------------------------------
# Processor memory layout

DEFAULT_BAUD = 38400
DEFAULT_PORT = '/dev/ttyUSB0'

# Communications settings

MOCK = True
DATA = 8
TOUT = 1


def read_info(com):
    """read config info"""
    icsp.load_config(com)
    icsp.jump(com, 5)

    chip_rev = int.from_bytes(icsp.read_page(com, b'F', 1), 'little')
    chip_id = int.from_bytes(icsp.read_page(com, b'F', 1), 'little')
    cfg1 = int.from_bytes(icsp.read_page(com, b'F', 1), 'little')
    cfg2 = int.from_bytes(icsp.read_page(com, b'F', 1), 'little')
    cal1 = int.from_bytes(icsp.read_page(com, b'F', 1), 'little')
    cal2 = int.from_bytes(icsp.read_page(com, b'F', 1), 'little')

    return chip_rev, chip_id, cfg1, cfg2, cal1, cal2


def read_firmware(com, device_param):
    """read firmware from target and tweak so that it can be written in standard
    Microchip format.  Certain words such as chip id and calibration for example
    need to be blanked."""
    prog_pages = icsp.read_program(com, device_param)
    data_pages = icsp.read_data(com, device_param)

    firmware = prog_pages + data_pages

    # Get config page data and tweak to read-only regions
    conf_data = icsp.read_config(com, device_param)
    conf_page = intelhex.Page(conf_data)

    # blank out any empty user ID locations
    for i in range(0, 4):
        if conf_page[i] == 0x3FFF:
            conf_page[i] = None

    # Blank out 0x04, reserved, revision and chip_id
    conf_page[4: 7] = None
    # blank out calibration words
    conf_page[9: 17] = None

    firmware[device_param['conf_page']] = conf_page

    return firmware


def start(com):
    """send start sequence"""

    # icsp_clk_output
    icsp.send_command(com, b'LL')
    # icsp_clk_low
    icsp.send_command(com, b'LM')

    # icsp_mclr2_output
    icsp.send_command(com, b'LH')
    # icsp_mclr2_low
    icsp.send_command(com, b'LI')

    time.sleep(0.001)

    # Send key sequence with an extra clock at the end
    icsp.send_command(com, b'UPUHUCUMLO')


def program(com):
    """main programming routine"""

    # Check for a filename
    if args.filename is None:
        parser.print_help()
        return

    # unless we are reading out the chip firmware read a new file to load
    if not args.read:
        with open(args.filename) as fp:
            file_firmware = intelhex.Hexfile()
            file_firmware.read(fp)
            if not args.quiet:
                print(args.filename)
                print(file_firmware.display())
    else:
        file_firmware = None

    # Bring target out of reset
    print('Reset...')
    time.sleep(0.050)
    com.pulse_dtr(0.250)
    time.sleep(0.050)
    com.flush()

    # Trigger and look for prompt
    while True:
        (count, value) = com.read(1)
        if count == 0 or value != b'\x00':
            break

    if count == 0 or value != b'K':
        print(f'[{count}, {value}] Could not find ICSP on {args.port}\n')
        return

    print('Connected...')

    # flush input buffer so that we can start out synchronized
    com.flush()

    # Get host controller version
    print('Getting Version...')
    ver = icsp.get_version(com)
    print('Hardware version:', ver)

    print('Start...')
    start(com)

    print("\nDevice Info:")
    chip_rev, chip_id, cfg1, cfg2, cal1, cal2 = read_info(com)

    # enhanced and midrange have different id/rev bits
    for mask, shift in ((0x00, 0), (0x00F, 4), (0x01F, 5)):
        if 0x00 < chip_rev < 0x3FFF:
            device_rev = chip_rev
        else:
            device_rev = chip_id & mask

        device_id = chip_id >> shift
        if device_id in picdevice.PARAM:
            break
    else:
        print(" ID: %04X not in device list" % chip_id)

        print("End...")
        icsp.release(com)

        return

    device_param = picdevice.PARAM[device_id]
    device_name = device_param['name']

    print(f" ID: {device_id:04X} {device_name} rev {device_rev:02X}")
    print(f"CFG: {cfg1:04X} {cfg2:04X}")
    print(f"CAL: {cal1:04X} {cal2:04X}")

    if device_name is None:
        raise RuntimeError("Unknown device")

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
    else:
        # Erase entire device including userid locations
        print("Erase Program...")
        icsp.load_config(com)
        icsp.erase_program(com)

        print("Reset Address...")
        icsp.reset_address(com)

        print("Writing Program 0x%X .. 0x%X ..." % (0, max_page))
        icsp.write_program_pages(com, file_firmware, device_param)

        if min_data < max_data:
            print("Erase Data...")
            icsp.erase_data(com)
            print("Writing Data 0x%X .. 0x%X ..." % (min_data, max_data))
            icsp.write_data_pages(com, file_firmware, device_param)

        print("Reset Address...")
        icsp.reset_address(com)

        print("Writing Config 0x%X ..." % conf_page_num)
        icsp.write_config(com, file_firmware, device_param)

        print("Reset Address...")
        icsp.reset_address(com)

        print("Reading Firmware...")
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
                print("File:")
                if file_firmware[page_num]:
                    print(file_firmware[page_num].display(page_num))
                print("Chip:")
                if verify_firmware[page_num]:
                    print(verify_firmware[page_num].display(page_num))
        else:
            print(" OK")

    print("End...")
    icsp.release(com)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='flash', description='icsp programming tool.')
    parser.add_argument('-p', '--port', default=DEFAULT_PORT, help='serial device')
    parser.add_argument('-b', '--baud', default=DEFAULT_BAUD, help='baud rate')
    parser.add_argument('-q', '--quiet', action='store_true', help="quiet mode. don't dump hex files")
    parser.add_argument('-e', '--enh', action='store_true', help='Enhanced midrange programming method')
    parser.add_argument('-f', '--fast', action='store_true', help='Fast mode.  Do minimal verification')
    parser.add_argument('-r', '--read', action='store_true', help='Read target and save to filename')
    parser.add_argument('-l', '--log', nargs='?', const='bload.log', default=None,
                        help='Log all I/O to file')
    parser.add_argument('-t', '--test', action='store_true', help='Test')
    parser.add_argument('--version', action='version',
                        version='$Id: flash.py 910 2018-05-15 02:28:20Z rnee $')
    parser.add_argument('filename', default=None, nargs='?', action='store', help='HEX filename')

    args = parser.parse_args()

    if args.log:
        if os.path.exists(args.log):
            os.unlink(args.log)
        logf = open(args.log, 'a')
    else:
        logf = None

    start_time = time.time()

    print('Initializing communications on {} {} ...'.format(args.port, args.baud))
    if not MOCK:
        ser = serial.Serial(args.port, baudrate=args.baud, bytesize=DATA, timeout=TOUT)

    else:
        import mock

        # unless we are reading out the chip firmware read a new file to load
        with open('mock.hex') as fp:
            mock_firmware = intelhex.Hexfile()
            mock_firmware.read(fp)

        ser = mock.ICSPHost(mock_firmware)

    # create wrapper
    ser_com = comm.Comm(ser, logf)
    program(ser_com)
    ser.close()

    print(f"elapsed time: {time.time() - start_time:0.2f} seconds")
