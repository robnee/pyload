"""Serial port comm routines

$Id: comm.py 817 2018-02-20 03:33:56Z rnee $
"""

import time


class Comm:
    """Serial port wrapper that supports logginga and mocking"""
    def __init__(self, ser, logf=None):
        self.ser = ser
        self.logf = logf

        # print('timeout', ser.timeout)
        # print('xonxoff', ser.xonxoff)
        # print('rtscts', ser.rtscts)
        # print('dsrdtr', ser.dsrdtr)

        self.read_count = 0
        self.write_count = 0

    def read(self, request=None):
        """ read a requested number of bytes.  If request is missing or zero read available """
        if not request:
            request = self.avail()

        data = self.ser.read(request)
        total = len(data)

        self.read_count += total

        if total > 0:
            self._log(data, "READ")

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

    def pulse_dtr(self, duration):
        """pulse DTR line"""
        self.ser.dtr = True
        time.sleep(duration / 1000.0)
        self.ser.dtr = False

        self._log(bytes("{0}".format(duration), 'utf-8'), "PDTR")

    def pulse_break(self, duration):
        """send a break"""
        self.ser.send_break(duration / 1000.0)

        self._log(bytes("{0}".format(duration), 'utf-8'), "PBRK")

    def _log(self, data, desc):
        """write a log string"""
        if self.logf:
            self.logf.write("%8.3f %s %3d : " % (0, desc, len(data)))
            for c in data:
                if ord(' ') <= c <= ord('~'):
                    self.logf.write("%02x[%s] " % (c, chr(c)))
                else:
                    self.logf.write("%02x " % c)

            self.logf.write("\n")


