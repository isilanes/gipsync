import re
import os
import sys
import time
import json
import shutil
import pickle
import hashlib
import datetime
import argparse
import subprocess as sp

# Functions:
def parse_args():
    """Parse command-line arguments."""
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

def collect_sizes(dir):
    """Collect the size of all data in remote repo (mounted locally by SSHFS)."""

    sizes = []

    for path, dirs, files in os.walk(dir):
        print(path)
        if os.path.basename(path) == 'data':
            for file in files:
                fn = os.path.join(path,file)
                sz = os.path.getsize(fn)
                mt = os.path.getmtime(fn)
                
                k = '%i.%s.%i' % (int(mt), fn, sz)
                sizes.append(k)
                sys.stdout.write('.') # "progress bar"
            print('')

    return sizes

def delete_asked(sizes,todelete):
    """Delete files from pivot dir, until given size is reached."""

    tn = now()
    tfiles = len(sizes)

    idel = 0
    deleted = 0
    while len(sizes):
        x = sizes.pop(0)
        xplit = x.split('.')
        datex = int(xplit[0])
        jfn = '.'.join(xplit[1:-1])
        fn = os.path.basename(jfn)
        sizex = int(xplit[-1])

        idel += 1
        deleted += sizex

        ago = (tn - datex)/86400.0

        fmt = '{0:>4d}/{1}  {2}  {3:>10}  {4:>10}  {5:>6.2f} d'
        print(fmt.format(idel, tfiles, fn, bytes2size(sizex), bytes2size(deleted), ago))
        os.unlink(jfn)

        if deleted > todelete:
            return True

def say(string=None):
    """Print out a message."""

    if string:
        print('\033[1m%s\033[0m' % (string))

def conf2dic(fname,separator='='):
    """Read a configuration file and interpret its lines as "key=value" pairs, assigning them
    to a dictionary, and returning it.
       fname = file name of the configuration file to read.
    """
    cf = {}

    with open(fname) as f:
        for line in f:
            line = line.replace('\n','')
            if line and not line[0] == '#': # ignore blank lines and comments
                aline = line.split(separator)
                cf[aline[0]] = separator.join(aline[1:])

    return cf

def now():
    """ Return current time, in seconds since epoch format."""

    date = datetime.datetime.now()
    
    return time.mktime(date.timetuple())

def s2hms(seconds):
    """Take an amount of seconds (or a timedelta object), and return 
    in HH:MM:SS format.
    """
    # Create output string, and return:
    hh = int(seconds/3600.0)
    mm = int((seconds - 3600*hh)/60.0)
    ss = int(seconds - 3600*hh - 60*mm)

    string = '{0:02}:{1:02}:{2:02}'.format(hh,mm,ss)

    return string

def get_present_files(server, dir, files):
    """Returns a list of which files of the list "files" is present in directory "dir",
    in server "server"."""

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
    """Takes a date in seconds since epoch, 
    and returns YYYY-MM-DD HH:MM:SS format.
    """
    date = datetime.datetime.fromtimestamp(epoch)

    return date.strftime('%Y-%m-%d %H:%M:%S')


# Classes:
class Timing(object):
      
    def __init__(self):
        self.t0         = now()
        self.milestones = []
        self.data       = {}

    def milestone(self,id=None):
        """Add a milestone to list. A milestone is just a point in time that 
        we record."""
        
        # ID of milestone:
        if not id:
            id = 'unk'
      
        # Avoid dupe IDs:
        while id in self.milestones:
            id += 'x'
      
        tnow = now()
        
        self.milestones.append(id)
        self.data[id] = { 'time' : tnow }

    def summary(self):
        """Print out a summary of timing so far."""
        
        otime = self.t0
        
        maxl = 9
        for milestone in self.milestones:
            l = len(milestone) + 1
            if l > maxl: maxl = l
            
        smry = '\n{0:>8} {1:>{3}} {2:>8}\n'.format('Time', 'Milestone', 'Elapsed', maxl)
        
        for milestone in self.milestones:
            t = self.data[milestone]['time']
            delta =  t - otime
            otime = t
            
            tt0 = s2hms(t - self.t0)
            dta = s2hms(delta)
            smry += '{0:>8} {1:>{3}} {2:>8}\n'.format(tt0, milestone, dta, maxl)
            
        print(smry)

