import select
import subprocess
import sys
import os
import logger

command_executer = None


def InitCommandExecuter(mock=False):
  global command_executer
  if mock:
    command_executer = MockCommandExecuter()
  else:
    command_executer = CommandExecuter()


def GetCommandExecuter():
  if command_executer is None:
    InitCommandExecuter()
  return command_executer


class CommandExecuter:
  def __init__(self):
    self.logger = logger.GetLogger()

  def RunCommand(self, cmd, return_output=False, machine=None,
                 username=None, command_terminator=None):
    """Run a command."""

    self.logger.Logcmd(cmd, machine, username)
    if command_terminator and command_terminator.IsTerminated():
      self.logger.LogError("Command was terminated!")
      return 1

    if machine is not None:
      user = ""
      if username is not None:
        user = username + "@"
      cmd = "ssh %s%s -- bash <<\EOF\n%s\nEOF" % (user, machine, cmd)

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, stdin=sys.stdin, shell=True)

    full_stdout = ""
    full_stderr = ""

    # Pull output from pipes, send it to file/stdout/string
    out = err = None
    while True:
      fds = select.select([p.stdout, p.stderr], [], [], 0.1)
      if command_terminator and command_terminator.IsTerminated():
        p.kill()
        p.stdout.close()
        p.stderr.close()
        wait = p.wait()
        self.logger.LogError("Command was terminated!")
        return wait
      for fd in fds[0]:
        if fd == p.stdout:
          out = os.read(p.stdout.fileno(), 4096)
          if return_output:
            full_stdout += out
          self.logger.LogCommandOutput(out)
        if fd == p.stderr:
          err = os.read(p.stderr.fileno(), 4096)
          if return_output:
            full_stderr += err
          self.logger.LogCommandError(err)

      if out == err == "":
        break

    p.wait()
    if return_output:
      return (p.returncode, full_stdout, full_stderr)
    return p.returncode

  def RunCommands(self, cmdlist, return_output=False, machine=None,
                  username=None, command_terminator=None):
    cmd = " ;\n" .join(cmdlist)
    return self.RunCommand(cmd, return_output, machine, username,
                           command_terminator)

  def CopyFiles(self, src, dest, src_machine, dest_machine,
                src_user=None, dest_user=None, recursive=True,
                command_terminator=None):
    if src_user is None:
      src_user = ""
    else:
      src_user = src_user + "@"
    if dest_user is None:
      dest_user = ""
    else:
      dest_user = dest_user + "@"
    recurse = ""
    if recursive:
      recurse = "-r"
    return self.RunCommand("sudo scp %s %s%s:%s %s%s:%s"
                           % (recurse, src_user, src_machine, src,
                              dest_user, dest_machine, dest),
                           command_terminator=command_terminator)


class MockCommandExecuter(CommandExecuter):
  def __init__(self):
    self.logger = logger.GetLogger()

  def RunCommand(self, cmd, return_output=False, machine=None, username=None):
    if machine is None:
      machine = "localhost"
    if username is None:
      username = "current"
    logger.GetLogger().Logcmd("(Mock)" + cmd, machine, username)
    return 0


class CommandTerminator:
  def __init__(self):
    self.terminated = False

  def Terminate(self):
    self.terminated = True

  def IsTerminated(self):
    return self.terminated
