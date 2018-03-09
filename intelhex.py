#! /usr/bin/python

"""Intel HEX file utilities

$Id: hex.py 714 2017-10-28 17:45:51Z rnee $
"""

import re
import binascii
import itertools

PAGELEN = 32
PAGEBYTES = PAGELEN * 2


def chunks(l, n):
    """Yield successive n-sized chunks from l

    >>> list(chunks('6F6665623838', 2))
    ['6F', '66', '65', '62', '38', '38']
    """

    for i in range(0, len(l), n):
        yield l[i: i + n]


def hex_to_sum(hex_str):
    """sum the hex bytes

    >>> hex_to_sum('afeb88'), 0xaf + 0xeb + 0x88
    (546, 546)
    """

    return sum(binascii.a2b_hex(hex_str))


class Page:
    r"""Represents one 64 byte page.  stores list of two char strings or None if empty

    >>> p = Page()
    >>> p[1] = '    '
    >>> p[2] = '4F2C'
    >>> p[PAGELEN - 1] = '9F6C'
    >>> p[23] = 0x5f
    >>> p[5:7] = '12345678'
    >>> p[9] = 'FF3F'
    >>> Page.NULLVAL = b'..'
    >>> format(p)
    '        4F2C        12345678        FF3F                                                    5F00                            9F6C'
    >>> p[6], p[9]
    (30806, 16383)
    >>> bytes(p)
    b'....O,....\x124Vx....\xff?.........................._\x00..............\x9fl'
    >>> p[PAGELEN] = '77'
    Traceback (most recent call last):
    ...
    IndexError: Page index out of range 33
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

    NULLVAL = b'\xff\xff'

    def __init__(self, s=None):
        if s is None:
            self.page = [None] * PAGELEN
        elif type(s) == str:
            if len(s) > PAGELEN * 4:
                raise ValueError(f'string len { len(s) } greater than {PAGELEN * 4} hex digits')

            self.page = [None if x == '    ' else int(x[:2], 16) + (int(x[2:], 16) << 8) for x in chunks(s, 4)]
        elif type(s) == bytes:
            if len(s) > PAGELEN * 2:
                    raise ValueError(f'bytes len {len(s)} greater than of {PAGELEN * 2}')

            self.page = [int.from_bytes(x, byteorder='little') for x in chunks(s, 2)]
        elif type(s) == Page:
            self.page = [x for x in s.page]
        else:
            raise TypeError('cannot initialize Page with', type(s))

        # make sure page is padded out to full length
        self._pad()

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

        if key.stop > PAGELEN:
            raise IndexError(f'Page index out of range {key.start} {key.stop}')

        if type(word) == int:
            value = [word] * length
        elif type(word) == str:
            if length * 4 != len(word):
                raise ValueError(f'value ({word}) is wrong length {length}')
            value = [None if x == '    ' else int(x[:2], 16) + (int(x[2:], 16) << 8) for x in chunks(word, 4)]
        elif word is None:
            value = [None]
        else:
            raise TypeError('int or str only')

        self.page[key] = value

    def __bytes__(self):
        x = [w.to_bytes(2, 'little') if w is not None else self.NULLVAL for w in self.page]
        return b''.join(x)

    def __str__(self):
        def fmt(w):
            """format for LSB MSB"""
            return '{:02X}{:02X}'.format(w % 0x100, w // 0x100)

        return ''.join([fmt(w) if w is not None else '    ' for w in self.page])

    def __repr__(self):
        return "Page('" + str(self) + "')"

    def _pad(self):
        """pad a page to length if necessary"""
        if len(self.page) < PAGELEN:
            self.page.extend([None] * (PAGELEN - len(self.page)))

    def display(self, page_num):
        """format page for display purposes"""

        disp = str(self)
        addr = page_num * PAGELEN

        return "%03X-%04X : |%s %s %s %s|\n%03X-%04X : |%s %s %s %s|" % (
            page_num, addr,
            disp[:PAGELEN * 1 // 2], disp[PAGELEN * 1 // 2: PAGELEN * 1],
            disp[PAGELEN * 1: PAGELEN * 3 // 2], disp[PAGELEN * 3 // 2: PAGELEN * 2],
            page_num, addr + PAGELEN // 2,
            disp[PAGELEN * 2: PAGELEN * 5 // 2], disp[PAGELEN * 5 // 2: PAGELEN * 3:],
            disp[PAGELEN * 3: PAGELEN * 7 // 2], disp[PAGELEN * 7 // 2:])

class Hexfile:
    """wrapper around list of Pages"""
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
        """"read Intel hex file"""
        base = 0x00

        for line_num, line in enumerate(fp, start=1):
            m = re.search('^:(?P<count>\S\S)(?P<address>\S\S\S\S)(?P<rectype>\S\S)(?P<words>\S*)(?P<checksum>\S\S)',
                          line.strip())
            count, address, rectype, words, checksum = m.groups()

            # Convert data fields from hex
            count = int(count, 16)

            # Look for a extended address record
            if rectype == '04':
                base = int(words, 16) << 16

            # Confirm checksum of data
            calcsum = count + hex_to_sum(address) + hex_to_sum(rectype) + hex_to_sum(words)
            calcsum = '{:02X}'.format((~calcsum + 1) & 0xff)

            assert calcsum == checksum, "line: {} address: ({} {}) has bad checksum ({})  I get {}".format(
                                    line_num, base, address, checksum, calcsum)

            full_address = base + int(address, 16)
            page_num = int(full_address + 1) // PAGEBYTES
            offset = full_address % PAGEBYTES

            # vet possibility to migrate the above to something simpler
            test_num, test_offset = divmod(full_address, PAGEBYTES)
            assert test_num == page_num and test_offset == offset, "divmod doesn't work"

            word_offset, word_count = offset // 2, count // 2

            # Add data records to page list
            if rectype == '00':
                if len(self.page_list) <= page_num:
                    self[page_num] = Page()
                self[page_num][word_offset: word_offset + word_count] = words
            # printf ("$type %2d $address(%04X %2d) $data $checksum $sum\n", $count, $page, $offset);

    def write(self, fp):
        """Write pages in .HEX format"""

        # This will force an extended address record to start
        base_page = -1

        # Loop over all pages
        for page_num, page in enumerate(self.page_list):
            # Check if we need an extended address line
            if int(page_num // 0x400) > base_page:
                base_page = page_num // 0x400
                data = f"{base_page:04X}"

                calcsum = 2 + 0 + 4 + hex_to_sum(data)
                calcsum = (~calcsum + 1) & 0xFF

                print(":02000004%s%02X" % (data, calcsum), file=fp, end='\r\n')

            if page is not None:
                # break each page into blocks of 8 words
                block_size = PAGELEN // 4
                for word_offset in range(0, PAGELEN, 8):
                    # compute addresses and offsets keeping things to 16bits
                    addr = page_num % 0x400 * PAGEBYTES + word_offset * 2
                    block = page[word_offset:word_offset + block_size]

                    def fmt(w):
                        """format for LSB MSB"""
                        return '{:02X}{:02X}'.format(w % 0x100, w // 0x100)

                    def block_chunks():
                        """Generator that yields pairs of empty space and non-empty data chunks
                        for output.  """
                        space = 0
                        start = 0
                        space_flag = True

                        for i, w in enumerate(block):
                            if space_flag:
                                if w is not None:
                                    start = i
                                    space_flag = False
                            else:
                                # if we find a space yield a pair
                                if w is None:
                                    yield start - space, ''.join(fmt(w) for w in block[start: i])
                                    space = i
                                    space_flag = True

                        # yield whatever is left unless we were parsing empty space
                        if not space_flag:
                            yield start - space, ''.join(fmt(w) for w in block[start:])

                    # Loop over block until everything has been dumped
                    for space_len, data in block_chunks():
                        # Update address to account for skipped words
                        addr += space_len * 2

                        byte_count = len(data) // 2

                        calcsum = byte_count + addr // 0x100 + (addr & 0xFF) + hex_to_sum(data)
                        calcsum = (~calcsum + 1) & 0xFF

                        # print(':%02X%04X%02X%s%02X' % (count, addr, 0x00, data, calcsum), file=fp, end='\r\n')
                        fp.write(':%02X%04X%02X%s%02X\r\n' % (byte_count, addr, 0x00, data, calcsum))

                        addr += byte_count

        print(':00000001FF', file=fp, end='\r\n')

    def compare(self, other, pages):
        """Check that the data is appropriate to download.  Returns a list of pages that mismatch"""
        errors = list()

        empty = "    " * PAGELEN

        # Check interrupt vector and boot loader
        for page_num in pages:
            this_page = str(self[page_num]) if page_num < len(self) and self[page_num] is not None else empty
            that_page = str(other[page_num]) if page_num < len(other) and other[page_num] is not None else empty
            if this_page != that_page:
                errors.append(page_num)

        return errors

    def display(self):
        """return a string formatted for display"""
        s = ''
        for page_num, page in enumerate(self.page_list):
            if page:
                s += page.display(page_num) + '\n'
        return s


    def memory_map(self):
        """
        MEMORY USAGE MAP ('X' = Used,  '-' = Unused)

        0000 : XX--XXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX
        0040 : XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX
        0680 : XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX
        06C0 : XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX
        0700 : XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX
        0740 : XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXXX
        0780 : XXXXXXXXXXXXXXXX XXXXXXXXXXXXXXX- ---------------- ----------------
        8000 : XXXX---XX------- ---------------- ---------------- ----------------
        F000 : X--------------- ---------------- ---------------- ----------------

        All other memory blocks unused.

        Program Memory Words Used:   413
        Program Memory Words Free:  1635

        """

        print("MEMORY USAGE MAP ('X' = Used,  '-' = Unused)\n")

        word_count = 0
        for page_num in range(0, len(self.page_list), 2):
            page1 = self.page_list[page_num]
            page2 = self.page_list[page_num + 1] if page_num + 1 < len(self.page_list) else None

            if page1 or page2:
                print(f"{page_num * PAGELEN:04X} : ", end='')
                if page1:
                    for word_num, word in enumerate(page1):
                        if word is not None:
                            print('X', end='')
                            word_count += 1
                        else:
                            print('-', end='')

                        if (word_num + 1) % 16 == 0:
                            print(' ', end='')
                else:
                    print("---------------- ---------------- ", end='')

                if page2:
                    for word_num, word in enumerate(page2):
                        if word is not None:
                            print('X', end='')
                            word_count += 1
                        else:
                            print('-', end='')

                        if (word_num + 1) % 16 == 0:
                            print(' ', end='')
                    print()
                else:
                    print("---------------- ---------------- ")

        print("\nAll other memory blocks unused.\n")

        print(f"Program Memory Words Used:{word_count:6d}")


if __name__ == '__main__':
    p = Page('        4F2C        12345678                                                                5F00                            9F6C')
    print(bytes(p))
    print(list(chunks(p, 4)))
    q = Page('00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28    ' + '00308C0001308D002100EA3099001A1C172888018C1425238C1025231A28    ')

    r = Page(b'\x01\x00\x02\x00\x08\x00\t\x00\xff?\xff?\x85\x1b\xc49\xff<\x91\x18e\x1e\xff?\xff?\xff?\xff?\xff?')
    print(r)
    print(bytes(q))

    print('q=', repr(q))
    print(q.display(0))
    print(bytes(q))
    q2 = Page(q)

    print('q2=', len(q), '>', len(q2), '>>', repr(q2))

    # with open('blink.hex') as inf:
    #     h = Hexfile()
    #     h.read(inf)
    #     print(h.display())
    #
    # with open('out2.hex', mode='w') as outf:
    #     h.write(outf)
