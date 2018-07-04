
"""A cli tool which creates the skeleton for a python package directory.

Creates the following structure:
	setup.py         Contains name, version, author, dependencies, etc
	NAME/
		__init__.py  Empty
		__main__.py  Optionally monkey patches, configures logging, imports and runs main.main() with argh
		main.py      Contains main()
"""

import os

from easycmd import cmd
from scriptlib import with_argv

__REQUIRES__ = ['easycmd', 'scriptlib']


def main(
	name,
	author=None, # default taken from git config
	email=None, # default taken from git config
	description=None, # will prompt user by default. set to '' to simply omit.
	dependencies=None, # comma-seperated list
	gevent=False, # enables gevent
):

	if author is None:
		author = cmd(['git', 'config', 'user.name']).strip()
	if email is None:
		email = cmd(['git', 'config', 'user.email']).strip()

	dependencies = dependencies.split(',') if dependencies else []
	dependencies.append('argh')
	if gevent:
		dependencies.append('gevent')

	if description is None:
		description = raw_input("Enter a description: ")

	write('setup.py',
		"from setuptools import setup, find_packages",
		"",
		"setup(",
		"\tname={name!r},",
		"\tversion='0.0.1',",
		"\tauthor={author!r},",
		"\tauthor_email={email!r},",
		"\tdescription={description!r},",
		"\tpackages=find_packages(),",
		"\tinstall_requires=[{dep_lines}",
		"\t],",
		")",
		name=name,
		author=author,
		email=email,
		description=description,
		dep_lines=(
			'\n' + '\n'.join("\t\t{!r},".format(dep) for dep in dependencies)
			if dependencies else ''
		),
	)

	os.mkdir(name)

	write(os.path.join(name, '__init__.py'))

	monkey = ''
	if gevent:
		monkey = (
			"\n"
			"import gevent.monkey\n"
			"gevent.monkey.patch_all()"
		)

	write(os.path.join(name, '__main__.py'),
		"{monkey}",
		"",
		"import logging",
		"logging.basicConfig(level='DEBUG')",
		"",
		"import argh",
		"",
		"from {name}.main import main",
		"",
		"argh.dispatch_command(main)",
		name=name, monkey=monkey
	)

	write(os.path.join(name, "main.py"),
		"",
		"def main():",
		"\tpass",
	)


def write(path, *lines, **variables):
	"""Write content to path. Content is all lines joined on newline, then formatted with variables."""
	if lines:
		content = '\n'.join(lines) + '\n'
		content = content.format(**variables)
	else:
		# special case: empty file has no trailing newline
		content = ''
	with open(path, 'w') as f:
		f.write(content)


if __name__ == '__main__':
	with_argv(main)()
