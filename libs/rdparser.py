
"""A recursive decent parser that returns a parse tree

Takes rules as a list of tuples (name, rule)
and a token list (a list of (token name, token value) pairs)
and returns a parse tree of nodes (rule name, value1, value2, ...)
where values may be (token, value) or a child node.

Rule values are lists of strings (or a single space-separated string),
where each string is either a rule name or a token name.
For clarity, it is suggested (but not required) that rule names
be in lowercase while token names be in uppercase.

Rule names may be repeated to specify alternate forms.

One rule must be specified as the start rule,
which matches the entire token stream.
"""

class ParseError(Exception):
	pass

def parse(rules, start_rule, tokens):
	options = [
		tree for tree, tokens_left in
		_parse(rules, start_rule, list(tokens))
		if not tokens_left
	]
	if not options:
		raise ParseError("Unable to parse input")
	elif len(options) > 1:
		raise ParseError("Ambiguous match")
	tree, = options
	return tree

def _parse(rules, rule, tokens):
	if not tokens:
		return

	token_name, token_value = tokens[0]
	if rule == token_name:
		yield tokens[0], tokens[1:]
		return

	for name, parts in rules:
		if name != rule:
			continue
		for values, tokens_left in _parse_rule(rules, parts, tokens):
			yield (rule,) + values, tokens_left

def _parse_rule(rules, rule_parts, tokens):
	if not rule_parts:
		yield (), tokens
		return
	sub_rule = rule_parts[0]
	for subtree, part_tokens in _parse(rules, sub_rule, tokens):
		for values, tokens_left in _parse_rule(rules, rule_parts[1:], part_tokens):
			yield (subtree,) + values, tokens_left

def pprint_tree(tree, indent=0):
	"""Helper function that pretty-prints a parse tree, for debugging"""
	name, values = tree[0], tree[1:]
	if len(values) == 1 and isinstance(values[0], basestring):
		print "{:<{indent}s}{} {}".format("", name, values[0], indent=indent)
	else:
		print "{:<{indent}s}{}:".format("", name, indent=indent)
		for value in values:
			pprint_tree(value, indent=indent+1)
