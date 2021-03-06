#! /usr/bin/python3

"""
Bootloader with automatic reset control.

$Id: pyload.py 901 2018-04-28 21:44:56Z rnee $

Uses DTR line to control MCLR pin on PIC.  This resets the PIC at which time it
waits 250us for a '!' character as an attention signal.  Once received the PIC
enters its bootloader mode and accepts program and data memory read and write
commands.

bload.pl [-p=port] [-b=rate] [-q] [-f] [-w] [-t] <filename.hex>

-p  followed by =port.  default is /dev/ttyS0
-b  Followed by =rate.  default is 9600
-q  Quiet mode.  Don't dump hex files
-f  Fast mode.  Do minimal verification
-w  Write Only mode.  Fastest but does no verification
-t  Start terminal on exit to capture debug output

V0.1 02/01/2007

Working version

V0.2 02/07/2007

Added -t, -q and -f options

V0.3 02/11/2007

Use break signal to start bootloader

V0.4 02/16/2007

Added write-only mode to suppress verify steps all together

V0.5 02/19/2007

Allow writing page zero just before reset.  No longer part of safe region

V0.6 02/22/2007

If -f is specified do not write data pages unless at least one is present

V0.7 03/05/2007

Add input to terminal mode

V0.8 03/05/2007

Allow -t to be used with out firmware upload

V1.0 03/06/2007

Add non-blocking non-canonical input to terminal mode

V1.23 03/13/2007

Added baud rate option -b=rate

V1.24 05/26/2009

Added port option

V1.25 05/29/2009

Converted from DeviceSerialPort to native Fcntl and POSIX serial I/O

V1.26 06/08/2009

Ensure IXON and IXOFF are turned off

V1.27 06/08/2009

Fix retries on page read function and dump short page bytes to help debugging

V1.28 04/02/2013

Ensure ICRNL is turned off.  This was converting \r to \n when reading firmware
When there is a verify error display the file and chip pages that differ

V1.28 04/11/2013

Add -r option which only resets target

V1.31 11/20/2015

Added support for I info command to set region sizes from info from chip
Added support for extended pages in hex file reader
Added comm logging

V1.32 11/25/2015

Added support for writing hex files with extended addresses
Fix bug in reading extended addresses
Add support for reading config words and saving them to hex file
Add more info including chip names to the info display

V1.33 11/26/2015

Added support for the 1.2 protocol which uses the same data record layout for data
and program pages
fix bug in writing hex extended address records
Add support for reading and writing eeprom data
Tweak config data words so firmware read from chip looks more like a assembler file

V1.34 11/27/2015

Added logging of low level serial port routines like comm_pulse_break
Added a separate bload_data_write that still uses the old protocol format
Dump display has addresses and to be easier to read
Add basis for parameters for various chips
Added ability to support the v10 and v11 bootloaders

12/20/2015

Added comm_flush and comm_avail routines
added ^B to send break signal in terminal mode

12/30/2015

Fix write_pages call when writing page zero

1/10/2016

Use comm routines for all I/O instead of low-level routines
Change default to 38400 baud

1/30/2016

Add -d options to convert a hex file to C definitions
"""

import os
import sys
import time
import argparse
import logging

import comm
import term
import intelhex
import bload
import picdevice

# -------------------------------------------------------------------------------
# Processor memory layout

DEFAULT_BAUD = 38400
DEFAULT_PORT = '/dev/ttyUSB0'

# Communications settings

DATA = 8
TOUT = 1


