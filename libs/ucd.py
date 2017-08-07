
"""Routines for parsing and presenting information from a copy of the Unicode Character Database unicodedata.txt"""


from bs4 import BeautifulSoup


class UCD(object):
	"""Represents a UCD database and provides methods for lookup, etc."""

	def __init__(self, path):
		"""path should be the path to ucd.all.flat.xml"""

		with open(path) as f:
			xml = BeautifulSoup(f.read().decode('utf-8'), 'lxml')

		self.code_points = {}

		rep = xml.ucd.repertoire
		chars = [(char, {}) for char in rep.find_all('char', recursive=False)]

		for group in rep.find_all('group', recursive=False):
			chars += [(char, group.attrs) for char in group.find_all('char', recursive=False)]

		for char, defaults in chars:
			attrs = defaults.copy()
			attrs.update(char.attrs)

			if 'cp' in attrs:
				cp_range = [int(attrs['cp'], 16)]
			else:
				start = int(attrs['first-cp'], 16)
				end = int(attrs['last-cp'], 16)
				cp_range = range(start, end + 1)

			aliases = {alias["alias"]: alias["type"] for alias in char.find_all("name-alias", recursive=False)}

			for cp in cp_range:
				self.code_points[cp] = CodePoint(self, cp, attrs, aliases)


	def by_id(self, id):
		"""Look up a code point by number, or KeyError"""
		return self.code_points[id]


	def by_char(self, char):
		"""Look up a code point by passing it as a string."""
		if not isinstance(char, unicode):
			char = char.decode('utf-8')
		if len(char) != 1:
			raise ValueError("Character must be single-length unicode string")
		return self.by_id(ord(char))


	def by_name(self, name):
		"""Look up a code point by its name, or KeyError. Includes all aliases. Case insensitive."""
		results = self.find(names=lambda names: name.lower() in [n.lower() for n in names])
		if not results:
			raise KeyError(name)
		if len(results) != 1:
			raise ValueError("Multiple characters matching name {!r}".format(name))
		result, = results
		return result


	def find(self, **criteria):
		"""Return a list of code points matching the given criteria.
		Each one is a keyword arg that specifies a value for an attribute of the code point.
		Values can be either a callable that takes a value, which will match if it returns true,
		or it can be a value that the candidate needs to equal.
		All criteria must match.
		Examples:
			The following will match all characters in the 'Emoticons' block that were introduced
			in Unicode version 9.0:
				ucd.find(block='Emoticons', age='9.0')
			The following will match all characters that have a numeric value:
				ucd.find(numeric_value=lambda v: not math.isnan(v))
		"""
		criteria = {
			attr: (value if callable(value) else (lambda v: v == value))
			for attr, value in criteria.items()
		}
		return [
			cp for cp in self.all_chars()
			if all(fn(getattr(cp, attr)) for attr, fn in criteria.items())
		]


	def all_chars(self):
		"""Returns a list of all code points"""
		return self.code_points.values()


	def __repr__(self):
		return '<{}, {} code points>'.format(type(self).__name__, len(self.code_points))
	__str__ = __repr__


