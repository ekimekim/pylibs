
"""Yet another enum implementation

This one aims to provide a simple, sane API with valuable properties.
It does NOT support treating enum values as integers.

* Enum types are subclasses of Enum
* Enum values are instances of their enum type
* Enum type exposes all instantiated values via attribute lookup
* str(value) gives value name, but repr on both value and class give helpfully formatted results

These are all equivilent:
	MyThing = enum("MyThing", "FOO", "BAR", "BAZ")
or:
	class MyThing(Enum):
		_values = "FOO", "BAR", "BAZ"
or:
	class MyThing(Enum):
		pass
	MyThing.define("FOO", "BAR", "BAZ")
or:
	class MyThing(Enum):
		pass
	MyThing("FOO")
	MyThing("BAR")
	MyThing("BAZ")
	
You may subclass subclasses of Enum, but values are not inherited.
It is reccomended that you only subclass subclasses without values to avoid confusion.
ie. do this:
	class MyLibEnum(Enum):
		pass
	class MySpecialLibEnum(MyLibEnum):
		_values = "SPECIAL", "VERY_SPECIAL"
	class MyNormalLibEnum(MyLibEnum):
		_values = "NOT_SPECIAL", "REALLY_BORING"
not this:
	class MyLibEnum(Enum):
		_values = "NOT_SPECIAL", "REALLY_BORING"
	class MySpecialLibEnum(MyLibEnum):
		_values = "SPECIAL", "VERY_SPECIAL"

"""


def enum(name, *values):
	"""Helper method ala namedtuple()"""
	return type(name, (Enum,), {'_values': values})


class _EnumMeta(type):
	"""Metaclass for Enum type. Provides various bits of functionality for the class."""

	def __init__(self, name, bases, kwargs):
		super(_EnumMeta, self).__init__(name, bases, kwargs)
		self.values = set()
		self.define(*kwargs.get('_values', ()))

	@property
	def names(self):
		return {value.name: value for value in self.values}

	def __getattr__(self, name):
		assert name not in ('names', 'values'), "_EnumMeta instance missing required attributes"
		if name in self.names:
			return self.names[name]
		raise AttributeError(name)

	def __repr__(self):
		return "<Enum Type {}>".format(self.__name__)
	__str__ = __repr__


class Enum(object):
	"""Useful class attributes:
		values : set of enum values (ie. instances of this type)
		names : dict mapping string names to values
	"""
	__metaclass__ = _EnumMeta

	def __new__(cls, name):
		if name in cls.names:
			raise ValueError("Enum value {} already exists".format(cls.names[name]))
		obj = super(Enum, cls).__new__(cls, name)
		cls.values.add(obj)

	@classmethod
	def define(cls, *names):
		"""Nice method for defining a new name, may be cleaner to read than simply instantiating."""
		for name in names:
			cls(name)

	def __init__(self, name):
		self.name = name

	def __repr__(self):
		return "<Enum {}.{}>".format(type(self).__name__, self.name)

	def __str__(self):
		return self.name
