#!/usr/bin/python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Script to build the ChromeOS toolchain.

This script sets up the toolchain if you give it the gcctools directory.
"""

__author__ = "asharif@google.com (Ahmad Sharif)"

import getpass
import optparse
import os
import sys
import tempfile

import tc_enter_chroot
from utils import command_executer
from utils import constants
from utils import misc


class ToolchainPart(object):
  def __init__(self, name, source_path, chromeos_root, board, incremental,
               build_env):
    self._name = name
    self._source_path = misc.CanonicalizePath(source_path)
    self._chromeos_root = chromeos_root
    self._board = board
    self._ctarget = misc.GetCtargetFromBoard(self._board,
                                              self._chromeos_root)
    self.tag = "%s-%s" % (name, self._ctarget)
    self._ce = command_executer.GetCommandExecuter()
    self._mask_file = os.path.join(
        self._chromeos_root,
        "chroot",
        "etc/portage/package.mask/cross-%s" % self._ctarget)
    self._new_mask_file = None

    self._chroot_source_path = os.path.join(constants.mounted_toolchain_root,
                                            self._name).lstrip("/")
    self._incremental = incremental
    self._build_env = build_env

  def RunSetupBoardIfNecessary(self):
    cross_symlink = os.path.join(
        self._chromeos_root,
        "chroot",
        "usr/local/bin/emerge-%s" % self._board)
    if not os.path.exists(cross_symlink):
      command = "./setup_board --board=%s" % self._board
      self._ce.ChrootRunCommand(self._chromeos_root, command)

  def Build(self):
    rv = 1
    try:
      self.UninstallTool()
      self.MoveMaskFile()
      self.MountSources(False)
      self.RemoveCompiledFile()
      rv = self.BuildTool()
    finally:
      self.UnMoveMaskFile()
      return rv

  def RemoveCompiledFile(self):
    compiled_file = os.path.join(self._chromeos_root,
                                 "chroot",
                                 "var/tmp/portage/cross-%s" % self._ctarget,
                                 "%s-9999" % self._name,
                                 ".compiled")
    command = "rm -f %s" % compiled_file
    self._ce.RunCommand(command)

  def MountSources(self, unmount_source):
    mount_points = []
    mounted_source_path = os.path.join(self._chromeos_root,
                                       "chroot",
                                       self._chroot_source_path)
    src_mp = tc_enter_chroot.MountPoint(
        self._source_path,
        mounted_source_path,
        getpass.getuser(),
        "ro")
    mount_points.append(src_mp)

    build_suffix = "build-%s" % self._ctarget
    build_dir = "%s-%s" % (self._source_path, build_suffix)

    if not self._incremental and os.path.exists(build_dir):
      command = "rm -rf %s/*" % build_dir
      self._ce.RunCommand(command)

    # Create a -build directory for the objects.
    command = "mkdir -p %s" % build_dir
    self._ce.RunCommand(command)

    mounted_build_dir = os.path.join(
        self._chromeos_root, "chroot", "%s-%s" %
        (self._chroot_source_path, build_suffix))
    build_mp = tc_enter_chroot.MountPoint(
        build_dir,
        mounted_build_dir,
        getpass.getuser())
    mount_points.append(build_mp)

    if unmount_source:
      unmount_statuses = [mp.UnMount() == 0 for mp in mount_points]
      assert all(unmount_statuses), "Could not unmount all mount points!"
    else:
      mount_statuses = [mp.DoMount() == 0 for mp in mount_points]

      if not all(mount_statuses):
        mounted = [mp for mp, status in zip(mount_points, mount_statuses) if status]
        unmount_statuses = [mp.UnMount() == 0 for mp in mounted]
        assert all(unmount_statuses), "Could not unmount all mount points!"


  def UninstallTool(self):
    command = "sudo CLEAN_DELAY=0 emerge -C cross-%s/%s" % (self._ctarget, self._name)
    self._ce.ChrootRunCommand(self._chromeos_root, command)

  def BuildTool(self):
    env = self._build_env
    # FEATURES=buildpkg adds minutes of time so we disable it.
    # TODO(shenhan): keep '-sandbox' for a while for compatibility, then remove
    # it after a while.
    features = "nostrip userpriv userfetch -usersandbox -sandbox noclean -buildpkg"
    env["FEATURES"] = features

    if self._incremental:
      env["FEATURES"] += " keepwork"

    env["USE"] = "multislot mounted_%s" % self._name
    env["%s_SOURCE_PATH" % self._name.upper()] = (
        os.path.join("/", self._chroot_source_path))
    env["ACCEPT_KEYWORDS"] = "~*"
    env_string = " ".join(["%s=\"%s\"" % var for var in env.items()])
    command = "emerge =cross-%s/%s-9999" % (self._ctarget, self._name)
    full_command = "sudo %s %s" % (env_string, command)
    return self._ce.ChrootRunCommand(self._chromeos_root, full_command)

  def MoveMaskFile(self):
    self._new_mask_file = None
    if os.path.isfile(self._mask_file):
      self._new_mask_file = tempfile.mktemp()
      command = "sudo mv %s %s" % (self._mask_file, self._new_mask_file)
      self._ce.RunCommand(command)

  def UnMoveMaskFile(self):
    if self._new_mask_file:
      command = "sudo mv %s %s" % (self._new_mask_file, self._mask_file)
      self._ce.RunCommand(command)


def Main(argv):
  """The main function."""
  # Common initializations
  parser = optparse.OptionParser()
  parser.add_option("-c",
                    "--chromeos_root",
                    dest="chromeos_root",
                    default="../../",
                    help=("ChromeOS root checkout directory"
                          " uses ../.. if none given."))
  parser.add_option("-g",
                    "--gcc_dir",
                    dest="gcc_dir",
                    help="The directory where gcc resides.")
  parser.add_option("--binutils_dir",
                    dest="binutils_dir",
                    help="The directory where binutils resides.")
  parser.add_option("-x",
                    "--gdb_dir",
                    dest="gdb_dir",
                    help="The directory where gdb resides.")
  parser.add_option("-b",
                    "--board",
                    dest="board",
                    default="x86-agz",
                    help="The target board.")
  parser.add_option("-n",
                    "--noincremental",
                    dest="noincremental",
                    default=False,
                    action="store_true",
                    help="Use FEATURES=keepwork to do incremental builds.")
  parser.add_option("--cflags",
                    dest="cflags",
                    default="",
                    help="Build a compiler with specified CFLAGS")
  parser.add_option("--cxxflags",
                    dest="cxxflags",
                    default="",
                    help="Build a compiler with specified CXXFLAGS")
  parser.add_option("--ldflags",
                    dest="ldflags",
                    default="",
                    help="Build a compiler with specified LDFLAGS")
  parser.add_option("-d",
                    "--debug",
                    dest="debug",
                    default=False,
                    action="store_true",
                    help="Build a compiler with -g3 -O0 appended to both"
                    " CFLAGS and CXXFLAGS.")
  parser.add_option("-m",
                    "--mount_only",
                    dest="mount_only",
                    default=False,
                    action="store_true",
                    help="Just mount the tool directories.")
  parser.add_option("-u",
                    "--unmount_only",
                    dest="unmount_only",
                    default=False,
                    action="store_true",
                    help="Just unmount the tool directories.")


  options, _ = parser.parse_args(argv)

  chromeos_root = misc.CanonicalizePath(options.chromeos_root)
  if options.gcc_dir:
    gcc_dir = misc.CanonicalizePath(options.gcc_dir)
  if options.binutils_dir:
    binutils_dir = misc.CanonicalizePath(options.binutils_dir)
  if options.gdb_dir:
    gdb_dir = misc.CanonicalizePath(options.gdb_dir)
  if options.unmount_only:
    options.mount_only = False
  elif options.mount_only:
    options.unmount_only = False
  build_env = {}
  if options.cflags:
    build_env["CFLAGS"] = options.cflags
  if options.cxxflags:
    build_env["CXXFLAGS"] = options.cxxflags
  if options.cxxflags:
    build_env["LDFLAGS"] = options.ldflags
  if options.debug:
    debug_flags = "-g3 -O0"
    if "CFLAGS" in build_env:
      build_env["CFLAGS"] += " %s" % (debug_flags)
    else:
      build_env["CFLAGS"] = debug_flags
    if "CXXFLAGS" in build_env:
      build_env["CXXFLAGS"] += " %s" % (debug_flags)
    else:
      build_env["CXXFLAGS"] = debug_flags

  # Create toolchain parts
  toolchain_parts = {}
  for board in options.board.split(","):
    if options.gcc_dir:
      tp = ToolchainPart("gcc", gcc_dir, chromeos_root, board,
                         not options.noincremental, build_env)
      toolchain_parts[tp.tag] = tp
      tp.RunSetupBoardIfNecessary()
    if options.binutils_dir:
      tp = ToolchainPart("binutils", binutils_dir, chromeos_root, board,
                         not options.noincremental, build_env)
      toolchain_parts[tp.tag] = tp
      tp.RunSetupBoardIfNecessary()
    if options.gdb_dir:
      tp = ToolchainPart("gdb", gdb_dir, chromeos_root, board,
                         not options.noincremental, build_env)
      toolchain_parts[tp.tag] = tp
      tp.RunSetupBoardIfNecessary()

  rv = 0
  try:
    for tag in toolchain_parts:
      tp = toolchain_parts[tag]
      if options.mount_only or options.unmount_only:
        tp.MountSources(options.unmount_only)
      else:
        rv = rv + tp.Build()
  finally:
    print "Exiting..."
    return rv

if __name__ == "__main__":
  retval = Main(sys.argv)
  sys.exit(retval)