def run_range_test(com):
    """ test the bootloader range checking """

    for addr in range(0x000, 0x1000, 0x010):
        cmd_code = b'T'
        address = addr.to_bytes(2, 'little')
        checksum = bytes([bload.calc_checksum(address)])

        cmd = bytes(cmd_code) + address + checksum

        com.write(cmd)
        count, result = com.read(1)

        if result == b'C':
            print(f'{addr:X} -> checksum {cmd} {address} {checksum}')

            count, result = com.read(1)
            if result != b'K':
                print('No prompt after error')
        elif result == b'R':
                print(f'{addr:X} -> Range Error')

                count, result = com.read(1)
                if result != b'K':
                    print('No prompt after error')

        elif result == b'E':
            print(f'{addr:X} -> Error')

            count, result = com.read(1)
            if result != b'K':
                print('No prompt after error')
        else:
            print(f'{addr:X} -> OK')

        avail = com.avail()
        if avail > 0:
            data = com.read(avail)
            print('avail:', avail, 'data:', data)


def reset(com: comm.Comm):
    """ reset the target """

    time.sleep(0.050)
    com.pulse_dtr(0.250)
    time.sleep(0.050)

    return


def connect(com):
    # pulse dtr to reset the device then flush the buffers to get rid
    # of noise from glitchy startup
    print('Reset ...')
    reset(com)
    com.flush()
    
    # boot loader is now waiting on a break signal to activate
    com.pulse_break(0.200)

    # Look for prompt but skip null character noise
    while True:
        (count, value) = com.read(1)
        if count == 0 or value != b'\x00':
            break

    if count == 0 or value != b'K':
        return False
        
    return True


def read_firmware(com, conf_page_num, prog_list, data_list):
    """read firmware from target and tweak so that it can be written in standard
    Microchip format.  Certain words such as chip id and calibration for example
    need to be blanked."""
    prog_pages = bload.read_program(com, prog_list)
    data_pages = bload.read_data(com, data_list)
    
    firmware = prog_pages + data_pages

    # Get config page data and tweak to read-only regions
    conf_data = bload.read_config(com)
    conf_page = intelhex.Page(conf_data)

    # Blank out 0x04, reserved, revision and chip_id
    conf_page[4: 7] = None
    # blank out calibration words
    conf_page[9: 17] = None

    # blank out any empty locations
    for i in range(intelhex.PAGELEN):
        if conf_page[i] == 0x3FFF:
            conf_page[i] = None

    firmware[conf_page_num] = conf_page

    return firmware

    
