

"""A collection of simple tricks and helper functions for working with classes"""


from weakref import WeakKeyDictionary, WeakSet


def gencls(*bases, **extras):
	"""Define a new class inline (ie. class version of "lambda").
	Takes classes to use as base class for args, and any extra attrs to set as kwargs.
	"""
	return type(','.join(bases), bases, extras)


_issubclass = issubclass # save the builtin
def issubclass(subcls, supercls):
	"""As per the builtin issubclass(), but will simply return False if either arg is not suitable
	(eg. if subcls is not a class), instead of raising TypeError.
	This is more desired behavour in certain situations, and should not adversely affect existing code.
	"""
	try:
		return _issubclass(subcls, supercls)
	except TypeError:
		return False


def get_resolved_dict(instance):
	"""Returns a fully-resolved __dict__ for an object.
	ie. The result reflects what you would get for each key if you do a getattr on instance.
	"""
	d = {}
	for cls in reversed(instance.__class__.mro()):
		d.update(cls.__dict__)
	d.update(instance.__dict__)
	return d


def with_parent(cls, callback=None):
	"""Use this to wrap a class and assign it to a class attribute.
	On first access, it will replace itself with an instance of cls,
	passing the class it is an attribute of to __init__.
	Or instead you can provide your own callback, which takes the
	args (cls, parent) and returns the object to replace the original wrapper with.
	Note: This will not work if the wrapped value is masked by instance variables or other
	classes before it in the mro.
	"""
	if not callback: callback = lambda cls, parent: cls(parent)
	class _with_parent_wrapper(object):
		def __get__(self, parent, parent_cls):
			replacement = callback(cls, parent)
			for k, v in get_resolved_dict(parent).items():
				if isinstance(v, _with_parent_wrapper):
					setattr(parent, k, replacement)
	return _with_parent_wrapper()


def unique(cls, *args, **kwargs):
	"""A simpler version of with_parent, drops the parent arg. If not given a class,
	will use type(obj) instead.
	args and kwargs get passed through to the __init__.
	Example:
		class Foo(object):
			bar = unique(list) # will replace bar with a new empty list at first access
	"""
	return with_parent(cls if isinstance(cls, type) else type(cls),
	                   callback = lambda cls, parent: cls(*args, **kwargs))


def get_all_subclasses(cls):
	"""Recursive method to find all decendents of cls, ie.
	it's subclasses, subclasses of those classes, etc.
	Returns a set.
	"""
	subs = set(cls.__subclasses__())
	subs_of_subs = [get_all_subclasses(subcls) for subcls in subs]
	return subs.union(*subs_of_subs)


class classproperty(object):
	"""Acts like a stdlib @property, but the wrapped get function is a class method.
	For simplicity, only read-only properties are implemented."""

	def __init__(self, fn):
		self.fn = fn

	def __get__(self, instance, cls):
		return self.fn(cls)


class mixedmethod(object):
	"""A decorator for methods such that they can act like a classmethod when called via the class,
	or an instance method when bound to an instance. For example:
		>>> class MyCls(object):
		...   x = 1
		...   @mixedmethod
		...   def foo(self):
		...     return self.x
		>>> print MyCls.foo()
		1
		>>> mycls = MyCls()
		>>> mycls.x = 2
		>>> print mycls.foo()
		2
	"""

	def __init__(self, fn):
		self.fn = fn

	def __get__(self, instance, cls):
		arg = cls if instance is None else instance
		return lambda *args, **kwargs: self.fn(arg, *args, **kwargs)


class dotdict(dict):
    def __getattr__(self, attr):
        if attr in self:
            return self[attr]
        raise AttributeError
    def __setattr__(self, attr, value):
        self[attr] = value
    def __delattr__(self, attr):
        if attr in self:
            del self[attr]
        raise AttributeError
    def __hasattr__(self, attr):
        return attr in self


class aliasdict(dict):
    """subclass of dict.
    aliases attribute specifies names that elements can be accessed with,
    but which do not show up in keys() or by iterating.
    Useful to make an alias name without it "being there twice" on search."""

    aliases = {}

    def __getitem__(self, item):
        if item in self.aliases: return self[self.aliases[item]]
        return super(aliasdict, self).__getitem__(item)

    def __contains__(self, item):
        if item in self.aliases: return self.aliases[item] in self
        return super(aliasdict, self).__contains__(item)


class TracksInstances(object):
	"""A mixin that lets you easily track instances of subclasses of this object.
	A set of all active (not garbage collected) instances of a class can be retrieved
	with cls.get_instances(). This includes instances of subclasses by default - you can pass the paramter
	exclusive=True to override this."""

	_instances = WeakKeyDictionary() # maps cls to set of instances

	def __new__(cls, *args, **kwargs):
		instances = cls._instances.setdefault(cls, WeakSet())
		instance = super(TracksInstances, cls).__new__(cls, *args, **kwargs)
		instances.add(instance)
		return instance

	@classmethod
	def get_instances(cls, exclusive=False):
		"""Get a set of instances that exist for this class or subclasses.
		If exculsive, restrict output to only instances strictly of this class."""
		result = cls._instances.setdefault(cls, WeakSet())
		if not exclusive:
			for subcls in cls.__subclasses__():
				result |= subcls.get_instances()
		return result
