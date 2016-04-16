
"""Returns git information about the given file.

The simplest way to use this is as a module global:
	GIT_INFO = git_info(__FILE__)

"""

__REQUIRES__ = ['easycmd']

import os

from easycmd import cmd, FailedProcessError


def git(target_path, command, *args):
	return cmd(['git', '-C', target_path, command] + list(args))


def git_info(target_path, fetch=True):
	"""Return the following info about the git repository that filepath is in:
		'repo': path to repo top level
		'commit': commit id as string
		'full_ref': branch, tag, etc (may be None if no ref checked out)
		'ref': Shorter version of full_ref, omitting "refs/.../" (eg. "refs/heads/") if unambiguous
		'ahead': number of commits ahead of upstream (may be None if no upstream)
		'behind': number of commits behind upstream (may be None if no upstream)
	Results are returned as a dict.
	If fetch = True, do a git fetch to get up-to-date info for remote upstreams.
	"""

	if os.path.isfile(target_path):
		target_path = os.path.dirname(target_path)

	# this might fuck up if someone puts a newline in the repo path
	# but it's more trouble than its worth to fix it
	rev_parse = git(target_path, 'rev-parse',
		'--show-toplevel', # returns repo path
		'HEAD', # returns commit id
		'--symbolic-full-name', 'HEAD', # returns full ref, or omitted
		'--abbrev-ref', 'HEAD', # returns short ref, or omitted
	)

	lines = rev_parse.strip().split('\n')
	if len(lines) == 4:
		full_ref, ref = lines[2:]
		lines = lines[:2]
	else:
		full_ref = None
		ref = None
	if len(lines) != 2:
		raise ValueError("Bad output from git rev-parse: {!r}".format(rev_parse))
	repo_path, commit_id = lines

	ahead = None
	behind = None
	if ref:
		try:
			git(target_path, 'rev-parse', '@{u}')
		except FailedProcessError:
			pass # no upstream
		else:
			if fetch:
				git(target_path, 'fetch')
			ahead = len(filter(None, git(target_path, 'rev-list', '@{u}..').split('\n')))
			behind = len(filter(None, git(target_path, 'rev-list', '..@{u}').split('\n')))

	return {
		'repo': repo_path,
		'commit': commit_id,
		'full_ref': full_ref,
		'ref': ref,
		'ahead': ahead,
		'behind': behind,
	}
