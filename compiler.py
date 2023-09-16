#!/usr/bin/env python
#
# a toy compiler for a minimal toy language v.2
#

import sys

import assembly

OUTFILE = 'out.asm'

COMMENT_CHAR = ';'

# for ld linker use '_start'
START_LABEL = 'main'

def split_expressions(program):

  """split a program into a list of expressions,

  filter out comments, and check for balanced parentheses"""

  expressions = []

  expr = ''
  depth = 0

  inline_comment = False

  for c in program:
    if c == COMMENT_CHAR:
      inline_comment = True
      continue
    elif c == '\n' and inline_comment:
      inline_comment = False
      continue
    elif inline_comment:
      continue

    elif c == '(':
      depth += 1
    elif c == ')':
      depth -= 1
      if depth == 0:
        expr += c
        expressions.append(expr.strip())
        expr = ''
        continue

    expr += c

  if depth != 0:
    sys.exit("Error: unbalanced parentheses in program: %s" % program)

  return expressions


def get_kwargstr(s):

  """split a keyword and argument string from an expression"""

  [ kw, argstr ] = s.split('(', 1)

  return [ kw.strip(), argstr.strip()[:-1] ]


def get_split_argstr(argstr):

  """split an argument string into a list of arguments"""

  split_argstr = []
  arg = ''
  depth = 0
  block_depth = 0
  list_depth = 0
  string_lit = False

  for c in argstr:
    if c == '(':
      depth += 1
    elif c == ')':
      depth -= 1
    elif c == '{':
      block_depth += 1
    elif c == '}':
      block_depth -= 1
    elif c == '[':
      list_depth += 1
    elif c == ']':
      list_depth -= 1
    elif c == "'":
      string_lit = not string_lit
    elif c == ',' and depth == 0 and block_depth == 0 and list_depth == 0 and not string_lit:
      split_argstr.append(arg.strip())
      arg = ''
      continue

    arg += c

  if depth != 0:
    sys.exit("Error: unbalanced parentheses in expression: %s" % argstr)

  if block_depth != 0:
    sys.exit("Error: unbalanced curly braces in expression: %s" % argstr)

  if list_depth != 0:
    sys.exit("Error: unbalanced square brackets in expression: %s" % argstr)

  if arg != '':
    split_argstr.append(arg.strip())

  return split_argstr


def check_arguments(args, num, fn_name=None):

  """check that the number of arguments is correct"""

  if len(args) != num:
    if fn_name is None:
      sys.exit("Error: expected " + str(num) + " arguments, got " + str(len(args)))
    else:
      sys.exit("Error: expected " + str(num) + " arguments for " + fn_name + ", got " + str(len(args)))


def parse(expr):

  """parse an expression of the form:

  <kw> ( <expr> [, <expr>]* )

  into a list of keyword and arguments, e.g.:

  [ "fn", [ "1", "2" ] ]
  [ "fn", [ "1", [ "add", [ "2", "3" ] ], [ "sub", [ "4", "5" ] ] ] ]

  """

  if '(' not in expr and ')' not in expr:
    return expr.strip()

  [ kw, argstr ] = get_kwargstr(expr)

  split_argstr = get_split_argstr(argstr)

  args = []
  for arg in split_argstr:
    if arg.lstrip().startswith('{'):
      args.append(arg)
    else:
      args.append(parse(arg))

  return [ kw, args ]


STACK_FRAMES = [ {
      'params': [],
      'vars': [ [] ],   # blocks
} ]

UNIQUE_COUNTER = 0

LOOP_IDS = []

FUNCTIONS = {}

LITERALS = []

TYPES = [ 'UNDEF', 'INT', 'STRING_LIT', 'STRING' ]

def get_unique_count():
  global UNIQUE_COUNTER
  UNIQUE_COUNTER += 1
  return UNIQUE_COUNTER

def find_variable(name, stack_frame):

  """find the stack position of a variable"""

  # we need to find the first occurrence, from the end (top) of the stack
  # but we want to return the index from the start (bottom)
  r = None
  _type = None
  c = 0
  for block in stack_frame:
    for var in block:
      if var[0] == name:
        r = c
        _type = var[1]
      c += 1
  return [ r, _type ]

