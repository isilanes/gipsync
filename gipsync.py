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
import gipsync.core
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

class repositories:
  '''
  All the data about both local and remote repos.
  '''

  def __init__(self):
      self.path_local   = None      # root path of local repo
      #self.proxy        = None      # root path of repo proxy
      self.files        = {}        # dict of filename/file object
      self.files_read   = {}        # dict of file names:true (to check pertenence)
      self.files_local  = {}        # dict of file names:true (to check pertenence)
      self.files_remote = {}        # dict of file names:true (to check pertenence)
      self.recipient    = None      # recipient of GPG encryption
      self.excludes     = {}        # excluded files (patterns)
      self.tmpdir       = None      # temporary directory
      self.gpgcom       = '/usr/bin/gpg --yes  -q' # command to encrypt/decrypt with GPG
      self.walked       = 0            # total considered files
      self.hashed       = 0            # total files for which hash was calculated
      self.diff         = repodiff()   # difference between repos

      # rsync command:
      if o.limit_bw:
          try:
              self.rsync = 'rsync -rto --bwlimit={0:1d}'.format(int(o.limit_bw))
          except:
              self.rsync = 'rsync -rto'
      else:
          self.rsync = 'rsync -rto'

  # ----- #

  def read(self, fromfile):
    if os.path.isfile(fromfile):
      for k,v in FM.conf2dic(fromfile,separator='|').items():
        self.files_read[k] = True
        
        av = v.split(':')
        
        if len(av) < 2:
            msj = 'The fucking length of dictionary entry "%s=%s" is too short!' % (k,v)
            sys.exit(msj)

        if not k in self.files:
            self.files[k] = fileitem(name=k)
            
        self.files_read[k]       = True
        self.files[k].hash_read  = av[0]
        #self.files[k].size_read  = long(float(av[1]))
        #self.files[k].mtime_read = long(float(av[2]))
        self.files[k].size_read  = float(av[1])
        self.files[k].mtime_read = float(av[2])

    else:
      msj = 'Can\'t read from non existint file "%s"!' % (fromfile)
      sys.exit(msj)

  # ----- #

  def dict2files(self, dict, here=True):
      fi = {}

      for k,v in dict.items():
          av = v.split(':')
          
          if len(av) < 2:
              msj = 'The length of dictionary entry "%s|%s" is too short!' % (k,v)
              sys.exit(msj)
          
          fi[k] = fileitem()
          fi[k].name = k
          
          if here:
              fi[k].hash_local  = av[0]
              #fi[k].size_local  = long(float(av[1]))
              #fi[k].mtime_local = long(float(av[2]))
              fi[k].size_local  = float(av[1])
              fi[k].mtime_local = float(av[2])
              
          else:
              fi[k].hash_remote  = av[0]
              #fi[k].size_remote  = long(float(av[1]))
              #fi[k].mtime_remote = long(float(av[2]))
              fi[k].size_remote  = float(av[1])
              fi[k].mtime_remote = float(av[2])
              
      return fi

  # ----- #

  def walk(self):
    '''
    Perform the acts upon each dir in the dir walk (get mtimes, MD5s, etc).
    '''

    for path, dirs, files in os.walk(self.path_local):
      prs = path.replace(self.path_local+'/','')

      # Ignore dif if excluded:
      if not find_exc(prs,self.excludes):
        for file in files:
          self.walked += 1

          fn = '%s/%s' % (path, file)

          # Ignore excluded files and symlinks (in ORs, check first
          # the cheapest and most probable condition, to speed up):
          if not os.path.islink(fn) and not find_exc(fn,self.excludes):
            if path == self.path_local: # current path is root path
                fname = file
            else: # it's a subdir of root
                fname = '%s/%s' % (prs, file)

            if not fname in self.files:
                self.files[fname] = fileitem()

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

            if o.force_hash or time_differ:
	        # Calc hash and save data:
                try:
                    old_hash = self.files[fname].hash_read
                except:
                    old_hash = -1 # if file is not in "read_files", give it a hash no-one can have

                new_hash = self.files[fname].get_hash()
                self.hashed += 1
                
                #if old_hash != new_hash: # (avoid mtime-ing unchanged files)
                if True: # mtime all files, even unchanged ones
                    if o.verbosity > 0:
                        print('[MD5] %s' % (fitit(fname)))
                        
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

                if o.verbosity > 2: # VERY verbose!
                    print('[SKIP]: %s' % (fitit(fname)))

  # ----- #

  def save(self,fn,local=True):
      '''
      Save hashes of current file list in file "fn" (either index.dat, or
      the corresponding file in ~/.gipsync/).
      '''
      if local:
          # Then save locally (generally, to corresponding hash file in ~/.gipsync/).

          string = ''

          for lfn in self.files_local:
              v = self.files[lfn]
              fmt = '{0}|{1.hash_local}:{1.size_local}:{1.mtime_local}\n'
              string += fmt.format(lfn, v)

          string = DM.mk_proper_utf(string)
          f = open(fn,'w')
          f.write(string)
          f.close()

      else:
          # Then save to remote repo, after GPGing it.

          # Save copy to local tmp file:
          tfn = '%s/%s' % (self.tmpdir, fn)
          string = ''

          if o.new:
              # Then we are creating a new repo.
              for lfn in self.files_local:
                  v = self.files[lfn]
                  fmt = '{0}|{1.hash_local}:{1.size_local}:{1.mtime_local}\n'
                  string += fmt.format(lfn, v)
          else:
              for lfn in self.files_remote:
                  v = self.files[lfn]
                  fmt = '{0}|{1.hash_remote}:{1.size_remote}:{1.mtime_remote}\n'
                  string += fmt.format(lfn, v)

          f = open(tfn,'w')
          f.write(string)
          f.close()

          # GPG temporary file tfn:
          fmt = '{0.gpgcom} -r {0.recipient} -o "{0.tmpdir}/{1}.gpg" -e "{2}"'
          cmnd = fmt.format(self, fn, tfn)
          doit(cmnd,2)

          # Upload to remote:
          cmnd1 = '{0} -q '.format(self.rsync)
          cmnd2 = ' "{0}.gpg" '.format(tfn)
          cmnd3 = ' "{0}/{1}.gpg"'.format(self.remote, fn)

          if o.verbosity > 1:
              print('\n' + cmnd1)
              print(' '  + cmnd2)
              print(' '  + cmnd3 + '\n')

          cmnd = cmnd1 + cmnd2 + cmnd3
          doit(cmnd,666)

  # ----- #

  def read_remote(self):
    '''
    Read remote repo metadata.
    '''
    fn   = 'index.dat'
    cmnd = '{0.gpgcom} -o "{0.tmpdir}/{1}" -d "{0.tmpdir}/{1}.gpg"'.format(self, fn)

    if o.verbosity > 0:
        print('\n'+cmnd)
    
    S.cli(cmnd)
    conf = '%s/%s' % (self.tmpdir, fn)

    dict = FM.conf2dic(conf,separator='|')

    for k,v in dict.items():
      av = v.split(':')

      if len(av) < 2:
        msj = 'The length of dictionary entry "%s|%s" is too short!' % (k,v)
        sys.exit(msj)

      if not k in self.files:
          self.files[k] = fileitem(k)

      if not k in self.files_remote:
          self.files_remote[k] = True

      self.files[k].hash_remote  = av[0]
      #self.files[k].size_remote  = long(float(av[1]))
      #self.files[k].mtime_remote = long(float(av[2]))
      self.files[k].size_remote  = float(av[1])
      self.files[k].mtime_remote = float(av[2])

  # ----- #

  def compare(self):
    '''
    Compare local and remote repositories.
    '''

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
                        if o.verbosity > 0:
                            fmt = '\ndiff: local [%s] -- remote [\033[32m%s\033[0m] %s'
                            print(fmt % (T.e2d(lmt), T.e2d(rmt), k))

                    elif lmt > rmt or (o.up and o.force_hash):
                        self.diff.newlocal.append(k)
                        self.diff.newlocal_hash[v.hash_local] = k
                        if o.verbosity > 0:
                            fmt = '\ndiff: local [\033[32m%s\033[0m] -- remote [%s] %s'
                            print(fmt % (T.e2d(lmt), T.e2d(rmt), k))

                    else:
                        fmt = '\033[33m[WARN]\033[0m "{0}" differs, but has same mtime.'
                        print(fmt.format(k))

            else:  # then file exists only locally
                self.diff.local.append(k)
                self.diff.local_hash[v.hash_local] = k

        elif v.hash_remote: # then file exists only remotely
            if not find_exc(k,self.excludes): # ignore files matching some rule
                self.diff.remote.append(k)
                self.diff.remote_hash[v.hash_remote] = k

    # Print summaries if enough verbosity:
    if o.verbosity > 1:
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

  # ----- #

  def upload(self):
      '''
      Upload files from local to remote.
      '''

      # List of files to upload:
      file_list = []
      file_list.extend(self.diff.newlocal)
      file_list.extend(self.diff.local)

      if really_do and file_list:
          # First encrypt files to tmp dir:
          self.encrypt(file_list, o.size_control)

          # Build list of files to upload from tmpdir to remote repo:
          tmpfile = '{0}/filelist.txt'.format(self.tmpdir)
          f = open(tmpfile,'w')
          for h in self.diff.local_hash:
              f.write(h+'.gpg\n')

          for h in self.diff.newlocal_hash:
              f.write(h+'.gpg\n')
          f.close()

          # Finally, upload all of them from tmpdir to remote repo:
          cmnd = '{0.rsync} -vh --progress {0.tmpdir}/data/ --files-from={1} {0.remote}/data/'.format(self,tmpfile)
          doit(cmnd,2)
          os.unlink(tmpfile)

          # Log changes:
          for name in file_list:
              v = self.files[name]
              v.hash_remote  = v.hash_local
              v.size_remote  = v.size_local
              v.mtime_remote = v.mtime_local

  # ----- #

  def encrypt(self, file_list, control=False):
    if file_list:
      print('\n')

    for name in file_list:

      v = self.files[name]

      # Log it:
      if not name in self.files_remote:
        self.files_remote[name] = True

      # GPG it:
      fgpg  = '%s.gpg'     % (v.hash_local)
      lfile = '%s/data/%s' % (self.tmpdir, fgpg)

      # Only GPG if not GPGed yet:
      if not os.path.isfile(lfile) and not control:
        if o.verbosity < 2:
            print('\033[32m[GPG]\033[0m %s' % (fitit(name)))

        cmnd = '%s -r %s -o "%s" -e "%s"' % (self.gpgcom, self.recipient, lfile, v.fullname())
        doit(cmnd,2)

  # ----- #

  def nuke_remote(self):
      '''
      Remove the files not present (or newer) locally from remote repo.
      '''

      if really_do:
          fn_list = []
          nuke_some = False

          # Create a sftp script file to delete remote files:
          tmpfile = '{0}/nuke_remote.sftp'.format(self.tmpdir)
          f = open(tmpfile,'w')
          f.write('sftp {0} <<EOF\n'.format(prefs['REMOTE']))

          for fn in self.diff.remote + self.diff.newlocal:
              hash = self.files[fn].hash_remote
              line = 'rm {0[REPODIR]}/data/{1}.gpg\n'.format(cfg, hash)
              f.write(line)
              nuke_some = True
              fn_list.append(fn)

          f.write('exit\nEOF\n')
          f.close()

          if nuke_some:
              print('\n')

              # Execute sftp script:
              cmnd = 'bash {0}'.format(tmpfile)
              doit(cmnd)

              # Delete nuked files from list of remote files:
              for fn in fn_list:
                  del self.files_remote[fn]

  # ----- #

  def enumerate(self,up=o.up,summary=True):
    if up:
      if not o.safe:
        self.say_nuke_remote()

      if o.size_control:
        if self.diff.local:
          print('\n')

          for name in self.diff.local:
            print('\033[32m[FKUP]\033[0m %s' % (fitit(name)))

        if self.diff.newlocal:
          print('')
      
          for name in self.diff.newlocal:
            print('\033[33m[FKSY]\033[0m %s' % (fitit(name)))

      else:
        if self.diff.local:
          print('\n')

          for name in self.diff.local:
            print('\033[32m[UP]\033[0m %s' % (fitit(name)))

        if self.diff.newlocal:
          print('')
      
          for name in self.diff.newlocal:
            print('\033[33m[SYNC]\033[0m %s' % (fitit(name)))

    else:
      if not o.safe:
        self.say_nuke_local()

      if self.diff.remote:
          print('\n')
          for name in self.diff.remote:
              print('\033[32m[DOWN]\033[0m %s' % (fitit(name)))

      if self.diff.newremote:
          print('\n')
          for name in self.diff.newremote:
              print('\033[33m[SYNC]\033[0m %s' % (fitit(name)))

    if summary:
      self.summary()

  # ----- #

  def say_nuke_remote(self):
      '''
      Print corresponding message for each file we are deleting
      from remote, with nuke_remote().
      '''

      if self.diff.remote:
          print('\n')
          for name in self.diff.remote:
              print('\033[31m[DEL]\033[0m %s' % (fitit(name)))

  # ----- #

  def download(self):
      '''
      Execute the downloading of remote files not in local, or
      superceding the ones in local.
      '''

      # Build list of files to dl from repo (defined by md5 hash):
      tmpfile = '{0}/filelist.txt'.format(self.tmpdir)
      f = open(tmpfile,'w')
      for h in self.diff.remote_hash:
          f.write(h+'.gpg\n')

      for h in self.diff.newremote_hash:
          f.write(h+'.gpg\n')
      f.close()

      # Download all of them from repo to tmpdir:
      fmt  = '{0.rsync} -vh --progress {0.remote}/data/ --files-from={1}'
      fmt += ' {0.tmpdir}/data/'
      cmnd = fmt.format(self,tmpfile)
      doit(cmnd,2)
      os.unlink(tmpfile)

      # List of files we just downloaded:
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

          # Warn of what is being done:
          print('\033[32m[DOWN]\033[0m %s' % (fitit(file.name)))

          # Create local dir to accomodate file, if necessary:
          dir_to = file.fullname().split('/')[:-1]
          dir_to = '/'.join(dir_to)
          if not os.path.isdir(dir_to):
              os.makedirs(dir_to)

          # Source GPG file:
          fn = '%s/data/%s' % (self.tmpdir, fgpg)

          if os.path.exists(fn):
	      # First un-GPG it to tmp dir:
              cmnd = '{0} -o "{1}/tmp" -d "{2}"'.format(self.gpgcom, self.tmpdir, fn)
              doit(cmnd,2)

	      # Then check if not corrupted:
              ref = file.hash_remote
              act = hashof('{0}/tmp'.format(self.tmpdir))
              
              if ref == act: # then it is OK. Proceed:
                  # Move tmp file into actual destination:
                  cmnd = 'mv -f "{0}/tmp" "{1}"'.format(self.tmpdir,file.fullname())
                  doit(cmnd)

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

  # ----- #

  def nuke_local(self):
      '''
      When downloading, delete the local files not in remote repo.
      '''
      for name in self.diff.local:
          v = self.files[name]
          cmnd = 'rm -f "%s/%s"' % (self.path_local, name)
          doit(cmnd,2)

          if really_do:
              del self.files_local[name]

  # ----- #

  def say_nuke_local(self):
    if self.diff.local:
      print('\n')

      for name in self.diff.local:
        print('\033[31m[DEL]\033[0m %s' % (fitit(name)))

  # ----- #

  def summary(self):
    lsl  = len(self.diff.local)
    lsr  = len(self.diff.remote)
    lddl = len(self.diff.newlocal)
    lddr = len(self.diff.newremote)
    size_up = 0
    size_dn = 0
    size_rm = 0

    if not really_do:
      if o.up:
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

    if really_do:
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

      if o.up:
        msj = '{0} {1}'.format("Number of files",up_msj)
        print('{0:30}: {1} ({2})'.format(msj, lsl + lddl, bytes2size(size_up)))

        if not o.safe:
          msj = '{0} {1}'.format("Number of files",rm_msj)
          print('{0:30}: {1} ({2})'.format(msj, lsr, bytes2size(size_rm)))

        print('{0:30}: {1}'.format("Diff files, newer in repo",lddr))

      else:
        msj = '{0} {1}'.format("Number of files",dn_msj)
        print('{0:30}: {1} ({2})'.format(msj, lsr + lddr, bytes2size(size_dn)))
 
        if not o.safe:
            msj = '{0} {1}'.format("Number of files",rm_msj)
            print('{0:30}: {1} ({2})'.format(msj, lsl, bytes2size(size_rm)))

        print('{0:30}: {1}'.format("Diff files, newer locally",lddl))

  # ----- #

  def clean(self):
      '''
      Clean up, which basically means rm tmpdir.
      '''

      global last_action_file

      if not o.keep:
          if os.path.isdir(self.tmpdir):
              shutil.rmtree(self.tmpdir)

      # Delete last action file:
      if os.path.isfile(last_action_file):
          os.unlink(last_action_file)

  # ----- #

  def repo_io(self, up=False, what='all'):
      '''
      This function makes the I/O to the online repo. Basically, it rsyncs the local
      proxy repo (which is an intermediate) to the online one, before and after manipulation,
      in the correct order (I hope).
      '''
      global last_action_file

      if what == 'all':
          # Sync all repo data:
          if up: fmt = '{0.rsync} -vh --progress --delete {0.proxy}/ {0.remote}/'
          else:  fmt = '{0.rsync} -vh --progress --delete {0.remote}/ {0.proxy}/'
        
          cmnd = fmt.format(self)

      else:
          # Then operate only on index.dat.gpg
          if up:
              pass # meaningless
 
          else:
              # Download remote index.dat:
              cmnd1 = '{0.rsync}'.format(self)
              cmnd2 = '  {0.remote}/index.dat.gpg'.format(self)
              cmnd3 = '  {0.tmpdir}/'.format(self)
              
              cmnd = cmnd1 + cmnd2 + cmnd3

      if o.verbosity > 1:
          print('\n' + cmnd1 + '\n' + cmnd2 + '\n' + cmnd3 + '\n')

      # Save command to file, in case we abort mid-rsync:
      f = open(last_action_file,'w')
      f.write(cmnd)
      f.close()

      # Perform rsync and delete just-in-case file afterwards:
      cmnd = '{0} && rm -f "{1}"'.format(cmnd, last_action_file)
      S.cli(cmnd)

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
last_action_file = '{0}/last_action'.format(conf_dir)

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
  repos = repositories()
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
  last_action()

  # Check arguments:
  if args and args[0] == 'all':
      args = prefs['ALL'].split(',')

  # Perform actions for each repo named in args:
  for what in args:
    repos = repositories()

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
        really_do = False
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
                really_do = True

        if really_do:
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
        really_do = False
        answer = False

        if not really_do:
            # Print summary/info:
            repos.enumerate()

            # Ask for permission to proceed:
            lsl  = len(repos.diff.local)
            lsr  = len(repos.diff.remote)
            lddr = len(repos.diff.newremote)

            if lsl + lsr + lddr > 0:
                answer = input('\nAct accordingly (y/N)?: ')
                if answer and 'y' in answer:
                    really_do = True

        if really_do:
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
