#!/usr/bin/python2
"""Emulate installation that fails (i.e. failed flash to device)"""

from __future__ import print_function

import sys


def Main():
  return 1  ## False, flashing failure


if __name__ == '__main__':
  retval = Main()
  sys.exit(retval)
