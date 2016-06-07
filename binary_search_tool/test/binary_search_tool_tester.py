#!/usr/bin/python2

# Copyright 2012 Google Inc. All Rights Reserved.
"""Tests for bisecting tool."""

from __future__ import print_function

__author__ = 'shenhan@google.com (Han Shen)'

import os
import random
import sys
import unittest

from utils import command_executer
from binary_search_tool import binary_search_state

import common
import gen_obj


class BisectingUtilsTest(unittest.TestCase):
  """Tests for bisecting tool."""

  def setUp(self):
    """Generate [100-1000] object files, and 1-5% of which are bad ones."""
    obj_num = random.randint(100, 1000)
    bad_obj_num = random.randint(obj_num / 100, obj_num / 20)
    if bad_obj_num == 0:
      bad_obj_num = 1
    gen_obj.Main(['--obj_num', str(obj_num), '--bad_obj_num', str(bad_obj_num)])

  def tearDown(self):
    """Cleanup temp files."""
    os.remove(common.OBJECTS_FILE)
    os.remove(common.WORKING_SET_FILE)
    print('Deleted "{0}" and "{1}"'.format(common.OBJECTS_FILE,
                                           common.WORKING_SET_FILE))

  def runTest(self):
    args = ['--get_initial_items', './gen_init_list.py', '--switch_to_good',
            './switch_to_good.py', '--switch_to_bad', './switch_to_bad.py',
            '--test_script', './is_good.py', '--prune', '--file_args']
    binary_search_state.Main(args)
    self.check_output()

  def test_install_script(self):
    args = ['--get_initial_items', './gen_init_list.py', '--switch_to_good',
            './switch_to_good.py', '--switch_to_bad', './switch_to_bad.py',
            '--test_script', './is_good.py', '--prune', '--file_args',
            '--install_script', './install.py']
    common.installed = False
    binary_search_state.Main(args)
    self.check_output()

  def test_bad_install_script(self):
    args = ['--get_initial_items', './gen_init_list.py', '--switch_to_good',
            './switch_to_good.py', '--switch_to_bad', './switch_to_bad.py',
            '--test_script', './is_good.py', '--prune', '--file_args',
            '--install_script', './install_bad.py']
    with self.assertRaises(AssertionError):
      binary_search_state.Main(args)

  def check_output(self):
    _, out, _ = command_executer.GetCommandExecuter().RunCommandWOutput(
        'tail -n 10 logs/binary_search_state.py.out')
    ls = out.splitlines()
    for l in ls:
      t = l.find('Bad items are: ')
      if t > 0:
        bad_ones = l[(t + len('Bad items are: ')):].split()
        objects_file = common.ReadObjectsFile()
        for b in bad_ones:
          self.assertEqual(objects_file[int(b)], 1)


def Main(argv):
  num_tests = 2
  if len(argv) > 1:
    num_tests = int(argv[1])

  suite = unittest.TestSuite()
  for _ in range(0, num_tests):
    suite.addTest(BisectingUtilsTest())
  suite.addTest(BisectingUtilsTest('test_install_script'))
  suite.addTest(BisectingUtilsTest('test_bad_install_script'))
  runner = unittest.TextTestRunner()
  runner.run(suite)


if __name__ == '__main__':
  Main(sys.argv)
