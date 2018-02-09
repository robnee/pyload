#! /usr/bin/python3

# -------------------------------------------------------------------------------
# $Id: flash.py 740 2017-11-25 02:25:22Z rnee $
#
# Microchip ICSP driver
#
# Uses PIC 16F819 as the hardware interface via the standard BLOAD 4pin serial
# interface.
#
# icsp.pl [-p=port] [-b=rate] [-q] [-f] [-w] [-t] <filename.hex>
#
# -p  followed by =port.  default is /dev/ttyS0
# -b  Followed by =rate.  default is 38400
# -q  Quiet mode.  Don't dump hex files
# -f  Fast mode.  Do minimal verification
# -w  Write Only mode.  Fastest but does no verification
#
# The Host controller understands the following commands
#
# Sn	- Start programming.  Hold MCLR on target low and send MCHP signiture
# En	- End programming.  Release MCLR on target
# X		- Reset the Address counter to zero
# I		- Increment the Address counter
# Jnn   - Jump the Address counter a given number of locations
# Bn	- Bulk erase program memory
# An	- Bulk erase data memory
# Cnn	- Set address to 8000h and Load config word
# Lnn	- Load program word at current address
# Mnn	- Load program word at current address and increment program counter
# Pn	- Program commit
# R		- Read program memory
# Fnn	- Fetch program memory words
# Gnn	- Get data memory words
# Dn	- Load data byte for programming
# V		- ICSP version
# K		- NOP.  Just returns the K prompt
#
# V0.1 04/18/2013
#
# Working version
#
# 12/22/2015
#
# Add dedicated comm_close function and write and read count totals in the logs
#
# 1/11/2016
#
# When requesting read from eeprom data memory only read half a page at a time.
# The bytes in these half pages are padded with a zero by to form a word for writing
# to hex file.
#
# 1/18/2016
#
# Utilize data latches for all devices.  Program command takes 5ms min so triggering
# it only when the latches are full is more efficient.
# Use the M command (Load Program and Increment) to speed up loading the latches
# Add icsp_command api to simplify the redundant parts of dispatching a command
# Add comparison of firmware file to what was just written
# Fix padding of config page when read from chip
# Improve progress messages
# Use v1.3 of programming spec which requires specifying method to A, B, S, E, and P
# commands so that the controller does not need to remember state.  Host software
# now takes care of that.
# D command no long triggers programming and increment.  Separate P and I commands
# most follow.
#
# 1/31/2016
#
# Fix problem in icsp_load_data which was unnecessarily trying to convert byte
# data using chr.  Pattern now matches other icsp_load_xxx functions.
#
# -------------------------------------------------------------------------------

import os
import sys
import time
import argparse
import importlib


class ImportHack:
    def __init__(self):
        # update or append instance
        for i, mp in enumerate(sys.meta_path):
            if mp.__class__.__name__ == 'ImportHack':
                sys.meta_path[i] = self
                return
        
        sys.meta_path.append(self)

    @staticmethod
    def find_spec(fullname, path, target):
        loc = __file__.rpartition('/')[0] + '/' + fullname + '.py'
        try:
            # test if target exists in same location without use of additional imports
            f = open(loc)
            f.close()
            return importlib.util.spec_from_file_location(fullname, loc)
        except:
            pass

ImportHack()

import picdevice
import hex
import mock
import comm
import icsp

# -------------------------------------------------------------------------------
# Processor memory layout

DEFAULT_BAUD = 38400
DEFAULT_PORT = 'COM6'

# Communications settings

DATA = 8
TOMS = 1
MOCK = True
TMP = os.environ['HOME']

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
                    version='$Id: flash.py 740 2017-11-25 02:25:22Z rnee $')
parser.add_argument('filename', default=None, nargs='?', action='store', help='HEX filename')

args = parser.parse_args()

#programming_method = icsp.ENH if args.enh else icsp.MID
programming_method = icsp.ENH

# Check for commands that don't require a filename
if args.filename is None:
    parser.print_help()
    sys.exit()

# unless we are reading out the chip firmware read a new file to load
if not args.read:
    page_list = hex.read_hex(TMP + '/' + args.filename)
    if not args.quiet:
        hex.dump_pages(page_list)

if args.log:
    if os.path.exists(args.log):
        os.unlink(args.log)
    logf = open(args.log, 'a')

args.log = sys.stdout

# Init comm (holds target in reset)
print('Initializing communications on {} at {} ...'.format(args.port, args.baud))
if MOCK:
    ser = mock.ICSPHost()
else:
    ser = serial.serial_for_url(port)
    ser = serial(port)
    ser.baudrate = args.baud
    ser.bytesize = DATA
    ser.timeout = TOMS
com = comm.Comm(ser, args.log)

# Bring target out of reset
print('Reset...')
time.sleep(0.050)
com.pulse_dtr(250)
time.sleep(0.050)

