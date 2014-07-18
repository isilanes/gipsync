import re
import os
import sys
import time
import json
import hashlib
import datetime
import subprocess as sp

#--------------------------------------------------------------------------------#

class Timing:
      
    def __init__(self):
        self.t0         = now()
        self.milestones = []
        self.data       = {}
    def milestone(self,id=None):
        '''Add a milestone to list. A milestone is just a point in time that 
        we record.'''
        
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
        '''Print out a summary of timing so far.'''
        
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

# --- #

class Configuration:
    '''Class containing all info of configurations.'''

    def __init__(self, dir=None):
        self.dir = dir  # where config files are
        self.prefs = {} # global preferences
        self.conf  = {} # config of current repo

        # Default config dir, if not givem:
        if not self.dir:
            self.dir = os.path.join(os.environ['HOME'], '.gipsync')
    def read_prefs(self):
        ''' Read the global preferences.'''

        fn = os.path.join(self.dir, 'config.json')
        try:
            with open(fn) as f:
                self.prefs = json.load(f)
        except:
            print('Could not read global preferences at "{0}"'.format(fn))
            sys.exit()
    def read_conf(self, what=None):
        '''Read the configuration for repo named "what" (both .conf 
        and  .excludes files).'''

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
        ''' Check that essential configuration variables are set.'''

        for var in [ 'REPODIR', 'LOCALDIR', 'EXCLUDES' ]:
            if not var in self.conf:
                fmt = 'Sorry, but variable "{0}" is not specified in conf file'
                string = fmt.format(var)
                sys.exit(string)

        for var in ['RECIPIENT', 'REMOTE']:
            if not var in self.prefs:
                fmt = 'Sorry, but variable "{0}" is not specified in global config file'
                string = fmt.format(var)
                sys.exit(string)

#--------------------------------------------------------------------------------#

def fitit(path,limit=None):
  '''Make a given string (path) fit in the screen width.'''

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
    '''
    Calc hash function for file.
    '''

    h = hashlib.md5()

    f = open(fn,'rb')
    while True:
        t = f.read(4096)
        if len(t) == 0:
            break
        h.update(t)
    f.close()
    
    return h.hexdigest()

def bytes2size(bytes):
    '''
    Get a number of bytes, and return in human-friendly form (kB, MB, etc).
    '''
    units = ['B', 'kB', 'MB', 'GB']
    
    i = 0
    sz = bytes
    while sz > 1024:
        sz = sz/1024.0
        i  += 1

    return '%.2f %s' % (sz, units[i])

def find_exc(it, patts):
    '''Return True if item "it" matches some pattern in "patts", False otherwise.'''

    for patt in patts:
        if patt in it:
            return True

    return False

def collect_sizes(dir):
    '''
    Collect the size of all data in remote repo (mounted locally by SSHFS).
    '''

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
    '''
    Delete files from pivot dir, until given size is reached.
    '''

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
    '''
    Print out a message.
    '''

    if string:
        print('\033[1m%s\033[0m' % (string))

def conf2dic(fname,separator='='):
    '''Read a configuration file and interpret its lines as "key=value" pairs, assigning them
    to a dictionary, and returning it.
       fname = file name of the configuration file to read.'''
     
    cf = {}

    with open(fname) as f:
        for line in f:
            line = line.replace('\n','')
            if line and not line[0] == '#': # ignore blank lines and comments
                aline = line.split(separator)
                cf[aline[0]] = separator.join(aline[1:])

    return cf

def now():
    ''' Return current time, in seconds since epoch format.'''
    date = datetime.datetime.now()
    
    return time.mktime(date.timetuple())

def s2hms(seconds):
    '''Take an amount of seconds (or a timedelta object), and return 
    in HH:MM:SS format.'''

    # Create output string, and return:
    hh = int(seconds/3600.0)
    mm = int((seconds - 3600*hh)/60.0)
    ss = int(seconds - 3600*hh - 60*mm)

    string = '{0:02}:{1:02}:{2:02}'.format(hh,mm,ss)

    return string

def get_present_files(server, dir, files):
    '''Returns a list of which files of the list "files" is present in directory "dir",
    in server "server".'''

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

#--------------------------------------------------------------------------------#
