
"""A library for dynamically loading modules

Allows individual python modules to be loaded at runtime, from arbitrary paths.
"""

import sys
import gc
from importlib import import_module


class Referenced(Exception):
	pass # TODO


def is_loaded(module):
	"""Return boolean of whether given module is currently loaded.
	Module can be a name, or a module object (a module object is "unloaded" if it is not the "canonical"
	version of that module that you would get by using "import MODULE").
	In most cases, you should prefer to just load() or unload() regardless as both operations
	are idempotent."""
	try:
		_resolve_module(module)
	except ValueError:
		return False
	return True


def load(name, paths=[]):
	"""Attempt to load a module of the given name. If paths is given, it will search those paths preferentially,
	but always default back to sys.path.
	Does nothing if module is already loaded - use reload to force the module to update.
	Returns the module that was loaded (though it may have already existed).
	"""
	old_path = sys.path
	try:
		sys.path = list(paths) + sys.path
		return import_module(name)
	finally:
		sys.path = old_path


def unload(module, safe=True):
	"""Attempt to unload the given module, which can either be an actual module object or the name of a module
	as per load(). If safe=True (the default), then it will fail to unload if any external references to the
	module exist. In other words, if safe is False, then the module might not actually be unloaded at all,
	which (in the case of reload()) could result in two versions of the module being in use at the same time!
	Raises Referenced() if safe is True and module cannot be unloaded.
	Does nothing if given module is not loaded.
	"""
	try:
		name, module = _resolve_module(module)
	except ValueError:
		return # no action to take

	# What we really want is to ensure that nothing still references anything defined by the module.
	# Technically this is impossible, since importing a module can have arbitrary side effects entirely
	# disassociated with the module.
	# However, in practice, we can consider this to mean "has access to the module's globals".
	# Unfortunately this is where we hit some problems. We ideally want to think of the module and its globals
	# as one and the same - the user thinks in terms of modules, as does the python sys.modules and import
	# abstractions. But they aren't. The globals, aka module.__dict__, are a seperate object and even if the module
	# is gone, the globals may still exist.
	# As a hacky workaround to get the behaviour we want, we introduce a backreference from the globals to the
	# module object, tying its life to that of the globals.
	# Yes, this means we introduce a reference loop, but since the globals generally already refer to objects
	# that refer to them, this isn't much of a change.
	module.__module__ = module

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
				return obj
		return None

	try:
		del sys.modules[name]
		if not safe:
			return
		gc.collect() # this is needed as modules *will* contain a ref loop
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


def reload(module, safe=True, paths=[]):
	"""Unload then load the given module. Args as per unload() (paths arg as per load()).
	Returns the new module object.
	Note that if the load fails, the module will be left unloaded.
	"""
	try:
		name, module = _resolve_module(module)
	except ValueError:
		pass
	else:
		# only unload if no ValueError
		unload(module, safe=safe)
	return load(name)


def _resolve_module(module):
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