class Configuration(object):
    """Class containing all info of configurations."""

    def __init__(self, dir=None):
        self.dir = dir  # where config files are
        self.prefs = {} # global preferences
        self.conf = {}  # config of current repo

        # Default config dir, if not givem:
        if not self.dir:
            self.dir = os.path.join(os.environ['HOME'], '.gipsync')

    def read_prefs(self):
        """ Read the global preferences."""

        fn = os.path.join(self.dir, 'config.json')
        try:
            with open(fn) as f:
                self.prefs = json.load(f)
        except:
            print('Could not read global preferences at "{0}"'.format(fn))
            sys.exit()

    def read_conf(self, what=None):
        """Read the configuration for repo named "what" (both .conf 
        and .excludes files)."""

        # Read .conf file for repo:
        jfn = '{0}.json'.format(what)
        cfile = os.path.join(self.dir, jfn)
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
        """ Check that essential configuration variables are set."""

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

class Repositories(object):
    """All the data about both local and remote repos."""
  
    def __init__(self, opts, cfg, what):
        self.files        = {}        # dict of filename/file object
        self.files_read   = {}        # dict of file names:true (to check pertenence)
        self.files_local  = {}        # dict of file names:true (to check pertenence)
        self.files_remote = {}        # dict of file names:true (to check pertenence)
        self.tmpdir       = None      # temporary directory
        self.gpgcom       = '/usr/bin/gpg --yes  -q' # command to encrypt/decrypt with GPG
        self.walked       = 0          # total considered files
        self.hashed       = 0          # total files for which hash was calculated
        self.diff         = RepoDiff() # difference between repos
        self.options      = opts       # optparse options
        self.done         = {}         # list of steps done
        self.cfg          = cfg        # Configuration object holding all config and prefs
        self.really_do = False
        self.tmpdir = os.path.join(self.cfg.dir, 'ongoing.{0}'.format(what))

        # Add bandwidth limit to rsync?:
        lim = int(self.options.limit_bw)
        if lim:
            self.rsync = 'rsync -rto --bwlimit={0}'.format(lim)
        else:
            self.rsync = 'rsync -rto'

        # Create tmp dir if necessary:
        try:
            os.makedirs(os.path.join(self.tmpdir, 'data'))
        except:
            pass # if it already exists
        
        # Make gpg more verbose?:
        if self.options.verbosity < 1:
            self.gpgcom += ' --no-tty '

    def read(self, fromfile):
        if os.path.isfile(fromfile):
            for k,v in conf2dic(fromfile,separator='|').items():
                self.files_read[k] = True
                
                av = v.split(':')
                
                if len(av) < 2:
                    msj = 'The length of dictionary entry "{0}={1}" is too short!'.format(k,v)
                    sys.exit(msj)
                if not k in self.files:
                    self.files[k] = Fileitem(name=k, repos=self)
                self.files_read[k] = True
                self.files[k].hash_read = av[0]
                self.files[k].size_read = float(av[1])
                self.files[k].mtime_read = float(av[2])
        else:
            msj = 'Can\'t read from non existint file "{0}"!'.format(fromfile)
            sys.exit(msj)

    def dict2files(self, dict, here=True):
        fi = {}

        for k,v in dict.items():
            av = v.split(':')
            
            if len(av) < 2:
                msj = 'The length of dictionary entry "{0}|{1}" is too short!'.format(k, v)
                sys.exit(msj)
            fi[k] = Fileitem(repos=self)
            fi[k].name = k
            
            if here:
                fi[k].hash_local  = av[0]
                fi[k].size_local  = float(av[1])
                fi[k].mtime_local = float(av[2])
                
            else:
                fi[k].hash_remote  = av[0]
                fi[k].size_remote  = float(av[1])
                fi[k].mtime_remote = float(av[2])
                
        return fi

    def walk(self):
        """Perform the acts upon each dir in the dir walk (get mtimes, MD5s, etc)."""
  
        pl = self.cfg.conf['LOCALDIR']
  
        for path, dirs, files in os.walk(pl):
            prs = path.replace(pl+'/','')
  
            # Ignore dif if excluded:
            if not find_exc(prs, self.cfg.conf['EXCLUDES']):
                for file in files:
                    self.walked += 1
      
                    fn = os.path.join(path, file)
      
                    # Ignore excluded files and symlinks (in ORs, check first
                    # the cheapest and most probable condition, to speed up):
                    if not os.path.islink(fn) and not find_exc(fn, self.cfg.conf['EXCLUDES']):
                        if path == pl: # current path is root path
                            fname = file
                        else: # it's a subdir of root
                            fname = '%s/%s' % (prs, file)
                        if not fname in self.files:
                            self.files[fname] = Fileitem(repos=self)
                        self.files[fname].name  = fname
                        self.files_local[fname] = True
                        
                        mt = int(os.path.getmtime(fn))
                        time_differ = False
                        
                        # Get file mtime:
                        try:
                            rmt = self.files[fname].mtime_read
                            #rmt = long(float(rmt))
                            rmt = float(rmt)
                            
                            if rmt - mt != 0:
                                time_differ = True
                        except:
                            time_differ = True
                        if self.options.force_hash or time_differ:
                            # Calc hash and save data:
                            try:
                                old_hash = self.files[fname].hash_read
                            except:
                                old_hash = -1 # if file is not in "read_files", give it a hash no-one can have
                            new_hash = self.files[fname].get_hash()
                            self.hashed += 1
                            
                            #if old_hash != new_hash: # (avoid mtime-ing unchanged files)
                            if True: # mtime all files, even unchanged ones
                                if self.options.verbosity > 0:
                                    print('[MD5] {0}'.format(fitit(fname)))
                                self.files[fname].hash_local = new_hash
                                self.files[fname].get_size()
                                self.files[fname].mtime_local = mt
        
                            else:
                                self.files[fname].hash_local = old_hash
                                self.files[fname].size_local = self.files[fname].size_read
                                self.files[fname].mtime_local = self.files[fname].mtime_read
                        else:
                            # Skip, because it's the same file (relying on mtime here):
                            self.files[fname].hash_local  = self.files[fname].hash_read
                            self.files[fname].size_local  = self.files[fname].size_read
                            self.files[fname].mtime_local = self.files[fname].mtime_read
        
                            if self.options.verbosity > 2: # VERY verbose!
                                print('[SKIP]: {0}'.format(fitit(fname)))

    def save(self, fn, local=True):
        """Save hashes of current file list in file "fn" (either index.dat, or
        the corresponding file in ~/.gipsync/)."""

        if local:
            # Then save locally (generally, to corresponding hash file in ~/.gipsync/).

            with open(fn, 'w') as f:
                for lfn in self.files_local:
                    val = self.files[lfn]
                    fmt = '{fn}|{v.hash_local}:{v.size_local}:{v.mtime_local}\n'
                    string = fmt.format(fn=lfn, v=val)
                    f.write(string)

        else:
            # Then save to remote repo, after GPGing it.

            # Save copy to local tmp file:
            tfn = '{0}/{1}'.format(self.tmpdir, fn)
            string = ''

            for lfn in self.files_remote:
                v = self.files[lfn]
                fmt = '{0}|{1.hash_remote}:{1.size_remote}:{1.mtime_remote}\n'
                string += fmt.format(lfn, v)
            with open(tfn,'w') as f:
                f.write(string)

            # GPG temporary file tfn:
            cmnd = '{0.gpgcom} -o "{0.tmpdir}/{1}.gpg" '.format(self, fn)
            for recipient in self.cfg.prefs['RECIPIENTS']:
                cmnd += ' -r {0} '.format(recipient)
            cmnd += ' -e {0} '.format(tfn)
            #fmt = '{0.gpgcom} -r {0.cfg.prefs[RECIPIENT]} -o "{0.tmpdir}/{1}.gpg" -e "{2}"'
            #cmnd = fmt.format(self, fn, tfn)
            self.doit(cmnd,2)

            # Upload to remote:
            cmnd1 = '{0} -q '.format(self.rsync)
            cmnd2 = ' "{0}.gpg" '.format(tfn)
            cmnd3 = ' "{0}/{1}/{2}.gpg"'.format(self.cfg.prefs['REMOTE'], self.cfg.conf['REPODIR'], fn)

            if self.options.verbosity > 1:
                print('\n' + cmnd1)
                print(' '  + cmnd2)
                print(' '  + cmnd3 + '\n')

            cmnd = cmnd1 + cmnd2 + cmnd3
            self.doit(cmnd,666)

    def read_remote(self):
        """Read remote repo metadata."""

        fn = 'index.dat'
        cmnd = '{0.gpgcom} -o "{0.tmpdir}/{1}" -d "{0.tmpdir}/{1}.gpg"'.format(self, fn)

        if self.options.verbosity > 0:
            print('\n'+cmnd)
        
        self.doit(cmnd)
        conf = os.path.join(self.tmpdir, fn)

        dict = conf2dic(conf,separator='|')

        for k,v in dict.items():
            av = v.split(':')
  
            if len(av) < 2:
                msj = 'The length of dictionary entry "{0}|{1}" is too short!'.format(k, v)
                sys.exit(msj)
            if not k in self.files:
                self.files[k] = Fileitem(k, repos=self)
            if not k in self.files_remote:
                self.files_remote[k] = True
            self.files[k].hash_remote  = av[0]
            self.files[k].size_remote  = float(av[1])
            self.files[k].mtime_remote = float(av[2])

    def compare(self):
        """Compare local and remote repositories."""

        # Check in single loop:
        for k,v in self.files.items():
            if v.hash_local: # then file exists locally
                if v.hash_remote: # then file exists remotelly too
                    if v.hash_local != v.hash_remote:
                        # Then files differ, use mtime to decice which
                        # one to keep (newest):
                        lmt = v.mtime_local
                        rmt = v.mtime_remote

                        if lmt < rmt:
                            self.diff.newremote.append(k)
                            self.diff.newremote_hash[v.hash_remote] = k
                            if self.options.verbosity > 0:
                                fmt = '\ndiff: local [{0}] -- remote [\033[32m{1}\033[0m] {2}'
                                print(fmt.format(e2d(lmt), e2d(rmt), k))

                        elif lmt > rmt or (self.options.up and self.options.force_hash):
                            self.diff.newlocal.append(k)
                            self.diff.newlocal_hash[v.hash_local] = k
                            if self.options.verbosity > 0:
                                fmt = '\ndiff: local [\033[32m{0}\033[0m] -- remote [{1}] {2}'
                                print(fmt.format(e2d(lmt), e2d(rmt), k))

                        else:
                            fmt = '\033[33m[WARN]\033[0m "{0}" differs, but has same mtime.'
                            print(fmt.format(k))
                            if self.options.update_equals:
                                if self.options.up:
                                    self.diff.newlocal.append(k)
                                    self.diff.newlocal_hash[v.hash_local] = k
                                else:
                                    self.diff.newremote.append(k)
                                    self.diff.newremote_hash[v.hash_remote] = k

                else:  # then file exists only locally
                    self.diff.local.append(k)
                    self.diff.local_hash[v.hash_local] = k

            elif v.hash_remote: # then file exists only remotely
                if not find_exc(k, self.cfg.conf['EXCLUDES']): # ignore files matching some rule
                    self.diff.remote.append(k)
                    self.diff.remote_hash[v.hash_remote] = k

        # Print summaries if enough verbosity:
        if self.options.verbosity > 1:
            print("\nLocal:")
            for k,v in self.diff.local_hash.items():
                print(k,v)
            print("Remote:")
            for k,v in self.diff.remote_hash.items():
                print(k,v)

            print("New local:")
            for k,v in self.diff.newlocal_hash.items():
                print(k,v)

            print("New remote:")
            for k,v in self.diff.newremote_hash.items():
                print(k,v)

    def upload(self):
        """Upload files from local to remote."""

        # List of files to upload:
        file_list = []
        file_list.extend(self.diff.newlocal)
        file_list.extend(self.diff.local)

        # Exit early if nothing to do:
        if not file_list:
            return True

        # In this case, we need to upload stuff:
        if self.really_do and file_list:
            # First encrypt files to tmp dir:
            self.encrypt(file_list, self.options.size_control)

            # Upload only if --size-control option not given:
            if not self.options.size_control:
                # Build list of files to upload from tmpdir to remote repo:
                tmpfile = '{0}/filelist.txt'.format(self.tmpdir)
                with open(tmpfile,'w') as f:
                    for h in self.diff.local_hash:
                        f.write(h+'.gpg\n')

                    for h in self.diff.newlocal_hash:
                        f.write(h+'.gpg\n')

                # Finally, upload all of them from tmpdir to remote repo:
                fmt  = '{0.rsync} -vh --progress {0.tmpdir}/data/ --files-from={1} '
                fmt += ' {0.cfg.prefs[REMOTE]}/{0.cfg.conf[REPODIR]}/data/'
                cmnd = fmt.format(self,tmpfile)
                try:
                    self.doit(cmnd,2)
                    os.unlink(tmpfile)
                except:
                    return False

            # Log changes:
            for name in file_list:
                v = self.files[name]
                v.hash_remote  = v.hash_local
                v.size_remote  = v.size_local
                v.mtime_remote = v.mtime_local

            return True

        # If we reach this point, return False:
        return False
    
    def encrypt(self, file_list, control):
        if file_list:
            print('\n')
            
        for name in file_list:
            v = self.files[name]
            
            # Log it:
            if not name in self.files_remote:
                self.files_remote[name] = True
            # If --size-control, GPG nothing:
            if not control:
                # GPG it:
                fgpg  = '{0}.gpg'.format(v.hash_local)
                lfile = '{0}/data/{1}'.format(self.tmpdir, fgpg)
                
                # Only GPG if not GPGed yet:
                if not os.path.isfile(lfile):
                    if self.options.verbosity < 2:
                        string = '\033[32m[GPG]\033[0m {0}'.format(fitit(name))
                        print(string)
                    cmnd = '{0.gpgcom} -o {1} '.format(self, lfile)
                    for recipient in self.cfg.prefs['RECIPIENTS']:
                        cmnd += ' -r {0} '.format(recipient)
                    cmnd += ' -e "{0}" '.format(v.fullname())
                    #fmt = '{0} -r {1} -o "{2}" -e "{3}"'
                    #cmnd = fmt.format(self.gpgcom, self.cfg.prefs['RECIPIENT'], lfile, v.fullname())
                    self.doit(cmnd,2)

    def nuke_remote(self):
        """Remove the files not present (or newer) locally from remote repo."""

        if self.really_do:
            fn_list = []
            nuke_some = False

            # Create a sftp script file to delete remote files:
            tmpfile = os.path.join(self.tmpdir, 'nuke_remote.sftp')
            with open(tmpfile,'w') as f:
                f.write('sftp {0} <<EOF\n'.format(self.cfg.prefs['REMOTE']))

                for fn in self.diff.remote + self.diff.newlocal:
                    hash = self.files[fn].hash_remote
                    line = 'rm {0[REPODIR]}/data/{1}.gpg\n'.format(self.cfg.conf, hash)
                    f.write(line)
                    nuke_some = True
                    fn_list.append(fn)
                f.write('exit\nEOF\n')
            if nuke_some:
                print('\n')

                # Execute sftp script:
                cmnd = 'bash {0}'.format(tmpfile)
                self.doit(cmnd)

                # Delete nuked files from list of remote files:
                for fn in fn_list:
                    del self.files_remote[fn]

    def enumerate(self,summary=True):
        if self.options.up:
          if not self.options.safe:
              self.say_nuke_remote()

          if self.options.size_control:
              if self.diff.local:
                  print('\n')

                  for name in self.diff.local:
                    print('\033[32m[FKUP]\033[0m {0}'.format(fitit(name)))
              if self.diff.newlocal:
                  print('')
              
                  for name in self.diff.newlocal:
                    print('\033[33m[FKSY]\033[0m {0}'.format(fitit(name)))
          else:
              if self.diff.local:
                  print('\n')

                  for name in self.diff.local:
                    print('\033[32m[UP]\033[0m {0}'.format(fitit(name)))
              if self.diff.newlocal:
                  print('')
              
                  for name in self.diff.newlocal:
                      print('\033[33m[SYNC]\033[0m {0}'.format(fitit(name)))
        else:
            if not self.options.safe:
                self.say_nuke_local()
            if self.diff.remote:
                print('\n')
                for name in self.diff.remote:
                    print('\033[32m[DOWN]\033[0m {0}'.format(fitit(name)))
            if self.diff.newremote:
                print('\n')
                for name in self.diff.newremote:
                    print('\033[33m[SYNC]\033[0m {0}'.format(fitit(name)))
        if summary:
            self.summary()

    def say_nuke_remote(self):
        """Print corresponding message for each file we are deleting
        from remote, with nuke_remote()."""

        if self.diff.remote:
            print('\n')
            for name in self.diff.remote:
                print('\033[31m[DEL]\033[0m {0}'.format(fitit(name)))

    def download(self):
        """Execute the downloading of remote files not in local, or
        superceding the ones in local."""

        # List of file(-hashe)s to download:
        lista = []
        for h in self.diff.remote_hash:
            lista.append(h)
        for h in self.diff.newremote_hash:
            lista.append(h)

        # Check which ones present remotely:
        dir = self.cfg.conf['REPODIR']
        server = self.cfg.prefs['REMOTE']
        newlist = get_present_files(server, dir, lista)

        # Proceed only if some or all are present:
        if newlist:
            # Build list of files to dl from repo (defined by md5 hash):
            tmpfile = '{0}/filelist.txt'.format(self.tmpdir)
            with open(tmpfile,'w') as f:
                for h in newlist:
                    f.write(h+'.gpg\n')
            # Download all of them from repo to tmpdir:
            fmt = '{0.rsync} -vh --progress {0.cfg.prefs[REMOTE]}/{0.cfg.conf[REPODIR]}/data/ --files-from={1}'
            fmt += ' {0.tmpdir}/data/'
            cmnd = fmt.format(self,tmpfile)
            try:
                self.doit(cmnd,2)
                os.unlink(tmpfile)
            except:
                return False

        # List of file names of files we just downloaded (or tried to):
        file_list = []

        for fn in self.diff.remote:
            file_list.append(fn)

        for fn in self.diff.newremote:
            file_list.append(fn)

        # Un-GPG from tmpdir dir to final destination in local:
        if file_list:
            print('\n')

        for fn in file_list:
            file = self.files[fn]
            fgpg = '{0}.gpg'.format(file.hash_remote)

            # Source GPG file:
            fn = '{0}/data/{1}'.format(self.tmpdir, fgpg)

            if os.path.exists(fn):
                # Create local dir to accomodate file, if necessary:
                dir_to = file.fullname().split('/')[:-1]
                dir_to = '/'.join(dir_to)
                if not os.path.isdir(dir_to):
                    os.makedirs(dir_to)
                # First un-GPG it to tmp dir:
                cmnd = '{0} -o "{1}/tmp" -d "{2}"'.format(self.gpgcom, self.tmpdir, fn)
                self.doit(cmnd,2)

                # Then check if not corrupted:
                ref = file.hash_remote
                act = hashof('{0}/tmp'.format(self.tmpdir))
                
                if ref == act: # then it is OK. Proceed:
                    # Warn of what is being done:
                    print('\033[32m[DOWN]\033[0m {0}'.format(fitit(file.name)))

                    # Move tmp file into actual destination:
                    cmnd = 'mv -f "{0}/tmp" "{1}"'.format(self.tmpdir,file.fullname())
                    self.doit(cmnd)

                    # Log changes:
                    file.hash_local  = file.hash_remote
                    file.size_local  = file.size_remote
                    file.mtime_local = file.mtime_remote

                    # Touch file accordingly:
                    os.utime(file.fullname(),(-1,file.mtime_remote))
                    
                else:
                    msg  = '\033[31m[NOOK]\033[0m {0}\n'.format(file.name)
                    msg += '\033[33m[IGNO]\033[0m {0}'.format(file.name)
                    print(msg)

            else:
                # Then file was not physically in repo:
                print('\033[31m[MISS]\033[0m %s' % (file.name))
                del self.files_remote[file.name]

        # If all went OK, return True:
        return True

    def nuke_local(self):
        """When downloading, delete the local files not in remote repo."""
        
        for name in self.diff.local:
            cmnd = 'rm -f "%s/%s"' % (self.cfg.conf['LOCALDIR'], name)
            self.doit(cmnd,2)

            if self.really_do:
                del self.files_local[name]

    def say_nuke_local(self):
        if self.diff.local:
            print('\n')
            for name in self.diff.local:
                print('\033[31m[DEL]\033[0m {0}'.format(fitit(name)))

    def summary(self):
        lsl  = len(self.diff.local)
        lsr  = len(self.diff.remote)
        lddl = len(self.diff.newlocal)
        lddr = len(self.diff.newremote)
        size_up = 0
        size_dn = 0
        size_rm = 0

        if not self.really_do:
            if self.options.up:
                for name in self.diff.local:
                    size_up += self.files[name].size_local
                for name in self.diff.newlocal:
                    size_up += self.files[name].size_local
                for name in self.diff.remote:
                    size_rm += self.files[name].size_remote
            else:
                for name in self.diff.remote:
                    size_dn += self.files[name].size_remote
                for name in self.diff.newremote:
                    size_dn += self.files[name].size_remote
                for name in self.diff.local:
                    size_rm += self.files[name].size_local
        if self.really_do:
            up_msj = 'uploaded'
            dn_msj = 'downloaded'
            rm_msj = 'deleted'
        else:
            up_msj = 'to upload'
            dn_msj = 'to download'
            rm_msj = 'to delete'
        if lsl + lddl + lsr + lddr == 0:
            print("\033[32mUp to date!\033[0m")
        else:
            print('\n{0:30}: {1}'.format('Number of files considered',self.walked))
            print('{0:30}: {1}'.format('Number of hashes calculated',self.hashed))
  
            if self.options.up:
                msj = '{0} {1}'.format("Number of files",up_msj)
                print('{0:30}: {1} ({2})'.format(msj, lsl + lddl, bytes2size(size_up)))
      
                if not self.options.safe:
                    msj = '{0} {1}'.format("Number of files",rm_msj)
                    print('{0:30}: {1} ({2})'.format(msj, lsr, bytes2size(size_rm)))
                print('{0:30}: {1}'.format("Diff files, newer in repo",lddr))
            else:
                msj = '{0} {1}'.format("Number of files",dn_msj)
                print('{0:30}: {1} ({2})'.format(msj, lsr + lddr, bytes2size(size_dn)))
         
                if not self.options.safe:
                    msj = '{0} {1}'.format("Number of files",rm_msj)
                    print('{0:30}: {1} ({2})'.format(msj, lsl, bytes2size(size_rm)))
    
                print('{0:30}: {1}'.format("Diff files, newer locally",lddl))

    def clean(self):
        """Clean up, which basically means rm tmpdir."""

        if not self.options.keep:
            if os.path.isdir(self.tmpdir):
                shutil.rmtree(self.tmpdir)

    def get_index(self):
        """Gets the remote index.dat file."""
        
        # Build command:
        cmnd1 = '{0.rsync}'.format(self)
        cmnd2 = '  {0.prefs[REMOTE]}/{0.conf[REPODIR]}/index.dat.gpg'.format(self.cfg)
        cmnd3 = '  {0.tmpdir}/'.format(self)
        
        cmnd = cmnd1 + cmnd2 + cmnd3

        # Print command if requested:
        if self.options.verbosity > 1:
            print('\n' + cmnd1 + '\n' + cmnd2 + '\n' + cmnd3 + '\n')

        # Perform rsync:
        self.doit(cmnd)

    def doit(self,command,level=1,fatal_errors=True):
        """Run/print command, depending on dry-run-nes and verbosity."""
        
        if not self.options.verbosity < level:
            print(command)
            
        s = sp.Popen(command, shell=True)
        s.communicate()
        if fatal_errors:
            ret = s.returncode
            if ret != 0:
                print('Error running command:\n%s' % (command))
                sys.exit()

    def ask(self,up=True):
        """Ask for permission to proceed, if need be."""

        lsl = len(self.diff.local)
        lsr = len(self.diff.remote)
        lddr = len(self.diff.newremote)
        lddl = len(self.diff.newlocal)

        if up:
            tot = lsl + lsr + lddl
        else:
            tot = lsl + lsr + lddr
        if tot:
            # There are differences:
            answer = input('\nAct accordingly (y/N)?: ')
            if answer and 'y' in answer:
                self.really_do = True
            return True
        else:
            # There was no difference:
            return False

    def step_check(self, what=None):
        """Check if some step has been completed in a previous run, and do not repeat."""

        # Directly avoid doing anything if command-line option --fresh was used:
        if self.options.fresh:
            return False

        # Return and do nothing if not asked what step to check for:
        if not what:
            return False

        # Then we've been told to check if task was finished, not log it:
        if what in self.done:
            return True

        return False

    def pickle(self, read=False):
        """Save/read repos object to/from file."""

        pickle_file = '{0}/repo.pickle'.format(self.tmpdir)

        if read: # then read pickled data, not write it.
            if os.path.isfile(pickle_file): 
                with open(pickle_file,'rb') as f:
                    return pickle.load(f)
            else: # if pickle_file does not exist, do nothing
                return self
        else:
            with open(pickle_file,'wb') as f:
                pickle.dump(self, f)

