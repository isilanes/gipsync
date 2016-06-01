import re
import os
import sys
import time
import json
import hashlib
import datetime
import argparse
import subprocess as sp

def read_args():
    """Parse command-line arguments and return options object."""
    parser = argparse.ArgumentParser()

    parser.add_argument('positional',
            nargs='+',
            help="Positional arguments")

    parser.add_argument("-u", "--up",
                      dest="up",
                      help="If set, upload files. Default: download.",
                      action="store_true",
                      default=False)

    parser.add_argument("-v", "--verbose",
                      dest="verbosity",
                      help="Increase verbosity level by 1 for each call of this option. Default: 0.",
                      action="count",
                      default=0)

    parser.add_argument("-s", "--safe",
                      help="Safe mode: do not delete any local or remote file, please. Default: unsafe.",
                      action="store_true",
                      default=False)

    parser.add_argument("-k", "--keep",
                      help="Do not delete the generated temporary dir. Default: delete after use.",
                      action="store_true",
                      default=False)

    parser.add_argument("-S", "--size-control",
                      dest='size_control',
                      help="Do NOT upload files, just pretend you did. Default: if true run, upload new and diff files.",
                      action="store_true",
                      default=False)

    parser.add_argument("-T", "--timing",
                      help="Measure elapsed time for different parts of the program, then show a summary in the end. Default: don't.",
                      action="store_true",
                      default=False)

    parser.add_argument("-d", "--delete",
                      help="Files will be deleted, starting from oldest, until DELETE megabytes are freed. Default: None",
                      type=float,
                      default=None)

    parser.add_argument("-c", "--sync",
                      help="Sync remote repo to local (e.g. to delete files). Default: False.",
                      action="store_true",
                      default=False)

    parser.add_argument("-f", "--force-hash",
                      help="Check hashes of local files (to check for updates), even if mtime has not changed with respect to log. Default: only calculate hashes of files with updated mtime.",
                      action="store_true",
                      default=False)

    parser.add_argument("-l", "--limit-bw",
                      help="Limit bandwidth usage to LIMIT kB/s. Default: no limit.",
                      metavar='LIMIT',
                      default=0)

    parser.add_argument("-F", "--fresh",
                      help="Do not try to recover from previous interupted run. Start afresh instead. Default: recover when available.",
                      action="store_true",
                      default=False)

    parser.add_argument("--update-equals",
                      help="If remote/local mtimes of a file coincide, but MD5s differ, update (upload local if -u, download remote otherwise. Default: Ignore (and warn about) such cases.",
                      action="store_true",
                      default=False)


    return parser.parse_args()

def collect_sizes(dir):
    """Collect the size of files in given dir.
    Return return sorted array of [ timestamp, filename, size ] elements. If path does not exist, return empty list."""

    sizes = []

    for path, dirs, files in os.walk(dir):
        if os.path.basename(path) == 'data':
            for file in files:
                fn = os.path.join(path, file)
                sz = os.path.getsize(fn)
                mt = os.path.getmtime(fn)
                sizes.append([ mt, fn, sz ])

    return sorted(sizes)

def since_epoch():
    """Return current time, in seconds since epoch format."""

    date = datetime.datetime.now()
    
    return time.mktime(date.timetuple())

def delete_asked(sizes, todelete):
    """Delete files from pivot dir, until "todelete" MB are deleted.
    Return True if so many files deleted, False if finished before deleting that many."""

    current_secs = since_epoch()
    tfiles = len(sizes)
    todelete = todelete*1024*1024 # MB to bytes

    idel, deleted = 0, 0
    while len(sizes):
        mtime, fn, sz = sizes.pop(0)
        
        idel += 1
        deleted += sz
        ago = (current_secs - mtime)/86400.0

        fmt = '{i:>4d}/{tot}  {fn:20}  {s:>10}  {d:>10}  {ago:>6.2f} d'
        string = fmt.format(i=idel, tot=tfiles, fn=os.path.basename(fn), s=bytes2size(sz), d=bytes2size(deleted), ago=ago)
        print(string)
        #os.unlink(fn)

        if deleted > todelete:
            return True

    return False

