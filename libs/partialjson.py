
"""A (mostly just for fun) JSON parser from scratch,
with an emphasis on doing something sane with partial
or (slightly) malformed inputs.

Usage examples:

# mixed example showing errors
parser = JSONStreamParser(stream)
try:
	for partial_result, new_value, new_value_path in parser:
		...
	result = parser.parse_all()
except Empty:
	print "stream contained no non-whitespace data"
except Partial:
	print "unterminated. partial result:"
	print parser.result
except ParseError as ex:
	print ex
	print "partial result:"
	print parser.result
	print "input remaining after error encountered:", stream.read()
else:
	print result
	print 'input remaining after object decoded:', stream.read()

# yield full JSON documents from stream
try:
	while True:
		yield JSONStreamParser(stream).parse_all()
except Empty:
	return

# progress reporting, counting top-level array length, early exit on error
# this would be pretty damn slow though
parser = JSONStreamParser(stream)
for partial_result, _, _ in parser:
	if not isinstance(partial_result, list):
		raise ValueError("Provided JSON was not array")
	print "{} items, {.2f}%".format(len(partial_result), 100.0 * stream.tell() / STREAM_LENGTH)

# extract all strings (except object keys)
for _, new_value, _ in parser:
	if isinstance(new_value, unicode):
		yield new_value

# extract all strings (including object keys)
for _, new_value, path in parser:
	if path:
		key = path[-1]
		if isinstance(key, unicode):
			yield key
	if isinstance(new_value, unicode):
		yield new_value

"""


from StringIO import StringIO
import itertools


def parse(stream_or_string):
	"""Shortcut for JSONStreamParser(stream_or_string).parse_all()"""
	return JSONStreamParser(stream_or_string).parse_all()


def parse_with_remainder(string):
	"""Parse string and return (result, trailing data)"""
	stream = StringIO(string)
	result = JSONStreamParser(stream).parse_all()
	return result, stream.read()


def parse_many(stream_or_string):
	"""Parse multiple JSON objects from a stream or string, and yield each one"""
	stream = StringIO(stream_or_string) if isinstance(stream_or_string, basestring) else stream_or_string
	while True:
		try:
			yield parse(stream)
		except Empty:
			return


class ParseError(Exception):
	pass

class Empty(Exception):
	pass

class Partial(Exception):
	pass

class Invalid(Exception):
	pass


