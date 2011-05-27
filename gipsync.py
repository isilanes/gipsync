#!/usr/bin/python
# coding=utf-8

'''
GPG/rsync
(c) 2008-2011, Iñaki Silanes

LICENSE

This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License (version 2), as
published by the Free Software Foundation.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
for more details (http://www.gnu.org/licenses/gpl.txt).

DESCRIPTION

Uses a remote destination to store checksums (MD5s) and GPG-encoded versions of local files, 
to sync with other computers.

USAGE

To upload local files (defined by ~/.gipsync/blah.conf) to remote ("pivot") site:

% gipsync.py blah -u

Then, in some other computer:

% gipsync.py blah
'''

import os
import re
import sys
import copy
import zlib
import shutil
import hashlib
import optparse
import gipsync.core as GC

import Time as T
import System as S
import FileManipulation as FM
import DataManipulation as DM
import subprocess as sp

#--------------------------------------------------#

# Read arguments:
parser = optparse.OptionParser()

parser.add_option("-u", "--up",
                  dest="up",
                  help="If set, upload files. Default: download.",
                  action="store_true",
		  default=False)

parser.add_option("-v", "--verbose",
                  dest="verbosity",
                  help="Increase verbosity level by 1 for each call of this option. Default: 0.",
                  action="count",
		  default=0)

parser.add_option("-s", "--safe",
                  help="Safe mode: do not delete any local or remote file, please. Default: unsafe.",
		  action="store_true",
		  default=False)

parser.add_option("-k", "--keep",
                  help="Do not delete the generated temporary dir. Default: delete after use.",
		  action="store_true",
		  default=False)

parser.add_option("-S", "--size-control",
                  dest='size_control',
                  help="Do NOT upload files, just pretend you did. Default: if true run, upload new and diff files.",
		  action="store_true",
		  default=False)

parser.add_option("-T", "--timing",
                  help="Measure elapsed time for different parts of the program, then show a summary in the end. Default: don't.",
		  action="store_true",
		  default=False)

parser.add_option("-d", "--delete",
                  help="Files will be deleted, starting from oldest, until DELETE megabytes are freed. Default: None",
		  type=float,
                  default=None)

parser.add_option("-n", "--new",
                  help="Create a new repo, from a config dir. Initial index file will be that of local reference. Default: False.",
		  action="store_true",
		  default=False)

parser.add_option("-c", "--sync",
                  help="Sync remote repo to local (e.g. to delete files). Default: False.",
		  action="store_true",
		  default=False)

parser.add_option("-f", "--force-hash",
                  help="Check hashes of local files (to check for updates), even if mtime has not changed with respect to log. Default: only calculate hashes of files with updated mtime.",
		  action="store_true",
		  default=False)

parser.add_option("-l", "--limit-bw",
                  help="Limit bandwidth usage to LIMIT kB/s. Default: no limit.",
                  metavar='LIMIT',
		  default=0)

(o,args) = parser.parse_args()

#--------------------------------------------------------------------------------#

def fitit(path,limit=None):
  '''
  Make a given string (path) fit in the screen width.
  '''

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

#--------------------------------------------------------------------------------#

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

#--------------------------------------------------------------------------------#

class fileitem:
    '''
    Each of the items of the list of local or remote files, holding its characteristics.
    '''

    def __init__(self, name=None):
        self.name         = name

        self.size_read    = 0
        self.size_local   = 0
        self.size_remote  = 0

        self.mtime_read   = 0
        self.mtime_local  = 0
        self.mtime_remote = 0

        self.hash_read    = None
        self.hash_local   = None
        self.hash_remote  = None

    def fullname(self):
        '''
        Return full (local) name of file.
        '''
        return '%s/%s' % (repos.path_local, self.name)

    def get_hash(self):
        '''
        Calc hash function for fileitem
        '''
        return hashof(self.fullname())

    def get_size(self):
        '''
        Calc file size for fileitem.
        '''
        self.size_local = os.path.getsize(self.fullname())

#--------------------------------------------------------------------------------#

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

#--------------------------------------------------------------------------------#

