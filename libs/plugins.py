
"""A plugin system for dynamically loadable components

A Plugin is an object which can be dynamically loaded, unloaded or reloaded
(ie. to update it to use the latest code off disk).
When a plugin is unloaded, the entire module is unloaded. For this reason, plugins should always
exist in their own seperate modules.
Plugins can be enabled and disabled seperately, this does NOT reload the code but simply halts the plugin's
functionality.

The reccomended way to use Plugins is to subclass the Plugin class with your specific kind of plugin, eg.
>>> class FooPlugin(Plugin):
...     \"\"\"Info on what methods the plugin should implement goes here\"\"\"

This ensures that multiple plugin systems do not interfere with each other, eg. both FooPlugins and BarPlugins
can be used in the same process at the same time, and are managed seperately.
We will henceforth refer to a subclass of Plugin used in this way as a "plugin superclass".

A plugin superclass contains various classmethods that are used to manipulate the plugins of that class.
See the method docs for more info.

To implement a plugin, you should subclass your plugin superclass in a seperate module.
When a module is loaded, the plugin is then said to also be "loaded".
Note that loading/unloading is done at the module level, so care should be taken in cases where multiple
plugin superclasses may be in use.

However, once the plugin is loaded, it simply means the code has been read, and the subclass has been defined.
To instantiate your plugin, you need to "enable" the plugin. A plugin can be enabled multiple times,
with different init arguments. You can disable the plugin later.
Plugins are automatically disabled before they are unloaded.
In a reload, plugins are re-enabled afterwards.

Anatomy of a plugin:
	name: The plugin should provide an attribute "name" that is the friendly name used to refer to it.
	      Plugins that do not define a name cannot be enabled.
	cleanup(): Called when the plugin is disabled. Must stop all operations the plugin is involved with,
	           and break all references to it.
	args: This attribute is set by Plugin.__init__() and shouldn't be modified.
	      It specifies the args it was initialized with. These args must be specified to later
	      disable this instance of the plugin.

Full example:
	(we use here some fictional "context" that has the ability to manage callbacks, for an example use case)
	base.py:
		class MyPlugin(Plugin):
			load_paths = ["./plugins"]
			def __init__(self, context):
				self.context = context
				self.init()
			def init(self):
				pass

	plugins/foo.py:
		from base import MyPlugin
		class FooPlugin(MyPlugin):
			def init(self):
				self.context.add_callback(self.callback)
			def callback(self):
				print "Called back!"
			def cleanup(self):
				self.context.rm_callback(self.callback)

	>>> MyPlugin.load('foo')
	>>> MyPlugin.enable('foo', context)
	>>> context.trigger_callbacks()
	Called back!
	>>> MyPlugin.enable('foo', other_context)
	>>> MyPlugin.disable('foo', context)
	>>> context.trigger_callbacks()
	>>> MyPlugin.unload('foo') # disables ('foo', other_context) automatically

"""

# TODO review for exception handling, don't let plugin-local exceptions propogate


__REQUIRES__ = ['classtricks', 'modulemanager']

import weakref
from types import ModuleType

import modulemanager
from classtricks import classproperty, TracksInstances, issubclass, get_all_subclasses