class CodePoint(object):
	"""Contains properties describing a single code point."""

	def __init__(self, db, value, attrs, aliases):
		self._db = db
		self.value = value
		self.attrs = attrs
		self._aliases = aliases

	def __repr__(self):
		return '<{} {} {!r}>'.format(type(self).__name__, self.value, self.name)
	__str__ = __repr__

	def _parse_bool(self, value):
		return {'Y': True, 'N': False}.get(value)

	def _parse_char(self, value):
		if value and value.isdigit():
			return self._db.code_points[int(value, 16)]
		elif value == '#':
			return self
		else:
			return None

	def _parse_chars(self, value):
		if value:
			return map(self._parse_char, value.split(' '))
		else:
			return []

	@property
	def age(self):
		"""The version of unicode in which this code point was assigned"""
		return self.attrs["age"]

	def _expand_name(self, name):
		return name.replace('#', str(self.value))

	@property
	def name(self):
		"""The canonical name of the code point"""
		return self._expand_name(self.attrs['na'])

	@property
	def original_name(self):
		"""The name of the character as it was in Unicode 1.0, or None"""
		return self._expand_name(self.attrs['na1']) if 'na1' in self.attrs else None

	@property
	def aliases(self):
		"""A dict with keys of aliases for this character, alternate names.
		Each alias maps to its alias type, indicating if it is eg. an abbreviation, a correction, etc.
		"""
		return self._aliases

	@property
	def names(self):
		"""A unified set of all possible names for this character."""
		names = set(self.aliases.keys()) | {self.name}
		if self.original_name:
			names.add(self.original_name)
		return names

	@property
	def block(self):
		"""The unicode block the set belongs to."""
		# TODO as string or as a class? String for now.
		return self.attrs['blk']

	@property
	def category(self):
		"""TODO"""
		return self.attrs['gc']

	@property
	def combining_class(self):
		"""TODO"""
		return self.attrs['ccc']

	@property
	def bidirectional_info(self):
		"""Dict of info. Contains class, and optionally 'mirrored', 'mirror_char',
		'control', 'paired_bracket_type', 'paired_bracket_properties'"""
		return {
			'class': self.attrs['bc'],
			'mirrored': self._parse_bool(self.attrs['bidi_m']),
			'mirror_char': self._parse_char(self.attrs['bmg']),
			'control': self._parse_bool(self.attrs['bidi_c']),
			'paired_bracket_type': self.attrs['bpt'],
			'paired_bracket_properties': self._parse_char(self.attrs['bpb']),
		}

	@property
	def decomposition_type(self):
		"""TODO"""
		return self.attrs['dt']

	@property
	def decomposition_properties(self):
		"""Returns a list of characters"""
		return self._parse_chars(self.attrs['dm'])

	@property
	def composition_properties(self):
		"""Returns tuple (Composition_Exclusion, Full_Composition_Exclusion)"""
		return tuple(self._parse_bool(self.attrs[key]) for key in ('ce', 'comp_ex'))

	@property
	def quick_check_properties(self):
		"""Returns tuple (quick check attributes, expands on attributes, NFCK Closure).
		The first two are dicts with keys for NFC, NFD, NFKC, NFKD. The last is a list of characters.
		Note that some of the values, while boolean, have a 'maybe' value. This is here represented as None.
		"""
		norms = 'nfc', 'nfd', 'nfkc', 'nfkd'
		return (
			{norm: self._parse_bool(self.attrs['{}_qc'.format(norm)]) for norm in norms},
			{norm: self._parse_bool(self.attrs['xo_{}'.format(norm)]) for norm in norms},
			self._parse_chars(self.attrs['fc_nfkc']),
		)

	@property
	def numeric_type(self):
		"""TODO"""
		return self.attrs['nt']

	@property
	def numeric_value(self):
		"""Returns the numeric value of the character as a float. May be NaN."""
		value = self.attrs['nv']
		if value.lower() == 'nan':
			return float('nan')
		elif '/' in value:
			n, d = value.split('/')
			return float(n)/float(d)
		else:
			return float(value)

	@property
	def joining_info(self):
		"""Returns a dict containing joining type 'type', joining group 'group' and 'control' boolean."""
		return {
			'type': self.attrs['jt'],
			'group': self.attrs['jg'],
			'control': self._parse_bool(self.attrs['Join_C']),
		}

	@property
	def linebreak(self):
		"""TODO"""
		return self.attrs['lb']

	@property
	def east_asian_width(self):
		"""TODO"""
		return self.attrs['ea']

	@property
	def case_info(self):
		"""Returns a dict with many properties. TODO."""
		ret = {
			'simple map': {
				'upper': self._parse_char(self.attrs['suc']),
				'lower': self._parse_char(self.attrs['slc']),
				'title': self._parse_char(self.attrs['stc']),
			},
			'map': {
				'upper': self._parse_chars(self.attrs['uc']),
				'lower': self._parse_chars(self.attrs['lc']),
				'title': self._parse_chars(self.attrs['tc']),
			},
			'simple fold': self._parse_chars(self.attrs['scf']),
			'fold': self._parse_chars(self.attrs['cf']),
			'nkfc fold': self._parse_chars(self.attrs['nfkc_cf']),
			'changes when': {k: self._parse_bool(self.attrs[v]) for k, v in {
				'folded': 'cwcf',
				'mapped': 'cwcm',
				'lowercased': 'cwl',
				'nfkc folded': 'cwkcf',
				'titlecased': 'cwt',
				'uppercased': 'cwu',
			}.items()}
		}
		ret.update({k: self._parse_bool(self.attrs[v]) for k, v in {
			'upper': 'upper',
			'lower': 'lower',
			'other upper': 'oupper',
			'other lower': 'olower',
			'case ignorable': 'ci',
			'cased': 'cased',
		}.items()})
		return ret

	@property
	def script(self):
		"""TODO"""
		return self.attrs['sc']

	@property
	def script_extension(self):
		"""TODO"""
		return self.attrs['scx'].split(' ') if self.attrs['scx'] else []

	@property
	def iso_comment(self):
		"""TODO"""
		return self.attrs['isc']

	@property
	def hangul_syllable_type(self):
		"""TODO"""
		return self.attrs['hst']

	@property
	def jamo_short_name(self):
		"""TODO"""
		return self.attrs['jsn']

	@property
	def indic_categories(self):
		"""TODO"""
		return {
			'syllabic': self.attrs['insc'],
			# 'matra': self.attrs['inmc'],  # This key appears to be missing?
			'positional': self.attrs['inpc'],
		}


	# TODO UPTO: Identifier and Pattern and programming language properties (4.4.18, http://www.unicode.org/reports/tr42/)



if __name__ == '__main__':
	# test code, dump everything as json
	import sys, json, logging

	logging.basicConfig(level='INFO')
	logging.info("started")
	ucd = UCD(sys.argv[1])
	logging.info("loaded")
	for i, cp in enumerate(ucd.all_chars()):
		d = {k: getattr(cp, k) for k in dir(cp) if not k.startswith('_')}
		print json.dumps(d, default=str)
		if i % 10000 == 0:
			logging.info("processed {}/{}".format(i, len(ucd.code_points)))