class Fileitem(object):
    """Each of the items of the list of local or remote files, 
    holding its characteristics.
    """

    def __init__(self, name=None, repos=None):
        self.name  = name
        self.repos = repos

        self.size_read   = 0
        self.size_local  = 0
        self.size_remote = 0

        self.mtime_read   = 0
        self.mtime_local  = 0
        self.mtime_remote = 0

        self.hash_read   = None
        self.hash_local  = None
        self.hash_remote = None

    def fullname(self):
        """Return full (local) name of file."""

        return '%s/%s' % (self.repos.cfg.conf['LOCALDIR'], self.name)

    def get_hash(self):
        """Calc hash function for Fileitem."""

        return hashof(self.fullname())

    def get_size(self):
        """Calc file size for Fileitem."""

        self.size_local = os.path.getsize(self.fullname())

class RepoDiff(object):
    """An object to store differences between local/remote repos."""

    def __init__(self):
        # Files that exist only in local repo;
        self.local = [] # list of filenames
        self.local_hash = {} # dict of hash -> filename 

        # Files that exist only in remote repo:
        self.remote = [] # list of filenames
        self.remote_hash = {} # dict of hash -> filename 

        # Files that exist in both repos, but are newer in local:
        self.newlocal = [] # list of filenames
        self.newlocal_hash = {} # dict of hash -> filename 

        # Files that exist in both repos, but are newer in remote:
        self.newremote = [] # list of filenames
        self.newremote_hash = {} # dict of hash -> filename 

    def sort(self):
        self.local = sorted(self.local)
        self.remote = sorted(self.remote)
        self.newlocal = sorted(self.newlocal)
        self.newremote = sorted(self.newremote)