def find_parameter(name, stack_frame):

  """find the stack position of a parameter"""

  # we need to find the first occurrence, from the end (top) of the stack
  for i, param in enumerate(reversed(stack_frame)):
    if param[0] == name:
      return i
  return None

def eval_block(block, asm, depth):

  if not block.startswith('{') or not block.endswith('}'):
    sys.exit("Error: block does not start and end with curly braces: %s" % block)

  STACK_FRAMES[-1]['vars'].append([])

  block_exprs = split_expressions(block.strip()[1:-1])
  for expr in block_exprs:
    [ asm, _type ] = eval(parse(expr), asm, depth + 1)

  for var in STACK_FRAMES[-1]['vars'][-1]:
    asm += assembly.POP_LOCAL_VARIABLE

  STACK_FRAMES[-1]['vars'].pop()

  return asm

def get_list_args(list_str):

  r = [ x.strip() for x in list_str.strip()[1:-1].split(',') ]

  if r == ['']: return [ [], [] ]

  args = []
  types = []
  for a in r:
    [ arg, _type ] = a.split(':')
    args.append(arg.strip())
    types.append(_type.strip())

  return [ args, types ]

def check_arg_types(kw, arg_types, expected_types):

  if len(arg_types) != len(expected_types):
    sys.exit("Error: expected %d arguments for %s, got %d" % (len(expected_types), kw, len(arg_types)))

  for i, _type in enumerate(arg_types):
    if type(expected_types[i]) == list:
      if _type not in expected_types[i]:
        sys.exit("Error: expected type %s for argument %d of %s, got %s" % (expected_types[i], i + 1, kw, _type))
    elif _type != expected_types[i]:
      sys.exit("Error: expected type %s for argument %d of %s, got %s" % (expected_types[i], i + 1, kw, _type))


