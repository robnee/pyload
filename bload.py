#! /usr/bin/python3

# -------------------------------------------------------------------------------
#    $Id: bload.py 814 2018-02-16 02:44:24Z rnee $
#

import sys
import struct

import hexfile

PAGESIZE = 64

# -------------------------------------------------------------------------------
# Bload protocol interface
# -------------------------------------------------------------------------------


def get_address(page_num: int) -> bytes:
    """ Return address as a LSB + MSB 16 bit word """
    addr = page_num * PAGESIZE // 2

    return addr.to_bytes(2, 'little')


def calc_checksum(data):
    """ Get the checksum """
    return sum(data) & 0xFF


def get_command(cmd_code, page_num: int, data: bytes=None) -> bytes:
    """ Generate a command string including a command char, address and checksum """

    if data is None:
        data = b''

    address = get_address(page_num)
    checksum = bytes([calc_checksum(address + data)])

    return bytes(cmd_code) + address + data + checksum


def wait_k(com) -> bytes:
    """ Wait for K (OK) prompt """

    data = bytes()
    timeout = 3

    while True:
        count, prompt = com.read(1)

        data += prompt
        if prompt == b'K':
            break

        # Check timeout
        timeout -= 1
        if count == 0 and timeout == 0:
            break

    return data


def get_info(com):
    cmd = b'I' + b'\0'

    com.write(cmd)

    count, data = com.read(16)

    # if bootloader responds with less than four bytes assume that it doesn't
    # support the I command.  Version 0x10, Boot region 0x38 - 0x3F, EEPROM data 0x108
    if count < 4:
        return bytes(16)

    # Check for an error
    if data == b'CK':
        print('\nChecksum error issuing bootloader info command')
        return bytes(16)

    count, checksum = com.read(1)

    # Check checksum
    if ord(checksum) != calc_checksum(data):
        print('\nChecksum error getting bootloader info.  chip:0x%02x calc:0x%02x' %
              (ord(checksum), calc_checksum(data)))
        return bytes(16)

    prompt = wait_k(com)
    if prompt != b'K':
        print('Error [%s] bootloader info' % prompt)
        return bytes(16)

    # return boot_version, boot_start, boot_end, data_start, data_end
    return struct.unpack('BBHHHHxxxxxx', data)


def erase_program_page(com, page_num: int):
    cmd = get_command(b'E', page_num)
    com.write(cmd)


def write_page(com, cmd_code: bytes, page_num: int, page_bytes):
    """ Write a single program page to the chip """

    length = len(page_bytes)
    if length != PAGESIZE:
        print('\nInvalid data page size (%d) for page %s %03x' % (length, cmd_code, page_num))
        return

    cmd = get_command(cmd_code, page_num, page_bytes)
    com.write(cmd)


