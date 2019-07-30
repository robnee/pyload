#! /usr/bin/python3

"""
$Id: bload.py 899 2018-04-28 20:26:42Z rnee $
"""

import sys
import struct
import logging

import intelhex

PAGESIZE = 64

# -------------------------------------------------------------------------------
# Bload protocol interface
# -------------------------------------------------------------------------------


def get_address(page_num: int) -> bytes:
    r""" Return address as a LSB + MSB 16 bit word

    >>> get_address(12)
    b'\x80\x01'
    """

    addr = page_num * PAGESIZE // 2

    return addr.to_bytes(2, 'little')


def calc_checksum(data: bytes) -> int:
    """ Get the checksum

    >>> calc_checksum(b'abcd')
    138
    >>> calc_checksum(b'')
    0
    """

    return sum(data) & 0xFF


def get_command(cmd_code, page_num: int, data: bytes=None) -> bytes:
    r""" Generate a command string including a command char, address and checksum

    >>> get_command(b'X', 12, b'1234')
    b'X\x80\x011234K'
    """

    if data is None:
        data = b''

    address = get_address(page_num)
    checksum = bytes([calc_checksum(address + data)])

    return bytes(cmd_code) + address + data + checksum


def sync(com) -> bool:
    """ synchronize with the target and prepare it for the next command """

    retries = 3

    while True:
        count, prompt = com.read(1)
        if prompt == b'K':
            return True

        if count == 0:
            if retries <= 0:
                break

            retries -= 1

        if com.avail() == 0:
            com.write(b'K')

    return False


def show_progress(cmd: bytes):
    """display a progress tick"""
    if cmd in (b'C', b'R', b'W'):
        sys.stdout.write('.')
    elif cmd == b'E':
        sys.stdout.write('x')
    elif cmd == b'S':
        sys.stdout.write('>')
    elif cmd in (b'D', b'F'):
        sys.stdout.write(':')

    sys.stdout.flush()


def get_info(com):
    """request info record from bootloader"""

    # allow 5 read tries
    for retry in range(5):
        try:
            cmd = b'I' + b'\0'
    
            com.write(cmd)
    
            count, data = com.read(16)
    
            # if bootloader responds with less than four bytes assume that it
            # doesn't  support the I command.
            if count < 4:
                break

            # Check for an error
            if data == b'CK':
                logging.warning('Checksum error issuing bootloader info command')
                raise RuntimeError
    
            count, checksum = com.read(1)
            if not checksum:
                logging.warning('no checksum returned')
                raise RuntimeError
    
            # Check checksum
            act_checksum = calc_checksum(data)
            if ord(checksum) != act_checksum:
                logging.warning('Checksum error getting bootloader info.',
                                f'chip:0x{ord(checksum):02x} calc:0x{act_checksum:02x}')
                raise RuntimeError
    
            ready = sync(com)
            if not ready:
                logging.warning('Sync error reading bootloader info')
                raise RuntimeError
    
            # return boot_version, boot_start, boot_size, data_start, data_end, code_end
            return struct.unpack('BBHHHHHxxxx', data)
            
        except RuntimeError:
            sync(com)

    return (0,) * 7


def erase_program_page(com, page_num: int):
    """Erase specified program page"""
    cmd = get_command(b'E', page_num)
    com.write(cmd)


def write_page(com, cmd_code: bytes, page_num: int, page_bytes: bytes):
    """ Write a single program page to the chip """

    length = len(page_bytes)
    if length != PAGESIZE:
        raise ValueError(f'Invalid page size ({length}) writing page {page_num:03x}')

    cmd = get_command(cmd_code, page_num, page_bytes)
    com.write(cmd)


def write_pages(com, cmd: bytes, pages: intelhex.Hexfile, page_nums):
    """write specified list of pages"""
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

        ready = sync(com)
        if not ready:
            logging.error('Sync error writing page 0x%03X:0x%04X' % (page_num, page_num * PAGESIZE // 2))
            return


def read_page(com, cmd: bytes, page_num: int) -> bytes:
    """read specified page. allow 5 read tries"""
    for retry in range(5):
        try:
            com.write(cmd)
    
            data_count, data = com.read(PAGESIZE)
    
            if data_count != PAGESIZE:
                # Check for specific errors
                if data.startswith(b'CK'):
                    logging.warning(f'Checksum error on read attempt {retry} on page {page_num}')
                    raise RuntimeError
                if data.startswith(b'EK'):
                    logging.warning(f'Command error on read attempt {retry} on page {page_num}')
                    raise RuntimeError
    
                logging.warning(f'Short page {page_num} [{data_count}]')
                raise RuntimeError
    
            # Check checksum
            count, checksum = com.read(1)
            if not checksum:
                logging.warning('no checksum returned')
                raise RuntimeError
    
            act_checksum = calc_checksum(data)
            if ord(checksum) != act_checksum:
                logging.warning(f'Checksum error reading page: 0x{page_num:03x} cmd: {cmd}')
                logging.warning(f'checksum: {ord(checksum)} computed: {act_checksum}')
                raise RuntimeError
    
            return data
        except RuntimeError:
            sync(com)

    # fails
    return b''


def read_config(com) -> bytes:
    """read config data"""
    page_num = 0

    # Read all pages and create a list
    data = read_page(com, b'C' + b'\0', page_num)

    ready = sync(com)
    if not ready:
        raise RuntimeError('Sync error reading config')

    show_progress(b'C')

    # Only send back first 9 words, 18 bytes.  Rest are zeros.
    return data


def read_pages(com, cmd_code: bytes, page_nums):
    """Read all pages and creates a list"""

    page_list = []

    for page_num in page_nums:
        cmd = get_command(cmd_code, page_num)
        data = read_page(com, cmd, page_num)

        ready = sync(com)
        if not ready:
            raise RuntimeError(f'Sync error reading page 0x{page_num:%3X}')

        show_progress(cmd_code)

        page_list.append(data)

    return page_list


def read_program(com, page_nums) -> intelhex.Hexfile:
    """Read all pages and create a list"""

    prog_list = read_pages(com, b'R', page_nums)

    pages = intelhex.Hexfile()

    for page_num, data in zip(page_nums, prog_list):
        if data:
            page = intelhex.Page(data)

            # Remove NULL words
            for offset in range(0, len(page)):
                if page[offset] == 0x3FFF:
                    page[offset] = None

            if any(page):
                pages[page_num] = page

    return pages


def read_data(com, page_nums) -> intelhex.Hexfile:
    """Read all pages and create a list"""

    data_list = read_pages(com, b'F', page_nums)

    pages = intelhex.Hexfile()

    for page_num, data in zip(page_nums, data_list):
        if data:
            page = intelhex.Page(data)

            # Remove NULL words and force unused high word to 00
            for offset in range(0, len(page)):
                if page[offset] == 0x00FF:
                    page[offset] = None

            if any(page):
                pages[page_num] = page

    return pages


if __name__ == "__main__":
    sys.argv = ['x.hex']
