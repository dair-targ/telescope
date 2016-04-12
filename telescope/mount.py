#!/usr/bin/python

import logging
import struct
import time
import unittest
import serial

COEFF = 360.0


def deg2str(v):
    dd = int(abs(v))
    mm = int(abs(v) * 60) % 60
    ss = int(abs(v) * 3600) % 60
    return '%s%sd%sm%ss' % (
        ('-' if v < 0 else ''),
        dd,
        mm,
        ss
    )


class Mount(object):
    def __init__(self, port, logger):
        self._logger = logger
        self._port = serial.Serial(
            port=port,
            baudrate=9600,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=100,
            write_timeout=100
        )

    def __enter__(self):
        if not self._port.isOpen():
            self._port.open()
        return self

    def __exit__(self, *args):
        self.cancel_goto_sync()
        self.set_tracking_off()
        self._port.close()

    def _command(self, command, rsize=None):
        command = ''.join([
                              chr(c) if isinstance(c, int) else str(c)
                              for c in command
                              ])
        self._logger.debug('>> %s' % command)
        self._port.write(command)
        if rsize is None:
            buf = []
            while True:
                c = self._port.read(size=1)
                buf.append(c)
                if c == '#':
                    break
        else:
            buf = self._port.read(size=rsize)
        response = str(''.join(chr(struct.unpack('B', b)[0]) for b in buf))
        self._logger.debug('<< %s' % response)
        return response

    def echo(self, c):
        if not isinstance(c, str) or len(c) != 1:
            raise ValueError('Argument must be a string of length 1')
        response = self._command('K' + c)
        return response[0]

    def get_version(self):
        response = self._command('V')
        return '%d.%d' % tuple(map(ord, response[:2]))

    def get_model(self):
        response = self._command('m')
        return ord(response[0])

    def set_tracking_mode(self, mode):
        self._command('T' + chr(mode))

    def set_tracking_off(self):
        return self.set_tracking_mode(0)

    def _get(self, command):
        response = self._command(command, 10)
        s2v = lambda s: int(s, 16) / 65536.0 * COEFF
        x, y = map(s2v, response[:-1].split(','))
        return x, y

    def _set(self, c, x, y):
        v2s = lambda v: '%X' % int(v * 65536.0 / COEFF)
        command = '%s%s,%s' % (c, v2s(x), v2s(y))
        self._command(command, 1)

    def get_ra_dec(self):
        return self._get('E')

    def goto_ra_dec(self, ra, dec):
        return self._set('R', ra, dec)

    def goto_ra_dec_sync(self, ra, dec):
        self.goto_ra_dec(ra, dec)
        self._wait_goto()

    def get_azm_alt(self):
        return self._get('Z')

    def goto_azm_alt(self, azm, alt):
        return self._set('B', azm, alt)

    def goto_azm_alt_sync(self, azm, alt):
        self.goto_azm_alt(azm, alt)
        self._wait_goto()

    def is_goto_in_progress(self):
        response = self._command('L')
        return response[0] != '0'

    def cancel_goto(self):
        self._command('M')

    def cancel_goto_sync(self):
        self.cancel_goto()
        self._wait_goto()

    def _wait_goto(self, timeout=30.0, step=0.1):
        spent = 0.0
        while self.is_goto_in_progress() and spent < timeout:
            time.sleep(step)
            spent += step
        return spent

    def _reset_az_alt(self, axis, value):
        self._logger.info('Reset %s to %s' % (axis, deg2str(value)))
        axis_b = dict(az=16, alt=17)[axis]
        value24 = int(2 ** 24 * (value / COEFF))
        vh = value24 / (2 ** 16) % 2 ** 8
        vm = value24 / (2 ** 8) % 2 ** 8
        vl = value24 / (2 ** 0) % 2 ** 8
        self._command([80, 4, axis_b, vh, vm, vl, 0])


def test_goto(mount, ra, dec, error):
    """
    :type mount: Mount
    """
    mount.goto_ra_dec_sync(ra, dec)
    actual_ra, actual_dec = mount.get_ra_dec()
    assert abs(actual_ra - ra) < error
    assert abs(actual_dec - dec) < error


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    with Mount(port='/dev/ttyUSB0', logger=logging) as mount:
        for ra, dec in [
            (270.0, 60.0),
            (243.0, 34.0),
            (120.0, 10.0)
        ]:
            test_goto(mount, ra, dec, 1.0)
