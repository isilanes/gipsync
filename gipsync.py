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
import optparse
import gipsync.core as GC

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

# --- Initialization --- #

times = GC.Timing()
cfg = GC.Configuration()
cfg.dir = '{0[HOME]}/.gipsync'.format(os.environ)
cfg.read_prefs()
la = GC.LastAction()
la.file = '{0}/last_action'.format(cfg.dir)

#--------------------------------------------------------------------------------#

####################
#                  #
# CREATION SECTION #
#                  #
####################

if o.new:
  tn = GC.now()

  try:
      conf_name = args[0]
  except:
      msg = 'You must input config name if you want to create new repo.'
      sys.exit(msg)

  # Check that conf file exists, and read it:
  cfile = '{0}/{1}.conf'.format(conf_dir,conf_name)
  if os.path.isfile(cfile):
      conf = GC.conf2dic(cfile)
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
  repos = GC.Repositories(o,la)
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
    repos.excludes = GC.conf2dic(excludes_file)

  times.milestone('Initialize')

  # Set variables if checks passed:
  repos.path_local = re.sub('/$','',conf['LOCALDIR'])
  repos.recipient  = prefs['RECIPIENT']

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

    tn = GC.now()

    # Get info:
    sizes = GC.collect_sizes(dir)

    # Sort info by date:
    asizes = [x for x in sizes]
    asizes.sort()
    tfiles = len(asizes)

    # Delete up to freeing requested size,
    # starting from oldest files:

    todelete = o.delete*1024*1024

    goon = True
    while goon:
        returned = GC.delete_asked(asizes, todelete)
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
      args = cfg.prefs['ALL'].split(',')

  # Perform actions for each repo named in args:
  for what in args:
      # Read and check configs:
      cfg.read_conf(what)
      cfg.check()

      # Initialize repo:
      repos = GC.Repositories(o,la,cfg)
      repos.tmpdir = '{0}/ongoing.{1}'.format(cfg.dir, what)
      
      if o.verbosity < 1:
          repos.gpgcom += ' --no-tty '
          
      times.milestone('Read confs')
      
      # Continue or not:
      cntdir = '{0}/data'.format(repos.tmpdir)
      if not os.path.isdir(cntdir):
          os.makedirs(cntdir)
          
      fmt = "\nRepository: \033[34m{0}\033[0m @ \033[34m{1}\033[0m"
      string = fmt.format(what, cfg.conf['LOCALDIR'])
      GC.say(string)
      
      # --- Read remote data --- #
      
      # Sync local proxy repo with remote repo:
      string = 'Downloading index.dat...'
      GC.say(string)
      repos.get_index() # first download only index.dat.gpg
      
      # Get remote md5tree:
      string = 'Reading remote md5tree...'
      GC.say(string)
      repos.read_remote()
      
      times.milestone('Read remote')
      
      # --- Read local data --- #
      
      # Read local file hashes from conf (for those files that didn't change):
      string = 'Reading local md5tree...'
      GC.say(string)
      hash_file = '{0}/{1}.md5'.format(cfg.dir, what)
      repos.read(hash_file)
      
      times.milestone('Initialize')
      
      # Traverse source and get list of file hashes:
      string = 'Finding new/different local files...'
      GC.say(string)
      repos.walk()
      
      times.milestone('Dir walk')
      
      # --- Write back local data --- #
      
      # Save local hashes, be it dry or real run:
      string = 'Saving local data...'
      GC.say(string)
      repos.save(hash_file)
      
      # --- Actually do stuff --- #
      
      # Compare remote and local md5 trees:
      string = 'Comparing remote/local...'
      GC.say(string)
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
          repos.ask()
                  
          if repos.really_do:
              if not o.safe:
                  string = 'Deleting remote files...'
                  GC.say(string)
                  repos.nuke_remote()
                  times.milestone('Nuke up')
          
              # Safe or not safe, upload:
              string = 'Uploading...'
              GC.say(string)
              repos.upload()
              times.milestone('Upload')
                
              # Write index file to remote repo:
              string = 'Saving index.dat remotely...'
              GC.say(string)
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
              repos.ask(up=False)
                      
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

              # Write index file to remote repo:
              string = 'Saving index.dat remotely...'
              GC.say(string)
              repos.save('index.dat', local=False)

      # Cleanup:
      string = 'Cleaning up...'
      GC.say(string)
      repos.clean()

      times.milestone('Finalize')

# Lastly, print out timing summary:
if o.timing:
    times.summary()
