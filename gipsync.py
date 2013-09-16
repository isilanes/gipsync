#!/usr/bin/python3
# coding=utf-8

'''
GPG/rsync
(c) 2008-2012, Iñaki Silanes

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
import libgipsync.core as LC

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

parser.add_option("-F", "--fresh",
                  help="Do not try to recover from previous interupted run. Start afresh instead. Default: recover when available.",
		  action="store_true",
		  default=False)

parser.add_option("--update-equals",
                  help="If remote/local mtimes of a file coincide, but MD5s differ, update (upload local if -u, download remote otherwise. Default: Ignore (and warn about) such cases.",
		  action="store_true",
		  default=False)

(o,args) = parser.parse_args()

#--------------------------------------------------------------------------------#

# --- Initialization --- #

times = LC.Timing()
cfg = LC.Configuration()
cfg.dir = '{0[HOME]}/.gipsync'.format(os.environ)
cfg.read_prefs()

#--------------------------------------------------------------------------------#

####################
#                  #
# CREATION SECTION #
#                  #
####################

if o.new:
  tn = LC.now()

  try:
      conf_name = args[0]
  except:
      msg = 'You must input config name if you want to create new repo.'
      sys.exit(msg)

  # Check that conf file exists, and read it:
  cfile = '{0}/{1}.conf'.format(conf_dir,conf_name)
  if os.path.isfile(cfile):
      conf = LC.conf2dic(cfile)
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
  repos = LC.Repositories(o,la)
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
    repos.excludes = LC.conf2dic(excludes_file)

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
    dir = cfg.prefs['PIVOTDIR']
    if not os.path.isdir(dir):
        msg = 'Can not find dir "{0}". Is it mounted?'.format(dir)
        sys.exit(msg)

    # Get info:
    sizes = LC.collect_sizes(dir)

    # Sort info by date:
    sizes.sort()

    # Delete up to freeing requested size,
    # starting from oldest files:

    todelete = o.delete*1024*1024

    goon = True
    while goon:
        returned = LC.delete_asked(sizes, todelete)
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

      # Initialize repo, and read from pickle, if present and not o.fresh:
      repos = LC.Repositories(o, cfg)
      repos.tmpdir = '{0}/ongoing.{1}'.format(cfg.dir, what)
      if not o.fresh:
          repos = repos.pickle(read=True)
          repos.options = o # use user-given options, not pickled ones from previous run

      # Create tmpdir if necessary:
      tmpdata = repos.tmpdir + '/data'
      try:
          os.makedirs(tmpdata)
      except:
          pass # if it already exists
      
      if o.verbosity < 1:
          repos.gpgcom += ' --no-tty '
          
      times.milestone('Read confs')
      
      # Print info:
      fmt = "\nRepository: \033[34m{0}\033[0m @ \033[34m{1}\033[0m"
      string = fmt.format(what, cfg.conf['LOCALDIR'])
      LC.say(string)
      
      # --- Read remote data --- #

      # Check if remote data already downloaded:
      string = 'Downloading index.dat...'
      if not o.fresh and 'dl_index' in repos.done:
          LC.say('[AVOIDED] {0}'.format(string))
      else:
          # Sync local proxy repo with remote repo:
          LC.say(string)
          repos.get_index() # first download only index.dat.gpg

          # Create flag to say "we already downloaded index.dat":
          repos.done['dl_index'] = True
      
      # For each step, we pickle and log time:
      repos.pickle()
      times.milestone('Download remote index')

      # Get remote md5tree:
      string = 'Reading remote md5tree...'
      if not o.fresh and 'read_index' in  repos.done:
          LC.say('[AVOIDED] {0}'.format(string))
      else:
          LC.say(string)
          repos.read_remote()

          # Create flag to say "we already read remote index.dat":
          repos.done['read_index'] = True

      # For each step, we pickle and log time:
      repos.pickle()
      times.milestone('Read remote index')

      # --- Read local data --- #

      hash_file = '{0}/{1}.md5'.format(cfg.dir, what)
      string = 'Reading local md5tree...'
      if not o.fresh and 'read_local_md5s' in repos.done:
          LC.say('[AVOIDED] {0}'.format(string))
      else:
          # Read local file hashes from conf (for those files that didn't change):
          LC.say(string)
          repos.read(hash_file)

          # Create flag to say "we already read local md5 file":
          repos.done['read_local_md5s'] = True
      
      # For each step, we pickle and log time:
      repos.pickle()
      times.milestone('Initialize')

      # Traverse source and get list of file hashes:
      string = 'Finding new/different local files...'
      if not o.fresh and 'check_local_files' in repos.done:
          LC.say('[AVOIDED] {0}'.format(string))
      else:
          LC.say(string)
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
          LC.say('[AVOIDED] {0}'.format(string))
      else:
          LC.say(string)
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
          LC.say('[AVOIDED] {0}'.format(string))
      else:
          LC.say(string)
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
                      LC.say('[AVOIDED] Deleting remote files...')
                  else:
                      string = 'Deleting remote files...'
                      LC.say(string)
                      repos.nuke_remote()

                      # Create flag to say "we already deleted remote files":
                      repos.done['delete_remote'] = True

              # For each step, we pickle and log time:
              repos.pickle()
              times.milestone('Nuke up')
          
              # Safe or not safe, upload:
              if not o.fresh and 'upload' in repos.done:
                  LC.say('[AVOIDED] Uploading...')
              else:
                  string = 'Uploading...'
                  LC.say(string)
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
                  LC.say('[AVOIDED] Saving index.dat remotely...')
              else:
                  string = 'Saving index.dat remotely...'
                  LC.say(string)
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
                      LC.say('[AVOIDED] Deleting local files...')
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
                  LC.say('[AVOIDED] Downloading...')
              else:
                  string = 'Downloading...'
                  LC.say(string)
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
                  LC.say('[AVOIDED] Saving index.dat remotely...')
              else:
                  string = 'Saving index.dat remotely...'
                  LC.say(string)
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
          LC.say(string)
          repos.clean()

      times.milestone('Finalize')

# Lastly, print out timing summary:
if o.timing:
    times.summary()