class repodiff:
    '''
    An object to store differences between local/remote repos.
    '''

    def __init__(self):
        # Files that exist only in local repo;
        self.local      = [] # list of filenames
        self.local_hash = {} # dict of hash -> filename 

        # Files that exist only in remote repo:
        self.remote = []      # list of filenames
        self.remote_hash = {} # dict of hash -> filename 

        # Files that exist in both repos, but are newer in local:
        self.newlocal = [] # list of filenames
        self.newlocal_hash = {} # dict of hash -> filename 

        # Files that exist in both repos, but are newer in remote:
        self.newremote = [] # list of filenames
        self.newremote_hash = {} # dict of hash -> filename 

    # ----- #

    def sort(self):
        self.local     = sorted(self.local)
        self.remote    = sorted(self.remote)
        self.newlocal  = sorted(self.newlocal)
        self.newremote = sorted(self.newremote)

#--------------------------------------------------------------------------------#

def find_exc(it,patts):
    '''
    Return True if item "it" matches some pattern in "patts", False otherwise.
    '''

    found = False
    for patt in patts:
        if patt in it:
            found = True
            break

    return found

#--------------------------------------------------------------------------------#

def doit(command,level=1,fatal_errors=True):
    '''
    Run/print command, depending on dry-run-nes and verbosity.
    '''

    global last_action_file

    if not o.verbosity < level:
        print(command)

    if really_do:
        f = open(last_action_file,'w')
        f.write(command)
        f.close()

        s = sp.Popen(command, shell=True)
        s.communicate()
        if fatal_errors:
            ret = s.returncode
            if ret != 0:
                print('Error running command:\n%s' % (command))
                sys.exit()

#--------------------------------------------------------------------------------#

def last_action():
    '''
    Check if gipsync was previously aborted by searching for a "last_action" file.
    If it was, suggest to perform action in "last_action" file, and exit.
    '''

    if os.path.isfile(last_action_file):
        last_action = None

        f = open(last_action_file,'r')
        for line in f:
            last_action = line
        f.close()

        if last_action:
            print("Aborting: command aborted from previous run:\n")
            print(last_action+'\n')
            print("Please do the following:")
            print(" 1 - Bring the above command to end by hand")
            print(" 2 - Delete file {0}".format(last_action_file))
            print(" 3 - Run gipsync again.")
            sys.exit()

#--------------------------------------------------------------------------------#

def collect_sizes(dir):
    '''
    Collect the size of all data in remote repo (mounted locally by SSHFS).
    '''

    sizes = {}

    for path, dirs, files in os.walk(dir):
        print(path)
        if os.path.basename(path) == 'data':
            for file in files:
                fn = os.path.join(path,file)
                sz = os.path.getsize(fn)
                mt = os.path.getmtime(fn)
                
                k = '%i.%s' % (int(mt),fn)
                sizes[k] = sz
                sys.stdout.write('.') # "progress bar"
            print('')

    return sizes

#--------------------------------------------------------------------------------#

def delete_asked(asizes,todelete):
    '''
    Delete files from pivot dir, until given size is reached.
    '''

    deleted = 0
    idel    = 0
    while len(asizes):
        x = asizes.pop(0)
        xplit = x.split('.')
        datex = int(xplit[0])
        jfn = '.'.join(xplit[1:])
        fn  = os.path.basename(jfn)

        idel += 1
        deleted += int(sizes[x])

        ago = (tn - datex)/86400.0

        fmt = '{0:>4d}/{1}  {2}  {3:>10}  {4:>10}  {5:>6.2f} d'
        print(fmt.format(idel, tfiles, fn, bytes2size(sizes[x]), bytes2size(deleted), ago))
        os.unlink(jfn)

        if deleted > todelete:
            return True

#--------------------------------------------------------------------------------#

def say(string=None):
    '''
    Print out a message.
    '''

    if string:
        print('\033[1m%s\033[0m' % (string))

#--------------------------------------------------------------------------------#

# --- Initialization --- #

conf_dir = '%s/.gipsync' % (os.environ['HOME'])
prefs = FM.conf2dic(conf_dir+'/config')
times = T.timing()
la = GC.LastAction()
la.file = '{0}/last_action'.format(conf_dir)

#--------------------------------------------------------------------------------#

####################
#                  #
# CREATION SECTION #
#                  #
####################

