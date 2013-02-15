#!/usr/bin/python2.6
#
# Copyright 2010 Google Inc. All Rights Reserved.

__author__ = "asharif@google.com (Ahmad Sharif)"

import getpass
import optparse
import os
import re
import socket
import sys
import tempfile
from utils import command_executer
from utils import logger
from utils import utils


class Repo:
  def __init__(self):
    self.repo_type = None
    self.address = None
    self.mappings = None
    self.revision = None
    self.ignores = []
    self.ignores.append(".gitignore")
    self.ignores.append(".p4config")
    self.ignores.append("README.google")


  def PullSources(self, root_dir):
    pass


  def __str__(self):
    r = str(self.repo_type) + "\n"
    r += str(self.address) + "\n"
    r += str(self.mappings) + "\n"
    return r


class P4Repo(Repo):
  def __init__(self, address, mappings):
    Repo.__init__(self)
    self.repo_type = "p4"
    self.address = address
    self.mappings = mappings


  def PullSources(self, root_dir):
    ce = command_executer.GetCommandExecuter()

    client_name = socket.gethostname()
    client_name += tempfile.mkstemp()[1].replace("/", "-")
    mappings = self.mappings
    port = self.address
    checkout_dir = root_dir
    command = utils.GetP4SetupCommand(client_name, port, mappings, checkout_dir=checkout_dir)
    command += "&& %s" % utils.GetP4SyncCommand()
    ce.RunCommand(command)
    command = utils.GetP4VersionCommand(client_name, checkout_dir)
    [r, o, e] = ce.RunCommand(command, return_output=True)
    self.revision = o.strip()
    command = utils.GetP4DeleteCommand(client_name)
    ce.RunCommand(command)


class SvnRepo(Repo):
  def __init__(self, address, mappings):
    Repo.__init__(self)
    self.repo_type = "svn"
    self.address = address
    self.mappings = mappings


  def PullSources(self, root_dir):
    ce = command_executer.GetCommandExecuter()

    command = "mkdir -p %s && cd %s" % (root_dir, root_dir)
    for mapping in self.mappings:
      if " " in mapping:
        [remote_path, local_path] = mapping.split()
      else:
        local_path = "."
        remote_path = mapping
      command += "&& svn co %s/%s %s" % (self.address, remote_path, local_path)
    ce.RunCommand(command)

    command = "cd %s" % (root_dir)
    self.revision = ""
    for mapping in self.mappings:
      if " " in mapping:
        [remote_path, local_path] = mapping.split()
      else:
        local_path = "."
        remote_path = mapping
      command += "&& cd %s && svnversion ." % (local_path)
      [r, o, e] = ce.RunCommand(command, return_output=True)
      self.revision += o.strip()


class GitRepo(Repo):
  def __init__(self, address, branch, ignores=None):
    Repo.__init__(self)
    self.repo_type = "git"
    self.address = address
    if not branch:
      self.branch = "master"
    else:
      self.branch = branch
    if ignores:
      self.ignores += ignores


  def SetupForPush(self, root_dir):
    ce = command_executer.GetCommandExecuter()
    command = "mkdir -p %s && cd %s" % (root_dir, root_dir)
    command += "&& git clone -v %s ." % self.address
    retval = ce.RunCommand(command)
    logger.GetLogger().LogFatalIf(retval, "Could not clone git repo %s." %
                                  self.address)

    command = "cd %s" % root_dir
    command += "&& git branch -a | grep -wq %s" % self.branch
    retval = ce.RunCommand(command)

    command = "cd %s" % root_dir
    if retval == 0:
      command += "&& git branch --track %s remotes/origin/%s" % (self.branch, self.branch)
      command += "&& git checkout %s" % self.branch
    else:
      command += "&& git symbolic-ref HEAD refs/heads/%s" % self.branch
    command += "&& rm -rf *"
    ce.RunCommand(command)


  def PushSources(self, root_dir, commit_message, dry_run=False):
    ce = command_executer.GetCommandExecuter()
    push_args = ""
    if dry_run:
      push_args += " -n "

    command = "cd %s" % (root_dir)
    if self.ignores:
      for ignore in self.ignores:
        command += "&& echo \"%s\" >> .gitignore" % ignore
    command += "&& git add -Av ."
    command += "&& git commit -v -m \"%s\"" % commit_message
    command += "&& git push -v %s origin %s:%s" % (push_args, self.branch, self.branch)
    ce.RunCommand(command)


class RepoReader():
  def __init__(self, filename):
    self.filename = filename
    self.main_dict = {}
    self.input_repos = []
    self.output_repos = []


  def ParseFile(self):
    f = open(self.filename)
    self.main_dict = eval(f.read())
    self.CreateReposFromDict(self.main_dict)
    f.close()
    return [self.input_repos, self.output_repos]


  def CreateReposFromDict(self, main_dict):
    for key, val in main_dict.items():
      repo_list = val
      for repo_dict in repo_list:
        repo = self.CreateRepoFromDict(repo_dict)
        if key == "input":
          self.input_repos.append(repo)
        elif key == "output":
          self.output_repos.append(repo)
        else:
          logger.GetLogger().LogFatal("Unknown key: %s found" % key)


  def GetDictValue(self, dictionary, key):
    if key in dictionary:
      return dictionary[key]
    else:
      return None


  def CreateRepoFromDict(self, repo_dict):
    repo_type = self.GetDictValue(repo_dict, "type")
    repo_address = self.GetDictValue(repo_dict, "address")
    repo_mappings = self.GetDictValue(repo_dict, "mappings")
    repo_ignores = self.GetDictValue(repo_dict, "ignores")
    repo_branch = self.GetDictValue(repo_dict, "branch")

    if repo_type == "p4":
      repo = P4Repo(repo_address,
                    repo_mappings)
    elif repo_type == "svn":
      repo = SvnRepo(repo_address,
                     repo_mappings)
    elif repo_type == "git":
      repo = GitRepo(repo_address,
                     repo_branch,
                     ignores=repo_ignores)
    else:
      logger.GetLogger().LogFatal("Unknown repo type: %s" % repo_type)
    return repo


def Main(argv):
  root_dir = tempfile.mkdtemp()

  parser = optparse.OptionParser()
  parser.add_option("-i",
                    "--input_file",
                    dest="input_file",
                    help="The input file that contains repo descriptions.")

  parser.add_option("-n",
                    "--dry_run",
                    dest="dry_run",
                    action="store_true",
                    default=False,
                    help="Do a dry run of the push.")

  options = parser.parse_args(argv)[0]
  if not options.input_file:
    parser.print_help()
    return 1
  rr = RepoReader(options.input_file)
  [input_repos, output_repos] = rr.ParseFile()

  for output_repo in output_repos:
    output_repo.SetupForPush(root_dir)

  input_revisions = []
  for input_repo in input_repos:
    input_repo.PullSources(root_dir)
    input_revisions.append(input_repo.revision)

  commit_message = "Sync'd repos to: %s" % ",".join(input_revisions)
  for output_repo in output_repos:
    output_repo.PushSources(root_dir, commit_message, dry_run=options.dry_run)


if __name__ == "__main__":
  retval = Main(sys.argv)
  sys.exit(retval)
