
"""A module for performing global program configuration.

Config files are fully fledged python source files,
and their global namespace becomes the config dict.

While not required, config items can be pre-registered - see register()
"""

import os
import sys
import types
from collections import namedtuple
from pprint import pformat

from scriptlib import parse_argv

__REQUIRES__ = ['scriptlib']


Registration = namedtuple('Registration', ['short_opts', 'long_opts', 'env_vars', 'map_fn'])


class Config(dict):
	"""Represents a single configuration dict. Contains extra methods for help
	with loading config.
	All load and from_* methods will perform an *update* operation - ie. order matters.

	Keys can be accessed with standard dict methods, or alternately via attribute access.
	You should ensure the attribute you're trying to access doesn't conflict with any
	pre-existing attribute or method.
	Keys retrieved with this method will return None if not present.
	"""

	def __init__(self, *args, **kwargs):
		super(Config, self).__init__(*args, config=self, **kwargs)
		self.registered = {}

	def __getattr__(self, name):
		if name in self:
			return self[name]
		return None

	def load(self, conf_file=None, argv=None, env=None, user_config=False, **kwargs):
		"""Populate the config object from the sources specified by kwargs:
		Source kwargs in order of precedence (least overriding first):
			conf_file: Load items from given filepath or list of filepaths.
			           See from_file().
			env: Load items from given environment dict, or os.environ if this option is True.
			     See from_env().
			argv: Load items from given command args, or sys.argv if this option is True.
			      See from_argv().
			Any extra keys passed as kwargs to this function.
		Extra options:
			user_config: If true (the default), it will register an action so that the act of
			             setting the conf_file key from argv or env (as --conf, --conf-file,
			             or CONF_FILE) will immediately load the given conf file.
			             For example, say the file "foo.py" sets the "foo" option to "bar".
			             Then the following command args:
			                 --foo=baz --conf=foo.py
			             would resolve to "foo": "bar", but the similar args:
			                 --conf=foo.py --foo=baz
			             would resolve to "foo": "baz".
		"""
		if user_config:
			def map_fn(path):
				self.from_file(path)
				return path
			self.register('conf_file', long_opts=['conf', 'conf-file'], map_fn=map_fn)

		if conf_file:
			if isinstance(conf_file, basestring):
				conf_file = conf_file,
			try:
				iter(conf_file)
			except TypeError:
				conf_file = str(conf_file),
			self.from_file(*conf_file)

		if env:
			self.from_env(None if env is True else env)

		if argv:
			self.from_argv(None if argv is True else argv)

		self.update(kwargs)

	def load_all(self, **extras):
		"""A shortcut for load() with all default sources enabled, including user config."""
		self.load(argv=True, env=True, user_config=True, **extras)

	def from_file(self, *conf_files):
		"""Update config from given conf files, in order (ie. last overrides all others).
		conf files should be python source files, which will be executed with this object
		as their global namespace.
		Note that user expansion is performed on the file paths.
		For advanced operations (eg. bulk update or recursively calling from_file() on other files),
		we set the global "config" to this object, avoiding the need for explicit globals() calls.
		Note that errors in the sourced files *will* be allowed to raise.
		"""
		for conf_file in conf_files:
			execfile(os.path.expanduser(conf_file), self)

	def from_argv(self, argv=None, convert=True):
		"""Update config from given command line args (default sys.argv, without progname) as follows:
			Short and long form options are extracted in the usual way.
				Since we don't know which options should expect an extra arg
				(ie. '--foo bar' could mean "the foo option has value bar" or it
				 could mean "the foo flag is set, and bar is a positional arg),
				we only allow associated values in the form '--foo=bar' and '-f=bar'.
				All non-option args are treated as positional.
			Each option is mapped as follows:
				* If the option has been registered with self.register(), the mapping
				  defined there is used to convert the arg name.
				* If convert is True (the default), the arg name is converted as follows:
					Names are lower-cased, and '-' is replaced with '_'
						For example, '--Foo-bar' becomes 'foo_bar'
		Returns the list of positional args.
		"""
		if argv is None:
			argv = sys.argv[1:]
		args, options = parse_argv(argv)

		registered_opts = {}
		for name, reg in self.registered.items():
			for opt in reg.short_opts + reg.long_opts:
				registered_opts[opt] = name

		for name, value in options.items():
			if name in registered_opts:
				name = registered_opts[opt]
			elif convert:
				name = name.lower().replace('-', '_')
			self[name] = self.apply_map(name, value)

	def from_env(self, env=None):
		"""Update config from the given environment dict (default os.environ).
		If any environment vars match an option registered with self.register(),
		that option is set from that env var's value (see register()).
		Otherwise use as is."""
		if env is None:
			env = os.environ

		registered_vars = {}
		for name, reg in self.registered.items():
			for var in reg.env_vars:
				registered_vars[var] = name

		for name, value in env.items():
			if name in registered_vars:
				name = registered_vars[var]
			self[name] = self.apply_map(name, value)

	def register(self, name, short_opts=[], long_opts=[], env_vars=[], default=None, map_fn=None):
		"""Register a config option with some extra helper information:
			short_opts: Short option command line args to treat as meaning this config option,
			            eg. register('filepath', short_opts=['f', 'p'])
			long_opts: Long option command line args to treat as meaning this config option,
			           eg. register('filepath', long_opts=['file', 'path'])
			env_vars: Environment vars (in order of precedence) to treat as meaning this option,
			          eg. register('filepath', env_vars=['MYPROG_FPATH'])
			default: The default value to take if not given (cannot be None).
			map_fn: Optional function to map the given value of the option to a usable value.
			        For example, an option that is intended to be an integer will have a string
			        value if it is populated from an env var or command line arg.
			        If map_fn=int, the value will be converted to int before being used.
					NOTE: The map_fn will only be applied to values loaded from argv or env.
					      It also does not affect values loaded before the name was registered.
		"""
		self.registered[name] = Registration(short_opts, long_opts, env_vars, map_fn)
		if default is not None:
			self.setdefault(name, default)

	def get_registered(self):
		"""Returns a dict containing only registered config options.
		This may be useful to seperate actual options from side-effects of file exec
		(such as modules and other incidential global variables) when logging or
		formatting a report."""
		return {name: self[name] for name in self.registered if name in self}

	def get_most(self):
		"""Makes an educated guess at what keys are "important" and which are side effects
		of file exec, without relying on an explicit register for all items.
		Strips out:
			itself
			all modules
			vars starting with _
		"""
		return {name: self[name] for name in self if all((
			self[name] is not self,
			not isinstance(self[name], types.ModuleType),
			not name.startswith('_'),
		))}

	def format(self):
		"""Returns a human-readable formatted string representing the config contents."""
		return pformat(self.get_most())

	def apply_map(self, name, value):
		"""Helper function that applies the map_fn for name (if any) to value."""
		map_fn = None
		if name in self.registered:
			map_fn = self.registered[name].map_fn
		if map_fn:
			return map_fn(value)
		return value


# We make available a default config object as a global
CONF = Config()


if __name__ == '__main__':
	# for running examples
	CONF.load_all()
	print CONF.format()