if o.new:
  tn = T.now()

  try:
      conf_name = args[0]
  except:
      msg = 'You must input config name if you want to create new repo.'
      sys.exit(msg)

  # Check that conf file exists, and read it:
  cfile = '{0}/{1}.conf'.format(conf_dir,conf_name)
  if os.path.isfile(cfile):
      conf = FM.conf2dic(cfile)
  else:
      msg = 'Requested file "{0}" does not exist!'.format(cfile)
      sys.exit(msg)
  
  # Check that repo dir is mounted:
  pivotdir = prefs['PIVOTDIR']
  if not os.path.isdir(pivotdir):
      msg = 'Can not find dir "{0}". Is it mounted?'.format(pivotdir)
      sys.exit(msg)

  # Create repo dir:
  proxy_repo = '{0}/{1}'.format(pivotdir, conf['REPODIR'])
  repos.proxy = proxy_repo

  if not os.path.isdir(proxy_repo):
    os.mkdir(proxy_repo)

  data_dir = proxy_repo+'/data'
  if not os.path.isdir(data_dir):
    os.mkdir(data_dir)

  # Create tmpdir:
  repos = GC.Repositories(o, last_action_file)
  repos.tmpdir = '{0}/ongoing.{1}'.format(conf_dir, conf_name)
  if not os.path.isdir(repos.tmpdir):
      os.mkdir(repos.tmpdir)

  # --- Read local data --- #

  # Read local file hashes from conf (for those files that didn't change):
  hash_file = '{0}/{1}.md5'.format(conf_dir, conf_name)
  if os.path.isfile(hash_file):
    repos.read(hash_file)

  # Read local excludes from .excludes:
  excludes_file = '{0}/{1}.excludes'.format(conf_dir, conf_name)
  if os.path.isfile(excludes_file):
    repos.excludes = FM.conf2dic(excludes_file)

  times.milestone('Initialize')

  # Set variables if checks passed:
  repos.path_local  = re.sub('/$','',conf['LOCALDIR'])
  repos.recipient   = prefs['RECIPIENT']

  # Traverse source and get list of file hashes:
  repos.walk()

  times.milestone('Dir walk')

  # Write index file to remote repo:
  tmpdat = '{0}/index.dat'.format(repos.tmpdir)
  repos.save('index.dat', local=False)

  times.milestone('Create index')

  # Cleanup:
  repos.clean()

  times.milestone('Finalize')

####################
#                  #
# DELETION SECTION #
#                  #
####################

elif o.delete:
    # Check that repo dir is mounted:
    dir = prefs['PIVOTDIR']
    if not os.path.isdir(dir):
        msg = 'Can not find dir "{0}". Is it mounted?'.format(dir)
        sys.exit(msg)

    tn = T.now()

    # Get info:
    sizes = collect_sizes(dir)

    # Sort info by date:
    asizes = [x for x in sizes]
    asizes.sort()
    tfiles = len(asizes)

    # Delete up to freeing requested size,
    # starting from oldest files:

    todelete = o.delete*1024*1024

    goon = True
    while goon:
        returned = delete_asked(asizes, todelete)
        if returned:
            string = 'How many MBs do you want to delete?: '
            todelete = input(string)
            try:
                todelete = float(todelete)*1024*1024
            except:
                goon = False
        else:
            goon = False

    sys.exit()

##################
#                #
# UPDATE SECTION #
#                #
##################

