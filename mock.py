"""
Mock icsp interface for testing.  Implements the serial port protocol that can be wrapped in a Comm object.

Attempting to create a state machine that runs on every call to the serial port read API and reads and writes to and
from the input and output queue until the state machine blocks on a serial read for the next icsp command byte.
At that point the inbound request can be satisfied from one of the two queues.

How to do that?  Perhaps this is an example of coroutine programming with yield?  That might simplify the handoff
in and out of the state machine.  Not sure how to yield out of the state machine without creating a call chain that
goes deeper and deeper.

"""

import hexfile


class Port:
    def __init__(self):
        self._dtr = False
        self.break_dur = 0
        self.inq = bytes()
        self.outq = bytes()

    @property
    def in_waiting(self):
        return len(self.inq)

    @property
    def dtr(self):
        return self._dtr

    @dtr.setter
    def dtr(self, state: bool):
        if self._dtr and not state:
            self.reset()
        self._dtr = state

    def read(self, num_bytes: int):
        while len(self.inq) < num_bytes:
            self.run()
            
        ret, self.inq = self.inq[: num_bytes], self.inq[num_bytes:]
        return ret

    def readline(self):
        if len(self.inq) < 1:
            self.run()
            
        nl = self.inq.find(b'\n')
        if nl < 0:
            ret, self.inq = self.inq, bytes()
        else:
            ret, self.inq = self.inq[: nl + 1], self.inq[nl + 1:]

        return ret
        
    def send_break(self, duration: int):
        self.break_dur = duration
        self.outq = bytes()

    def write(self, data: bytes):
        self.outq += data

    def open(self):
        self.inq = bytes()
        self.outq = bytes()
        self.break_dur = 0
        
    def close(self):
        pass

    def ser_avail(self):
        return self.outq
        
    def ser_get(self):
        if not self.ser_avail():
            raise EOFError

        ret, self.outq = self.outq[:1], self.outq[1:]
        
        return ret

    def ser_out(self, data: bytes):
        self.inq += data


class ICSP:
    def __init__(self):
        self.address = 0
        
    def reset(self):
        self.ser_out(b'K')
        
    def run(self):
        # print('running addr:', hex(self.address), 'in:', self.inq, 'out:', self.outq)
        while True:
            c = self.ser_get()

            if c == b'V':
                self.ser_out(b'V1.4\n')
            elif c == b'S':
                # read extra byte
                _ = self.ser_get()
                self.address = 0
            elif c == b'X':
                self.address = 0
            elif c == b'E':
                # read extra byte
                _ = self.ser_get()
            elif c == b'C':
                # read two extra bytes
                _ = self.ser_get()
                _ = self.ser_get()
                self.address = 0x8000
            elif c == b'I':
                self.address += 1
            elif c == b'J':
                a = self.ser_get()
                b = self.ser_get()
                self.address += int.from_bytes(a + b, 'little')
            elif c == b'F':
                a = self.ser_get()
                b = self.ser_get()
                num_words = int.from_bytes(a + b, 'little')
                
                for _ in range(num_words):
                    if self.address == 0x8006:
                        chip_id = (0b10_0111_000 << 5) + 0b0_0101
                        self.ser_out(chip_id.to_bytes(2, 'little'))
                    else:
                        word = self.get_word(self.address)
                        self.ser_out(word)
                    self.address += 1
            elif c == b'G':
                a = self.ser_get()
                b = self.ser_get()
                num_words = int.from_bytes(a + b, 'little')
                if self.address < 0xF000:
                    self.address = 0xF000
                
                for _ in range(num_words):
                    self.ser_out(b'\xFF')
                    self.address += 1
                
            elif c == 'D':
                pass
            elif c == 'BALMP':
                pass
            self.ser_out(b'K')
            
            if not self.ser_avail():
                break
        # print('done in:', self.inq, 'out:', self.outq)

        
class Target:
    def __init__(self, firmware=None):
        self.firmware = firmware

    def get_word(self, word_address: int):
        """access a two byte firmware word by word address"""
        page_num, word_num = divmod(word_address, hexfile.PAGESIZE // 2)
        byte_num = word_num * 2

        print(word_address, 'pn:', page_num, 'bn:', byte_num, 'wn:', word_num)

        if page_num < len(self.firmware):
            page = bytes(self.firmware[page_num])

            return page[byte_num: byte_num + 2]


class ICSPHost(Port, ICSP, Target):
    def __init__(self, firmware):
        Port.__init__(self)
        ICSP.__init__(self)
        Target.__init__(self, firmware)