def perform_deletion(cfg, opts):
    # Get info:
    sizes = collect_sizes(cfg.prefs['PIVOTDIR'])

    # Delete up to freeing requestes size, starting from oldest files:
    todelete = opts.delete
    while True:
        returned = delete_asked(sizes, todelete)
        if returned:
            string = 'How many MBs do you want to delete?: '
            todelete = raw_input(string)
            if not todelete:
                break
            try:
                todelete = float(todelete)
            except:
                break
        else:
            break


def fitit(path,limit=None):
    """Make a given string (path) fit in the screen width."""

    # If not explicitly given, make "limit" be terminal width:
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
      npath   = nparts[0]
      limit   = limit - 3

      if not npath:
          break

    newpath = os.path.join(nparts[0],newpath)

    return newpath

def hashof(fn):
    """Calc hash function for file."""

    h = hashlib.md5()

    with open(fn,'rb') as f:
        while True:
            t = f.read(4096)
            if len(t) == 0:
                break
            h.update(t)
    
    return h.hexdigest()

def bytes2size(bytes):
    """Get a number of bytes, and return in human-friendly form (kB, MB, etc)."""

    units = ['B', 'kB', 'MB', 'GB']
    
    i = 0
    sz = bytes
    while sz > 1024:
        sz = sz/1024.0
        i  += 1

    return '%.2f %s' % (sz, units[i])

def find_exc(it, patts):
    """Return True if item "it" matches some pattern in "patts", False otherwise."""

    for patt in patts:
        if patt in it:
            return True

    return False

def say(string=None):
    """Print out a message."""

    if string:
        print('\033[1m%s\033[0m' % (string))

def conf2dic(fname,separator='='):
    """Read a configuration file and interpret its lines as "key=value" pairs, assigning them to a dict, and returning it.
       fname = file name of the configuration file to read."""
     
    cf = {}

    with open(fname) as f:
        for line in f:
            line = line.replace('\n','')
            if line and not line[0] == '#': # ignore blank lines and comments
                aline = line.split(separator)
                cf[aline[0]] = separator.join(aline[1:])

    return cf

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


class Configuration(object):
    """Class containing all info of configurations."""

    def __init__(self, basedir=None):
        self.basedir = basedir  # where config files are
        self.prefs = {} # global preferences
        self.conf = {}  # config of current repo

        # Default config dir, if not givem:
        if not self.basedir:
            self.basedir = os.path.join(os.environ['HOME'], '.gipsync')

        # Global config file name:
        self.global_fn = os.path.join(self.basedir, 'config.json')

    def read_prefs(self, fn=None):
        """Read the global preferences."""

        if not fn:
            fn = self.global_fn

        try:
            with open(fn) as f:
                self.prefs = json.load(f)
        except:
            print('Could not read global preferences at "{fn}"'.format(fn=fn))
            sys.exit()

    def read_conf(self, what=None):
        """Read the configuration for repo named "what" (both .conf and .excludes files)."""

        # Read .conf file for repo:
        jfn = '{0}.json'.format(what)
        cfile = os.path.join(self.basedir, jfn)
        try:
            with open(cfile) as f:
                self.conf = json.load(f)
        except:
            print('Could not read configuration of repo "{0}"'.format(what))
            sys.exit()

        # Some fixes:
        try:
            # Remove trailing slash from localdir path (if any):
            self.conf['LOCALDIR'] = re.sub('/$','',self.conf['LOCALDIR'])
        except:
            print('Could not find variable "LOCALDIR" in configuration')
            sys.exit()

    def check(self):
        """Check that essential configuration variables are set."""

        for var in [ 'REPODIR', 'LOCALDIR', 'EXCLUDES' ]:
            if not var in self.conf:
                fmt = 'Sorry, but variable "{0}" is not specified in conf file'
                string = fmt.format(var)
                sys.exit(string)

        for var in ['RECIPIENTS', 'REMOTE']:
            if not var in self.prefs:
                fmt = 'Sorry, but variable "{0}" is not specified in global config file'
                string = fmt.format(var)
                sys.exit(string)

