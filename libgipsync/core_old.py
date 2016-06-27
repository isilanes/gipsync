import os
import datetime
import subprocess as sp

def fitit(path, limit=None):
    """Make a given string (path) fit in the screen width."""

    # If not explicitly given, make "limit" be actual terminal width:
    if not limit:
        cmnd  = "stty size | awk '{print $2 - 13}'"
        s = sp.Popen(cmnd,stdout=sp.PIPE,shell=True)
        limit = s.communicate()[0]
        try:
            limit = int(limit)
        except:
            limit = 80

    if len(path) < limit:
        return path

    parts = os.path.split(path)

    newpath = parts[1]

    limit = limit - len(newpath) - 3

    if limit < 1:
        return path

    npath = parts[0]
    while len(npath) > limit:
      nparts = os.path.split(npath)
      tail   = nparts[1]
      if len(tail) > 3:
          tail = tail[0]+'..'
      
      newpath = os.path.join(tail,newpath)
      npath = nparts[0]
      limit = limit - 3

      if not npath:
          break

    return os.path.join(nparts[0],newpath)

def bytes2size(bytes):
    """Get a number of bytes, and return in human-friendly form (kB, MB, etc)."""

    units = ['B', 'kB', 'MB', 'GB']
    
    i = 0
    sz = bytes
    while sz > 1024:
        sz = sz/1024.0
        i  += 1

    return '%.2f %s' % (sz, units[i])

def s2hms(seconds):
    """Take an amount of seconds (or a timedelta object), and return in HH:MM:SS format."""

    # Create output string, and return:
    hh = int(seconds/3600.0)
    mm = int((seconds - 3600*hh)/60.0)
    ss = int(seconds - 3600*hh - 60*mm)

    string = '{0:02}:{1:02}:{2:02}'.format(hh,mm,ss)

    return string

def get_present_files(server, dir, files):
    """Returns a list of which files of the list "files" is present in directory "dir", in server "server"."""

    # Build a script to use SFTP to do what we need to do:
    string  = 'sftp {0} <<EOF\n'.format(server)
    string += 'cd {0}/data\n'.format(dir)

    for file in files:
        string += 'ls {0}.gpg\n'.format(file)

    string += 'EOF\n'

    tmpf = 'check.sftp'
    with open(tmpf,'w') as f:
        f.write(string)

    # Use script and get output:
    cmnd = 'bash {0}'.format(tmpf)
    s = sp.Popen(cmnd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
    out = s.communicate()[0].decode('utf-8')

    # Extract present files from output:
    present = []
    for line in out.split('\n'):
        for file in files:
            if file in line and not 'ls '+file in line:
                present.append(file)

    # Clean up:
    os.unlink(tmpf)

    return present

def message(which, what, cfg):
    if which == 'repo':
        fmt = "\nRepository: \033[34m{0}\033[0m @ \033[34m{1}\033[0m"
        string = fmt.format(what, cfg.conf['LOCALDIR'])
        say(string)

def e2d(epoch=0):
    """Takes a date in seconds since epoch, and returns YYYY-MM-DD HH:MM:SS format."""

    date = datetime.datetime.fromtimestamp(epoch)

    return date.strftime('%Y-%m-%d %H:%M:%S')