else:
  # First of all, check whether there's some unresolved (truncated) action
  # from a previous run:
  la.check()

  # Check arguments:
  if args and args[0] == 'all':
      args = prefs['ALL'].split(',')

  # Perform actions for each repo named in args:
  for what in args:
    repos = GC.Repositories(o,la)

    repos.tmpdir = '{0}/ongoing.{1}'.format(conf_dir, what)

    if o.verbosity < 1:
        repos.gpgcom += ' --no-tty '

    # Read configs:
    cfile = '{0}/{1}.conf'.format(conf_dir, what)
    cfg = FM.conf2dic(cfile)

    times.milestone('Read confs')

    # --- Checks --- #

    # Continue or not:
    cntdir = '{0}/data'.format(repos.tmpdir)

    if not os.path.isdir(cntdir):
        os.makedirs(cntdir)

    # Config items:
    if not 'REPODIR' in cfg:
        sys.exit('Sorry, but REPODIR is not specified in conf file!')

    if not 'LOCALDIR' in cfg:
        sys.exit('Sorry, but local dir is not specified in conf file!')

    if not 'RECIPIENT' in prefs:
        sys.exit('Sorry, but RECIPIENT is not specified in global conf file!')

    if not 'REMOTE' in prefs:
        sys.exit('Sorry, but REMOTE is not specified in global conf file!')

    # Set variables if checks passed:
    repos.path_local = re.sub('/$','',cfg['LOCALDIR'])
    repos.recipient = prefs['RECIPIENT']
    repos.remote = prefs['REMOTE']+'/'+cfg['REPODIR']

    fmt = "\nRepository: \033[34m{0}\033[0m @ \033[34m{1}\033[0m"
    string = fmt.format(what, repos.path_local)
    say(string)

    # --- Read remote data --- #

    # Sync local proxy repo with remote repo:
    string = 'Downloading index.dat...'
    say(string)
    repos.repo_io(what='index') # first download only index.dat.gpg

    # Get remote md5tree:
    string = 'Reading remote md5tree...'
    say(string)
    repos.read_remote()

    times.milestone('Read remote')

    # --- Read local data --- #

    # Read local file hashes from conf (for those files that didn't change):
    string = 'Reading local md5tree...'
    say(string)
    hash_file = '{0}/{1}.md5'.format(conf_dir, what)
    repos.read(hash_file)

    # Read local excludes from .excludes:
    excludes_file = '{0}/{1}.excludes'.format(conf_dir, what)
    if os.path.isfile(excludes_file):
        repos.excludes = FM.conf2dic(excludes_file)

    times.milestone('Initialize')

    # Traverse source and get list of file hashes:
    string = 'Finding new/different local files...'
    say(string)
    repos.walk()

    times.milestone('Dir walk')

    # --- Write back local data --- #

    # Save local hashes, be it dry or real run:
    string = 'Saving local data...'
    say(string)
    repos.save(hash_file)

    # --- Actually do stuff --- #

    # Compare remote and local md5 trees:
    string = 'Comparing remote/local...'
    say(string)
    repos.compare()

    times.milestone('Compare')

    # Sort lists, for easy reading:
    repos.diff.sort()

    times.milestone('Sort diff')

    # Act according to differences in repos:

    ##########
    # Upload #
    ##########
    if o.up:
        repos.really_do = False
        answer = False

        # Print summary/info:
        repos.enumerate()

        # Ask for permission to proceed, if there are changes:
        lsl = len(repos.diff.local)
        lsr = len(repos.diff.remote)
        lddl = len(repos.diff.newlocal)

        if lsl + lsr + lddl > 0:
            answer = input('\nAct accordingly (y/N)?: ')
            if answer and 'y' in answer:
                repos.really_do = True

        if repos.really_do:
            if not o.safe:
                string = 'Deleting remote files...'
                say(string)
                repos.nuke_remote()
                times.milestone('Nuke up')

            # Safe or not safe, upload:
            string = 'Uploading...'
            say(string)
            repos.upload()
            times.milestone('Upload')

            # Write index file to remote repo:
            string = 'Saving index.dat remotely...'
            say(string)
            repos.save('index.dat', local=False)

    ############
    # Download #
    ############
    else:
        repos.really_do = False
        answer = False

        if not repos.really_do:
            # Print summary/info:
            repos.enumerate()

            # Ask for permission to proceed:
            lsl  = len(repos.diff.local)
            lsr  = len(repos.diff.remote)
            lddr = len(repos.diff.newremote)

            if lsl + lsr + lddr > 0:
                answer = input('\nAct accordingly (y/N)?: ')
                if answer and 'y' in answer:
                    repos.really_do = True

        if repos.really_do:
            if not o.safe:
                # Delete files only in local:
                repos.nuke_local()
                times.milestone('Nuke local')

            # Safe or not, download:
            repos.download()
            times.milestone('Download')

            # Save logs:
            repos.save(hash_file)
            repos.save('index.dat', local=False)

    # Cleanup:
    string = 'Cleaning up...'
    say(string)
    repos.clean()

    times.milestone('Finalize')

# Lastly, print out timing summary:
if o.timing:
    print(times.summary())
