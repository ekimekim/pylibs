
"""A simple plugin system for dynamically loadable components

A Plugin is an object which can be dynamically loaded, unloaded or reloaded
(ie. to update it to use the latest code off disk).
When a plugin is unloaded, the entire module is unloaded. For this reason, plugins should always
exist in their own seperate modules.

The reccomended way to use Plugins is to subclass the Plugin class with your specific kind of plugin, eg.
>>> class FooPlugin(Plugin):
...     \"\"\"Info on what methods the plugin should implement goes here\"\"\"

This ensures that multiple plugin systems do not interfere with each other, eg. both FooPlugins and BarPlugins
can be used in the same process at the same time, and are managed seperately.

A Plugin subclass contains various classmethods that are used to manipulate the plugins of that class.
See the method docs for more info.

A module that implements a plugin will generally define a subclass of that plugin, then instantiate it.
However, you're free to instantiate as many plugins as you want - just be aware that they are loaded and
unloaded as a single unit. The instances are deleted before unloading.
For example:
>>> from myapplication import FooPlugin
>>> class ExampleFooPlugin(FooPlugin):
...     def __init__(self):
...         print "plugin loaded"
...     def __del__(self):
...         print "plugin unloaded"
...
>>> example = ExampleFooPlugin()

As an alternate example:
>>> from myapplication import MyCannedPlugin
>>> # these plugins are both loaded together and unloaded together - you can't load one without the other
>>> some_vars_plugin = MyCannedPlugin("some vars", 123)
>>> other_vars_plugin = MyCannedPlugin("some other vars", 456)
"""

__REQUIRES__ = ['classtricks']

import sys
import gc
from importlib import import_module

from classtricks import classproperty, TracksInstances


class Referenced(Exception):
	pass # TODO


class Plugin(TracksInstances):
	# Implementation Details:
	# We manage the life cycle of a plugin instance with careful use of references.
	# The plugin's module should contain a reference to the plugin instance (generally as a global, see examples)
	# Thus the plugin instance is kept alive via sys.modules -> module's globals -> instance
	# We only reference it weakly here.
	# When we unload the module (by removing it from sys.modules), this causes the chain to break and the instance
	# to die.


	# Set this to a list of paths to search for plugins in.
	# Regardless of these paths, plugins in sys.path are also valid.
	# The default value is a tuple so it's immutable, so you can't accidentially affect ALL plugins by appending.
	load_paths = ()

	@classproperty
	def loaded(cls):
		"""Get the set of all plugins loaded"""
		return cls.get_instances()

	@classmethod
	def load(cls, name):
		"""Attempt to load a module of the given name. If the load_paths class variable is set,
		it will search those paths preferentially, but always default back to sys.path.
		Does nothing if module is already loaded - use reload to force the module to update.
		Returns the module that was loaded (though it may have already existed), however you generally
		don't care about this - use cls.loaded instead.
		"""
		old_path = sys.path
		try:
			sys.path = list(cls.load_paths) + sys.path
			return import_module(name)
		finally:
			sys.path = old_path

	@classmethod
	def _resolve_module(cls, module):
		"""Internal method that strongly checks that module is actually loaded and not "weird",
		and returns (name, module object). Module can be module name or module object.
		Raises ValueError if module isn't loaded or is weird."""
		if isinstance(module, basestring):
			name = module
			if name not in sys.modules:
				raise ValueError("No such module")
			module = sys.modules[name]
		else:
			name = module.__name__
			if sys.modules.get(name, None) is not module:
				raise ValueError("Module not in sys.modules")
		return name, module

	@classmethod
	def unload(cls, module, safe=True):
		"""Attempt to unload the given module, which can either be an actual module object or the name of a module
		as per load(). If safe=True (the default), then it will fail to unload if any external references to the
		module exist. In other words, if safe is False, then the module might not actually be unloaded at all,
		which (in the case of reload()) could result in two versions of the module being in use at the same time!
		Raises Referenced() if safe is True and module cannot be unloaded.
		Does nothing if given module is not loaded.
		"""
		try:
			name, module = cls._resolve_module(module)
		except ValueError:
			return # no action to take

		# we want to be able to undelete the module if not all references disappear,
		# but we obviously can't hold on to our own reference (and modules can't be weakref'd)
		# so we use a hack: Grab our id() now, and scan gc.get_objects() later.
		# There is a danger of a new object being created with the same id in the interim, so
		# we take care to match on all of id, type and name.
		get_info = lambda m: (id(m), type(m), getattr(m, '__name__', None))
		module_info = get_info(module)
		module = None
		def find_module():
			for obj in gc.get_objects():
				if get_info(obj) == module_info:
					return module
			return None

		try:
			del sys.modules[name]
			if not safe:
				return
			module = find_module()
			if module is None:
				return
			# ok, so it wasn't deleted immediately...let's try harder, find ref loops
			gc.collect()
			module = find_module()
			if module is None:
				return
			raise Referenced(name, module)
		except:
			# revert the unload (if we can)
			if module is None:
				module = find_module()
			if module is not None:
				sys.modules[name] = module
			raise

	@classmethod
	def reload(cls, module, safe=True):
		"""Unload then load the given module. Args are as per unload().
		Note that if the load fails, the module will be left unloaded.
		"""
		try:
			name, module = cls._resolve_module(module)
		except ValueError:
			pass
		else:
			# only unload if no ValueError
			cls.unload(module, safe=safe)
		return cls.load(name)