# Trigger and look for prompt
com.flush()
com.write(b'\n')
(count, value) = com.read(1)
if count == 0 or value != b'K':
    com.close()

    print('[{}, {}] Could not find ICSP on {}\n'.format(count, value, args.port))
    sys.exit()

print('Connected...')

# flush input buffer so that we can start out synchronized
com.flush()

# Get host controller version
print('Getting Version...')
ver = icsp.get_version(com)
print('Hardware version:', ver)
print('Method: ', icsp.FAMILY_NAMES[programming_method])

print('Start...')
icsp.send_start(com, programming_method)

print("\nDevice Info:")
icsp.load_config(com)
icsp.jump(com, 6)

chip_id = icsp.read_program(com, 1)
cfg1 = icsp.read_program(com, 1)
cfg2 = icsp.read_program(com, 1)
cal1 = icsp.read_program(com, 1)
cal2 = icsp.read_program(com, 1)

idnum = int.from_bytes(chip_id, 'little')

# enhanced and midrange have different id/rev bits
device_id = idnum >> (5 if programming_method == icsp.ENH else 4)
device_rev = idnum & (0x1F if programming_method == icsp.ENH else 0x0F)
if device_id not in picdevice.PARAM:
    print(" ID: %04X rev %x not in device list" % (device_id, device_rev))

    print("End...")
    icsp.send_end(com, programming_method)

    print("Reset...")
    icsp.hard_reset(com)

    sys.exit()

device_param = picdevice.PARAM[device_id]
device_name = device_param['name']

print(" ID: %04X %s rev %x" % (device_id, device_name, device_rev))
print("CFG: %s %s" % (hex.bytes_to_hex(cfg1), hex.bytes_to_hex(cfg2)))
print("CAL: %s %s" % (hex.bytes_to_hex(cal1), hex.bytes_to_hex(cal2)))

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
    icsp.reset(com, device_param)

    print("Reading Firmware...")
    prog_list = icsp.read_program_pages(com, device_param)
    data_list = icsp.read_data_pages(com, device_param)
    chip_list = hex.merge_pages(prog_list, data_list)

    config_page = icsp.read_config(com, device_param)

    # Blank out 0x04 and 0x05, reserved
    config_page = config_page[:4 * 4] + '        ' + config_page[6 * 4:]
    # blank out chip id
    config_page = config_page[:6 * 4] + '    ' + config_page[7 * 4:]
    # blank out calibration words
    config_page = config_page[:9 * 4] + '        ' + config_page[11 * 4:]

    hex.add_page(chip_list, conf_page_num)
    chip_list[conf_page_num] = config_page

    print()

    if not args.quiet:
        hex.dump_pages(chip_list)

    hex.write_hex(TMP + '/' + args.filename, chip_list)
else:
    # Erase entire device including userid locations
    print("Erase Device...")
    icsp.load_config(com)
    icsp.erase_program(com, device_param)
    icsp.erase_data(com, device_param)

    print("Reset Address...")
    icsp.reset(com, device_param)

    print("Writing Program 0x%X .. 0x%X ..." % (0, max_page))
    icsp.write_program_pages(com, page_list, device_param)

    print("Writing Data 0x%X .. 0x%X ..." % (min_data, max_data))
    icsp.write_data_pages(com, page_list, device_param)

    print("Reset Address...")
    icsp.reset(com, device_param)

    print("Writing Config 0x%X ..." % conf_page_num)
    icsp.write_config(com, page_list, device_param)

    print("Reset Address...")
    icsp.reset(com, device_param)

    print("Reading Firmware...")
    prog_list = icsp.read_program_pages(com, device_param)
    data_list = icsp.read_data_pages(com, device_param)
    chip_list = hex.merge_pages(prog_list, data_list)

    config_page = icsp.read_config(com, device_param)

    # Blank out 0x04 and 0x05, reserved
    config_page = config_page[:4 * 4] + '        ' + config_page[6 * 4:]
    # blank out chip id
    config_page = config_page[:6 * 4] + '    ' + config_page[7 * 4:]
    # blank out calibration words
    config_page = config_page[:9 * 4] + '        ' + config_page[11 * 4:]

    hex.add_page(chip_list, conf_page_num)
    chip_list[conf_page_num] = config_page

    print()

    # Compare protected regions to ensure they are compatible
    print("Comparing firmware pages 0x%X .. 0x%X, 0x%X .. 0x%X, 0x%X..." %
          (min_page, max_page, min_data, max_data, conf_page_num))
    check_list = list(range(min_page, max_page + 1)) + list(range(min_data, max_data)) + [conf_page_num]
    error_list = hex.compare_pages(page_list, chip_list, check_list)

    if error_list:
        print("\nWARNING!\nError verifying firmware.")

        for page_num in error_list:
            print("File:")
            hex.dump_page(page_list, page_num)
            print("Chip:")
            hex.dump_page(chip_list, page_num)
    else:
        print(" OK")

print("End...")
icsp.send_end(com, programming_method)

print("Reset...")
icsp.hard_reset(com)

com.close()