def eval(expr, asm, depth = 0):

  """evaluate an expression of the form:

  <kw | func> ( <expr> [, <expr>]* )

  """

  # first we check if the expression is a string,
  # if it is, it can be:
  #
  # 1. a SYMBOL of a variable or a parameter
  #             these are allocated on the stack, so we find
  #             the stack position and load the value into the
  #             return register
  # 2. a DIGIT, currently this can be a positive or negative integer
  #             we put the value into the return register
  # 3. a STRING, a string literal, we add the string to the text section
  #             and put the address into the return register

  if type(expr) == str:

    if expr == '': return [ asm, 'UNDEF' ]

    # check for variable
    [ stack_pos, vtype ] = find_variable(expr, STACK_FRAMES[-1]['vars'])

    if stack_pos is not None:
      asm += assembly.GET_LOCAL_VARIABLE.format(4 + stack_pos * 4)
      return [ asm, vtype ]

    # check for parameter
    stack_pos = find_parameter(expr, STACK_FRAMES[-1]['params'])

    if stack_pos is not None:
      asm += assembly.GET_PARAMETER.format(8 + stack_pos * 4)
      return [ asm, 'SYMBOL' ]

    if expr.isdigit():
      asm += assembly.LITERAL.format(expr)
      return [ asm, 'INT' ]

    # negative numbers
    if expr.startswith('-') and expr[1:].isdigit():
      asm += assembly.LITERAL.format(expr)
      return [ asm, 'INT' ]

    if expr.startswith("'") and expr.endswith("'"):
      # add literal to text section/literals
      str_id = 'string_' + str(get_unique_count())
      LITERALS.append(assembly.DATA_STRING.format(str_id, expr[1:-1]))
      asm += assembly.LITERAL.format(str_id)
      return [ asm, 'STRING_LIT' ]

    sys.exit("Error: unknown variable or literal: " + expr)

  # at this point we know we have an expression

  [ kw, args ] = expr

  # first we handle cases, where the arguments need some special handling
  # e.g. var takes a variable name and an expression, but if we parse the
  # variable name now it would result in an error, because it is not yet
  # defined
  # -> idea: we could use a string for the variable names and then parse them
  # regularly, (but this would be a bit ugly <-- this is what copilot thinks)

  if kw == "var":
    check_arguments(args, 2, 'var')

    # check that variable name starts with a letter
    if not args[0][0].isalpha():
      sys.exit("Error: variable name must start with a letter")

    # check redeclaration
    [ stack_pos, vtype ] = find_variable(args[0], STACK_FRAMES[-1]['vars'][-1])
    if stack_pos is not None:
      sys.exit("Redeclaration Error: '" + args[0] + "'")

    # evaluate the 2nd argument
    [ asm, _type ] = eval(args[1], asm, depth + 1)
    asm += assembly.PUSH_RESULT

    if _type not in [ 'SYMBOL', 'INT', 'STRING', 'STRING_LIT' ]:
      sys.exit("Error: invalid type: '" + _type + "'" + " for variable: '" + args[0] + "'")

    # if the value is a string, we want to allocate it (in the heap)
    # => why ?
    #if _type == 'STRING':
    #  asm += assembly.CALL_EXTENSION["allocate_str"]
      # the result is the address of the allocated string
      # we store it in the variable
    #  asm += assembly.PUSH_RESULT

    # store variable in compiler stack
    STACK_FRAMES[-1]['vars'][-1].append([ args[0], _type ])

    return [ asm, 'UNDEF' ]

  if kw == 'set':
    check_arguments(args, 2, 'set')

    [ stack_pos, vtype ] = find_variable(args[0], STACK_FRAMES[-1]['vars'])
    if stack_pos is None:
      sys.exit("Error setting undeclared variable: '" + args[0] + "'")

    # this pushes the value onto the stack in asm
    [ asm, _type ] = eval(args[1], asm, depth + 1)
    asm += assembly.PUSH_RESULT

    if _type != vtype:
      sys.exit("Error: Type mismatch variable: '" + args[0] + "'" + " expected: '" \
        + vtype + "'" + " got: '" + _type + "'")

    # this will consume the value on the stack top
    # and update the variable in the correct stack location
    asm += assembly.PRIMARIES[kw].format(4 + stack_pos * 4)

    return [ asm, 'UNDEF' ]

  if kw == 'block':
    asm = eval_block(args[0], asm, depth)
    return [ asm, 'BLOCK' ]

  if kw == 'if':
    # get id for block
    id = get_unique_count()

    # eval condition
    [ asm, _type ] = eval(args[0], asm, depth + 1)
    asm += assembly.PUSH_RESULT

    if _type != 'INT':
      sys.exit("Error: if condition must be of type INT: '" + expr + "'")

    asm += assembly.IF_START.format(id)

    asm = eval_block(args[1], asm, depth)

    if len(args) == 3:
      asm += assembly.ELSE_START.format(id)

      asm = eval_block(args[2], asm, depth)

    else:
      asm += assembly.ELSE_START.format(id)

    asm += assembly.IF_END.format(id)

    return [ asm, 'BLOCK' ]

  if kw == 'while':
    # get id for block
    id = get_unique_count()

    asm += assembly.WHILE_START.format(id)

    # eval condition
    [ asm, _type ] = eval(args[0], asm, depth + 1)
    asm += assembly.PUSH_RESULT

    if _type != 'INT':
      sys.exit("Error: while condition must be of type INT: '" + expr + "'")

    # emit condition evaluation
    asm += assembly.WHILE_CONDITION_EVAL.format(id)

    LOOP_IDS.append(id)
    asm = eval_block(args[1], asm, depth)
    LOOP_IDS.pop()

    asm += assembly.WHILE_END.format(id)

    return [ asm, 'BLOCK' ]

  if kw == 'function':
    check_arguments(args, 4, 'function')

    # check that function name starts with a letter
    if not args[0][0].isalpha():
      sys.exit("Error: function name must start with a letter")

    if args[2] not in TYPES:
      sys.exit("Error: unknown type: '" + args[2] + "'" + " for function: '" + args[0] + "'")

    [ params, types ] = get_list_args(args[1])
    for t in types:
      if t not in TYPES:
        sys.exit("Error: unknown type: '" + t + "'" + " for function: '" + args[0] + "'")
    #print(types)
    FUNCTIONS[args[0]] = {
      'param_types': types,
      'return_type': args[2],
      'asm': ''
    }

    # push a new frame onto the stack_frames
    STACK_FRAMES.append({
      'name': args[0],
      'params': [],
      'vars': [],
      'return_type': args[2]
    })

    # check that parameter names start with a letter
    for param in params:
      if not param[0].isalpha():
        sys.exit("Error: parameter name must start with a letter")

      STACK_FRAMES[-1]['params'].append(param)

    fn_asm = ""
    fn_asm += assembly.FUNCTION_START.format(args[0])

    fn_asm = eval_block(args[3], fn_asm, 0)

    fn_asm += assembly.FUNCTION_END.format(args[0])

    FUNCTIONS[args[0]]['asm'] = fn_asm

    STACK_FRAMES.pop()

    return [ asm, args[2] ]

  arg_types = []
  for i, arg in enumerate(args):
    [ asm, _type ] = eval(arg, asm, depth + 1)
    asm += assembly.PUSH_RESULT

    arg_types.append(_type)
    #check_type(kw, i, _type)

  rtype = 'UNDEF'

  if kw == "exit":
    if len(args) == 0:
      asm += assembly.LITERAL.format(0)
      asm += assembly.PUSH_RESULT
    else:
      check_arg_types(kw, arg_types, ['INT'])
    asm += assembly.PRIMARIES[kw]

  elif kw == "print":
    #check_arguments(args, 1, 'print')
    check_arg_types(kw, arg_types, [ [ 'STRING_LIT', 'STRING' ] ])
    asm += assembly.CALL_EXTENSION[kw]

  elif kw == "free_str":
    #check_arguments(args, 1, 'free_str')
    check_arg_types(kw, arg_types, [ 'STRING' ])
    asm += assembly.CALL_EXTENSION[kw]

  elif kw == "print_i":
    #check_arguments(args, 1, 'print_i')

    # 35-function-recursion
    # Error: expected type INT for argument 1 of print_i, got SYMBOL
    #check_arg_types(kw, arg_types, [ 'INT' ])
    asm += assembly.CALL_EXTENSION[kw]

  elif kw == "println_i":
    #check_arguments(args, 1, 'println_i')

    # 35-function-recursion
    # Error: expected type INT for argument 1 of print_i, got SYMBOL
    #check_arg_types(kw, arg_types, [ 'INT' ])
    asm += assembly.CALL_EXTENSION["print_i"]
    asm += assembly.CALL_EXTENSION["println"]

  elif kw == "println":
    if len(args) == 0:
      asm += assembly.CALL_EXTENSION[kw]
    else:
      check_arg_types(kw, arg_types, [ [ 'STRING_LIT', 'STRING' ] ])
      asm += assembly.CALL_EXTENSION["print"]
      asm += assembly.CALL_EXTENSION[kw]

  elif kw == "int_to_str":
    #check_arguments(args, 1, 'int_to_str')
    check_arg_types(kw, arg_types, [ 'INT' ])
    asm += assembly.CALL_EXTENSION[kw]
    rtype = 'STRING'

  elif kw == "return":
    rtype = STACK_FRAMES[-1]['return_type']
    fname = STACK_FRAMES[-1]['name']

    if rtype == 'UNDEF':
      if len(args) != 0:
        sys.exit("Error: return type UNDEF should not have any arguments:\n'" \
          + "function: " + fname + ", arg: " + args[0] + "'")

    if len(args) == 0:
      if rtype != 'UNDEF':
        sys.exit("Error: expected type " + rtype + " for return, got no arguments:\n'" \
          + "function: " + fname + "'")

    if len(args) == 1:
      if arg_types[0] != rtype:
        sys.exit("Error: expected type " + rtype + " for return, got " + arg_types[0] + ":\n'" \
          + "function: " + fname + ", arg: " + args[0] + "'")

    elif len(arg_types) > 1:
      sys.exit("Error: return should have at most one argument:\n'" \
        + "function: " + fname + ", arg: " + str(args) + "'")

    asm += assembly.PRIMARIES[kw]

  elif kw == 'inc' or kw == 'dec':
    #check_arguments(args, 1, 'inc/dec')
    # -> check that arg is a symbol
    check_arg_types(kw, arg_types, [ 'INT' ])

    [ stack_pos, _type ] = find_variable(args[0], STACK_FRAMES[-1]['vars'])
    if stack_pos is None:
      sys.exit("Error in inc/dec: variable '" + args[0] + "' not found")

    asm += assembly.PRIMARIES[kw].format(4 + stack_pos * 4)

  elif kw in assembly.UNARIES:
    #check_arguments(args, 1, kw)
    check_arg_types(kw, arg_types, [ 'INT' ])

    asm += assembly.UNARIES[kw]
    rtype = 'INT'

  elif kw in assembly.BINARIES:
    #check_arguments(args, 2, kw)
    #check_arg_types(kw, arg_types, [ 'INT', 'INT' ])

    asm += assembly.BINARIES[kw]
    rtype = 'INT'

  elif kw in assembly.COMPARISONS:
    #check_arguments(args, 2, kw)
    #check_arg_types(kw, arg_types, [ 'INT', 'INT' ])

    asm += assembly.COMPARISONS[kw].format(get_unique_count())
    rtype = 'INT'

  elif kw in assembly.LOGICALS:
    if kw == 'not':
      #check_arguments(args, 1, kw)
      check_arg_types(kw, arg_types, [ 'INT' ])
    else:
      #check_arguments(args, 2, kw)
      check_arg_types(kw, arg_types, [ 'INT', 'INT' ])

    asm += assembly.LOGICALS[kw].format(get_unique_count())
    rtype = 'INT'

  elif kw == 'check_overflow':
    check_arg_types(kw, arg_types, [])
    id = get_unique_count()
    asm += assembly.CHECK_OVERFLOW.format(id)
    rtype = 'INT'

  elif kw == 'break':
    check_arg_types(kw, arg_types, [])
    asm += assembly.WHILE_BREAK.format(LOOP_IDS[-1])

  elif kw == 'continue':
    check_arg_types(kw, arg_types, [])
    asm += assembly.WHILE_CONTINUE.format(LOOP_IDS[-1])

  elif kw in FUNCTIONS:
    #print(FUNCTIONS)
    check_arg_types(kw, arg_types, FUNCTIONS[kw]['param_types'])
    asm += assembly.FUNCTION_CALL.format(kw, len(args) * 4)

    rtype = FUNCTIONS[kw]['return_type']

  else:
    sys.exit("Error: unknown keyword '" + kw + "'")

  return [ asm, rtype ]


def main():

  """main function"""

  # check for program file
  if len(sys.argv) < 2:
    sys.exit("""Usage: compiler.py <program file>
  Output: {}""".format(OUTFILE))

  # open program file
  with open(sys.argv[1], 'r') as f:
    program = f.read()

  # parse program
  expressions = split_expressions(program)

  parsed_expressions = []
  for expr in expressions:
    parsed_expressions.append(parse(expr))

  # evaluate program
  main_asm = ''
  for expr in parsed_expressions:
    [ main_asm, _type ] = eval(expr, main_asm)

  fn_asm = ''
  for fn in FUNCTIONS:
    fn_asm += FUNCTIONS[fn]['asm']

  # combine main assembly code with header, built-in functions and footer
  out = assembly.HEAD.format(START_LABEL) \
    + assembly.DATA \
    + ''.join(LITERALS) \
    + assembly.TEXT \
    + assembly.EXIT \
    + fn_asm \
    + assembly.START.format(START_LABEL) \
    + main_asm + assembly.DEFAULT_EXIT

  # write to output file
  with open(OUTFILE, 'w') as f:
    f.write(out)


# run main function
if __name__ == '__main__':
  main()
