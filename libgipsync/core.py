import re
import os
import sys
import time
import json
import hashlib
import datetime
import argparse

def read_args():
    """Parse command-line arguments and return options object."""

    parser = argparse.ArgumentParser()

    parser.add_argument('positional',
            nargs='*',
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
        os.unlink(fn)

        if deleted > todelete:
            return True

    return False

def perform_deletion(cfg, opts):
    """Function to delete old files from remote repo."""

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

def say(string=None):
    """Print out a message."""

    if string:
        string = u'\033[1m{s}\033[0m'.format(s=string)
        print(string)

def string2dict(string, separator='='):
    """Interpret string as a series of lines where each line is a key=value pair.
    The character separating key from value will be "separator".
    Return resulting dictionary."""

    cf = {}

    for line in string.split("\n"):
        if line and not line[0] == '#': # ignore blank lines and comments
            aline = line.split(separator)
            cf[aline[0]] = separator.join(aline[1:])

    return cf

def conf2dict(fname, separator='='):
    """Read a configuration file and interpret its lines as "key=value" pairs, assigning them to a dict, and returning it.
       fname = file name of the configuration file to read."""

    with open(fname) as f:
        return string2dict(f.read(), separator)
     
def is_item_in_patterns(item, patts):
    """Return True if item "item" matches some pattern in "patts", False otherwise."""

    for patt in patts:
        if re.search(patt, item):
            return True

    return False

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


class Configuration(object):
    """Class containing all info of configurations."""

    def __init__(self, basedir=None):
        self.basedir = basedir # where config files are
        self._prefs = {} # global preferences
        self.conf = {} # config of current repo

        # Default config dir, if not givem:
        if not self.basedir:
            self.basedir = os.path.join(os.environ['HOME'], '.gipsync')

        # Global config file name:
        self.global_fn = os.path.join(self.basedir, 'config.json')

    def read_prefs(self, fn=None):
        """Read and return the global preferences."""

        if not fn:
            fn = self.global_fn

        try:
            with open(fn) as f:
                return json.load(f)
        except:
            print('Could not read global preferences at "{fn}"'.format(fn=fn))
            sys.exit()

    def read_conf(self, what):
        """Read the configuration for repo named "what"."""

        # Read .conf file for repo:
        jfn = '{w}.json'.format(w=what)
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
            self.conf['LOCALDIR'] = re.sub('/$','', self.conf['LOCALDIR'])
        except:
            pass

        # Whenever read, check:
        self.check_conf()

    def check_conf(self):
        """Check that essential configuration variables (particular to a repo) are set."""

        for var in [ 'REPODIR', 'LOCALDIR', 'EXCLUDES' ]:
            if not var in self.conf:
                string = 'Sorry, but variable "{v}" is not specified in conf file'.format(v=var)
                print(string)
                sys.exit()

    def check_prefs(self):
        """Check that essential (general) preference variables are set."""

        for var in ['RECIPIENTS', 'REMOTE']:
            if not var in self.prefs:
                string = 'Sorry, but variable "{v}" is not specified in global config file'.format(v=var)
                print(string)
                sys.exit()

    @property
    def prefs(self):
        """Return preferences if they have been read. Read and then return, if not."""

        if not self._prefs:
            self._prefs = self.read_prefs()
            self.check_prefs()

        return self._prefs

