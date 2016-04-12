#!/usr/bin/python

import logging
import struct
import time

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
    return self

  def __exit__(self, exc_type, exc_value, exc_traceback):
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
    response = [struct.unpack('B', b) for b in buf]
    self._logger.debug('<< %s' % response)
    return [t[0] for t in response]

  def echo(self, c):
    if not isinstance(c, str) or len(c) != 1:
      raise ValueError('Argument must be a string of length 1')
    response = self._command(c)
    return chr(response[0])

  def get_version(self):
    response = self._command('V')
    return '%d.%d' % (response[0], response[1])

  def get_model(self):
    response = self._command('m')
    return response[0]

  def set_tracking_mode(self, mode):
    self._command('T' + chr(mode))

  def set_tracking_off(self):
    return self.set_tracking_mode(0)

  def _get(self, command):
    response = self._command(command, 10)
    response_s = ''.join(map(chr, response))
    self._logger.debug('ALT/AZ << %s' % response_s)
    s2v = lambda s: int(s, 16) / 65536.0 * COEFF
    x, y = map(s2v, response_s[:-1].split(','))
    return x, y

  def _set(self, command, x, y):
    v2s = lambda v: '%X' % int(v * 65536.0 / COEFF)
    command = 'R%s,%s' % (v2s(x), v2s(y))
    self._logger.debug('ALT/AZ >> %s' % command)
    response = self._command(command, 1)

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
    return chr(response[0]) != '0'

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



if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO)
  with Mount(port='/dev/ttyUSB0', logger=logging) as mount:
    print('Protocol: %s' % mount.get_version())
    print('Model: %s' % mount.get_model())
    print(
      'RA: %s, DEC: %s' % tuple(map(deg2str, mount.get_ra_dec())))
    mount.goto_ra_dec_sync(270, 35.0)
    print(
      'RA: %s, DEC: %s' % tuple(map(deg2str, mount.get_ra_dec())))
