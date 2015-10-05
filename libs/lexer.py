
r"""A very simple, very limited string lexer.

Only contains a function lex(rules, data).
The rules should be a list of tuples (match, name).

Name is the token's name, eg. "NUMBER"
Match is one of the following:
	A string: Will match on this literal string.
	          eg. `"for"` will match the literal word "for".
	A function: The function will be called with the data to match.
	            It should return the number of characters to consume from data,
	            or False if the match fails. Number of characters cannot be 0.
	            Data can be assumed non-empty.
	            eg. `lambda s: s[0] != '"' and 1` will match any non-" character.
	An iterable: Will match if any of the elements match. Elements are tried in order.
	             Note that the iterable cannot be a string.
	             eg. `list(string.printable)` will match any printable character.
	None: Will match one character. Equivilent to `lambda s: 1`.

Note that the first match will succeed before moving on.
This can be used as a simple way of doing "not" operations, eg:
	(r"\n", "NEWLINE")
	("n", "LETTER")

The function will yield tuples (name, matched text).

>>> rules = [
... 	([r"\n", "\n"], "NEWLINE"),
... 	(" ", "SPACE"),
... 	(list(string.letters), "LETTER"),
... 	(None, "SYMBOL"),
... ]
>>> for name, text in lex(rules, "m n\\ o\np\\nq"):
... 	print name, repr(text)
LETTER "m"
SPACE " "
LETTER "n"
LETTER "\\"
SPACE " "
NEWLINE "\n"
LETTER "p"
NEWLINE "\\n"
LETTER "q"

"""

def lex(rules, data):
	while data:
		for match, name in rules:
			length = _get_match(match, data)
			if length:
				text, data = data[:length], data[length:]
				yield name, text
				break
		else:
			raise ValueError("Could not lex next token: {!r}".format(data))

def _get_match(match, data):
	if isinstance(match, basestring):
		return len(match) if data.startswith(match) else None
	if callable(match):
		return match(data)
	if match is None:
		return 1
	try:
		iter(match)
	except TypeError:
		raise ValueError("Bad match rule: {!r} is not callable, iterable or None")
	for submatch in match:
		length = _get_match(submatch, data)
		if length:
			return length
