gipsync
=======

A GPG/rsync tool to syncronize your files.

Introduction
------------

gipsync lets you syncronize two or more local directories (for example, your HOME dir in two different computers), that might not be directly connected. It does so by using a third resource (for example a web server) that can be accessed to and from the local ones. We call this third resource a "pivot". The contents of a local resource are syncronized first to the pivot, and they can afterwards be syncronized down from the pivot to other local resources.

The main characteristic of gipsync is that all content stored in the pivot is encrypted, so third parties controlling the pivot (e.g. it's someone elses computer, a web server, etc.), can not gain access to your data. Your files are encrypted locally, then transferred, so there is never a clear copy of any data on the pivot.

Due to gipsync having to be able to create, delete and read files in the pivot, you will need SSH access to it (rssh suffices). Basically, you'll need a user there, and the capability to perform a successfull SFTP connection.

How it works
------------

Each directory that we want gipsync to syncronize will be referred to as a "repo". A repo is simply a name tag given to the directory, so that we can configure it.

Each time we use gipsync on a repo, it will begin by making a list ("index") of the files in the local repo. Next, it will compare it with the index file of the repo instance in the pivot. Then (and after we agree to it), it will proceed to upload the files that exist in the local repo but not in the pivot (or are newer locally), and delete from the pivot the files that don't exist locally. Finally, the index in the pivot will be substituted by a copy of the local index. If we are syncing down instead, the inverse will be true: files not in pivot will be deleted locally, and files only in pivot (or different and newer) will be downloaded.

The pivot location for each repo consists of a directory containing a file named "index.dat.gpg" and a dir named "data/". The file contains the index of the present contents of the repo in the pivot, and the data/ dir contains all the actual files, with no dir structure (this information is saved in the index file). The files are saved in encrypted form, and their names are substituted by the md5sum string of their contents, so they are completely opaque to any eavesdropping by third parties. For example, consider the file "example.txt", with the following md5sum:

    $ md5sum example.txt
    0ad053233751e0c872b1271a44b22e52  example.txt

Then it would be saved under the data/ dir, as "0ad053233751e0c872b1271a44b22e52.gpg", after being encrypted with GPG.

How to use it
-------------

First, you will need some configuration files, placed at $HOME/.gipsync/. You will need a main "config" file, and some whatever.* files for a repo called "whatever". You can find sample configuration files in the examples/ dir distributed with gipsync.

* config

This file contains variable=value pairs, with the following meaning:

REMOTE: the complete string we would use to SFTP to the folder devoted to gipsync in the pivot, with the general syntax "user@ip:path".
RECIPIENT: a string we would (and will) give to the "--recipient" option of GPG, to encrypt/decrypt in the name of this identity.
ALL: a comma-separated list of repo names, that will be synced if gipsync is called with the reserved repo name "all", instead of a given repo name.
PIVOTDIR: tbd

* whatever.conf

Main configuration file for repo "whatever". It also contains variable=value pairs:

REPODIR: the name of the subdir of REMOTE (see above) in which the contents of repo whatever are stored. I generally use the md5 of the repo name, but any string is acceptable.
LOCALDIR: the path of the local directory whose content is synced when we refer to this repo.

* whatever.md5

Index file for repo "whatever". It contains the required info (name, md5sum, size, mtime) of each file in LOCALDIR.

* whatever.excludes

Exclude file for repo "whatever". Each line will be used as a reference string. Any path in LOCALDIR that matches (wholly or partially) any reference string, will be ignored by gipsync.

Deployment
----------

Export relevant key from computer it already works on:

    $ gpg --export-secret-keys -a 12345678 > secret.asc 

Import key in computer where we want to deploy, and edit it to give it ultimate trust:

    $ gpg --import ~/secret.asc 
    $ gpg --edit-key 12345678
      ... then: "trust"
      ... then: "5"
      ... then: "y"
      ... then: "quit"

Configure GNUPG agent:

    $ vi ~/.gnupg/gpg.conf

and uncomment this line:

    use-agent


You should install a PIN entry program, such as pinentry-curses in Debian/Ubuntu, and configure the gpg-agent program to use it:

    $ vi ~/.gnupg/gpg-agent.conf

and add the line:

    pinentry-program /usr/bin/pinentry-curses

And then reload the agent:

    $ gpg-connect-agent reloadagent /bye