class Plugin(TracksInstances):

	# Name for your plugin. Must be unique within the context of your plugin superclass.
	name = None

	# Set this to a list of paths to search for plugins in.
	# Regardless of these paths, plugins in sys.path are also valid.
	# The default value is a tuple so it's immutable, so you can't accidentially affect ALL plugins by appending.
	load_paths = ()

	# Note that this set() is shared between all subclasses of Plugin.
	# It contains all enabled plugin instances.
	# To save on bookkeeping, we make use of cls.get_instances() instead of this set.
	# However, those are obtained via weak references. This set is the only place we strongly refer
	# to an enabled plugin. Thus, we can destroy the instance simply by removing it from the set.
	_enabled = set()

	@classproperty
	def loaded(cls):
		"""Get the set of all plugins loaded"""
		return set(subcls for subcls in get_all_subclasses(cls) if subcls.name)

	@classproperty
	def loaded_by_name(cls):
		"""Convenience method, returns a dict {name: plugin} for all loaded plugin classes."""
		return {plugin.name: plugin for plugin in cls.loaded}

	@classproperty
	def enabled(cls):
		"""Get the set of all plugin instances, ie. plugins that are enabled.
		Note that there may be more than one instance of a given plugin if they have different init args.
		You may want to check plugin.args.
		"""
		return set(cls.get_instances())

	@classmethod
	def get_plugin(cls, plugin, *args):
		"""Returns the plugin of the given name (or given plugin class) that was enabled with the
		given init args. Returns None if no such plugin has been enabled."""
		if not issubclass(plugin, cls):
			if plugin not in cls.loaded_by_name:
				return
			plugin = cls.loaded_by_name[plugin]
		for instance in plugin.enabled:
			if instance.args == args:
				return instance

	@classmethod
	def plugins_of(cls, module):
		"""Returns the set of Plugins that are defined in a given module.
		You may specify the module object or the module name."""
		name, module = modulemanager._resolve_module(module)
		return set(subcls for subcls in cls.loaded if subcls.__module__ == name)

	@classmethod
	def load(cls, name, load_paths=[]):
		"""Attempt to load a module of the given name. If the load_paths class variable is set,
		it will search those paths preferentially, but always default back to sys.path.
		If the load_paths argument is given, these paths are in preference to the load_paths class variable also.
		Returns the plugins that were found in that module (note that they may not be new if the module
		was already loaded).
		Does nothing if module is already loaded - use reload to force the module to update.
		"""
		modulemanager.load(name, list(load_paths) + list(cls.load_paths))
		return cls.plugins_of(name)

	@classmethod
	def enable(cls, plugin, *args):
		"""Enable the given plugin, possibly with init args.
		Plugin may be a plugin name or a plugin subclass itself.
		If the plugin is already enabled, no action is taken.
		May raise KeyError if no plugin exists of given name.
		"""
		if not issubclass(plugin, cls):
			plugin = cls.loaded_by_name[plugin]
		instance = cls.get_plugin(plugin, *args)
		if not instance:
			instance = plugin(*args)
			if getattr(instance, 'args', None) != args:
				raise Exception("plugin.args did not match init args -  overrided __init__ without calling super?")
			cls._enabled.add(instance)
		return instance

	@classmethod
	def disable(cls, plugin, *args, **kwargs):
		"""Disable the specified plugin. The plugin can be specified in the following ways:
			a plugin instance: the exact instance to disable
			a plugin name, and init args: disable the plugin of that name with those init args
			a plugin class, and init args: disable the plugin of that class with those init args
		Does nothing if the enabled plugin cannot be found (ie. if its already disabled).
		Takes the optional kwargs:
			safe: Whether or not to strongly verify that the plugin is fully disabled.
			      In particular we check that, after cleanup is called, the instance is no longer referenced.
			      Obviously, this doesn't work so well if you're passing the instance as an argument.
			      If True and the instance is still referenced, we raise modulemanager.Referenced().
			      The default is True.
		"""
		safe = kwargs.pop('safe', True)
		if kwargs:
			raise TypeError("Unexpected keyword args: {}".format(kwargs))
		if not isinstance(plugin, cls):
			plugin = cls.get_plugin(plugin, *args)
			if not plugin:
				return
		if plugin not in cls._enabled:
			return # weird case: plugin exists but isn't enabled. Created independently, or a double-disable?
		plugin.cleanup()
		cls._enabled.remove(plugin)
		plugin_ref = weakref.ref(plugin)
		del plugin
		if safe and plugin_ref():
			raise modulemanager.Referenced()

	@classmethod
	def disable_all(cls, plugin, safe=True):
		"""As disable(), but disables all instances of plugin.
		plugin can be a plugin name or a plugin class.
		"""
		if not issubclass(plugin, cls):
			if plugin not in cls.loaded_by_name:
				return
			plugin = cls.loaded_by_name[plugin]
		# we need to be careful here not to be holding references to any instances
		enabled_args = map(lambda instance: instance.args, plugin.enabled)
		for args in enabled_args:
			cls.disable(plugin, *args, safe=safe)

	@classmethod
	def _resolve_module(cls, arg):
		"""Shared input handling for unload and reload. Returns (name, module), or (None, None) for no match."""
		if not isinstance(arg, ModuleType):
			if isinstance(arg, cls):
				arg = type(arg)
			if not issubclass(arg, cls):
				if arg not in cls.loaded_by_name:
					return None, None
				arg = cls.loaded_by_name[arg]
			arg = arg.__module__
		try:
			return modulemanager._resolve_module(arg)
		except ValueError:
			return None, None

	@classmethod
	def unload(cls, target, safe=True):
		"""Attempt to unload the given module, or the module that defines the given plugin.
		Target can be a module object, a plugin class, or a plugin name.
		Note that all plugins defined by the module will be disabled.
		Has no effect if target is not loaded.
		safe arg is as per disable() and modulemanager.unload().
		"""
		name, module = cls._resolve_module(target)
		if not module:
			return
		del module # we shouldn't be keeping a reference to it, we can work with name alone
		for plugin in cls.plugins_of(name):
			cls.disable_all(plugin, safe=safe)
		modulemanager.unload(name)

	@classmethod
	def reload(cls, target, load_paths=[], safe=True):
		"""Unload then load the specified module. Args are as per unload().
		Any enabled plugins will be disabled, then re-enabled after.
		Note that in the event of a failure, the module may or may not be loaded, and plugins may or may
		not be enabled.
		load_paths is as per load().
		safe is as per unload().
		Returns new module.
		"""
		name, module = cls._resolve_module(target)
		if not module:
			return
		del module # we shouldn't be keeping a reference to it, we can work with name alone
		# there's no good reason for using a lambda here - but it prevents the variables from leaking,
		# which prevents accidential references.
		enabled = (lambda: {plugin.name: [instance.args for instance in plugin.enabled]
		                    for plugin in cls.plugins_of(name)})()
		cls.unload(name, safe=safe) # also disables
		module = cls.load(name, load_paths)
		for plugin, enabled_args in enabled.items():
			for args in enabled_args:
				cls.enable(plugin, *args)
		return module

	def __init__(self, *args):
		self.args = args

	def cleanup(self):
		"""This method must disable plugin operations and break all references to this instance."""
		pass
