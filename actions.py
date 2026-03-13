import re
from typing import Any, Callable, Self

PATTERN_NAME = r"(?:[a-zA-Z_][a-zA-Z0-9_]*)"
PATTERN_OPERATOR = r"(?:\.|=|[+\-*\/%]=?)"
PATTERN_INTEGER_LITERAL = r"(?:[0-9]+)"
PATTERN_FLOAT_LITERAL = r"(?:[0-9]+\.[0-9]+)"
PATTERN_STRING_LITERAL_SINGLE = r"(?:f?\'[^\\]*?(?:\\.[^\\]*?)*\')"
PATTERN_STRING_LITERAL_DOUBLE = r"(?:f?\"[^\\]*?(?:\\.[^\\]*?)*\")"
PATTERN_STRING_LITERAL = f"(?:{PATTERN_STRING_LITERAL_DOUBLE}|{PATTERN_STRING_LITERAL_SINGLE})"
PATTERN_LITERAL = f"(?:(?P<value_float>{PATTERN_FLOAT_LITERAL})|(?P<value_integer>{PATTERN_INTEGER_LITERAL})|(?P<value_string>{PATTERN_STRING_LITERAL}))"
PATTERN_VALUE = f"(?:(?P<value_name>{PATTERN_NAME})|{PATTERN_LITERAL})"
PATTERN_FUNCTION_BEGIN = f"(?:(?P<function_name>{PATTERN_NAME})\\s*\\()"
#PATTERN_ASSIGN_BEGIN = f"(?:(?P<assign_name>{PATTERN_NAME})\\s*=)"
PATTERN_MAIN = f"\\s*(?P<function>{PATTERN_FUNCTION_BEGIN})|(?P<value>{PATTERN_VALUE})|(?P<semicolon>;)|(?P<comma>,)|(?P<parenthesis>\()(?P<enclend>[\]\)])|(?P<operator>{PATTERN_OPERATOR})"

RE_MAIN = re.compile(PATTERN_MAIN)

# max told me to call this language Tronix, i'll think abt it 

class ScriptValue[T]:
    def __init__(self, value_type:"ScriptDataType", inner:T):
        self.type = value_type
        self.inner = inner

class ScriptVariable:
    def __init__(self, value:ScriptValue):
        self.value = value
    
    def get(self)->ScriptValue:
        return self.value
    
    def assign(self, value:ScriptValue):
        self.value = value

class ScriptDataType:
    def __init__(self, name:str, inner:type, parent:Self):
        self.name = name
        self.inner = inner
        self.parent = parent
    
    def construct(self, ctx:"ScriptContext")->"ScriptFunctionResult":
        return NotImplemented
    
    def add(self, lhs:ScriptVariable, rhs:ScriptVariable)->ScriptValue|None:
        return NotImplemented
    
    def sub(self, lhs:ScriptVariable, rhs:ScriptVariable)->ScriptValue|None:
        return NotImplemented
    
    def mlt(self, lhs:ScriptVariable, rhs:ScriptVariable)->ScriptValue|None:
        return NotImplemented
    
    def div(self, lhs:ScriptVariable, rhs:ScriptVariable)->ScriptValue|None:
        return NotImplemented
    
    def mod(self, lhs:ScriptVariable, rhs:ScriptVariable)->ScriptValue|None:
        return NotImplemented
    
    def iadd(self, lhs:ScriptVariable, rhs:ScriptVariable)->ScriptValue|None:
        return NotImplemented
    
    def isub(self, lhs:ScriptVariable, rhs:ScriptVariable)->ScriptValue|None:
        return NotImplemented
    
    def imlt(self, lhs:ScriptVariable, rhs:ScriptVariable)->ScriptValue|None:
        return NotImplemented
    
    def idiv(self, lhs:ScriptVariable, rhs:ScriptVariable)->ScriptValue|None:
        return NotImplemented
    
    def imod(self, lhs:ScriptVariable, rhs:ScriptVariable)->ScriptValue|None:
        return NotImplemented
    
    def getattr(self, obj:ScriptValue, name:str)->ScriptValue:
        return NotImplemented
    
    def setattr(self, obj:ScriptValue, name:str, value:ScriptVariable)->ScriptValue:
        return NotImplemented

    def delattr(self, obj:ScriptValue, name:str)->ScriptValue:
        return NotImplemented

    def getitem(self, obj:ScriptValue, name:str)->ScriptValue:
        return NotImplemented
    
    def setitem(self, obj:ScriptValue, name:str, value:ScriptVariable)->ScriptValue:
        return NotImplemented

    def delitem(self, obj:ScriptValue, name:str)->ScriptValue:
        return NotImplemented