def program(com: comm.Comm, args):
    """ main """

    start_time = time.time()

    # unless we are reading out the chip firmware read a new file to load
    if not args.read:
        # Read, parse and display image to load
        with open(args.filename) as fp:
            file_firmware = intelhex.Hexfile()
            file_firmware.read(fp)
            if not args.quiet:
                print(args.filename)
                print(file_firmware.display())
    else:
        file_firmware = None

    if args.cdef:
        for page_num in range(64):
            if file_firmware[page_num]:
                print('page_list[%d] = "%s";' % (page_num, file_firmware[page_num]))

        return

    if not connect(com):
        print('[{count}, {value}] Could not find boot loader on {com.port}\n')
        return
        
    print('Connected...')

    # Get info about the bootloader
    (boot_version, boot_pagesize, boot_start, boot_size,
     data_start, data_end, code_end) = bload.get_info(com)

    # Recompute word addresses as page addresses
    boot_start = (boot_start & 0x7FFF) // boot_pagesize
    boot_end = boot_start + (boot_size // boot_pagesize) - 1
    code_end //= boot_pagesize
    data_start //= boot_pagesize
    data_end //= boot_pagesize

    # Get config info
    config = bload.read_config(com)

    user_id = ""
    for word in config[0: 4 * 2: 2]:
        user_id += '{:X}'.format(word & 0x0F)

    chip_id = int.from_bytes(config[6 * 2: 7 * 2], 'little')
    chip_rev = int.from_bytes(config[6 * 2: 7 * 2], 'little')
    config_words = [int.from_bytes(config[7 * 2: 8 * 2], 'little'),
                    int.from_bytes(config[8 * 2: 9 * 2], 'little')]

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
        reset(com)
        sys.exit()

    device_param = picdevice.PARAM[device_id]
    device_name = device_param['name']

    print("\nBootloader Version: %02X\n"
          "Page Size:          0x%02X\n"
          "Bootloader Region:  0x%03X - 0x%03X\n"
          "Program Region:     0x%03X - 0x%03X\n"
          "EEPROM Data Region: 0x%03X - 0x%03X\n" %
          (boot_version, boot_pagesize, boot_start, boot_end, 0, code_end, data_start, data_end))

    print("CONFIG User ID: %s  Device ID: %04X %s Rev: %1X  Config Words: %x %x" %
          (user_id, device_id, device_name, device_rev, config_words[0], config_words[1]))

    # Set ranges and addresses based on the bootloader config and device information
    min_user = 1
    max_user = boot_start - 1
    conf_page = picdevice.PARAM[device_id]['conf_page']
    min_data = picdevice.PARAM[device_id]['min_data']
    max_data = picdevice.PARAM[device_id]['max_data']

    if min_data != data_start or max_data != data_end:
        print("Error:")
        print("min_data=", min_data, 'max_data=', max_data)
        print("data_start=", data_start, 'data_end=', data_end)

        return

    prog_list = list(range(0, code_end + 1))
    user_list = list(range(min_user, max_user + 1))
    boot_list = list(range(boot_start, boot_end + 1))
    data_list = list(range(min_data, max_data + 1))

    #
    # Test routine for bootloader range check
    #
    # run_range_test(com)

    # Read existing firmware
    if args.fast:
        sys.stdout.write("Reading Bootloader  ")
        chip_firmware = bload.read_program(com, [0] + boot_list)
        print()
    else:
        sys.stdout.write("Reading Firmware    ")
        chip_firmware = read_firmware(com, conf_page, prog_list, data_list)
        if not args.quiet:
            print()
            print(chip_firmware.display())
        
    if args.read:
        print('Saving firmware to', args.filename, '...')
        with open(args.filename, mode='w') as fp:
            chip_firmware.write(fp)
    else:
        if not args.fast:
            print('Saving firmware to previous.hex ...')
            with open("previous.hex", mode='w') as fp:
                chip_firmware.write(fp)

        # Compare protected regions to ensure they are compatible
        # noinspection PyUnboundLocalVariable
        errors = chip_firmware.compare(file_firmware, boot_list)
        if errors:
            # Reset the target
            com.pulse_dtr(0.250)

            print("\nError!\n",
                  "The reserved bootloader portions of the new and existing program images\n",
                  "are different.  Attempting to load this image using the bootloader may\n",
                  "result in damage to the firmware and may require reflashing the chip\n",
                  "Diff pages: ", errors)

            for page_num in errors:
                print("File:")
                print(file_firmware[page_num].display(page_num))
                print("Chip:")
                print(chip_firmware[page_num].display(page_num))

            return

        page_zero = chip_firmware.compare(file_firmware, [0])

        # Compute write list based on hex file and existing firmware if available.
        # Compute check list for verify step.  Either all pages or abbreviated list
        prog_write_list = []
        data_write_list = []
        prog_check_list = []
        data_check_list = []
        if args.fast:
            # we don't have the existing firmware to compare to so write all pages
            # in the input file and erase all others
            prog_write_list = user_list
            data_write_list = data_list

            for page_num in user_list:
                if file_firmware[page_num]:
                    prog_check_list.append(page_num)
            for page_num in data_list:
                if file_firmware[page_num]:
                    data_check_list.append(page_num)
        else:
            # don't write pages if input and existing are both already blank
            for page_num in user_list:
                if file_firmware[page_num] or chip_firmware[page_num]:
                    prog_write_list.append(page_num)
            for page_num in data_list:
                if file_firmware[page_num] or chip_firmware[page_num]:
                    data_write_list.append(page_num)

            prog_check_list = user_list
            data_check_list = data_list

        # Write the new firmware.  Use a loop in case multiple attempts are necessary
        while True:
            sys.stdout.write("Writing Firmware    ")
            bload.write_pages(com, b'W', file_firmware, prog_write_list)
            bload.write_pages(com, b'D', file_firmware, data_write_list)

            print()

            # Verify what was just written
            if not args.fast:
                sys.stdout.write("Checking Firmware    ")

                prog_pages = bload.read_program(com, prog_check_list)
                data_pages = bload.read_data(com, data_check_list)
                sys.stdout.write('\n')

                check_firmware = prog_pages + data_pages
                check_list = prog_check_list + data_check_list

                errors = check_firmware.compare(file_firmware, check_list)
                if errors:
                    for page_num in errors:
                        print("File:")
                        print(file_firmware[page_num].display(page_num))
                        print("Chip:")
                        print(check_firmware[page_num].display(page_num))

                    print("\nWARNING!\n",
                          "Error verifying firmware.  Do not power down target.\n",
                          "Press Enter to attempt reflash.")

                    # Wait for confirmation
                    input()
                    continue

            # Done
            break

        # if the first page is different then update it last
        if page_zero:
            sys.stdout.write("Writing Page Zero    ")
            bload.write_pages(com, b'W', file_firmware, [0])
            print()

        sys.stdout.flush()
        print("Update successful.")

    print("Reseting target...")
    reset(com)
                   
    print(f"elapsed time: {time.time() - start_time:0.2f} seconds")


def run(argv=None):
    parser = argparse.ArgumentParser(prog='pyload', description='pyload Bload bootloader tool.')
    parser.add_argument('-p', '--port', default=DEFAULT_PORT, help=f'serial device ({DEFAULT_PORT})')
    parser.add_argument('-b', '--baud', default=DEFAULT_BAUD, help='baud rate')
    parser.add_argument('-q', '--quiet', action='store_true', help='quiet mode. dont dump hex files')
    parser.add_argument('-c', '--cdef', action='store_true', help='Convert filename to C definition statements')
    parser.add_argument('-f', '--fast', action='store_true', help='Fast mode.  Do minimal verification')
    parser.add_argument('-r', '--read', action='store_true', help='Read target and save to filename')
    parser.add_argument('-x', '--reset', action='store_true', help='Reset target and exit')
    parser.add_argument('-t', '--term', action='store_true', help='Start terminal mode after processing')
    parser.add_argument('-l', '--log', nargs='?', const='bload.log', default=None, help='Log all I/O to file')
    parser.add_argument('--version', action='version', version='$Id: pyload.py 901 2018-04-28 21:44:56Z rnee $')

    parser.add_argument('filename', default=None, nargs='?', action='store', help='HEX filename')

    args = parser.parse_args(args=argv if argv else sys.argv[1:])

    # reading and fast mode are incompatible
    if args.read and args.fast:
        parser.print_help()
        sys.exit()

    if args.log:
        if os.path.exists(args.log):
            os.unlink(args.log)
        logf = open(args.log, 'a')
    else:
        logf = None

    print('Initializing communications on {} {} ...'.format(args.port, args.baud))
    if args.port.upper() == 'MOCK':
        import mock

        # unless we are reading out the chip firmware read a new file to load
        with open('mock.hex') as fp:
            mock_firmware = intelhex.Hexfile()
            mock_firmware.read(fp)

        ser = mock.BLoadHost('12F1822', mock_firmware)
    else:
        import serial

        ser = serial.Serial(args.port, baudrate=args.baud, bytesize=DATA, timeout=TOUT)

    # create wrapper
    with comm.Comm(ser, logf) as ser_com:
        if args.reset:
            ser_com.pulse_dtr(0.250)
            if args.term:
                term.terminal(ser_com)

        # Check for commands that require a filename
        if args.filename is not None:
            program(ser_com, args)
        
        if args.term:
            ser_com.pulse_dtr(0.250)
            term.terminal(ser_com)
            

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
