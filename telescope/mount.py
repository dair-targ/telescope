#!/usr/bin/python

from __future__ import print_function
from __future__ import print_function
import logging.config
import struct
import time

from astropy import units
from astropy import coordinates

import config
import serial


class Mount(object):
    def __init__(
            self,
            port,
            logger,
    ):
        """
        :type port: str
        :type logger: logging.Logger
        """
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
        self.cancel_goto_sync()
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

    def goto(self, sky_coord):
        """
        :type sky_coord: coordinates.SkyCoord
        """
        self._logger.info('Going to %s', sky_coord.to_string('hmsdms'))
        v2s = lambda v: '%04X' % int(v * 65536.0)
        self._command('R%s,%s' % (
            v2s(sky_coord.ra.cycle + 0.5),
            v2s(sky_coord.dec.cycle + 0.25)
        ), 1)

    def goto_sync(self, sky_coord, timeout=30.0):
        """
        :type sky_coord: coordinates.SkyCoord
        :type timeout:
        """
        self.goto(sky_coord)
        self._wait_goto(timeout)

    def get_coord(self):
        """
        :rtype: coordinates.SkyCoord
        """
        response = self._command('E', 10)
        s2v = lambda s: int(s, 16) / 65536.0
        ra, dec = map(s2v, response[:-1].split(','))
        return coordinates.SkyCoord(
            ra=(ra - 0.5) * units.cycle,
            dec=(dec - 0.25) * units.cycle,
        )

    def is_goto_in_progress(self):
        response = self._command('L')
        return response[0] != '0'

    def cancel_goto(self):
        if self.is_goto_in_progress():
            self._logger.info('GOTO is already canceled')
        else:
            self._logger.info('Canceling GOTO')
            self._command('M', 1)

    def cancel_goto_sync(self):
        self.cancel_goto()
        self._wait_goto()

    def _wait_goto(self, timeout=30.0, step=0.1):
        self._logger.info('Waiting while GOTO in progress...')
        spent = 0.0
        while self.is_goto_in_progress() and spent < timeout:
            time.sleep(step)
            spent += step
            logging.info(
                'Position after %.2fs is %s',
                spent,
                mount.get_coord().to_string('hmsdms')
            )
        self._logger.info('GOTO completed in %.1f seconds', spent)
        return spent


def find_bounds(mount):
    """
    Looks up for actual area mount can go

    :type Mount
    """
    initial_coord = mount.get_coord()
    def search(initial_coord, step):
        """
        :type initial_coord: coordinates.SkyCoord
        :type step: coordinates.SkyCoord
        """
        logging.info('Initial coord: %s' % initial_coord.to_string('hmsdms'))
        expected_coord = actual_coord = initial_coord
        while expected_coord.separation(actual_coord) < 5.0 * units.degree:
            expected_coord = coordinates.SkyCoord(
                ra=expected_coord.ra + step.ra,
                dec=expected_coord.dec + step.dec,
            )
            logging.info('Expected coord: %s' % expected_coord.to_string('hmsdms'))
            mount.goto_sync(expected_coord)
            actual_coord = mount.get_coord()
            logging.info('Actual coord: %s' % actual_coord.to_string('hmsdms'))
        logging.info('Max dec is reached at %s' % actual_coord.to_string('hmsdms'))
        return expected_coord
    top = search(initial_coord, coordinates.SkyCoord(
        ra=0.0 * units.degree,
        dec=10.0 * units.degree,
    ))
    bottom = search(initial_coord, coordinates.SkyCoord(
        ra=0.0 * units.degree,
        dec=-10.0 * units.degree,
    ))
    left = search(initial_coord, coordinates.SkyCoord(
        ra=10.0 * units.degree,
        dec=0.0 * units.degree,
    ))
    right = search(initial_coord, coordinates.SkyCoord(
        ra=-10.0 * units.degree,
        dec=0.0 * units.degree,
    ))
    return top, bottom, left, right


def test_goto(expected_coord, allowed_error):
    """
    :type expected_coord: coordinates.SkyCoord
    """
    logging.info('Testing goto to %s', expected_coord.to_string('hmsdms'))
    try:
        mount.goto_sync(coordinates.SkyCoord(ra=0.0 * units.degree, dec=0.0 * units.degree))
        logging.info('Initial position: %s', mount.get_coord().to_string('hmsdms'))
        mount.goto_sync(expected_coord)
        actual_coord = mount.get_coord()
        separation = expected_coord.separation(actual_coord)
        if separation > allowed_error:
            logging.error('Separation (%s) is greater than allowed error(%s)' % (
                separation,
                allowed_error
            ))
        else:
            logging.info(
                'Separation (%s) is less than allowed error(%s)' % (
                    separation,
                    allowed_error
                ))
    finally:
        logging.info('Position after goto: %s', mount.get_coord().to_string('hmsdms'))


if __name__ == '__main__':
    logging.config.dictConfig(config.LOGGING)
    with Mount(
            port='/dev/ttyUSB0',
            logger=logging
    ) as mount:
        logging.info(mount.get_coord().to_string('hmsdms'))
        # test_goto()
        # logging.info('Result:\n%s' % '\n'.join([sc.to_string('hmsdms') for sc in find_bounds(mount)]))
        for sky_coord in [
            coordinates.SkyCoord(ra=0.0 * units.degree, dec=0.0 * units.degree),
            coordinates.SkyCoord(ra=0.0 * units.degree, dec=89.0 * units.degree),
            coordinates.SkyCoord(ra=0.0 * units.degree, dec=-89.0 * units.degree),
            coordinates.SkyCoord(ra=179.0 * units.degree, dec=0.0 * units.degree),
            coordinates.SkyCoord(ra=-179.0 * units.degree, dec=0.0 * units.degree),
            coordinates.SkyCoord(ra=0.0 * units.degree, dec=0.0 * units.degree),
        ]:
            test_goto(sky_coord, 1.0 * units.degree)