Namespace = dict[str, ScriptVariable]

class ScriptContext:
    def __init__(self, global_ns:Namespace, local_ns:Namespace, params:list[ScriptVariable]):
        self.global_ns = global_ns
        self.local_ns = local_ns
        self.params = params

class ScriptFunctionResult:
    ...


FunctionTable = dict[str, Callable[[ScriptContext], ScriptFunctionResult]]

class _ParsingNode:
    def __init__(self, parent:"_ParsingNode"|None=None, children:list["_ParsingNode"]|None=None):
        self.parent = parent
        self.children = [] if children is None else children

class _ParsingNode_Terminating(_ParsingNode):
    def __init__(self, parent:_ParsingNode|None=None):
        super().__init__(parent, None)

class _ParsingNodeExpression(_ParsingNode):
    pass

class _ParsingNodeName(_ParsingNode):
    def __init__(self, name:str, parent:_ParsingNode|None=None, children:list[_ParsingNode]|None=None):
        super().__init__(parent, children)
        self.name = name

class _ParsingNodeFunction(_ParsingNode):
    def __init__(self, function_name:str, parent:_ParsingNode|None=None, parameters:list[_ParsingNode]|None=None):
        super().__init__(parent, parameters)
        self.function_name = function_name

class _ParsingNodeValue(_ParsingNode_Terminating):
    def __init__(self, value:Any, parent:_ParsingNode|None=None):
        super().__init__(parent)
        self.value = value

class _ParsingNodeParentheses(_ParsingNode):
    pass

class _ParsingNodeComma(_ParsingNode_Terminating):
    pass

class _ParsingNodeOperator(_ParsingNode_Terminating):
    def __init__(self, operator:str, parent:_ParsingNode|None=None, children:list[_ParsingNode]|None=None):
        super().__init__(parent, children)
        self.operator = operator

class _enclose_stack:
    def __init__(self, c:str, end:str, pnode:_ParsingNode, prev:Self|None=None):
        self.c = c
        self.end = end
        self.pnode = pnode
        self.prev = prev

class _ns_stack:
    def __init__(self, ns:Namespace, prev:Self|None=None):
        self.ns = ns
        self.prev = prev

    def find_name(self, name:str):
        node = self
        while node is not None:
            if name in node.ns:
                return node.ns
            node = node.prev

class _operation_node:
    def __init__(self, operation:str, onode:_ParsingNodeOperator, lhand:Self|Any, rhand:Self|Any):
        self.operation = operation
        self.onode = onode
        self.lhand = lhand
        self.rhand = rhand

_escape_character_mapping = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "\n": "",
    "\\": "\\",
    "'": "'",
    "\"": "\"",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "v": "\v"
}

#direction to evaluate in (right/left) (True: x+y+z means $<-x+y;$<-$+z / False: x+y+z means $<-y+z;$<-x+$)
_operator_direction = {
    "()": True,
    "+": True,
    "-": True,
    "*": True,
    "/": True,
    "%": True,
    "=": False,
    "+=": False,
    "-=": False,
    "*=": False,
    "/=": False,
    "%=": False,
    ".": True,
    "-u": True,
    "+u": True
}

_operator_order = [
    {"()"},
    {"."},
    {"-u", "+u"},
    {"*", "/", "%"},
    {"+", "-"},
    {"=", "+=", "-=", "*=", "/=", "%="},
]


