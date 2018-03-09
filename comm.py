"""Serial port comm routines

$Id: comm.py 845 2018-03-09 01:26:51Z rnee $
"""

import time


class Comm:
    """Serial port wrapper that supports logginga and mocking"""
    def __init__(self, ser, logf=None):
        self.ser = ser
        self.logf = logf
        self.time0 = time.time()

        self.read_count = 0
        self.write_count = 0

        # log initial state of lines
        self._log(b'\x01' if ser.dtr else b'\x00', "DTR")
        self._log(b'\x01' if ser.dsr else b'\x00', "DSR")
        self._log(b'\x01' if ser.cts else b'\x00', "CTS")
        self._log(b'\x01' if ser.rts else b'\x00', "RTS")

    def read(self, request=None):
        """ read a requested number of bytes.  If request is missing or zero read available """
        if not request:
            request = self.avail()

        data = self.ser.read(request)
        total = len(data)

        self.read_count += total

        if total > 0:
            self._log(data, "READ")
        else:
            self._log(data, "TIME")

        return total, data

    def read_line(self):
        """"read line up to newline character or timeout"""
        data = self.ser.readline()

        self._log(data, "RDLN")

        return data

    def write(self, data):
        """Write bytes"""
        self.ser.write(data)

        self.write_count += len(data)

        self._log(data, "WRIT")

    def avail(self):
        """ return number of bytes available to read """
        return self.ser.in_waiting

    def flush(self):
        """flush input buffer"""
        waiting = self.avail()
        if waiting > 0:
            (count, data) = self.read(waiting)
            self._log(data, "DISC")

    def close(self):
        """close port and log file"""
        self.ser.close()
        self.ser = None

        if self.logf:
            self.logf.write("\nbytes read: {} bytes writen: {}".format(
                self.read_count, self.write_count))

    def dtr_active(self, state):
        """set state of DTR line"""
        self.ser.dtr = state
        self._log(b'high' if state else b'low', "ADTR")

    def pulse_dtr(self, duration: float=0.001):
        """pulse DTR line duration in seconds"""
        self.ser.dtr = True
        time.sleep(duration / 1000.0)
        self.ser.dtr = False

        self._log(bytes("{0}".format(duration), 'utf-8'), "PDTR")

    def pulse_rts(self, duration: float=0.001):
        """pulse DTR line duration in seconds.  Autodetects polarity"""
        init_state = self.ser.rts
        self.ser.rts = not init_state
        time.sleep(duration)
        self.ser.rts = init_state

        self._log(bytes("{0}".format(duration), 'utf-8'), "PRTS")

    def pulse_break(self, duration):
        """send a break"""
        self.ser.send_break(duration / 1000.0)

        self._log(bytes("{0}".format(duration), 'utf-8'), "PBRK")

    def _log(self, data: bytes, desc: str):
        """write a log string"""
        if self.logf:
            self.logf.write("%8.3f %4s %3d : " %
                            (time.time() - self.time0, desc, len(data)))
            for n, c in enumerate(data):
                if ord(' ') <= c <= ord('~'):
                    self.logf.write("%02x[%s] " % (c, chr(c)))
                else:
                    self.logf.write("%02x[ ] " % c)

                if (n + 1) % 16 == 0:
                    self.logf.write("\n                  : ")

            self.logf.write("\n")

            avail = self.avail()
            if avail > 0:
                self.logf.write("%8.3f INBF %3d\n" % (0, avail))