class JSONStreamParser(object):
	"""Parses a given input stream (or string) as JSON, with the ability to return partial results."""
	WHITESPACE = " \n\t"

	_CLOSE = object()

	def __init__(self, stream_or_string, encoding='utf-8'):
		"""stream or string can be given, and may contain unicode or bytes.
		If stream or string contains bytes, encoding will be used to decode.
		Set encoding=None to make bytes an error."""
		if isinstance(stream_or_string, basestring):
			stream_or_string = StringIO(stream_or_string)
		self.stream = stream_or_string
		self.encoding = encoding
		self.complete = False
		self.result = None
		self._path = None # note () is different to None. () means active container is root value, None means no root value exists
		self._pushback_buffer = [] # used sparingly, in the only place it can't be avoided: parsing numbers

	def parse_all(self):
		"""Parse until a complete JSON object is finished, or an error occurs."""
		if not self.complete:
			# consume self until exhausted
			for _, _, _ in self:
				pass
		return self.result

	def __iter__(self):
		"""Iterating over parser will parse the next whole value and yield (result so far, new value, path to new value).
		Details on each of these:
			result so far: The full data structure parsed so far, may be incomplete.
				eg. a dict may be missing keys.
			new value: The value that was just parsed.
				Either a basic value (string, number, bool, None) or an empty list/dict.
			path to new value: A tuple of either dict keys or list indices,
				such that looking up each key in succession from the result so far would result in the new value.
		Example: If we were parsing '{"a": 1, "b": ["c", true]}', the results yielded in order would be:
			{}, {}, ()
			{"a": 1}, 1, ("a",)
			{"a": 1, "b": []}, [], ("b",)
			{"a": 1, "b": ["c"]}, "c", ("b", 0)
			{"a": 1, "b": ["c", True]}, True, ("b", 1)
		NOTE: The values returned are references, not copies! Expect them to change with subsequent parsing.
		"""
		return self

	def next(self):
		result, new_value, path = self.parse_one()
		if path is None:
			assert self.complete, "parse_one() returned path of None but complete flag not set"
			raise StopIteration
		return result, new_value, path

	def parse_one(self):
		"""Return the next partial result tuple (result so far, new value, path to new value).
		See __iter__() for a full description of these values.
		If object is complete, returns (result, None, None).
		If you're checking this condition, it's reccomended you check for path=None, not value=None
		as value may be None when a "null" is parsed. Alternately, check parser.completed directly.
		"""
		while True:
			if self.complete:
				return self.result, None, None

			container = self._lookup_path(self._path) if self._path is not None else None
			new_value = self._read_value(to_close=container)
			if new_value is self._CLOSE:
				assert self._path is not None, "non-existent path and got valid close"
				self._close_path()
				continue # keep going until we get a new (non-close) value

			if self._path is not None:
				if isinstance(container, dict):
					key, new_value = new_value
					container[key] = new_value
				elif isinstance(container, list):
					key = len(container)
					container.append(new_value)
				else:
					assert False, "container {!r} is not a dict or list".format(container)
				self._path += (key,)
			else:
				# special case for non-existent path, root value
				self.result = new_value
				self._path = ()

			new_path = self._path
			# unless new value is a container, immediately close it
			if not isinstance(new_value, (dict, list)):
				self._close_path()

			return self.result, new_value, new_path


	def _close_path(self):
		if self._path:
			self._path = self._path[:-1]
		else:
			# we just closed the root object - we're done!
			self.complete = True


	def _lookup_path(self, path):
		result = self.result
		for part in path:
			result = result[part]
		return result


	def _read_value(self, to_close):
		"""Read either the next whole leaf value, or the next container that is opened,
		or self._CLOSE on container close. Error if the close type doesn't match the given to_close.
		to_close=None means no close is possible.
		if to_close is a dict, expect "string:value" instead of just value, and return tuple
		"""
		if isinstance(to_close, dict):
			dispatch = {
				u'"': self._read_obj_pair,
				u'}': lambda c: self._CLOSE,
			}
		else:
			dispatch = {
				u'"': self._read_string,
				u'tf': self._read_bool,
				u'n': self._read_null,
				u'[': lambda c: [],
				u'{': lambda c: {},
				u'0123456789-': self._read_number,
			}
			if isinstance(to_close, list):
				dispatch[u']'] = lambda c: self._CLOSE
			else:
				assert to_close is None, "unexpected value for to_close: {!r}".format(to_close)

		# hack: skip over any ',' characters - this violates the spec but is strictly more lenient
		# and is easier than trying to keep track of whether there should be a "," berore the next value or not.
		char = u','
		while char == u',':
			char = self._read_nonws()

		for matching, handler in dispatch.items():
			if char in matching:
				return handler(char)
		raise Invalid("Unexpected character {!r} - expected one of: {!r}".format(
			char,
			u''.join(dispatch.keys())
		))


	def _read_null(self, char):
		self._read_exact(char, u"null")
		return None


	def _read_bool(self, char):
		if char == u't':
			self._read_exact(char, u"true")
			return True
		else:
			self._read_exact(char, u"false")
			return False


	def _read_obj_pair(self, char):
		key = self._read_string(char)
		char = self._read_nonws()
		if char != ':':
			raise Invalid("Unexpected character {!r} after object key - expected ':'".format(char))
		value = self._read_value(None) # recurse, but strictly one level as to_close is None, not a dict
		return key, value


	def _read_string(self, char):
		assert char == u'"', "bad initial char {!r} for _read_string()".format(char)
		resultlist = []
		while True:
			char = self._read()
			# terminator
			if char == '"':
				break
			# escapes
			if char == u'\\':
				char = self._read()
				if char == u'u':
					char = self._read_unicode_escape()
				else:
					# translate, with default being 'whatever the second character is'
					char = {
						u'b': u'\b',
						u'f': u'\f',
						u'n': u'\n',
						u'r': u'\r',
						u't': u'\t',
					}.get(char, char) # char char char!
			resultlist.append(char)
		# JSON encodes non-BMP chars as surrogate pairs :(
		# we need to fix that
		result = u''
		while resultlist:
			c = resultlist.pop(0)
			if resultlist and (0xd800 <= ord(c) < 0xdc00) and (0xdc00 <= ord(resultlist[0]) < 0xe000):
				c2 = resultlist.pop(0)
				# c,c2 is a surrogate pair, convert to true value
				c = unichr(0x10000 + ((ord(c) - 0xd800) << 10) + ord(c2) - 0xdc00)
			result += c
		return result


	def _read_unicode_escape(self):
		digits = self._read_or_pushback(u'0123456789abcdefABCDEF', 4)
		if not digits:
			raise Invalid("Invalid unicode escape - no valid digits after '\\u'")
		value = int(digits, 16)
		return unichr(value)


	def _read_number(self, char):
		read_digits = lambda: self._read_or_pushback(u'0123456789')

		dec_part = None
		exp_part = None

		int_part = char
		int_part += read_digits()
		int_part = int(int_part)

		# from here in, we keep (char = the next char to be parsed) between sections
		char = self._read()

		# decimal part?
		if char == u'.':
			dec_part = read_digits()
			dec_part = float(u'0.' + dec_part)
			char = self._read()

		# exponent part?
		if char in u'Ee':
			exp_part = self._read_or_pushback(u'+-', 1) + read_digits()
			if exp_part in {u'', u'+', u'-'}:
				raise Invalid("Invalid exponent in number")
			exp_part = int(exp_part)
		else:
			# no exponent, return unused char
			self._pushback_buffer.append(char)

		# note we're careful here to ensure integers don't become floats
		value = int_part
		if dec_part is not None:
			value += dec_part
		if exp_part is not None:
			# 10 ** exp is an int if exp is an int and exp >= 0
			value *= 10 ** exp_part
		return value


	def _read_or_pushback(self, acceptable, limit=None):
		"""Read up to limit of the acceptable chars, or push back if not acceptable.
		limit=None for no limit."""
		buf = u''
		limit = itertools.count() if limit is None else xrange(limit)
		for x in limit:
			char = self._read()
			if char not in acceptable:
				self._pushback_buffer.append(char)
				break
			buf += char
		return buf


	def _read_exact(self, leading, target):
		"""Attempt to read the exact given string. Raise Invalid on fail.
		Removes leading from target before beginning. Leading must match start of target."""
		assert target.startswith(leading), "target {!r} does not start with leading {!r}".format(target, leading)
		for t in target[len(leading):]:
			char = self._read()
			if char != t:
				raise Invalid("Unexpected character {!r} while parsing {!r}".format(char, target))


	def _read_nonws(self):
		"""Read one non-whitespace character or raise EOF"""
		while True:
			char = self._read()
			if char not in self.WHITESPACE:
				return char

	def _read(self):
		"""Read one unicode character, or raise EOF"""
		if self._pushback_buffer:
			return self._pushback_buffer.pop(0)
		char = self.stream.read(1)
		if not char:
			raise EOFError
		if isinstance(char, unicode):
			return char
		if not self.encoding:
			raise TypeError("Byte {!r} was read but unicode expected".format(char))
		while True:
			# read a byte at a time until we have a successful decode
			try:
				return char.decode(self.encoding)
			except UnicodeDecodeError:
				byte = self.stream.read(1)
				if not byte:
					# we want the error we report to be the failed decode of the truncated character, not EOF
					raise
				char += byte
				# sanity check - we don't want to read the entire stream if a truly malformed encoding is found
				# limit of 8 is somewhat arbitrary - most encodings (eg. utf-8) cap out at 4 or lower.
				if len(char) > 8:
					raise
