
"""A library for identifying and directly reading input devices

This can be used to implement global hotkeys, keyloggers, mouse tracking

Uses sysfs interface mounted at /sys to determine device capabilities.
Expects input devices to be available under /dev/input/ and readable
(which on most machines requires root or to be in group 'input')
"""

import os
import struct
import select
import errno


# maps value to event type names. note that event type mask = (1 << value).
# (information taken from linux/include/uapi/linux/input.h at commit b2776bf (v3.18))
EVENT_TYPES = {
	0: 'syn', # a special event for conveying syncronising info
	1: 'key', # key press events (this includes things like keyboards, but also mouse buttons, etc)
	2: 'rel', # relative change events (eg. mouse movement)
	3: 'abs', # absolute change events (eg. touch location)
	4: 'msc', # misc, for events that don't fall under other categories
	5: 'sw', # switch event, inputs that change between two states, eg. laptop lid
	11: 'led', # used to query state of LEDs on devices (eg. num lock on a keyboard)
	12: 'snd', # send sound commands to simple sound devices
	14: 'rep', # specifying repeated events (?)
	15: 'ff', # send info to a force feedback device
	16: 'pwr', # used in power management (?)
}
# event types which have additional capability info
HAS_CAP_INFO = {'abs', 'ff', 'key', 'led', 'msc', 'rel', 'snd', 'sw'}


class InputEvent(object):
	time = None # timestamp of event (as epoch float)
	type = None # EVENT_TYPE value as string
	code = None # Specific event identifier, depends on type, eg. KEY_BACKSPACE or REL_X (see kernel docs)
	value = None # event value, depends on type, eg. 1 for EV_KEY down, absolute value for EV_ABS

	STRUCT_SPEC = 'llHHI'
	def __init__(self, packed):
		secs, usecs, type, self.code, self.value = struct.unpack(self.STRUCT_SPEC, packed)
		self.time = secs + usecs * 1e-6
		self.type = EVENT_TYPES[type]

	def __str__(self):
		return "<{cls.__name__} {self.type} {self.code:x} = {self.value} @{self.time}>".format(
		       cls=type(self), self=self)

	@classmethod
	def size(cls):
		return struct.calcsize(cls.STRUCT_SPEC)


def read_long_bitmask(s):
	"""Converts a bitmask to a string when the bitmask is in a format of hex longs seperated by spaces"""
	# it'd be nice if we could get away with just removing the spaces, but the words aren't zero-padded
	mask = 0
	long_bits = struct.calcsize('L') * 8
	for word in s.split(' '):
		mask <<= long_bits
		mask += int(word, 16)
	return mask

def _gen_cap_property(name, mask):
	def _generated_property(self):
		if not self.ev & mask:
			return None
		if name in HAS_CAP_INFO:
			return read_long_bitmask(self._sysfs('capabilities', name))
		return True
	_generated_property.__name__ = name
	return property(_generated_property)


