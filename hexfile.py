#! /usr/bin/python
#
# Intel HEX file utilities
#
#
# $Id: hex.py 714 2017-10-28 17:45:51Z rnee $
# -------------------------------------------------------------------------------

import re
import itertools

PAGESIZE = 64


def words(data):
    """return words made up of 2 bytes

    >>> list(words('6F6665623838'))
    ['6F', '66', '65', '62', '38', '38']
    """

    i = iter(data)
    for c in i:
        s = c + next(i)
        yield None if s == '  ' else s


def hex_to_int(strval):
    """convert hex strin to int

    >>> hex_to_int('78ad'), hex_to_int('6f')
    (30893, 111)
    """

    return int(strval, 16)


def hex_to_sum(hex_data):
    """sum the hex bytes

    >>> hex_to_sum('afeb88'), 0xaf + 0xeb + 0x88
    (546, 546)
    """

    calcsum = 0
    for word in words(hex_data):
        calcsum += hex_to_int(word)

    return calcsum


def hex_to_bytes(data, nullval=b'\xff'):
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


class Page:
    r"""Represents one 64 byte page.  stores list of two char strings or None if empty

    >>> p = Page()
    >>> p[2] = '  '
    >>> p[3] = '4F'
    >>> p[PAGESIZE - 1] = '9F'
    >>> p[23] = 0x5f
    >>> p[5:7] = '1234'  #there is no check for the mismatched len here
    >>> Page.NULLVAL = ord('.')
    >>> format(p)
    '      4F  1234                                5F                                                                              9F'
    >>> bytes(p)
    b'...O.\x124................_.......................................\x9f'
    >>> p[PAGESIZE] = '77'
    Traceback (most recent call last):
    ...
    IndexError: Page index out of range 65
    >>> p[4] = '4ff'
    Traceback (most recent call last):
    ...
    ValueError: value is wrong length
    >>> q = Page('00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28    ' + '00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28    ')
    >>> repr(q)
    "Page('00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28    00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28    ')"
    >>> q.display(0)
    '000-0000 : |00308C0001308D002100EA3099001A1C 172888018C1425238C1025231A28    |\n000-0010 : |00308C0001308D002100EA3099001A1C 172888018C1425238C1025231A28    |'
    >>> bytes(q)
    b'\x000\x8c\x00\x010\x8d\x00!\x00\xea0\x99\x00\x1a\x1c\x17(\x88\x01\x8c\x14%#\x8c\x10%#\x1a(..\x000\x8c\x00\x010\x8d\x00!\x00\xea0\x99\x00\x1a\x1c\x17(\x88\x01\x8c\x14%#\x8c\x10%#\x1a(..'
    """

    NULLVAL = 0xff

    def __init__(self, s=None):
        if s is None:
            self.page = [None] * PAGESIZE
        elif type(s) == str:
            if len(s) != PAGESIZE * 2:
                raise ValueError('string must be full page of 128 hex digits', len(s))

            self.page = [None if x == '  ' else x for x in words(s)]
        elif type(s) == bytes:
            if len(s) != PAGESIZE:
                    raise ValueError('must be full page of 64 bytes')

            self.page = ['%02X' % (x) for x in s]
        elif type(s) == Page:
            self.page = [x for x in s.page]
        else:
            raise TypeError('cannot initialize Page with', type(s))

    def __len__(self):
        return len(self.page)

    def __getitem__(self, key):
        return self.page[key]

    def __setitem__(self, key, word):
        if type(key) is slice:
            length = key.stop - key.start
        else:
            length = 1
            key = slice(key, key + 1)

        if key.stop > PAGESIZE:
            raise IndexError('Page index out of range {}'.format(key.stop))

        if type(word) == int:
            value = ['{:02X}'.format(word)] * length
        elif type(word) == str:
            if length * 2 != len(word):
                raise ValueError('value is wrong length')
            value = words(word.upper())
        elif word is None:
            value = [None]
        else:
            raise TypeError('int or str only')

        self.page[key] = value

    def __bytes__(self):
        return bytes([int(b, 16) if b else self.NULLVAL for b in self.page])

    def __str__(self):
        return ''.join([x if x else '  ' for x in self.page])

    def __repr__(self):
        return "Page('" + str(self) + "')"

    def display(self, page_num):
        """format page for display purposes"""

        p = str(self)

        addr = page_num * PAGESIZE // 2
        return "%03X-%04X : |%s %s|\n%03X-%04X : |%s %s|" % (
            page_num, addr, p[:PAGESIZE // 2], p[PAGESIZE // 2:PAGESIZE],
            page_num, addr + PAGESIZE // 4, p[PAGESIZE:PAGESIZE * 3 // 2],
            p[PAGESIZE * 3 // 2:])


class Hexfile:
    def __init__(self, page_list=None):
        self.page_list = page_list or []

    def __setitem__(self, page_num, page):
        short = page_num - len(self.page_list) + 1
        if short > 0:
            self.page_list.extend([None] * short)

        self.page_list[page_num] = Page(page)

    def __getitem__(self, key):
        try:
            return self.page_list[key]
        except IndexError:
            return None

    def __len__(self):
        return len(self.page_list)

    def __add__(self, other):
        new_list = []
        for s, t in itertools.zip_longest(self.page_list, other.page_list):
            new_list.append(t or s)

        return Hexfile(new_list)

    def read(self, fp):
        base = 0x00

        for line_num, line in enumerate(fp, start=1):
            m = re.search('^:(\S\S)(\S\S\S\S)(\S\S)(\S*)(\S\S)', line.strip())
            count, address, rectype, data, checksum = m.groups()

            # Convert data fields from hex
            count = int(count, 16)

            # Look for a extended address record
            if rectype == '04':
                base = int(data, 16) << 16

            # Confirm checksum of data
            calcsum = count + hex_to_int(address[0:2]) + hex_to_int(address[2:4]) + hex_to_int(rectype) + hex_to_sum(data)
            calcsum = '{:02X}'.format((~calcsum + 1) & 0xff)

            assert calcsum == checksum, "line: {} address: ({} {}) has bad checksum ({})  I get {}".format(
                                    line_num, base, address, checksum, calcsum)

            full_address = base + hex_to_int(address)
            page_num = int(full_address + 1) // PAGESIZE
            offset = full_address % PAGESIZE

            # Add data records to page list
            if rectype == '00':
                if len(self.page_list) <= page_num:
                    self[page_num] = Page()
                self[page_num][offset: offset + count] = data
            # printf ("$type %2d $address(%04X %2d) $data $checksum $sum\n", $count, $page, $offset);

    def write(self, fp):
        """Write pages in .HEX format
        """

        # This will force an extended address record to start
        base_page = -1

        # Loop over all pages
        for page_num, page in enumerate(self.page_list):
            # Check if we need an extended address line
            if int(page_num // 0x400) > base_page:
                base_page = page_num // 0x400
                data = "%04X" % (base_page)

                calcsum = 2 + 0 + 4 + hex_to_sum(data)
                calcsum = (~calcsum + 1) & 0xFF

                print(":02000004%s%02X" % (data, calcsum), file=fp, end='\r\n')

            if page is not None:
                # break each page into blocks of 16 bytes
                block_size = PAGESIZE // 4
                for offset in range(0, 64, 16):
                    # compute addresses and offsets keeping things to 16bits
                    addr = page_num % 0x400 * PAGESIZE + offset
                    block = page[offset:offset + block_size]

                    def chunks():
                        """Generator that yields chunks of non-empty words for output"""
                        space = 0
                        start = 0
                        pre_flag = True

                        for i, w in enumerate(block):
                            if pre_flag:
                                if w:
                                    start = i
                                    pre_flag = False
                            else:
                                if not w:
                                    yield start - space, ''.join(block[start: i])
                                    space = i
                                    pre_flag = True

                        # yield whatever is left unless it’s empty
                        if not pre_flag:
                            yield start - space, ''.join(block[start:])

                    # Loop over block until everything has been dumped
                    for space_pos, data in chunks():
                        # Update address to account for skipped bytes
                        addr += space_pos

                        count = len(data) // 2

                        calcsum = count + addr // 0x100 + (addr & 0xFF) + hex_to_sum(data)
                        calcsum = (~calcsum + 1) & 0xFF

                        # print(':%02X%04X%02X%s%02X' % (count, addr, 0x00, data, calcsum), file=fp, end='\r\n')
                        fp.write(':%02X%04X%02X%s%02X\r\n' % (count, addr, 0x00, data, calcsum))

                        addr += count

        print(':00000001FF', file=fp, end='\r\n')

    def compare(self, other, pages):
        """Check that the data is appropriate to download.  Returns a list of pages that mismatch"""
        errors = list()

        # Check interrupt vector and boot loader
        for page_num in pages:
            this_page = str(self[page_num]) if page_num < len(self) and self[page_num] is not None else "  " * PAGESIZE
            that_page = str(other[page_num]) if page_num < len(other) and other[page_num] is not None else "  " * PAGESIZE
            if this_page != that_page:
                errors.append(page_num)

        return errors

    def display(self):
        s = ''
        for page_num, page in enumerate(self.page_list):
            if page:
                s += page.display(page_num) + '\n'
        return s


if __name__ == '__main__':
    q = Page('00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28    ' + '00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28    ')

    print('q=', repr(q))
    print(q.display(0))
    print(bytes(q))
    q2 = Page(q)

    print('q2=', len(q), '>', len(q2), '>>', repr(q2))

    with open('blink.hex') as inf:
        h = Hexfile()
        h.read(inf)
        print(h.display())

    with open('out2.hex', mode='w') as outf:
        h.write(outf)
