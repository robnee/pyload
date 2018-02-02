#! /usr/bin/python
#
# Intel HEX file utilities
#
#
# $Id: hex.py 741 2017-11-25 02:26:07Z rnee $
# -------------------------------------------------------------------------------

import re
import itertools

PAGESIZE = 64


def add_page(page_list, page_num):
    short = page_num - len(page_list) + 1
    if short > 0:
        page_list.extend([None] * short)
    if page_list[page_num] is None:
        page_list[page_num] = "  " * PAGESIZE


def merge_pages(target_list, source_list):
    out_list = []
    for t, s in itertools.zip_longest(target_list, source_list):
        out_list.append(s if s else t)

    return out_list


def read_hex(filename):
    """Read and parse hex file"""

    with open(filename) as fp:
        base = 0x00
        page_list = list()

        for line in fp:
            m = re.search('^:(\S\S)(\S\S\S\S)(\S\S)(\S*)(\S\S)', line.strip())
            count, address, rectype, data, checksum = m.groups()

            # Convert data fields from hex
            count = int(count, 16)

            # Look for a extended address record
            if rectype == '04':
                base = int(data, 16) << 16

            # Confirm checksum of data
            calcsum = count + hex_to_int(address[0:2]) + hex_to_int(address[2:4]) + hex_to_int(rectype) + hex_to_sum(
                data)
            calcsum = '{:02X}'.format((~calcsum + 1) & 0xff)

            assert calcsum == checksum, "Record at address ({} {}) has bad checksum ({})  I get {}".format(base,
                                                                                                           address,
                                                                                                           checksum,
                                                                                                           calcsum)

            full_address = base + hex_to_int(address)
            page_num = int(full_address + 1) // PAGESIZE
            offset = full_address % PAGESIZE

            # Add data records to page list
            if rectype == '00':
                add_page(page_list, page_num)

                page_list[page_num] = page_list[page_num][:offset * 2] + data +\
                    page_list[page_num][(offset + count) * 2:]

                # printf ("$type %2d $address(%04X %2d) $data $checksum $sum\n", $count, $page, $offset);

    return page_list


def write_hex(filename, pages):
    with open(filename, mode='w') as fp:

        # This will force an extended address record to start
        base_page = -1

        # Loop over all pages
        for page_num, page in enumerate(pages):
            # Check if we need an extended address line
            if int(page_num // 0x400) > base_page:
                base_page = page_num // 0x400
                data = "%04X" % (base_page)

                calcsum = 2 + 0 + 4 + hex_to_sum(data)
                calcsum = (~calcsum + 1) & 0xFF

                fp.write(":02000004%s%02X\r\n" % (data, calcsum))

            if page is not None:
                # break each page into blocks of 16 bytes
                for block_num in range(4):
                    # compute addresses and offsets keeping things to 16bits
                    offset = block_num * PAGESIZE // 2
                    addr = page_num % 0x400 * PAGESIZE + offset // 2
                    block = page[offset:offset + PAGESIZE // 2]

                    # Loop over block until everything has been dumped
                    for m in re.finditer('(\s*)(\S+)', block):
                        (pre, data) = m.groups()

                        # Update address to account for skipped bytes
                        addr += len(pre) // 2

                        count = len(data) // 2

                        calcsum = count + addr // 0x100 + (addr & 0xFF) + hex_to_sum(data)
                        calcsum = (~calcsum + 1) & 0xFF

                        fp.write(':%02X%04X%02X%s%02X\r\n' % (count, addr, 0x00, data, calcsum))

                        addr += len(data) // 2

        fp.write(':00000001FF\r\n')


def dump_page(page_list, page_num):
    """format page for display purposes"""
    page = page_list[page_num] if page_num < len(page_list) else None

    if page is not None:
        addr = page_num * PAGESIZE // 2
        sect = PAGESIZE // 2
        print("%03X-%04X : |%s %s|" % (page_num, addr, page[:sect], page[sect:sect * 2]))
        print("%03X-%04X : |%s %s|" % (page_num, addr + PAGESIZE // 4, page[sect * 2:sect * 3], page[sect * 3:]))


def dump_pages(pages):
    for page_num, page in enumerate(pages):
        dump_page(pages, page_num)


def compare_pages(new, old, pages):
    """Check that the data is appropriate to download.  Returns a list of pages that mismatch"""
    errors = list()

    # Check interrupt vector and boot loader
    for page_num in pages:
        new_page = new[page_num] if page_num < len(new) and new[page_num] is not None else "  " * PAGESIZE
        old_page = old[page_num] if page_num < len(old) and old[page_num] is not None else "  " * PAGESIZE
        if new_page != old_page:
            errors.append(page_num)

    return errors


def hex_to_sum(hex_data):
    """sum the hex bytes

    >>> hex_to_sum('afeb88'), 0xaf + 0xeb + 0x88
    (546, 546)
    """

    calcsum = 0
    for word in words(hex_data):
        calcsum += hex_to_int(word)

    return calcsum


def words(data):
    """return words made up of 2 bytes

    >>> list(words('6F6665623838'))
    ['6F', '66', '65', '62', '38', '38']
    """

    i = iter(data)
    for c in i:
        s = c + next(i)
        yield None if s == '  ' else s


def hex_to_bytes(data, chunk_size=2, nullval=b'\xff'):
    r"""Converts hex string to data bytes.  Empty values are set to the nullval

    >>> hex_to_bytes('6F666562383812')
    bytearray(b'ofeb88\x12')
    """

    b = bytearray()
    for word in words(data):
        # Replace blank words with nullval
        if word:
            b += bytes([hex_to_int(word)])
        else:
            b += nullval

    return b


def hex_to_int(strval):
    """convert hex strin to int

    >>> hex_to_int('78ad'), hex_to_int('6f')
    (30893, 111)
    """

    return int(strval, 16)


def bytes_to_hex(data):
    """Converts data bytes to a hex string

    >>> bytes_to_hex(b'afeb88')
    '616665623838'
    """

    string = ""
    for b in data:
        string += "%02X" % (b)

    return string


def bytes_to_word(data):
    r"""Converts data bytes to a single 16bit value LSB MSB

    >>> bytes_to_word(b'\x03\x01')
    259
    >>> ord(b'\x03') + (ord(b'\x01') << 8)
    259
    """

    length = len(data)

    value = 0
    if length > 0:
        value += data[0]
    if length > 1:
        value += data[1] << 8

    return value


if __name__ == '__main__':
    h = read_hex('blink.hex')
    dump_pages(h)
    write_hex('out.hex', h)