class InputDevice(object):
	"""Represents an input device in the system. The device is not opened unless you attempt to
	read events, and other properties are looked up in sysfs on demand."""

	@classmethod
	def all(cls):
		"""Return a list of all event handlers"""
		return [cls(name) for name in os.listdir('/dev/input') if name.startswith('event')]

	@classmethod
	def find(cls, **criteria):
		"""Search for relevant devices.
		Criteria kwargs can be any key, which will be looked up as an attribute for every device.
		To match, the device's value must either match the given value, or (if given value is callable) must
		return true when callable is passed the device's value.
		Examples:
			Find all devices that have keys or buttons:
				InputDevice.find(key=lambda value: value is not None)
			Find devices with a specific name:
				InputDevice.find(name="My specific device")
			Find a particular product:
				InputDevice.find(product_id=PRODUCT_ID, vendor_id=VENDOR_ID)
		"""
		results = []
		for device in cls.all():
			for key, criterion in criteria.items():
				func = criterion if callable(criterion) else lambda value: value == criterion
				dev_value = getattr(device, key)
				if not func(dev_value):
					break
			else:
				results.append(device)
		return results

	def __init__(self, name):
		"""Expects name to be a handler like 'eventN' or 'mouseN' (as per /dev/input/).
		See find() if you wish to look up by other indicators."""
		self.handler = name

	@property
	def device(self):
		"""The device name, eg. input0"""
		return os.path.basename(os.readlink('/sys/class/input/{}/device'.format(self.handler)))

	def _handler_sysfs(self, *args):
		"""As per _sysfs, but start from handler directory instead of device directory"""
		path = '/sys/class/input/{}/{}'.format(self.handler, '/'.join(args))
		if os.path.isdir(path):
			return os.listdir(path)
		else:
			with open(path) as f:
				return f.read().strip()

	def _sysfs(self, *args):
		"""Read file from sysfs under /sys/class/input/DEVICE/ARG1/ARG2/...
		If file is a directory, instead return a list of contents."""
		return self._handler_sysfs('device', *args)

	@property
	def device_number(self):
		"""Returns (major, minor) as int"""
		return map(int, self._handler_sysfs('dev').split(':'))

	# ids
	def _get_id(self, name):
		return int(self._sysfs('id', name), 16)
	@property
	def bus_id(self):
		return self._get_id('bustype')
	@property
	def product_id(self):
		return self._get_id('product')
	@property
	def vendor_id(self):
		return self._get_id('vendor')
	@property
	def version_id(self):
		return self._get_id('version')

	@property
	def phys(self):
		"""Physical address in the system"""
		return self._sysfs('phys')

	@property
	def name(self):
		return self._sysfs('name')

	@property
	def properties(self):
		"""A bitmask indicating device properties.
		See relevant kernel documentation for flag values and meanings."""
		return read_long_bitmask(self._sysfs('properties'))

	@property
	def uniq(self):
		"""If available, unique identifier for the hardware.
		Returns '' if not available (mimicing the kernel interface)"""
		return self._sysfs('uniq')

	@property
	def unique(self):
		"""Attempts to build a unique profile of a device, even if uniq is not available.
		Uses product, vendor, version ids, as well as name and all capabilities.
		If uniq is available, just uses uniq.
		Return value is an integer hash."""
		if self.uniq:
			return hash(self.uniq)
		data = (self.product_id, self.version_id, self.vendor_id, self.name, self.ev)
		for name in EVENT_TYPES.values():
			data += (getattr(self, name),)
		return hash(data)

	@property
	def modalias(self):
		return self._sysfs('modalias')

	@property
	def ev(self):
		"""A bitmask representing device capabilities. Generally you should explicitly check each capability
		you want instead of using this value, see below."""
		return read_long_bitmask(self._sysfs('capabilities', 'ev'))

	# capabilities: These values are None if the type of event is not supported,
	#   True if they are supported with no further information, and an integer bitmask if they are supported
	#   and have further capability information. See kernel documentation for more info on these bitmasks.
	locals().update({_name: _gen_cap_property(_name, (1 << _value)) for _value, _name in EVENT_TYPES.items()})

	# --- Read operations ---

	_file = None

	def _ensure_file(self):
		if self._file is not None:
			return
		self._file = open('/dev/input/{}'.format(self.handler), 'rb')

	def fileno(self):
		self._ensure_file()
		return self._file.fileno()

	def read(self):
		"""Reads an event and returns it."""
		while True:
			try:
				r, w, x = select.select([self.fileno()], [], [])
			except OSError as ex:
				if ex.errno != errno.EINTR:
					raise
			else:
				if r:
					break
		data = self._file.read(InputEvent.size())
		assert len(data) == InputEvent.size(), "Bad read from {}: Asked for {} bytes but got {!r}".format(self._file, InputEvent.size(), data)
		return InputEvent(data)

	def read_iter(self):
		"""Returns an iterator that will read events and yield them forever."""
		while True:
			yield self.read()

	def close(self):
		if self._file is None:
			return
		file, self._file = self._file, None
		file.close()

	def __eq__(self, other):
		if isinstance(other, InputDevice) and self.unique == other.unique:
			return True
		return False