_operator_order_index = {k:i for i, so in enumerate(_operator_order) for k in so} #maps each operator to the index of its order set

_cached_operator_resolution_orders:dict[str, list[tuple[int, str]]] = {}

def _calc_operator_resolution_order(operator:str):
    lun = f"{operator}u"
    run = f"u{operator}"
    l = len(_operator_order)
    p = _operator_order_index.get(operator, l)
    pl = _operator_order_index.get(lun, l)
    pr = _operator_order_index.get(run, l)
    
    resolution_order = sorted([(p, operator), (pl, lun), (pr, run)], key=lambda pair: pair[0])
    while resolution_order and resolution_order[-1][0] >= l:
        resolution_order.pop()

    return resolution_order

def _get_operator_resolution_order(operator:str):
    ro = _cached_operator_resolution_orders.get(operator, None)
    if ro is None:
        ro = _calc_operator_resolution_order(operator)
        if ro:
            _cached_operator_resolution_orders[operator] = ro
    return ro

class Script:
    def __init__(self, raw:str, scope:Namespace=None):
        self.raw = raw
        self.scope = {} if scope is None else scope
        self.steps_callbacks:list[Callable[[], Callable[[], None]]] = []
        self.stack = _ns_stack(self.scope, _ns_stack(script_global_scope))
    
    def parse(self)->_ParsingNode:
        i = 0
        root = _ParsingNode()
        current = root
        enclstack:_enclose_stack|None = None

        #build the parse tree
        while True:
            r = RE_MAIN.match(self.raw[i:])
            if r["function"] is not None:
                node = _ParsingNodeFunction(r["function_name"], current)
                current.children.append(node)
                current = node
                enclstack = _enclose_stack("(",")", node, enclstack)
                i += r.end()
            elif r["value"] is not None:
                v_name = r["value_name"]
                v_string = r["value_string"]
                v_integer = r["value_integer"]
                v_float = r["value_float"]
                if not isinstance(current, _ParsingNodeExpression):
                    exprnode = _ParsingNodeExpression(current)
                    current.children.append(exprnode)
                    current = exprnode
                if v_name:
                    node = _ParsingNodeName(v_name, current)
                else:
                    if v_string:
                        vs = v_string[1:-1] #strip off the quotes
                        chars = []
                        ci = 0 #TODO anywhere a ci lookahead (or an i lookahead in the compile functions) happens, a range check should happen to prevent IndexErrors
                        while ci < len(vs):
                            c = vs[ci]
                            if c == "\\":
                                ci += 1
                                c = vs[ci]
                                ec = _escape_character_mapping.get(c, None)
                                if ec:
                                    chars.append(ec)
                                elif c == "u":
                                    chars.append(chr(int(vs[ci+1:ci+5], 16)))
                                    ci += 4 #(ci + 5 - 1) + 1
                                elif c == "U":
                                    chars.append(chr(int(vs[ci+1:ci+9], 16)))
                                    ci += 8
                                elif c == "o":
                                    chars.append(chr(int(vs[ci+1:ci+3], 8)))
                                    ci += 2
                                elif c == "x":
                                    chars.append(chr(int(vs[ci+1:ci+3], 16)))
                                    ci += 2
                                else:
                                    chars.append(f"\\{c}")
                            else:
                                chars.append(c)
                            ci += 1
                        value = "".join(chars)
                    elif v_integer:
                        value = int(v_integer)
                    elif v_float:
                        value = float(v_float)
                    else:
                        ... #TODO error unknown value
                    node = _ParsingNodeValue(value, current)
                current.children.append(node)
                i += r.end()
            elif (operator := r["operator"]) is not None:
                node = _ParsingNodeOperator(operator, current)
                current.children.append(node)
                i += r.end()
            elif r["parenthesis"] is not None:
                node = _ParsingNodeParentheses(current)
                current.children.append(node)
                enclstack = _enclose_stack("(",")", node, enclstack)
                i += r.end()
            elif (enclend := r["enclend"]) is not None:
                if enclstack is None:
                    ... #TODO error unexpected end
                elif enclstack.end != enclend:
                    ... #TODO error mismatched end
                enclstack = enclstack.prev
                current = enclstack.pnode.parent
                i += r.end()
            elif r["comma"] is not None:
                if enclstack is not None:
                    if isinstance(enclstack.pnode, _ParsingNodeFunction):
                        current = enclstack.pnode
                        current.children.append(_ParsingNodeComma(current))
                        continue
                ... #TODO error unexpected comma
            elif r["semicolon"] is not None:
                if enclstack is not None: #NOTE: if adding code blocks, allow code blocks to contain semicolons (enclstack.pnode isinstance check)
                    ... #TODO error unexpected semicolon
                if isinstance(current, _ParsingNodeExpression):
                    current = root #NOTE: this only works if code blocks dont exist, the semicolon must bring current to the nearest code block (or default to root)
                i += r.end()
            elif enclstack is not None:
                ... #TODO error incomplete encl
            else:
                return root

    def _generate_function_call_step(self, node:_ParsingNodeFunction, params:list[ScriptVariable], result_cb:Callable[[ScriptFunctionResult], None]|None=None):
        def _function_step_cb():
            if node.function_name in script_function_table:
                function = script_function_table[node.function_name]
                def _function_step():
                    local_ns = {}
                    ctx = ScriptContext(global_ns=script_global_scope, local_ns=local_ns, params=params)
                    self.stack = _ns_stack(local_ns, self.stack)
                    result = function(ctx)
                    self.stack = self.stack.prev
                    if result_cb is not None:
                        result_cb(result)
                return _function_step
            else:
                ... #TODO error missing function
        return _function_step_cb

    def _generate_function_steps(self, node:_ParsingNodeFunction, rtv:ScriptVariable|None):
        params:list[ScriptVariable] = []
        param:ScriptVariable|None = None
        for child in node.children:
            if isinstance(child, _ParsingNodeComma):
                if param is None:
                    ... #TODO error unexpected comma
                params.append(param)
            elif isinstance(child, _ParsingNodeFunction):
                r_rtv = ScriptVariable(None)
                self._generate_function_steps(child, r_rtv)

        if rtv is None:
            result_cb = None
        else:
            result_cb = lambda result: rtv.assign(result)
        self.steps_callbacks.append(self._generate_function_call_step(node, params, result_cb))

    def _generate_expression_steps(self, node:_ParsingNodeExpression|_ParsingNodeParentheses):
        workingVariable = ScriptVariable(None)

        #TODO generate operator appearance table

        operators:list[list[tuple[int, str, _ParsingNodeOperator|_ParsingNodeParentheses]]] = [[] for _ in range(len(_operator_order))]

        lh_index = None
        rh_index = None

        for i, child in enumerate(node.children):
            if isinstance(child, _ParsingNodeParentheses):
                operator = "()"
                lh_index = i
            elif isinstance(child, _ParsingNodeOperator):
                operator = child.operator
                
            else:
                lh_index = i
                continue

            operators[_operator_order_index[operator]].append((i, operator, child))
        
        for t in operators:
            if not t:
                continue
            elif len(t) == 1:
                i, operator, child = t[0]
            else:
                ii, ioperator, ichild = t[0]
                direction = _operator_direction[operator]
                for j in range(1, len(t)):
                    ...

        return workingVariable
        


    def compile(self, tree:_ParsingNode):
        for node in tree.children:
            if isinstance(node, _ParsingNodeExpression):
                self._generate_expression_steps(node)
            elif isinstance(node, _ParsingNodeParentheses):
                ...
            elif isinstance(node, _ParsingNodeFunction):
                self._generate_function_steps(node)

        


class Action:
    def __init__(self, name:str, script:Script):
        ...


script_function_table:FunctionTable = {}
script_global_scope:Namespace = {}
