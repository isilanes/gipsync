import os
import gnupg

from libgipsync import core

class FileItem(object):
    """All characteristics of a given file."""

    def __init__(self, name, cfg):
        self.name = name
        self.cfg = cfg
        self.hash = None
        self.size = 0
        self.mtime = 0

    @property
    def fullpath(self):
        """Return full path."""

        return os.path.join(self.cfg.conf["LOCALDIR"], self.name)

    def get_hash(self):
        """Calculate and return hash function of file."""

        return core.hashof(self.fullpath)

    def get_size(self):
        """Calculate and return file size of file."""

        return os.path.getsize(self.fullpath)


class Repo(object):

    def __init__(self, what, cfg):
        self.what = what
        self.files = {
            "actual": {}, # dict of path -> FileItem for actual files
            "read": {},   # dict of path -> FileItem for files read from log (local) or index (remote)
        }
        self.cfg = cfg # Configuration object holding all config and prefs
        self.walked = 0 # total considered files
        self.hashed = 0 # total local files for which hash is computed

    def dict_to_read_files(self, mydict):
        """Populate self.files["read"], when passed a dictionary read from log or index."""

        for k,v in mydict.items():
            try:
                hash, sz, mtime = v.split(':')
            except:
                msg = "[WARNING] Could not process line: {line}".format(line=v)
                print(msg)
                continue
            
            self.files["read"][k] = FileItem(name=k, cfg=self.cfg)
            self.files["read"][k].hash = hash
            self.files["read"][k].size = int(float(sz))
            self.files["read"][k].mtime = int(float(mtime))


class RemoteRepo(Repo):

    @property
    def index_gpg_fn(self):
        """Return full path of index.gpg."""

        return os.path.join(self.cfg.prefs["PIVOTDIR"], self.cfg.conf["REPODIR"], 'index.dat.gpg')

    def read_index_gpg(self):
        """Read metadata from remote index.gpg."""

        core.say("Reading remote index.dat.gpg...")

        # Decrypting object:
        gnupghome = os.path.join(os.environ["HOME"], ".gnupg")
        gpg = gnupg.GPG(gnupghome=gnupghome)

        # Read and decrypt index file into string:
        with open(self.index_gpg_fn) as f:
            encrypted = f.read()
            decrypted = gpg.decrypt(encrypted)

        # Turn decrypted text into dictionary, and save into self:
        index_dict = core.string2dict(decrypted.data, separator="|")
        self.dict_to_read_files(index_dict)


class LocalRepo(Repo):

    @property
    def md5_fn(self):
        """Return full path of .md5 file."""

        return os.path.join(self.cfg.basedir, '{w}.md5'.format(w=self.what))

    def read_local_md5(self):
        """Read metadata from local .md5 file."""

        core.say("Reading local .md5 file...")

        # Read and decrypt index file into string:
        with open(self.md5_fn) as f:
            content = f.read()

        # Turn into dictionary, and save into self:
        index_dict = core.string2dict(content, separator="|")
        self.dict_to_read_files(index_dict)

    def walk_local_tree(self):
        """Walk the local file tree, and get the info (mtimes, MD5s, etc) required."""
  
        local_basedir = self.cfg.conf['LOCALDIR']
  
        for path, dirs, files in os.walk(local_basedir):
            rel_path = path.replace(local_basedir+'/','')
  
            # Ignore whole directory if excluded:
            if not core.is_item_in_patterns(rel_path, self.cfg.conf['EXCLUDES']):
                for file in files:
                    self.walked += 1
      
                    fn = os.path.join(path, file)
      
                    # Ignore excluded files and symlinks (in ORs, check first
                    # the cheapest and most probable condition, to speed up):
                    if not os.path.islink(fn) and not core.is_item_in_patterns(fn, self.cfg.conf['EXCLUDES']):
                        if path == local_basedir: # current path is root path
                            fname = file

                        else: # it's a subdir of root
                            fname = os.path.join(rel_path, file)

                        # Use mtime to skip if unchanged:
                        mtime_actual = int(os.path.getmtime(fn))

                        try:
                            mtime_read = self.files["read"][fname].mtime
                            mtime_equal = mtime_actual == mtime_read
                        except:
                            mtime_equal = False

                        if not mtime_equal:
                            # Calc hash and save data:
                            core.say(u'[MD5] {fn}'.format(fn=core.fitit(fname)))
                            print mtime_actual, mtime_read
                            self.hashed += 1
                            
                            FI = FileItem(name=fname, cfg=self.cfg)
                            FI.hash = FI.get_hash()
                            FI.size = FI.get_size()
                            FI.mtime = mtime_actual

                            self.files["actual"][fname] = FI
        