def write_pages(com, cmd: bytes, pages: hexfile.Hexfile, page_nums):
    for page_num in page_nums:
        page = pages[page_num] if page_num < len(pages) else None

        # Data checks
        if page is None:
            # for program pages only!
            if cmd == b'W':
                erase_program_page(com, page_num)
                show_progress(b'E')
            else:
                # write an empty page to erase data
                write_page(com, cmd, page_num, b'\xFF' * PAGESIZE)
                show_progress(b'S')
        else:
            write_page(com, cmd, page_num, bytes(page))
            show_progress(cmd)

        prompt = wait_k(com)
        if prompt != b'K':
            for c in prompt:
                print('[%02X] ' % c, end='')

            print('Error [%s] writing page 0x%03X:0x%04X' % (prompt, page_num,
                  page_num * PAGESIZE // 2))
            return


def read_page(com, cmd: bytes, page_num: int) -> bytes:
    # allow 5 read tries
    for retry in range(5):
        com.write(cmd)

        count, data = com.read(PAGESIZE)

        # Check for an error
        if data == b'CK':
            print('\nChecksum error issuing read attempt %d on page %d' % (retry,
                  page_num))
            continue

        if count != PAGESIZE:
            print('Short page %d [%d]' % (page_num, count))
            print('[', hexfile.bytes_to_hex(data), ']')
            continue

        # Check checksum
        count, checksum = com.read(1)
        if ord(checksum) != calc_checksum(data):
            print('checksum:', ord(checksum), 'bl:', calc_checksum(data))
            print('\nChecksum error reading %s page 0x%03x\n' % (cmd, page_num))
            continue

        return data

    # fails
    return b''


def read_config(com) -> bytes:
    page_num = 0

    # Read all pages and create a list
    data = read_page(com, b'C' + b'\0', page_num)

    prompt = wait_k(com)
    assert prompt == b'K', 'Error [%s] reading config' % prompt

    show_progress(b'C')

    # Only send back first 9 words, 18 bytes.  Rest are zeros.
    return data


def show_progress(cmd: bytes):
    if cmd in (b'C', b'R', b'W'):
        sys.stderr.write('.')
    elif cmd == b'E':
        sys.stderr.write('x')
    elif cmd == b'S':
        sys.stderr.write('>')
    elif cmd in (b'D', b'F'):
        sys.stderr.write(':')

    sys.stderr.flush()


def read_pages(com, cmd_code: bytes, page_nums):
    """Read all pages and creates a list"""

    page_list = []

    for page_num in page_nums:
        cmd = get_command(cmd_code, page_num)
        data = read_page(com, cmd, page_num)

        prompt = wait_k(com)
        assert prompt == b'K', 'Error [%s] reading page %2X:%3X' % (prompt, page_num, page_num * PAGESIZE // 2)

        show_progress(cmd_code)

        page_list.append(data)

    return page_list


def read_program(com, page_nums) -> hexfile.Hexfile:
    """Read all pages and create a list"""

    prog_list = read_pages(com, b'R', page_nums)

    pages = hexfile.Hexfile()

    for page_num, data in zip(page_nums, prog_list):
        if data:
            page = hexfile.Page(data)

            # Remove NULL words
            for offset in range(0, len(page), 2):
                word = page[offset: offset + 2]
                if word == ['FF', '3F']:
                    page[offset] = None
                    page[offset + 1] = None

            if any(page):
                pages[page_num] = page

    return pages


def read_data(com, page_nums) -> hexfile.Hexfile:
    """Read all pages and create a list"""

    data_list = read_pages(com, b'F', page_nums)

    pages = hexfile.Hexfile()

    for page_num, data in zip(page_nums, data_list):
        if data:
            page = hexfile.Page(data)

            # Remove NULL words and force unused high word to 00
            for offset in range(0, len(page), 2):
                word = [page[offset], '00']
                if word == ['FF', '00']:
                    page[offset] = None
                    page[offset + 1] = None

            if any(page):
                pages[page_num] = page

    return pages


def write_data_page(com, page_num: int, page1, page2):
    """ This is the v1.0 routine that writes data pages in the legacy format with 64
    byte pages with no high bytes.  Newer bootloaders (1.1+) write pages with high
    bytes (which are ignored) to make the format identical to program pages """

    # combine pages and account for empty pages
    page = (page1 or " " * (PAGESIZE * 2)) + (page2 or " " * (PAGESIZE * 2))

    length = len(page)
    if length != PAGESIZE * 4:
        print('\nInvalid page size (%d) for page %d' % (length, page_num))
        return

    address = get_address(page_num)
    data = hexfile.hex_to_bytes(page, 4)
    checksum = bytes([calc_checksum(address + data)])

    sys.stderr.write('.')
    sys.stderr.flush()

    cmd = b"D" + address + data + checksum
    com.write(com, cmd)


def write_data(com, min_data: int, max_data: int, data):
    for i in range(min_data, max_data, 2):
        page_num = i - min_data
        write_data_page(com, page_num, data[i], data[i + 1])

        prompt = wait_k(com)

        if prompt != b'K':
            print("Error [%s] writing data page %2X\n" % (prompt, page_num * PAGESIZE // 2))
            return
