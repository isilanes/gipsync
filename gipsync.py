#!/usr/bin/python3
# -*- coding=utf-8 -*-

'''
GPG/rsync
(c) 2008-2014, Iñaki Silanes

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

#--------------------------------------------------------------------------------#

import os
import sys
import argparse

from libgipsync import core
from libgipsync import classes

#--------------------------------------------------#

# Read arguments:
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

o = parser.parse_args()
args = o.positional

#--------------------------------------------------------------------------------#

# --- Initialization --- #

times = core.Timing()
cfg = core.Configuration()
cfg.read_prefs()

#--------------------------------------------------------------------------------#

####################
#                  #
# DELETION SECTION #
#                  #
####################

if o.delete:
    # Check that repo dir is mounted:
    dir = cfg.prefs['PIVOTDIR']
    if not os.path.isdir(dir):
        msg = 'Can not find dir "{0}". Is it mounted?'.format(dir)
        sys.exit(msg)

    # Get info:
    sizes = core.collect_sizes(dir)

    # Sort info by date:
    sizes.sort()

    # Delete up to freeing requested size,
    # starting from oldest files:

    todelete = o.delete*1024*1024

    goon = True
    while goon:
        returned = core.delete_asked(sizes, todelete)
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
  # Check arguments:
  if args and args[0] == 'all':
      args = cfg.prefs['ALL']

  # Perform actions for each repo named in args:
  for what in args:
      # Read and check configs:
      cfg.read_conf(what)
      cfg.check()

      # Initialize repo (read from pickle, if present and not o.fresh):
      repos = classes.Repositories(opts=o, cfg=cfg, what=what)
      if not o.fresh:
          repos = repos.pickle(read=True)
          repos.options = o # use currently user-given options, not pickled ones

      times.milestone('Read confs')
      
      # Print info:
      core.message('repo', what=what, cfg=cfg)
      
      # --- Read remote data --- #

      # Check if remote data already downloaded:
      string = 'Downloading index.dat...'
      if not o.fresh and 'dl_index' in repos.done:
          core.say('[AVOIDED] {0}'.format(string))
      else:
          # Sync local proxy repo with remote repo:
          core.say(string)
          repos.get_index() # first download only index.dat.gpg

          # Create flag to say "we already downloaded index.dat":
          repos.done['dl_index'] = True
      
      # For each step, we pickle and log time:
      repos.pickle()
      times.milestone('Download remote index')

      # Get remote md5tree:
      string = 'Reading remote md5tree...'
      if not o.fresh and 'read_index' in  repos.done:
          core.say('[AVOIDED] {0}'.format(string))
      else:
          core.say(string)
          repos.read_remote()

          # Create flag to say "we already read remote index.dat":
          repos.done['read_index'] = True

      # For each step, we pickle and log time:
      repos.pickle()
      times.milestone('Read remote index')

      # --- Read local data --- #

      hash_file = os.path.join(cfg.dir, '{0}.md5'.format(what))
      string = 'Reading local md5tree...'
      if not o.fresh and 'read_local_md5s' in repos.done:
          core.say('[AVOIDED] {0}'.format(string))
      else:
          # Read local file hashes from conf (for those files that didn't change):
          core.say(string)
          repos.read(hash_file)

          # Create flag to say "we already read local md5 file":
          repos.done['read_local_md5s'] = True
      
      # For each step, we pickle and log time:
      repos.pickle()
      times.milestone('Initialize')

      # Traverse source and get list of file hashes:
      string = 'Finding new/different local files...'
      if not o.fresh and 'check_local_files' in repos.done:
          core.say('[AVOIDED] {0}'.format(string))
      else:
          core.say(string)
          repos.walk()

          # Create flag to say "we already checked local files":
          repos.done['check_local_files'] = True
      
      # For each step, we pickle and log time:
      repos.pickle()
      times.milestone('Dir walk')
      
      # --- Write back local data --- #
      
      # Save local hashes, be it dry or real run:
      string = 'Saving local data...'
      if not o.fresh and 'save_local_md5s' in repos.done:
          core.say('[AVOIDED] {0}'.format(string))
      else:
          core.say(string)
          repos.save(hash_file)

          # Create flag to say "we already saved local MD5s":
          repos.done['save_local_md5s'] = True
      
      # For each step, we pickle and log time:
      repos.pickle()
      times.milestone('Save local hash')
      
      # --- Actually do stuff --- #
      
      # Compare remote and local md5 trees:
      string = 'Comparing remote/local...'
      if not o.fresh and 'compare_md5_trees' in repos.done:
          core.say('[AVOIDED] {0}'.format(string))
      else:
          core.say(string)
          repos.compare()

          # Create flag to say "we already checked local files":
          repos.done['compare_md5_trees'] = True
      
      # For each step, we pickle and log time:
      repos.pickle()
      times.milestone('Compare')
      
      # Sort lists, for easy reading:
      repos.diff.sort()

      # For each step, we pickle and log time:
      repos.pickle()
      times.milestone('Sort diff')
      
      # Act according to differences in repos:
      success = False

      ##########
      # Upload #
      ##########
      if o.up:
          repos.really_do = False
          
          # Print summary/info:
          repos.enumerate()
          
          # Ask for permission to proceed, if there are changes:
          any_diff = repos.ask()
                  
          if repos.really_do:
              if not o.safe:
                  if o.safe or not o.fresh and 'delete_remote' in repos.done:
                      core.say('[AVOIDED] Deleting remote files...')
                  else:
                      string = 'Deleting remote files...'
                      core.say(string)
                      repos.nuke_remote()

                      # Create flag to say "we already deleted remote files":
                      repos.done['delete_remote'] = True

              # For each step, we pickle and log time:
              repos.pickle()
              times.milestone('Nuke up')
          
              # Safe or not safe, upload:
              if not o.fresh and 'upload' in repos.done:
                  core.say('[AVOIDED] Uploading...')
              else:
                  string = 'Uploading...'
                  core.say(string)
                  success = repos.upload()

                  # Create flag to say "we already uploaded files":
                  if success:
                      repos.done['upload'] = True
                  
              # For each step, we pickle and log time:
              repos.pickle()
              times.milestone('Upload')

              if not success:
                  sys.exit()
                
              # Write index file to remote repo:
              if not o.fresh and 'write_remote_index' in repos.done:
                  core.say('[AVOIDED] Saving index.dat remotely...')
              else:
                  string = 'Saving index.dat remotely...'
                  core.say(string)
                  repos.save('index.dat', local=False)

                  # Create flag to say "we already wrote remote index":
                  repos.done['write_remote_index'] = True

              # For each step, we pickle and log time:
              repos.pickle()
              times.milestone('Write remote index')

      ############
      # Download #
      ############
      else:
          repos.really_do = False
          
          # Print summary/info:
          repos.enumerate()
          
          # Ask for permission to proceed:
          any_diff = repos.ask(up=False)
                      
          if repos.really_do:
              if not o.safe:
                  if not o.fresh and 'delete_local' in repos.done:
                      core.say('[AVOIDED] Deleting local files...')
                  else:
                      # Delete files only in local:
                      repos.nuke_local()

                      # Create flag to say "we already deleted local files":
                      repos.done['delete_local'] = True
                      
                  # For each step, we pickle and log time:
                  repos.pickle()
                  times.milestone('Nuke local')

              # Safe or not, download:
              if not o.fresh and 'download' in repos.done:
                  core.say('[AVOIDED] Downloading...')
              else:
                  string = 'Downloading...'
                  core.say(string)
                  success = repos.download()

                  # Create flag to say "we already downloaded remote files":
                  repos.done['download'] = True
              
              # For each step, we pickle and log time:
              repos.pickle()
              times.milestone('Download')

              if not success:
                  sys.exit()

              # Save logs:
              repos.save(hash_file)

              # Write index file to remote repo:
              if not o.fresh and 'write_remote_index' in repos.done:
                  core.say('[AVOIDED] Saving index.dat remotely...')
              else:
                  string = 'Saving index.dat remotely...'
                  core.say(string)
                  repos.save('index.dat', local=False)

                  # Create flag to say "we already wrote remote index":
                  repos.done['write_remote_index'] = True

              # For each step, we pickle and log time:
              repos.pickle()
              times.milestone('Save remote index')

      # Cleanup, either because all went well, or because 
      # there was nothing to do:
      if success or not any_diff:
          string = 'Cleaning up...'
          core.say(string)
          repos.clean()

      times.milestone('Finalize')

# Lastly, print out timing summary:
if o.timing:
    times.summary()
