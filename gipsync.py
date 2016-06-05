#!/usr/bin/python3
# -*- coding=utf-8 -*-

"""
GPG/rsync
(c) 2008-2016, Iñaki Silanes

LICENSE

This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License (version 3), as
published by the Free Software Foundation.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
for more details (http://www.gnu.org/licenses/gpl.txt).

DESCRIPTION

Uses a remote destination to store checksums (MD5s) and GPG-encoded versions of local files, 
to sync with other computers.

USAGE

To upload local files (defined by ~/.gipsync/blah.conf) to remote site:

$ gipsync.py blah -u

Then, in some other computer:

$ gipsync.py blah
"""

import os
import sys

from libgipsync import core
from libgipsync import classes

# --- Initialization --- #

o = core.read_args()
args = o.positional
cfg = core.Configuration()

# --- Execution --- #

# Deletion means just deletion:
if o.delete:
    core.perform_deletion(cfg, o)
    exit()

# If no deletion, then sync. Go on:
if args[0] == 'all':
    args = cfg.prefs['ALL']

# Perform actions for each repo named in args:
for what in args:
    # Read and check configs:
    cfg.read_conf(what)
    
    # Check that localdir is present:
    ldir = cfg.conf['LOCALDIR']
    if not os.path.isdir(ldir):
        print("[ERROR] Required local dir '{d}' not present".format(d=ldir))
        exit()
        
    # --- Read remote data --- #
    RR = classes.RemoteRepo(cfg)
    RR.read_index_gpg()

    
""" 
      repos.read_remote()

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
  
  # Sort lists, for easy reading:
  repos.diff.sort()

  # For each step, we pickle and log time:
  repos.pickle()
  
  # Act according to differences in repos:
  success = False
""" 
exit()

##################
#                #
# UPDATE SECTION #
#                #
##################

if False:
  # Check arguments:
  if args and args[0] == 'all':
      args = cfg.prefs['ALL']

  # Perform actions for each repo named in args:
  for what in args:
      # Read and check configs:
      cfg.read_conf(what)
      cfg.check()

      # Check that localdir is present:
      ldir = cfg.conf['LOCALDIR']
      if not os.path.isdir(ldir):
          print("[ERROR] Required local dir '{0}' not present".format(ldir))
          sys.exit()

      # Initialize repo (read from pickle, if present and not o.fresh):
      repos = classes.Repositories(opts=o, cfg=cfg, what=what)
      if not o.fresh:
          repos = repos.pickle(read=True)
          repos.options = o # use currently user-given options, not pickled ones

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
      
      # Sort lists, for easy reading:
      repos.diff.sort()

      # For each step, we pickle and log time:
      repos.pickle()
      
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

      # Cleanup, either because all went well, or because 
      # there was nothing to do:
      if success or not any_diff:
          string = 'Cleaning up...'
          core.say(string)
          repos.clean()

